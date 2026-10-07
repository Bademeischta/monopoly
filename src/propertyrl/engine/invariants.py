"""Game state invariants (§4.8), checked after every apply when enabled."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.errors import InvariantError

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine


def _fail(eng: Engine, message: str) -> InvariantError:
    st = eng.state
    excerpt = {
        "cash": list(st.cash),
        "owner": list(st.owner),
        "mortgaged": list(st.mortgaged),
        "level": list(st.level),
        "bank_houses": st.bank_houses,
        "bank_hotels": st.bank_hotels,
        "bankrupt": list(st.bankrupt),
        "stack_top": list(st.stack[-1]) if st.stack else None,
    }
    err = InvariantError(message, game_seed=st.game_seed, decision_index=st.decision_index, details={"state": excerpt})
    err.game_log = eng.to_log()
    return err


def violations(eng: Engine) -> list[str]:
    """Return the list of violated invariants (empty if the state is consistent)."""
    st = eng.state
    rules = eng.ruleset
    out: list[str] = []
    n = st.n_players
    houses_on_board = sum(lv for lv in st.level if lv < C.HOTEL_LEVEL)
    hotels_on_board = sum(1 for lv in st.level if lv == C.HOTEL_LEVEL)
    if houses_on_board + st.bank_houses != rules.bank_houses:
        out.append(f"houses {houses_on_board} + bank {st.bank_houses} != {rules.bank_houses}")
    if hotels_on_board + st.bank_hotels != rules.bank_hotels:
        out.append(f"hotels {hotels_on_board} + bank {st.bank_hotels} != {rules.bank_hotels}")
    if st.bank_houses < 0 or st.bank_hotels < 0:
        out.append("negative bank stock")
    for p in range(C.N_PROPS):
        o = st.owner[p]
        if not (o == C.BANK or 0 <= o < n):
            out.append(f"p{p} has invalid owner {o}")
        elif o >= 0 and st.bankrupt[o]:
            out.append(f"p{p} owned by bankrupt seat {o}")
        if st.mortgaged[p] and o == C.BANK:
            out.append(f"p{p} mortgaged but owned by the bank")
        if st.interest_prepaid[p] >= 0 and not st.mortgaged[p]:
            out.append(f"p{p} interest_prepaid without mortgage")
    for g in range(C.N_COLOR_GROUPS):
        builds = C.GROUP_BUILDS[g]
        levels = [st.level[b] for b in builds]
        if max(levels) - min(levels) > 1:
            out.append(f"uneven building in group {C.GROUP_NAMES[g]}: {levels}")
        props = C.GROUP_PROPS[g]
        if max(levels) > 0:
            owners = {st.owner[p] for p in props}
            if len(owners) != 1 or C.BANK in owners:
                out.append(f"buildings on incomplete group {C.GROUP_NAMES[g]}")
            if any(st.mortgaged[p] for p in props):
                out.append(f"mortgage in built group {C.GROUP_NAMES[g]}")
    for s in range(n):
        if st.cash[s] < 0:
            out.append(f"seat {s} has negative cash")
        if st.cash[s] != rules.starting_cash + st.ledger_in[s] - st.ledger_out[s]:
            out.append(f"seat {s} cash inconsistent with ledger")
        if not 0 <= st.position[s] < C.N_SQUARES:
            out.append(f"seat {s} position out of range")
        if st.bankrupt[s]:
            if st.cash[s] != 0 or st.jail_cards[s] != 0:
                out.append(f"bankrupt seat {s} still holds cash or cards")
    if eng.log and (st.decision_index % 256 == 0 or st.game_over):
        inflow, outflow = eng.ledger.totals(n)
        if inflow != st.ledger_in or outflow != st.ledger_out:
            out.append("transaction ledger and ledger totals disagree")
    for deck_idx, deck in ((C.DECK_A, st.deck_a), (C.DECK_B, st.deck_b)):
        held = sum(1 for s in range(n) if st.jail_cards[s] & C.DECK_BITS[deck_idx])
        if len(deck) + held != C.DECK_SIZE or len(set(deck)) != len(deck):
            out.append(f"deck {deck_idx} has {len(deck)} cards + {held} held")
    if st.doubles_count > 2:
        out.append("doubles_count > 2")
    n_active = st.n_active()
    if n_active <= 1 and not st.game_over:
        out.append("game not over with at most one active player")
    if st.game_over and n_active > 1 and not st.ended_by_rounds:
        out.append("game over with more than one active player")
    if not st.game_over:
        top = st.stack[-1] if st.stack else None
        if top is None or top[0] not in F.DECISION_OPS:
            out.append("no pending decision")
        else:
            d = eng.pending()
            if d is not None and st.bankrupt[d.seat]:
                out.append(f"open decision for bankrupt seat {d.seat}")
    return out


def check_invariants(eng: Engine) -> None:
    """Raise InvariantError if any invariant is violated."""
    problems = violations(eng)
    if problems:
        raise _fail(eng, "; ".join(problems))
