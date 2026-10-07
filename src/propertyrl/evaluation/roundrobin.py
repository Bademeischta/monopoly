"""Baseline round-robin (§8.9, gate G3): Copeland ranking per SELECT block, transitivity, frozen top."""

from __future__ import annotations

import itertools
import logging
import time
from typing import Any

from propertyrl.agents.registry import BENCHMARK_POLICIES
from propertyrl.evaluation.duplicate import duplicate_specs, summarize
from propertyrl.evaluation.evaluate import records_frame
from propertyrl.evaluation.harness import run_games
from propertyrl.evaluation.ratings import elo, openskill
from propertyrl.evaluation.seeds import subset
from propertyrl.infra.config import frozen_dir
from propertyrl.infra.storage import sub_artifacts, write_json

log = logging.getLogger(__name__)


def copeland(pairs: dict[tuple[str, str], dict[str, Any]], policies: list[str]) -> list[tuple[str, int, float]]:
    """(policy, Copeland score, mean win rate) sorted best first."""
    wins = dict.fromkeys(policies, 0)
    rates: dict[str, list[float]] = {p: [] for p in policies}
    for (a, b), res in pairs.items():
        wr = res["win_rate"]
        rates[a].append(wr)
        rates[b].append(1.0 - wr)
        if wr > 0.5:
            wins[a] += 1
        elif wr < 0.5:
            wins[b] += 1
    table = [(p, wins[p], sum(rates[p]) / max(1, len(rates[p]))) for p in policies]
    return sorted(table, key=lambda x: (-x[1], -x[2], x[0]))


def significant_cycles(pairs: dict[tuple[str, str], dict[str, Any]], policies: list[str]) -> list[tuple[str, ...]]:
    """Triangles a > b > c > a among edges whose Wilson interval excludes 50 %."""
    beats: set[tuple[str, str]] = set()
    for (a, b), res in pairs.items():
        if res["wilson_lower"] > 0.5:
            beats.add((a, b))
        elif res["wilson_upper"] < 0.5:
            beats.add((b, a))
    cycles = []
    for x, y, z in itertools.permutations(policies, 3):
        if (x, y) in beats and (y, z) in beats and (z, x) in beats and x == min(x, y, z):
            cycles.append((x, y, z))
    return cycles


def run_round_robin(
    seeds_per_block: int | None = None,
    smoke: bool = False,
    workers: int | None = None,
    policies: list[str] | None = None,
) -> dict[str, Any]:
    """All pairs of the benchmark policies in 2P duplicate on SELECT block 1 and block 2 separately."""
    pols = list(policies or BENCHMARK_POLICIES)
    if smoke:
        k = seeds_per_block or 10
        blocks = {"block1": subset("SMOKE", start=0, end=k), "block2": subset("SMOKE", start=k, end=2 * k)}
    else:
        k = seeds_per_block or 1000
        blocks = {"block1": subset("SELECT", start=0, end=k), "block2": subset("SELECT", start=1000, end=1000 + k)}
    result: dict[str, Any] = {"policies": pols, "smoke": smoke, "seeds_per_block": k, "blocks": {}}
    all_records = []
    start = time.perf_counter()
    for name, seeds in blocks.items():
        pairs: dict[tuple[str, str], dict[str, Any]] = {}
        specs = []
        index = []
        for a, b in itertools.combinations(pols, 2):
            s = duplicate_specs(a, [b], seeds, "OFFICIAL_US_CLASSIC_2008", 2)
            index.append((a, b, len(specs), len(specs) + len(s)))
            specs += s
        records = run_games(specs, workers=workers)
        all_records += records
        for a, b, lo, hi in index:
            summary = summarize(records[lo:hi], a, bootstrap_reps=500)
            pairs[(a, b)] = {
                "win_rate": summary["win_rate"],
                "wilson_lower": summary["wilson_lower"],
                "wilson_upper": summary["wilson_upper"],
                "games": summary["games"],
                "truncation_rate": summary["truncation_rate"],
            }
        ranking = copeland(pairs, pols)
        result["blocks"][name] = {
            "pairs": {f"{a}|{b}": v for (a, b), v in pairs.items()},
            "ranking": [{"policy": p, "copeland": c, "mean_win_rate": m} for p, c, m in ranking],
            "top": ranking[0][0],
            "cycles": significant_cycles(pairs, pols),
        }
    tops = {b["top"] for b in result["blocks"].values()}
    result["transitive"] = all(not b["cycles"] for b in result["blocks"].values())
    result["stable_top"] = len(tops) == 1
    result["passed"] = bool(result["transitive"] and result["stable_top"])
    result["strongest"] = result["blocks"]["block1"]["top"]
    result["elo"] = elo(all_records)
    result["openskill"] = openskill(all_records)
    result["seconds"] = time.perf_counter() - start
    out = sub_artifacts("roundrobin")
    tag = "smoke" if smoke else time.strftime("%Y%m%d-%H%M%S")
    records_frame(all_records).to_parquet(out / f"games_{tag}.parquet", index=False)
    write_json(out / f"roundrobin_{tag}.json", result)
    frozen = {"policy": result["strongest"], "passed": result["passed"], "transitive": result["transitive"],
              "stable_top": result["stable_top"], "smoke": smoke, "seeds_per_block": k}  # fmt: skip
    write_json(frozen_dir() / ("strongest_baseline_smoke.json" if smoke else "strongest_baseline.json"), frozen)
    if not smoke:  # the real report reads latest.json; smoke results stay in roundrobin_smoke.json
        write_json(out / "latest.json", result)
    return result
