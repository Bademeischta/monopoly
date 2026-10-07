"""Game metrics (§8.7) computed from evaluation records."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from propertyrl.evaluation.duplicate import agent_seat, score
from propertyrl.evaluation.harness import JAIL_BUCKETS


def _seat_counter(rec: dict[str, Any], name: str, seat: int) -> int:
    return int(rec["counters"][name][seat])


def agent_metrics(records: Sequence[dict[str, Any]], agent: str) -> dict[str, Any]:
    """All secondary metrics of ``agent`` over a set of games."""
    if not records:
        return {}
    seats = [agent_seat(r, agent) for r in records]
    n = len(records)

    def mean_counter(name: str) -> float:
        return float(np.mean([_seat_counter(r, name, s) for r, s in zip(records, seats, strict=True)]))

    placements = [r["placements"][s] for r, s in zip(records, seats, strict=True)]
    n_players = records[0]["n_players"]
    dist = {p: placements.count(p) / n for p in range(1, n_players + 1)}
    auction_spend = sum(_seat_counter(r, "auction_spend", s) for r, s in zip(records, seats, strict=True))
    auction_face = sum(_seat_counter(r, "auction_face_value", s) for r, s in zip(records, seats, strict=True))
    build_spend = sum(_seat_counter(r, "build_spend", s) for r, s in zip(records, seats, strict=True))
    rent = sum(_seat_counter(r, "rent_received", s) for r, s in zip(records, seats, strict=True))
    offers_received = sum(_seat_counter(r, "trade_offers_received", s) for r, s in zip(records, seats, strict=True))
    offers_accepted = sum(_seat_counter(r, "trade_offers_accepted", s) for r, s in zip(records, seats, strict=True))
    stay = [0, 0, 0]
    leave = [0, 0, 0]
    for r, s in zip(records, seats, strict=True):
        for b in range(len(JAIL_BUCKETS)):
            stay[b] += r["jail_decisions"]["stay"][b][s]
            leave[b] += r["jail_decisions"]["leave"][b][s]
    total_rounds = sum(r["rounds"] for r in records)
    runtime = sum(r["runtime_s"] for r in records)
    return {
        "games": n,
        "win_rate": float(np.mean([score(r, agent) for r in records])),
        "placement_distribution": dist,
        "mean_placement": float(np.mean(placements)),
        "bankruptcy_rate": float(np.mean([r["bankrupt"][s] for r, s in zip(records, seats, strict=True)])),
        "truncation_rate": float(np.mean([r["truncated"] for r in records])),
        "mean_rounds": total_rounds / n,
        "mean_decisions": float(np.mean([r["decisions"] for r in records])),
        "mean_agent_decisions": mean_counter("decisions"),
        "purchases_per_game": mean_counter("purchases"),
        "builds_per_game": mean_counter("houses_built") + mean_counter("hotels_built"),
        "mortgages_per_game": mean_counter("mortgages"),
        "unmortgages_per_game": mean_counter("unmortgages"),
        "auction_price_ratio": auction_spend / auction_face if auction_face else None,
        "scarcity_auctions_per_game": mean_counter("scarcity_auctions_triggered"),
        "scarcity_premium_per_game": mean_counter("scarcity_premium_paid"),
        "trades_per_game": mean_counter("trades_executed"),
        "trade_acceptance_rate": offers_accepted / offers_received if offers_received else None,
        "monopoly_rate": float(np.mean([r["complete_groups"][s] > 0 for r, s in zip(records, seats, strict=True)])),
        "build_efficiency": rent / build_spend if build_spend else None,
        "jail_stay_share_by_phase": {
            JAIL_BUCKETS[b]: (stay[b] / (stay[b] + leave[b]) if stay[b] + leave[b] else None) for b in range(3)
        },
        "jail_balance_per_game": mean_counter("jail_income") - mean_counter("jail_expense"),
        "final_equity": float(np.mean([r["final_equities"][s] for r, s in zip(records, seats, strict=True)])),
        "illegal_actions": 0,
        "throughput_games_per_s": n / runtime if runtime > 0 else None,
    }


def seat_win_rates(records: Sequence[dict[str, Any]]) -> list[float]:
    """Win rate per seat over all games (positional bias, R19)."""
    if not records:
        return []
    n_players = records[0]["n_players"]
    wins = [0.0] * n_players
    for r in records:
        if r["truncated"] or r["winner"] is None:
            for s in range(n_players):
                wins[s] += 1.0 / n_players
        else:
            wins[r["winner"]] += 1.0
    return [w / len(records) for w in wins]
