"""Compute planning (§7.11): run time per experiment from measured throughput, evaluation share, warnings."""

from __future__ import annotations

import json
import os
from typing import Any

from propertyrl.infra.storage import query, read_json, sub_artifacts

MAX_RUN_HOURS = 12.0
MAX_EVAL_FRACTION = 0.2
#: Fallbacks when nothing was measured yet (env steps/s incl. PPO updates on one core, games/s).
DEFAULT_TRAIN_SPS = 1200.0
DEFAULT_GAMES_PER_S = 15.0


def measured_throughput() -> dict[str, Any]:
    """Training steps/s from finished runs (preferred) and evaluation games/s from the benchmark."""
    train_sps = None
    rows = query("SELECT run_json FROM runs WHERE status = 'completed'")
    rates = []
    for (raw,) in rows:
        meta = json.loads(raw)
        hours = float(meta.get("training_hours") or 0.0)
        steps = int(meta.get("timesteps_done") or 0)
        if hours > 0 and steps > 10_000:
            rates.append(steps / (hours * 3600.0))
    if rates:
        train_sps = sum(rates) / len(rates)
    games = None
    bench = sorted(p for p in sub_artifacts("benchmarks").glob("benchmark_*.json") if "smoke" not in p.name)
    bench = bench or sorted(sub_artifacts("benchmarks").glob("benchmark_*.json"))
    if bench:
        data = read_json(bench[-1])
        games = data["engine"]["without_logging"]["games_per_s"] * max(1, (os.cpu_count() or 2) - 1)
        if train_sps is None:
            train_sps = 0.5 * data["recommendation"]["env_steps_per_s"]
    return {
        "train_steps_per_s": train_sps or DEFAULT_TRAIN_SPS,
        "eval_games_per_s": games or DEFAULT_GAMES_PER_S,
        "measured": bool(rates or bench),
    }


def plan(experiments: list[str], smoke: bool = False) -> dict[str, Any]:
    """Run time per run, totals, evaluation share and warnings."""
    from propertyrl.evaluation.evaluate import test_size
    from propertyrl.training.train import resolve

    tp = measured_throughput()
    rows = []
    total_train = total_eval = 0.0
    warnings = []
    for name in experiments:
        exp, ppo, env = resolve(name, 1, smoke)
        seeds = len(exp.training.seeds) if exp.mode != "sweep" else len(exp.sweep.gammas if exp.sweep else [])
        steps = exp.sweep.timesteps if exp.mode == "sweep" and exp.sweep else ppo.total_timesteps
        hours = steps / tp["train_steps_per_s"] / 3600.0
        evals_in_training = (steps // ppo.select_eval_interval) * ppo.select_eval_seeds * 2
        if exp.opponents.mode == "curriculum":
            evals_in_training += (steps // ppo.checkpoint_interval) * exp.opponents.select_mini_seeds * 2
        n_opp = len(exp.evaluation.opponents)
        test_games = test_size(env.n_players) * (2 * n_opp if env.n_players == 2 else env.n_players)
        # RL agents need network inference: count their games at half the heuristic game rate.
        eval_hours = (evals_in_training + test_games) / (0.5 * tp["eval_games_per_s"]) / 3600.0
        total_train += hours * seeds
        total_eval += eval_hours * seeds
        if hours > MAX_RUN_HOURS:
            warnings.append(f"{name}: geplanter Lauf {hours:.1f} h > {MAX_RUN_HOURS} h")
        rows.append({"experiment": name, "seeds": seeds, "timesteps": steps, "hours_per_run": hours,
                     "eval_hours_per_run": eval_hours})  # fmt: skip
    total = total_train + total_eval
    frac = total_eval / total if total else 0.0
    if frac > MAX_EVAL_FRACTION:
        warnings.append(f"Evaluationsanteil {frac:.0%} > {MAX_EVAL_FRACTION:.0%}")
    return {
        "throughput": tp,
        "runs": rows,
        "total_train_hours": total_train,
        "total_eval_hours": total_eval,
        "eval_fraction": frac,
        "warnings": warnings,
        "smoke": smoke,
    }
