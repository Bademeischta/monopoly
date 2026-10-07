"""Evaluation harness (§8.3): games directly on the engine with policy objects per seat, in parallel.

Workers rebuild policies from picklable spec strings; RL agents are evaluated deterministically and
benchmark policies without epsilon.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from propertyrl.agents.base import respond
from propertyrl.agents.registry import cached_policy
from propertyrl.engine import Engine, EngineOptions, PropertyRLError
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.events import COUNTER_NAMES
from propertyrl.engine.rng import AgentRng
from propertyrl.infra.config import load_setup

log = logging.getLogger(__name__)
JAIL_BUCKETS = ("early", "middle", "late")


@dataclass(frozen=True)
class GameSpec:
    """One evaluation game: seed, seat assignment (policy specs) and ruleset."""

    ruleset_id: str
    seed: int
    seats: tuple[str, ...]
    rotation: int = 0
    safety_horizon_rounds: int | None = None
    max_rounds: int | None = None
    max_decisions: int = 2_000_000
    seed_index: int = -1

    def to_dict(self) -> dict[str, Any]:
        """Plain dict form."""
        return asdict(self)


def _setup(spec: GameSpec) -> Any:
    overrides: dict[str, Any] = {}
    if spec.safety_horizon_rounds is not None:
        overrides["safety_horizon_rounds"] = spec.safety_horizon_rounds
    if spec.max_rounds is not None:
        overrides["max_rounds"] = spec.max_rounds
    return load_setup(spec.ruleset_id, len(spec.seats), **overrides)


def play_game(spec: GameSpec) -> dict[str, Any]:
    """Play one game to its natural end or the safety horizon and return the record."""
    start = time.perf_counter()
    rules, board, decks = _setup(spec)
    n = len(spec.seats)
    policies = [cached_policy(s) for s in spec.seats]
    eng = Engine.new(rules, board, decks, n, spec.seed, EngineOptions(log_events=False))
    eng.meta = {"policies": list(spec.seats)}
    rngs = [AgentRng(spec.seed, s) for s in range(n)]
    horizon = rules.safety_horizon_rounds
    truncated = False
    jail = {"stay": [[0] * n for _ in JAIL_BUCKETS], "leave": [[0] * n for _ in JAIL_BUCKETS]}
    try:
        while not eng.is_over():
            if not rules.short_game and eng.state.round_index >= horizon:
                truncated = True
                break
            d = eng.pending()
            assert d is not None
            response = respond(policies[d.seat], eng, rngs[d.seat])
            if (
                d.kind == D.MAIN
                and d.phase == D.JAIL_PRE_ROLL
                and response in (A.ROLL, A.PAY_JAIL_FINE, A.USE_JAIL_CARD)
            ):
                bucket = jail_bucket(eng.state.round_index)
                jail["stay" if response == A.ROLL else "leave"][bucket][d.seat] += 1
            eng.apply(response)
            if eng.state.decision_index >= spec.max_decisions:
                truncated = True
                break
    except PropertyRLError as err:
        from propertyrl.infra.logging_setup import dump_error_log

        if err.game_log is None:
            err.game_log = eng.to_log()
        dump_error_log(err, prefix="eval")
        raise
    res = eng.result()
    st = eng.state
    counters = {name: res.counters[name] for name in COUNTER_NAMES}
    return {
        "seed": spec.seed,
        "seed_index": spec.seed_index,
        "rotation": spec.rotation,
        "ruleset_id": spec.ruleset_id,
        "n_players": n,
        "seats": list(spec.seats),
        "policy_versions": [policies[s].version for s in range(n)],
        "winner": res.winner if not truncated else None,
        "placements": list(res.placements) if not truncated else _equity_placements(res.final_equities, st.bankrupt),
        "rounds": res.rounds,
        "decisions": res.decisions,
        "decisions_per_seat": counters["decisions"],
        "truncated": truncated,
        "ended_by_rounds": res.ended_by_rounds,
        "final_equities": list(res.final_equities),
        "bankrupt": list(st.bankrupt),
        "counters": counters,
        "jail_decisions": jail,
        "complete_groups": [
            sum(1 for g in range(C.N_COLOR_GROUPS) if all(st.owner[p] == s for p in C.GROUP_PROPS[g])) for s in range(n)
        ],
        "runtime_s": time.perf_counter() - start,
    }


def jail_bucket(round_index: int) -> int:
    """Game phase bucket for jail decisions: 0 early (< 20 rounds), 1 middle (< 60), 2 late."""
    return 0 if round_index < 20 else (1 if round_index < 60 else 2)


def _equity_placements(equities: list[int], bankrupt: list[bool]) -> list[int]:
    """Placement by equity for truncated games (sensitivity analysis; bankrupt seats last)."""
    n = len(equities)
    order = sorted(range(n), key=lambda s: (bankrupt[s], -equities[s], s))
    out = [0] * n
    for rank, s in enumerate(order):
        out[s] = rank + 1
    return out


def _worker_init() -> None:
    try:
        import torch

        torch.set_num_threads(1)
    except ImportError:  # pragma: no cover - torch is a runtime dependency
        log.debug("torch not importable in evaluation worker; heuristic policies only")


def default_workers() -> int:
    """CPU cores minus one, at least 1 (env PROPERTYRL_EVAL_WORKERS overrides)."""
    env = os.environ.get("PROPERTYRL_EVAL_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, (os.cpu_count() or 2) - 1)


def run_games(specs: Iterable[GameSpec], workers: int | None = None, chunksize: int = 4) -> list[dict[str, Any]]:
    """Play all games (in parallel when workers > 1); results keep the input order."""
    items = list(specs)
    n_workers = default_workers() if workers is None else max(1, workers)
    if n_workers == 1 or len(items) <= 2:
        return [play_game(s) for s in items]
    method = "spawn" if sys.platform == "win32" else (
        "forkserver" if "forkserver" in multiprocessing.get_all_start_methods() else "spawn")  # fmt: skip
    ctx = multiprocessing.get_context(method)
    with ctx.Pool(processes=n_workers, initializer=_worker_init) as pool:
        return list(pool.imap(play_game, items, chunksize=chunksize))
