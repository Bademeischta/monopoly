"""Evaluation driver (`propertyrl evaluate`): SELECT / TEST / SMOKE splits, Parquet records, ledger."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd

from propertyrl.engine.errors import ConfigError
from propertyrl.evaluation import ledger
from propertyrl.evaluation.duplicate import duplicate_specs, per_seed_scores, summarize
from propertyrl.evaluation.harness import run_games
from propertyrl.evaluation.metrics import agent_metrics, seat_win_rates
from propertyrl.evaluation.seeds import subset
from propertyrl.infra.config import read_frozen
from propertyrl.infra.storage import record_eval_summary, sub_artifacts, write_json

log = logging.getLogger(__name__)
SPLITS = ("select", "test", "smoke")
DEFAULT_SEEDS = {"select": 200, "smoke": 20}
DEFAULT_TEST = {2: 1200, 4: 250}


def strongest_baseline() -> str:
    """Frozen strongest baseline from G3 (expected strong_a_v1); strong_a_v1 before G3."""
    frozen = read_frozen("strongest_baseline")
    return str(frozen["policy"]) if frozen and frozen.get("policy") else "strong_a_v1"


def resolve_agent(agent: str) -> str:
    """Accept policy specs, checkpoint paths (*.zip) and ``experiment:<name>[:seed]`` references."""
    if agent.endswith(".zip") and ":" not in agent.split("/")[-1]:
        return f"sb3:{Path(agent).resolve()}"
    if agent.startswith("experiment:"):
        from propertyrl.training.train import find_checkpoint

        parts = agent.split(":")
        seed = int(parts[2]) if len(parts) > 2 else None
        smoke = len(parts) > 3 and parts[3] == "smoke"
        path = find_checkpoint(parts[1], seed, smoke)
        if path is None:
            raise ConfigError(f"no checkpoint for {agent}")
        return f"sb3:{path}"
    return agent


def resolve_opponents(opponents: list[str]) -> list[str]:
    """Replace 'strongest_baseline' by the frozen G3 result."""
    return [strongest_baseline() if o == "strongest_baseline" else o for o in opponents]


def test_size(n_players: int) -> int:
    """TEST seeds per evaluation (artifacts/frozen/test_size.json or the standard 1200 / 250)."""
    frozen = read_frozen("test_size")
    key = f"{n_players}p"
    if frozen and key in frozen:
        return int(frozen[key])
    return DEFAULT_TEST.get(n_players, 250)


def seeds_for(split: str, n: int | None, n_players: int) -> list[int]:
    """Seeds of a split (TEST only through this function after the ledger check)."""
    if split == "select":
        return subset("SELECT", start=0, end=n or DEFAULT_SEEDS["select"])
    if split == "smoke":
        return subset("SMOKE", start=0, end=n or DEFAULT_SEEDS["smoke"])
    if split == "test":
        return subset("TEST", start=0, end=n or test_size(n_players))
    raise ConfigError(f"unknown split {split!r}")


def records_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Flatten records for Parquet (nested fields as JSON strings)."""
    rows = []
    for r in records:
        row = {k: v for k, v in r.items() if not isinstance(v, (list, dict))}
        for k, v in r.items():
            if isinstance(v, (list, dict)):
                row[k] = json.dumps(v)
        rows.append(row)
    return pd.DataFrame(rows)


def evaluate_agent(
    agent: str,
    opponents: list[str],
    split: str = "select",
    n_seeds: int | None = None,
    ruleset_id: str = "OFFICIAL_US_CLASSIC_2008",
    n_players: int = 2,
    experiment: str = "adhoc",
    force_retest: bool = False,
    workers: int | None = None,
    smoke: bool = False,
    label: str = "official",
) -> dict[str, Any]:
    """Duplicate evaluation of ``agent`` against each opponent (2P) or a lineup (4P)."""
    if split not in SPLITS:
        raise ConfigError(f"split must be one of {SPLITS}")
    if smoke and split == "test":
        raise ConfigError("smoke runs never use the TEST split")
    agent = resolve_agent(agent)
    opponents = resolve_opponents(opponents)
    a_hash = ledger.agent_hash(agent)
    if split == "test" and not force_retest:
        ledger.check(a_hash)
    seeds = seeds_for(split, n_seeds, n_players)
    start = time.perf_counter()
    groups: dict[str, list[dict[str, Any]]] = {}
    if n_players == 2:
        for opp in opponents:
            groups[opp] = run_games(duplicate_specs(agent, [opp], seeds, ruleset_id, 2), workers=workers)
    else:
        lineup = opponents[: n_players - 1]
        key = "+".join(lineup)
        groups[key] = run_games(duplicate_specs(agent, lineup, seeds, ruleset_id, n_players), workers=workers)
    elapsed = time.perf_counter() - start
    eval_id = f"{split}_{experiment}_{a_hash[:10]}_{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir = sub_artifacts("eval", eval_id)
    all_records = [r for recs in groups.values() for r in recs]
    records_frame(all_records).to_parquet(out_dir / "games.parquet", index=False)
    summary: dict[str, Any] = {
        "eval_id": eval_id,
        "agent": agent,
        "agent_hash": a_hash,
        "split": split,
        "smoke": smoke or split == "smoke",
        "label": "SMOKE – keine Aussagekraft" if (smoke or split == "smoke") else label,
        "experiment": experiment,
        "ruleset_id": ruleset_id,
        "n_players": n_players,
        "n_seeds": len(seeds),
        "n_games": len(all_records),
        "seconds": elapsed,
        "strongest_baseline": strongest_baseline(),
        "opponents": {},
        "seat_win_rates": seat_win_rates(all_records),
    }
    for key, recs in groups.items():
        summary["opponents"][key] = {
            **summarize(recs, agent),
            "metrics": agent_metrics(recs, agent),
            "per_seed": {str(k): v for k, v in per_seed_scores(recs, agent).items()},
        }
    write_json(out_dir / "summary.json", summary)
    record_eval_summary(
        eval_id, a_hash, experiment, split, ruleset_id, len(seeds), len(all_records), list(groups), summary,
        out_dir, bool(summary["smoke"]),
    )  # fmt: skip
    if split == "test":
        ledger.record(a_hash, experiment, ruleset_id, len(seeds), eval_id, force=force_retest)
    return summary
