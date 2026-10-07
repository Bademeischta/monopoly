"""Duplicate evaluation (§8.3, §8.4): seat rotation over identical seeds and scoring of the agent."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from propertyrl.evaluation.harness import GameSpec
from propertyrl.evaluation.stats import cluster_bootstrap, wilson


def duplicate_specs(
    agent: str,
    opponents: Sequence[str],
    seeds: Sequence[int],
    ruleset_id: str,
    n_players: int = 2,
    safety_horizon_rounds: int | None = None,
    max_rounds: int | None = None,
    index_offset: int = 0,
) -> list[GameSpec]:
    """2P: every seed in both seat assignments. 4P: every seed in all 4 cyclic rotations."""
    if n_players == 2:
        opp = opponents[0]
        lineups = [((agent, opp), 0), ((opp, agent), 1)]
    else:
        opps = list(opponents) if len(opponents) == n_players - 1 else [opponents[0]] * (n_players - 1)
        base = [agent, *opps]
        lineups = [(tuple(base[(k - r) % n_players] for k in range(n_players)), r) for r in range(n_players)]
    out = []
    for i, seed in enumerate(seeds):
        for seats, rotation in lineups:
            out.append(
                GameSpec(
                    ruleset_id,
                    int(seed),
                    tuple(seats),
                    rotation,
                    safety_horizon_rounds,
                    max_rounds,
                    seed_index=index_offset + i,
                )
            )
    return out


def agent_seat(record: dict[str, Any], agent: str) -> int:
    """Seat of the agent in a record (rotation decides when the spec appears more than once)."""
    seats = record["seats"]
    hits = [s for s, spec in enumerate(seats) if spec == agent]
    if not hits:
        raise ValueError(f"agent {agent!r} not seated in game {record['seed']}")
    if len(hits) == 1:
        return hits[0]
    return record["rotation"] % len(seats)


def score(record: dict[str, Any], agent: str, sensitivity: bool = False) -> float:
    """Win 1, loss 0, truncated game 0.5 (A-20); with ``sensitivity`` truncated games decided by equity."""
    seat = agent_seat(record, agent)
    if record["truncated"]:
        if sensitivity:
            return 1.0 if record["placements"][seat] == 1 else 0.0
        return 0.5
    winner = record["winner"]
    if winner is None:  # short-game draw
        return 0.5
    if record["n_players"] == 2:
        return 1.0 if winner == seat else 0.0
    return 1.0 if record["placements"][seat] == 1 else 0.0


def summarize(records: Sequence[dict[str, Any]], agent: str, bootstrap_reps: int = 5000) -> dict[str, Any]:
    """Win rate with Wilson and seed-cluster bootstrap CI, sensitivity, seat rates, placements."""
    if not records:
        return {"games": 0}
    scores = [score(r, agent) for r in records]
    sens = [score(r, agent, sensitivity=True) for r in records]
    clusters = [r["seed_index"] if r["seed_index"] >= 0 else r["seed"] for r in records]
    n = len(scores)
    total = sum(scores)
    lo, hi = wilson(total, n)
    boot = cluster_bootstrap(scores, clusters, reps=bootstrap_reps, seed_key=(n, len(set(clusters))))
    n_seats = records[0]["n_players"]
    seat_rates: dict[int, float] = {}
    for s in range(n_seats):
        sub = [sc for sc, r in zip(scores, records, strict=True) if agent_seat(r, agent) == s]
        if sub:
            seat_rates[s] = sum(sub) / len(sub)
    placements = [r["placements"][agent_seat(r, agent)] for r in records]
    return {
        "agent": agent,
        "games": n,
        "seeds": len(set(clusters)),
        "win_rate": total / n,
        "wilson_lower": lo,
        "wilson_upper": hi,
        "bootstrap": boot.to_dict(),
        "sensitivity_win_rate": sum(sens) / n,
        "truncation_rate": sum(1 for r in records if r["truncated"]) / n,
        "seat_win_rates": seat_rates,
        "mean_placement": sum(placements) / n,
        "first_place_rate": sum(1 for p in placements if p == 1) / n,
        "mean_rounds": sum(r["rounds"] for r in records) / n,
    }


def per_seed_scores(records: Sequence[dict[str, Any]], agent: str) -> dict[int, float]:
    """Mean score per seed index (for paired comparisons)."""
    acc: dict[int, list[float]] = {}
    for r in records:
        key = r["seed_index"] if r["seed_index"] >= 0 else r["seed"]
        acc.setdefault(key, []).append(score(r, agent))
    return {k: sum(v) / len(v) for k, v in acc.items()}
