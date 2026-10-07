"""gamma sweep (§7.7): pilot runs, selection on SELECT against roi_markov_v1, frozen gamma.json."""

from __future__ import annotations

import logging
import statistics
from typing import Any

from propertyrl.agents.registry import clear_cache
from propertyrl.evaluation.duplicate import duplicate_specs, summarize
from propertyrl.evaluation.harness import default_workers, run_games
from propertyrl.evaluation.seeds import subset
from propertyrl.infra.config import frozen_dir, load_experiment
from propertyrl.infra.storage import write_json
from propertyrl.training.smoke import smoke_settings
from propertyrl.training.train import train

log = logging.getLogger(__name__)
SWEEP_OPPONENT = "roi_markov_v1"


def _quantiles(values: list[int]) -> dict[str, float]:
    if not values:
        return {}
    vals = sorted(values)
    q = statistics.quantiles(vals, n=10) if len(vals) >= 2 else [float(vals[0])] * 9
    return {"median": float(statistics.median(vals)), "p10": q[0], "p90": q[-1], "min": vals[0], "max": vals[-1],
            "n": len(vals)}  # fmt: skip


def run_gamma_sweep(smoke: bool = False, experiment: str = "gamma_sweep") -> dict[str, Any]:
    """Run the pilot runs, pick gamma and freeze it in artifacts/frozen/gamma.json."""
    exp = load_experiment(experiment)
    assert exp.sweep is not None
    timesteps = smoke_settings().sweep_timesteps if smoke else exp.sweep.timesteps
    n_seeds = smoke_settings().select_eval_seeds if smoke else 200
    seeds = subset("SMOKE" if smoke else "SELECT", start=0, end=n_seeds)
    pilots = []
    for g in exp.sweep.gammas:
        res = train("mcr_official_2p", exp.sweep.seed, smoke=smoke, gamma=g, timesteps=timesteps, run_tag=f"g{g}")
        agent = f"sb3:{res['best_select']}"
        specs = duplicate_specs(agent, [SWEEP_OPPONENT], seeds, "OFFICIAL_US_CLASSIC_2008", 2)
        records = run_games(specs, workers=1 if len(specs) <= 40 else default_workers())
        clear_cache()
        summary = summarize(records, agent, bootstrap_reps=1000)
        ev = res["ev_history"]
        steps = res["episode_steps"]
        durations = res["episode_durations"]
        horizon = 1.0 / (1.0 - g)
        med_d = statistics.median(durations) if durations else float("nan")
        pilots.append(
            {
                "gamma": g,
                "run_id": res["run_id"],
                "select_win_rate": summary["win_rate"],
                "wilson_lower": summary["wilson_lower"],
                "wilson_upper": summary["wilson_upper"],
                "mean_explained_variance": float(statistics.fmean(ev)) if ev else float("nan"),
                "genuine_decisions_per_game": _quantiles(steps),
                "sum_durations_per_game": _quantiles(durations),
                "effective_horizon": horizon,
                "horizon_over_median_k_sum": horizon / med_d if med_d == med_d and med_d else None,
            }
        )
    best = max(pilots, key=lambda p: p["select_win_rate"])
    ties = [p for p in pilots if p["select_win_rate"] >= best["wilson_lower"]]
    if len(ties) > 1:
        # Difference within the CI: higher mean explained variance decides.
        best = max(ties, key=lambda p: (p["mean_explained_variance"] if p["mean_explained_variance"] == p[
            "mean_explained_variance"] else -1.0, p["select_win_rate"]))  # fmt: skip
    result = {
        "gamma": best["gamma"],
        "rule": "max SELECT win rate vs roi_markov_v1; ties within CI by mean explained variance",
        "pilots": pilots,
        "timesteps_per_pilot": timesteps,
        "smoke": smoke,
    }
    if not smoke:
        write_json(frozen_dir() / "gamma.json", result)
    else:
        write_json(frozen_dir() / "gamma_smoke.json", result)
    log.info("gamma sweep selected gamma=%s", best["gamma"])
    return result
