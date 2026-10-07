"""Safety-horizon calibration (§8.10): ceil(median + 2 sd) of natural game lengths, truncation rate < 5 %."""

from __future__ import annotations

import math
import statistics
import time
from typing import Any

from propertyrl.evaluation.harness import GameSpec, run_games
from propertyrl.evaluation.seeds import subset
from propertyrl.infra.config import frozen_dir
from propertyrl.infra.storage import write_json

MAX_ROUNDS = 5000
TRUNCATION_LIMIT = 0.05


def _specs(n_games: int, n_players: int, smoke: bool) -> list[GameSpec]:
    pool = "SMOKE" if smoke else "SELECT"
    half = max(1, n_games // 2)
    seeds = subset(pool, start=0, end=half)
    if n_players == 2:
        lineups = [("strong_a_v1", "strong_b_v1"), ("strong_a_v1", "strong_a_v1")]
    else:
        lineups = [("strong_a_v1", "strong_b_v1", "roi_markov_v1", "strong_a_v1"),
                   ("strong_a_v1", "strong_a_v1", "strong_b_v1", "strong_b_v1")]  # fmt: skip
    specs = []
    for i, seed in enumerate(seeds):
        for k, seats in enumerate(lineups):
            if len(specs) >= n_games:
                break
            specs.append(GameSpec("OFFICIAL_US_CLASSIC_2008", seed, seats, k, MAX_ROUNDS, seed_index=i))
    return specs


def calibrate(n_games: int = 2000, n_players: int = 2, smoke: bool = False, workers: int | None = None) -> dict[str, Any]:
    """Play games without horizon (up to 5000 rounds) and derive the horizon."""
    start = time.perf_counter()
    records = run_games(_specs(n_games, n_players, smoke), workers=workers)
    natural = [r["rounds"] for r in records if not r["truncated"]]
    if len(natural) >= 2:
        med = statistics.median(natural)
        sd = statistics.stdev(natural)
    else:
        med, sd = float(natural[0] if natural else MAX_ROUNDS), 0.0
    horizon = math.ceil(med + 2 * sd)
    truncated = sum(1 for r in records if r["truncated"] or r["rounds"] > horizon)
    rate = truncated / len(records) if records else 1.0
    return {
        "n_players": n_players,
        "games": len(records),
        "natural_games": len(natural),
        "median_rounds": med,
        "sd_rounds": sd,
        "horizon": horizon,
        "truncation_rate": rate,
        "passed": rate < TRUNCATION_LIMIT,
        "seconds": time.perf_counter() - start,
        "smoke": smoke,
    }


def calibrate_horizon(
    n_games: int = 2000, smoke: bool = False, workers: int | None = None, include_4p: bool = True
) -> dict[str, Any]:
    """Calibrate 2P (and 4P) horizons and freeze them in artifacts/frozen/horizon.json."""
    two = calibrate(n_games, 2, smoke, workers)
    result: dict[str, Any] = {"horizon_2p": two["horizon"], "details_2p": two, "smoke": smoke}
    if include_4p:
        four = calibrate(max(4, n_games // 2), 4, smoke, workers)
        result["horizon_4p"] = four["horizon"]
        result["details_4p"] = four
    result["passed"] = bool(two["passed"] and (not include_4p or result["details_4p"]["passed"]))
    write_json(frozen_dir() / ("horizon_smoke.json" if smoke else "horizon.json"), result)
    return result
