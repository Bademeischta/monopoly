"""Target criteria Z3, Z4 and Z5 (§8.4) computed from stored evaluations (summaries plus Parquet games)."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from propertyrl.engine.errors import ArtifactError
from propertyrl.evaluation.duplicate import agent_seat, score
from propertyrl.evaluation.stats import cluster_bootstrap, wilson
from propertyrl.infra.storage import query

#: Record fields that are stored as JSON strings in games.parquet.
NESTED_FIELDS = (
    "seats", "policy_versions", "placements", "decisions_per_seat", "final_equities", "bankrupt", "counters",
    "jail_decisions", "complete_groups",
)  # fmt: skip
INT_FIELDS = ("seed", "seed_index", "rotation", "n_players", "rounds", "decisions")
Z3_MIN_SEEDS = 3
Z4_MARGIN = 0.02
Z5_FIRST_PLACE = 0.25
BOOT_REPS = 5000


def load_records(eval_dir: Path) -> list[dict[str, Any]]:
    """Game records of one evaluation (games.parquet) with nested fields decoded."""
    path = eval_dir / "games.parquet"
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError) as err:  # pyarrow.ArrowInvalid is a ValueError
        raise ArtifactError(f"{path} is damaged or missing ({err}); run 'propertyrl doctor' for the repair step",
                            details={"path": str(path)}) from err  # fmt: skip
    out = []
    for row in frame.to_dict("records"):
        for key in NESTED_FIELDS:
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])
        winner = row.get("winner")
        row["winner"] = None if winner is None or (isinstance(winner, float) and math.isnan(winner)) else int(winner)
        for key in INT_FIELDS:
            if key in row:
                row[key] = int(row[key])
        row["truncated"] = bool(row["truncated"])
        out.append(row)
    return out


def latest_evals(experiment: str, split: str, smoke: bool) -> list[tuple[dict[str, Any], Path]]:
    """Newest evaluation per agent hash of an experiment and split, in creation order."""
    rows = query(
        "SELECT agent_hash, summary_json, path FROM eval_summaries WHERE experiment = ? AND split = ? AND smoke = ? "
        "ORDER BY created",
        (experiment, split, int(smoke)),
    )
    latest: dict[str, tuple[dict[str, Any], Path]] = {}
    for agent_hash, raw, path in rows:
        latest.pop(agent_hash, None)
        latest[agent_hash] = (json.loads(raw), Path(path))
    return list(latest.values())


def _games_against(records: Sequence[dict[str, Any]], agent: str, opponent: str) -> list[dict[str, Any]]:
    return [r for r in records if agent in r["seats"] and opponent in r["seats"]]


def _pooled(groups: Sequence[tuple[str, Sequence[dict[str, Any]]]], seed_key: Sequence[int]) -> dict[str, Any]:
    values: list[float] = []
    clusters: list[int] = []
    for agent, recs in groups:
        values += [score(r, agent) for r in recs]
        clusters += [r["seed_index"] if r["seed_index"] >= 0 else r["seed"] for r in recs]
    if not values:
        return {"games": 0, "win_rate": None, "lower": None, "upper": None}
    boot = cluster_bootstrap(values, clusters, reps=BOOT_REPS, seed_key=seed_key)
    return {"games": len(values), "win_rate": boot.estimate, "lower": boot.lower, "upper": boot.upper,
            "p_value": boot.p_value, "clusters": boot.n_clusters}  # fmt: skip


def training_seed_of(agent: str) -> int | None:
    """Training seed of an RL agent spec ``sb3:<runs>/<run_id>/<file>.zip`` from its run.json (None if unknown)."""
    _, _, path = agent.partition(":")
    meta_path = Path(path).parent / "run.json"
    if not path or not meta_path.exists():
        return None
    seed = json.loads(meta_path.read_text(encoding="utf-8")).get("training_seed")
    return int(seed) if seed is not None else None


def z3(experiment: str = "mcr_official_2p", split: str = "test", smoke: bool = False) -> dict[str, Any]:
    """Z3: pooled over the training seeds the lower 95 % bound > 50 % and every seed's point estimate > 50 %.

    Only the experiment's configured training seeds count, with the newest evaluation per seed, so additional
    seeds (``--extended``) or repeated runs do not change the gate (A-137).
    """
    from propertyrl.infra.config import list_experiments, load_experiment

    configured = set(load_experiment(experiment).training.seeds) if experiment in list_experiments() else None
    by_seed: dict[Any, tuple[dict[str, Any], Path]] = {}
    excluded = []
    for summary, path in latest_evals(experiment, split, smoke):
        seed = training_seed_of(summary["agent"])
        if seed is not None and configured is not None and seed not in configured:
            excluded.append(summary["agent"])
            continue
        by_seed[seed if seed is not None else summary["agent"]] = (summary, path)
    evals = list(by_seed.values())
    per_agent = []
    groups = []
    primary = None
    for summary, path in evals:
        agent = summary["agent"]
        primary = summary.get("strongest_baseline") or "strong_a_v1"
        recs = _games_against(load_records(path), agent, primary)
        groups.append((agent, recs))
        rate = sum(score(r, agent) for r in recs) / len(recs) if recs else None
        per_agent.append({"agent": agent, "games": len(recs), "win_rate": rate})
    pooled = _pooled(groups, (3, len(groups)))
    rates = [a["win_rate"] for a in per_agent]
    passed = (
        len(per_agent) >= Z3_MIN_SEEDS
        and pooled["lower"] is not None
        and pooled["lower"] > 0.5
        and all(r is not None and r > 0.5 for r in rates)
    )
    return {"criterion": "Z3", "experiment": experiment, "split": split, "smoke": smoke, "primary_opponent": primary,
            "agents": per_agent, "pooled": pooled, "required_seeds": Z3_MIN_SEEDS, "evaluated": bool(evals),
            "excluded_extra_seeds": excluded, "passed": bool(passed)}  # fmt: skip


def _rate(summary: dict[str, Any], opponent: str) -> float | None:
    opp = summary.get("opponents", {}).get(opponent)
    return float(opp["win_rate"]) if opp else None


def z4(split: str = "test", smoke: bool = False) -> dict[str, Any]:
    """Z4: (a) champion vs MCR agent lower bound > 50 %; (b) vs strong_a/strong_b at most 2 pp below the MCR
    agent; (c) mean win rate against older snapshots > 50 % (reported with CI)."""
    champions = latest_evals("selfplay_official_2p", split, smoke)
    mcr = {s["agent"]: s for s, _ in latest_evals("mcr_official_2p", split, smoke)}
    results = []
    for summary, path in champions:
        agent = summary["agent"]
        opps = summary.get("opponents", {})
        mcr_keys = [k for k in opps if k.startswith("sb3:") and "mcr_official_2p" in k]
        snap_keys = [k for k in opps if k.startswith("sb3:") and "/snapshots/" in k.replace("\\", "/")]
        entry: dict[str, Any] = {"agent": agent, "mcr_agent": mcr_keys[0] if mcr_keys else None}
        if mcr_keys:
            vs_mcr = opps[mcr_keys[0]]
            entry["a_vs_mcr"] = {"win_rate": vs_mcr["win_rate"], "lower": vs_mcr["bootstrap"]["lower"]}
            entry["a_passed"] = vs_mcr["bootstrap"]["lower"] > 0.5
        else:
            entry["a_passed"] = False
        b_checks = {}
        for base in ("strong_a_v1", "strong_b_v1"):
            mine = _rate(summary, base)
            ref = _rate(mcr[mcr_keys[0]], base) if mcr_keys and mcr_keys[0] in mcr else None
            b_checks[base] = {"champion": mine, "mcr": ref,
                              "passed": mine is not None and ref is not None and mine >= ref - Z4_MARGIN}  # fmt: skip
        entry["b"] = b_checks
        entry["b_passed"] = all(v["passed"] for v in b_checks.values())
        if snap_keys:
            records = load_records(path)
            pooled = _pooled([(agent, _games_against(records, agent, k)) for k in snap_keys], (4, len(snap_keys)))
            entry["c_vs_snapshots"] = pooled
            entry["c_passed"] = pooled["win_rate"] is not None and pooled["win_rate"] > 0.5
        else:
            entry["c_vs_snapshots"] = None
            entry["c_passed"] = False
        entry["passed"] = bool(entry["a_passed"] and entry["b_passed"] and entry["c_passed"])
        results.append(entry)
    return {"criterion": "Z4", "split": split, "smoke": smoke, "champions": results, "evaluated": bool(champions),
            "passed": bool(results) and all(r["passed"] for r in results)}  # fmt: skip


def z5(experiment: str = "fourp_official", split: str = "test", smoke: bool = False) -> dict[str, Any]:
    """Z5 (4P): first-place Wilson lower bound > 25 %, mean placement better than every baseline (bootstrap CI
    of the difference excludes 0) and a first-place point estimate > 25 % in each of the 4 rotations."""
    results = []
    evals = latest_evals(experiment, split, smoke)
    for summary, path in evals:
        agent = summary["agent"]
        records = load_records(path)
        if not records:
            continue
        seats = [agent_seat(r, agent) for r in records]
        firsts = [1.0 if r["placements"][s] == 1 else 0.0 for r, s in zip(records, seats, strict=True)]
        lower, upper = wilson(sum(firsts), len(firsts))
        clusters = [r["seed_index"] if r["seed_index"] >= 0 else r["seed"] for r in records]
        baselines = sorted({spec for r in records for spec in r["seats"] if spec != agent})
        diffs = {}
        for base in baselines:
            values = []
            cl = []
            for r, s, c in zip(records, seats, clusters, strict=True):
                if r["seats"].count(base) != 1:
                    continue
                values.append(float(r["placements"][s] - r["placements"][r["seats"].index(base)]))
                cl.append(c)
            boot = cluster_bootstrap(values, cl, reps=BOOT_REPS, seed_key=(5, len(values)), null=0.0)
            diffs[base] = {"mean_difference": boot.estimate, "lower": boot.lower, "upper": boot.upper,
                           "passed": boot.upper < 0.0}  # fmt: skip
        by_rotation: dict[int, list[float]] = defaultdict(list)
        for r, f in zip(records, firsts, strict=True):
            by_rotation[r["rotation"]].append(f)
        rotations = {rot: sum(v) / len(v) for rot, v in sorted(by_rotation.items())}
        n_players = records[0]["n_players"]
        passed = (
            lower > Z5_FIRST_PLACE
            and bool(diffs)
            and all(d["passed"] for d in diffs.values())
            and len(rotations) == n_players
            and all(v > Z5_FIRST_PLACE for v in rotations.values())
        )
        results.append({"agent": agent, "games": len(records), "first_place_rate": sum(firsts) / len(firsts),
                        "wilson_lower": lower, "wilson_upper": upper, "placement_differences": diffs,
                        "rotations": rotations, "passed": bool(passed)})  # fmt: skip
    return {"criterion": "Z5", "experiment": experiment, "split": split, "smoke": smoke, "agents": results,
            "evaluated": bool(evals), "passed": any(r["passed"] for r in results)}  # fmt: skip
