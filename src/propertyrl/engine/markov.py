"""Markov chains of board movement (§4.11), pure Python.

(a) Exact chain of the reduced configuration (TEST_MOVEMENT_ONLY): 120 states
    (square x doubles counter 0-2); every transition is one rest event.
(b) Approximate chain for heuristics: (a) plus movement cards drawn with
    replacement and a jail policy ("leave" immediately or "stay"), giving the
    expected number of rest events per opponent turn on every square.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from propertyrl.engine import cards as K
from propertyrl.engine import constants as C
from propertyrl.engine.rng import u64

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.cards import Decks
    from propertyrl.engine.ruleset import Ruleset

JAIL_LEAVE = "leave"
JAIL_STAY = "stay"
_OUTCOMES = [(d1, d2) for d1 in range(1, 7) for d2 in range(1, 7)]
_JAIL = -1


def solve_stationary(matrix: list[list[float]]) -> list[float]:
    """Stationary distribution of a row-stochastic matrix by Gauss elimination with pivoting."""
    n = len(matrix)
    # Build (P^T - I) pi = 0 and replace the last equation by sum(pi) = 1.
    a = [[matrix[j][i] - (1.0 if i == j else 0.0) for j in range(n)] + [0.0] for i in range(n)]
    a[n - 1] = [1.0] * n + [1.0]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-300:
            continue
        a[col], a[piv] = a[piv], a[col]
        pivot_row = a[col]
        inv = 1.0 / pivot_row[col]
        for k in range(col, n + 1):
            pivot_row[k] *= inv
        for r in range(n):
            if r != col:
                row = a[r]
                factor = row[col]
                if factor != 0.0:
                    for k in range(col, n + 1):
                        row[k] -= factor * pivot_row[k]
    return [a[i][n] for i in range(n)]


def power_iteration(matrix: list[list[float]], tol: float = 1e-12, max_iter: int = 1_000_000) -> list[float]:
    """Stationary distribution by (lazy) power iteration until the max change is below ``tol``."""
    n = len(matrix)
    pi = [1.0 / n] * n
    for _ in range(max_iter):
        new = [0.0] * n
        for i in range(n):
            pi_i = pi[i]
            if pi_i == 0.0:
                continue
            row = matrix[i]
            for j in range(n):
                if row[j]:
                    new[j] += pi_i * row[j]
        new = [0.5 * (x + y) for x, y in zip(pi, new, strict=True)]
        delta = max(abs(x - y) for x, y in zip(pi, new, strict=True))
        pi = new
        if delta < tol:
            break
    total = sum(pi)
    return [x / total for x in pi]


def exact_chain() -> list[list[float]]:
    """Transition matrix of the 120-state exact chain (a)."""
    n = C.N_SQUARES * 3
    m = [[0.0] * n for _ in range(n)]
    p = 1.0 / 36.0
    for sq in range(C.N_SQUARES):
        for c in range(3):
            row = m[sq * 3 + c]
            for d1, d2 in _OUTCOMES:
                if d1 == d2 and c == 2:
                    dest = C.JAIL_SQUARE * 3  # third double -> jail, counter 0
                else:
                    target = (sq + d1 + d2) % C.N_SQUARES
                    if target == C.ARREST_SQUARE:
                        dest = C.JAIL_SQUARE * 3
                    elif d1 == d2:
                        dest = target * 3 + c + 1
                    else:
                        dest = target * 3
                row[dest] += p
    return m


def exact_square_frequencies(method: str = "gauss") -> list[float]:
    """Fraction of rest events per square in the exact chain (square 30 has frequency 0)."""
    m = exact_chain()
    pi = solve_stationary(m) if method == "gauss" else power_iteration(m)
    return [sum(pi[sq * 3 + c] for c in range(3)) for sq in range(C.N_SQUARES)]


def _card_resolution(decks: Decks, square: int, depth: int = 0) -> dict[int, float]:
    """Distribution of the final square (or _JAIL) after drawing at a card square (with replacement)."""
    if depth > 4:
        return {square: 1.0}
    deck_idx = C.DECK_A if square in C.CARD_A_SQUARES else C.DECK_B
    codes = decks.codes[deck_idx]
    params = decks.params[deck_idx]
    out: dict[int, float] = {}
    w = 1.0 / len(codes)

    def add(key: int, prob: float) -> None:
        out[key] = out.get(key, 0.0) + prob

    for code, prm in zip(codes, params, strict=True):
        if code == K.E_ADVANCE_TO:
            add(prm[0], w)
        elif code == K.E_NEAREST_RAIL:
            add(_next(square, C.RAIL_SQUARES), w)
        elif code == K.E_NEAREST_UTIL:
            add(_next(square, C.UTIL_SQUARES), w)
        elif code == K.E_MOVE_BACK:
            back = (square - prm[0]) % C.N_SQUARES
            for key, prob in _resolve_square(decks, back, depth + 1).items():
                add(key, w * prob)
        elif code == K.E_SEND_TO_JAIL:
            add(_JAIL, w)
        else:
            add(square, w)
    return out


def _next(position: int, squares: tuple[int, ...]) -> int:
    for k in range(1, C.N_SQUARES + 1):
        s = (position + k) % C.N_SQUARES
        if s in squares:
            return s
    return position


def _resolve_square(decks: Decks, square: int, depth: int = 0) -> dict[int, float]:
    """Final outcome distribution after landing on ``square`` (arrest and card effects)."""
    if square == C.ARREST_SQUARE:
        return {_JAIL: 1.0}
    if square in C.CARD_A_SQUARES or square in C.CARD_B_SQUARES:
        return _card_resolution(decks, square, depth)
    return {square: 1.0}


def approximate_chain(decks: Decks, jail_policy: str) -> tuple[list[list[float]], list[int], list[bool]]:
    """Transition matrix of chain (b); returns (matrix, square of each state, turn-start flag)."""
    n_reg = C.N_SQUARES * 3
    stay = jail_policy == JAIL_STAY
    n = n_reg + (3 if stay else 0)
    m = [[0.0] * n for _ in range(n)]
    square_of = [i // 3 for i in range(n_reg)] + [C.JAIL_SQUARE] * (n - n_reg)
    turn_start = [i % 3 == 0 for i in range(n_reg)] + [True] * (n - n_reg)
    jail_state = n_reg if stay else C.JAIL_SQUARE * 3
    resolved = [_resolve_square(decks, s) for s in range(C.N_SQUARES)]
    p = 1.0 / 36.0

    def dest_of(outcome: int, counter: int) -> int:
        if outcome == _JAIL:
            return jail_state
        return outcome * 3 + counter

    for sq in range(C.N_SQUARES):
        for c in range(3):
            row = m[sq * 3 + c]
            for d1, d2 in _OUTCOMES:
                if d1 == d2 and c == 2:
                    row[jail_state] += p
                    continue
                target = (sq + d1 + d2) % C.N_SQUARES
                nc = c + 1 if d1 == d2 else 0
                for outcome, prob in resolved[target].items():
                    # After being jailed the turn ends; otherwise doubles continue the turn.
                    row[dest_of(outcome, nc if outcome != _JAIL else 0)] += p * prob
    if stay:
        for k in range(3):
            row = m[n_reg + k]
            for d1, d2 in _OUTCOMES:
                target = (C.JAIL_SQUARE + d1 + d2) % C.N_SQUARES
                if d1 == d2 or k == 2:
                    # Doubles free the player (no extra roll); third failure pays and moves.
                    for outcome, prob in resolved[target].items():
                        row[dest_of(outcome, 0)] += p * prob
                else:
                    row[n_reg + k + 1] += p
    return m, square_of, turn_start


def landing_frequencies(decks: Decks, jail_policy: str = JAIL_LEAVE) -> list[float]:
    """Expected rest events per opponent turn on each square under chain (b)."""
    m, square_of, turn_start = approximate_chain(decks, jail_policy)
    pi = solve_stationary(m)
    turns = sum(x for x, t in zip(pi, turn_start, strict=True) if t)
    freq = [0.0] * C.N_SQUARES
    for x, sq in zip(pi, square_of, strict=True):
        freq[sq] += x / turns
    return freq


def simulate_rest_frequencies(
    ruleset: Ruleset, board: Board, decks: Decks, moves: int, seed: int = 1
) -> tuple[list[float], int]:
    """Play TEST_MOVEMENT_ONLY until ``moves`` rest events (both players) and return the frequencies."""
    from propertyrl.engine.game import Engine, EngineOptions

    if not ruleset.movement_only:
        raise ValueError("the Markov comparison requires the TEST_MOVEMENT_ONLY ruleset (A-11)")
    # The per-game watchdog (P-16) caps one game at WATCHDOG_GAME_DECISIONS decisions, so long samples are
    # split into consecutive games with derived seeds; each game contributes about a million rest events,
    # which makes the start-square transient negligible.
    limit = C.WATCHDOG_GAME_DECISIONS - 1000
    totals = [0] * C.N_SQUARES
    segment = 0
    total = 0
    while total < moves:
        game_seed = seed if segment == 0 else u64(seed, segment) & ((1 << 63) - 1)
        eng = Engine.new(ruleset, board, decks, 2, game_seed, EngineOptions(log_events=False))
        counts = eng.state.rest_counts
        base = total
        while total < moves and eng.state.decision_index < limit:
            d = eng.pending()
            assert d is not None and d.legal is not None
            eng.apply(d.legal.index(True))
            total = base + sum(counts)
        totals = [a + b for a, b in zip(totals, counts, strict=True)]
        segment += 1
    return [c / total for c in totals], total


def markov_check(
    ruleset: Ruleset, board: Board, decks: Decks, moves: int, tolerance_pp: float, seed: int = 1
) -> dict[str, Any]:
    """Compare empirical rest frequencies with the exact chain (a); tolerance in percentage points."""
    exact = exact_square_frequencies()
    empirical, total = simulate_rest_frequencies(ruleset, board, decks, moves, seed)
    diffs = [abs(e - x) * 100.0 for e, x in zip(empirical, exact, strict=True)]
    worst = max(range(C.N_SQUARES), key=lambda i: diffs[i])
    return {
        "moves": total,
        "tolerance_pp": tolerance_pp,
        "max_abs_diff_pp": diffs[worst],
        "worst_square": worst,
        "passed": diffs[worst] <= tolerance_pp,
        "exact": exact,
        "empirical": empirical,
    }
