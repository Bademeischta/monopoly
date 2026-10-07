"""Kingmaking analysis for 4P (§8.8): winner sensitivity via rollouts from late decision points."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from propertyrl.agents.base import respond
from propertyrl.agents.registry import cached_policy
from propertyrl.engine import Engine, EngineOptions
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.equity import equity_shares
from propertyrl.engine.rng import AgentRng, SeededStream, u64
from propertyrl.evaluation.harness import GameSpec, _setup
from propertyrl.evaluation.stats import cluster_bootstrap
from propertyrl.infra.config import load_seeds_config


@dataclass(frozen=True)
class KingmakingParams:
    """Configurable parameters (§8.8)."""

    games: int = 100
    points_per_game: int = 2
    alternatives: int = 3
    rollouts: int = 12
    threshold: float = 0.25
    max_rollout_decisions: int = 200_000


def _play_out(eng: Engine, specs: Sequence[str], seed: int, limit: int) -> int:
    """Play a cloned game to its end with fixed policies; returns the winner seat (-1 if none)."""
    policies = [cached_policy(s) for s in specs]
    rngs = [AgentRng(seed, s) for s in range(len(specs))]
    horizon = eng.ruleset.safety_horizon_rounds
    steps = 0
    while not eng.is_over() and steps < limit and eng.state.round_index < horizon:
        d = eng.pending()
        assert d is not None
        eng.apply(respond(policies[d.seat], eng, rngs[d.seat]))
        steps += 1
    res = eng.result()
    if eng.is_over() and res.winner is not None:
        return res.winner
    # Unfinished rollout: leader by canonical equity.
    shares = equity_shares(eng.state, eng.board)
    return int(np.argmax(shares))


def _tv(a: Counter[int], b: Counter[int], n: int) -> float:
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a[k] / n - b[k] / n) for k in keys)


def analyse_game(spec: GameSpec, params: KingmakingParams, game_index: int) -> dict[str, Any]:
    """Play one game, pick late points of hopeless players and measure winner sensitivity."""
    rules, board, decks = _setup(spec)
    n = len(spec.seats)
    eng = Engine.new(rules, board, decks, n, spec.seed, EngineOptions(log_events=False))
    policies = [cached_policy(s) for s in spec.seats]
    rngs = [AgentRng(spec.seed, s) for s in range(n)]
    candidates: list[tuple[int, Engine, int]] = []
    while not eng.is_over() and eng.state.round_index < rules.safety_horizon_rounds:
        d = eng.pending()
        assert d is not None
        response = respond(policies[d.seat], eng, rngs[d.seat])
        if d.kind == D.MAIN and d.legal is not None and sum(d.legal) >= 2:
            shares = equity_shares(eng.state, board)
            active = [s for s in range(n) if not eng.state.bankrupt[s]]
            last = min(active, key=lambda s: (shares[s], s))
            if d.seat == last and shares[d.seat] < 0.5 / len(active):
                candidates.append((eng.state.decision_index, eng.clone(log_events=False), int(response)))
        eng.apply(response)
    total = eng.state.decision_index
    late = [c for c in candidates if c[0] >= 2 * total / 3]
    master = load_seeds_config().master_seed
    picker = SeededStream(master, C.STREAM_ROLLOUT, game_index)
    chosen_points = []
    while late and len(chosen_points) < params.points_per_game:
        chosen_points.append(late.pop(picker.randint(0, len(late) - 1)))
    points = []
    for p_idx, (dec_index, snapshot, chosen) in enumerate(chosen_points):
        d = snapshot.pending()
        assert d is not None and d.legal is not None
        alts = [a for a in d.legal_actions() if a != chosen]
        sel = []
        while alts and len(sel) < params.alternatives:
            sel.append(alts.pop(picker.randint(0, len(alts) - 1)))
        dists: dict[int, Counter[int]] = {}
        for a_idx, action in enumerate([chosen, *sel]):
            winners: Counter[int] = Counter()
            for r in range(params.rollouts):
                reseed = u64(master, C.STREAM_ROLLOUT, game_index, p_idx, a_idx, r)
                twin = snapshot.clone(reseed=reseed, log_events=False)
                twin.apply(action)
                winners[_play_out(twin, spec.seats, reseed, params.max_rollout_decisions)] += 1
            dists[action] = winners
        ws = max((_tv(dists[a], dists[chosen], params.rollouts) for a in sel), default=0.0)
        points.append({"decision_index": dec_index, "seat": d.seat, "chosen": chosen, "alternatives": sel, "ws": ws})
    return {
        "seed": spec.seed,
        "seats": list(spec.seats),
        "points": points,
        "max_ws": max((p["ws"] for p in points), default=0.0),
        "kingmaking": any(p["ws"] >= params.threshold for p in points),
    }


def run_kingmaking(specs: Sequence[GameSpec], params: KingmakingParams | None = None) -> dict[str, Any]:
    """Winner-sensitivity distribution, mean with bootstrap CI and kingmaking rate."""
    prm = params or KingmakingParams()
    start = time.perf_counter()
    games = [analyse_game(s, prm, i) for i, s in enumerate(list(specs)[: prm.games])]
    ws = [p["ws"] for g in games for p in g["points"]]
    clusters = [i for i, g in enumerate(games) for _ in g["points"]]
    boot = cluster_bootstrap(ws, clusters, reps=2000, seed_key=(len(ws),), null=0.0).to_dict() if ws else None
    return {
        "params": prm.__dict__,
        "games": len(games),
        "points": len(ws),
        "ws_values": ws,
        "ws_mean": float(np.mean(ws)) if ws else 0.0,
        "ws_bootstrap": boot,
        "kingmaking_rate": sum(1 for g in games if g["kingmaking"]) / len(games) if games else 0.0,
        "details": games,
        "seconds": time.perf_counter() - start,
    }
