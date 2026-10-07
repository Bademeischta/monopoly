"""Pipelines: one experiment from training to report, the full smoke chain, and `repro` (§9.7, §12)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd

from propertyrl.evaluation import ledger
from propertyrl.evaluation.duplicate import duplicate_specs
from propertyrl.evaluation.evaluate import evaluate_agent, resolve_opponents, strongest_baseline
from propertyrl.evaluation.harness import run_games
from propertyrl.evaluation.seeds import subset
from propertyrl.infra.config import list_experiments, load_experiment
from propertyrl.infra.runmeta import load_run_meta
from propertyrl.infra.storage import artifacts_dir, query, read_json, sub_artifacts, write_json

log = logging.getLogger(__name__)
SMOKE_ABLATIONS = (
    "ablation_a0_terminal",
    "ablation_a2_purdue",
    "ablation_n4_buy_delegated",
    "ablation_no_trade",
    "ablation_shared_delegation",
    "ablation_no_smdp",
    "fallback_research_2p",
    "research_shortgame_2p",
)


def _agent_of(result: dict[str, Any], selfplay: bool) -> str:
    path = Path(result["run_dir"]) / ("champion.zip" if selfplay else "best_select.zip")
    if not path.exists():
        path = Path(result["final"])
    return f"sb3:{path}"


def selfplay_opponents(result: dict[str, Any], smoke: bool, max_snapshots: int = 5) -> list[str]:
    """Extra Z4 opponents of a champion: its MCR start agent (a) and up to 5 older snapshots, evenly spaced (c)."""
    from propertyrl.training.train import find_checkpoint

    rdir = Path(result["run_dir"])
    meta = load_run_meta(rdir)
    start = meta.get("init_from")
    mcr = Path(start) if start else find_checkpoint("mcr_official_2p", None, smoke)
    out = [f"sb3:{mcr}"] if mcr is not None and Path(mcr).exists() else []
    state = read_json(rdir / "training_state.json") if (rdir / "training_state.json").exists() else {}
    pool = [p for p in (state.get("pool") or {}).get("paths", []) if Path(p).exists()]
    champion = str(state.get("champion") or "").split(":", 1)[-1]
    older = pool[: pool.index(champion)] if champion in pool else []
    if len(older) > max_snapshots:
        step = len(older) / max_snapshots
        older = [older[int(i * step)] for i in range(max_snapshots)]
    return out + [f"sb3:{p}" for p in older]


def existing_eval(agent: str, experiment: str, split: str, smoke: bool) -> dict[str, Any] | None:
    """Newest stored evaluation of ``agent`` (policy spec) for an experiment and split, if any."""
    rows = query(
        "SELECT summary_json FROM eval_summaries WHERE agent_hash = ? AND experiment = ? AND split = ? AND smoke = ? "
        "ORDER BY created DESC LIMIT 1",
        (ledger.agent_hash(agent), experiment, split, int(smoke)),
    )
    return json.loads(rows[0][0]) if rows else None


def _evaluate_once(agent: str, experiment: str, split: str, smoke: bool, **kwargs: Any) -> dict[str, Any]:
    """Evaluate unless this agent already has an evaluation for the experiment and split (re-runnable pipeline)."""
    found = existing_eval(agent, experiment, split, smoke)
    if found is not None:
        log.info("reusing %s evaluation %s of %s", split, found.get("eval_id"), agent)
        return found
    return evaluate_agent(agent, split=split, experiment=experiment, smoke=smoke, **kwargs)


def evaluate_experiment_agents(
    experiment: str, results: list[dict[str, Any]], smoke: bool, force_retest: bool = False
) -> list[dict[str, Any]]:
    """SELECT evaluation plus the primary split (TEST, or SMOKE in smoke mode) for every run.

    Every opponent of the primary split is evaluated in a single call, because the ledger allows one TEST
    evaluation per agent; for self-play this includes the MCR agent and older snapshots (Z4).
    """
    exp = load_experiment(experiment)
    selfplay = exp.mode == "selfplay"
    n_players = exp.env.n_players
    opponents = resolve_opponents(list(exp.evaluation.opponents))
    if n_players == 2:
        opponents = list(dict.fromkeys(opponents))
    else:
        opponents = opponents[: n_players - 1]
    out = []
    for res in results:
        agent = _agent_of(res, selfplay)
        opps = opponents + selfplay_opponents(res, smoke) if selfplay else opponents
        common = {"opponents": opps, "ruleset_id": exp.env.ruleset, "n_players": n_players, "label": exp.label}
        if smoke:
            out.append(_evaluate_once(agent, experiment, "smoke", True, **common))
            continue
        out.append(_evaluate_once(agent, experiment, "select", False, n_seeds=exp.evaluation.n_select_seeds, **common))
        n_test = None if exp.evaluation.n_test_seeds == "frozen" else int(exp.evaluation.n_test_seeds)
        if force_retest:
            out.append(evaluate_agent(agent, split="test", n_seeds=n_test, experiment=experiment, force_retest=True,
                                      **common))  # fmt: skip
        else:
            out.append(_evaluate_once(agent, experiment, "test", False, n_seeds=n_test, **common))
    return out


def kingmaking_for(experiment: str, agent: str | None, smoke: bool) -> dict[str, Any]:
    """Kingmaking on the 4P lineup (agent games on TEST/SMOKE seeds, baselines on SELECT/SMOKE seeds)."""
    from propertyrl.evaluation.kingmaking import KingmakingParams, run_kingmaking
    from propertyrl.training.smoke import smoke_settings

    lineup = ["strong_a_v1", "strong_b_v1", "roi_markov_v1"]
    if smoke:
        so = smoke_settings()
        params = KingmakingParams(so.kingmaking_games, so.kingmaking_points, so.kingmaking_actions,
                                  so.kingmaking_rollouts)  # fmt: skip
        seeds = subset("SMOKE", start=0, end=params.games)
    else:
        params = KingmakingParams()
        from propertyrl.evaluation.evaluate import test_size

        seeds = subset("TEST" if agent else "SELECT", start=0, end=min(params.games, test_size(4)))
    first = agent or "strong_a_v1"
    specs = duplicate_specs(first, lineup, seeds, "OFFICIAL_US_CLASSIC_2008", 4)[::4][: params.games]
    result = run_kingmaking(specs, params)
    tag = ("smoke_" if smoke else "") + experiment + "_" + time.strftime("%Y%m%d-%H%M%S")
    write_json(sub_artifacts("kingmaking") / f"kingmaking_{tag}.json", result)
    return result


def run_experiment_pipeline(experiment: str, smoke: bool = False, force_retest: bool = False) -> dict[str, Any]:
    """Training (all seeds) -> evaluation -> (kingmaking) -> report."""
    from propertyrl.evaluation.report import generate_report
    from propertyrl.training.sweep import run_gamma_sweep
    from propertyrl.training.train import train, train_or_reuse

    exp = load_experiment(experiment)
    if exp.mode == "sweep":
        sweep = run_gamma_sweep(smoke=smoke, experiment=experiment)
        report = generate_report(experiment, smoke)
        return {"experiment": experiment, "sweep": sweep, "report": str(report)}
    seeds = exp.training.seeds[:1] if smoke else exp.training.seeds
    # Finished runs with the identical configuration are reused and interrupted ones resumed (A-136);
    # smoke runs always train afresh.
    results = [train(experiment, seed, smoke=True) if smoke else train_or_reuse(experiment, seed) for seed in seeds]
    evals = evaluate_experiment_agents(experiment, results, smoke, force_retest)
    km = None
    if exp.env.n_players > 2:
        km = kingmaking_for(experiment, _agent_of(results[0], False), smoke)
    report = generate_report(experiment, smoke)
    return {
        "experiment": experiment,
        "runs": [r["run_id"] for r in results],
        "evaluations": [e["eval_id"] for e in evals],
        "kingmaking_rate": km["kingmaking_rate"] if km else None,
        "report": str(report),
    }


def repro(run_path: Path) -> dict[str, Any]:
    """Re-run the stored evaluations of a run from its run.json and compare game by game; regenerate the report."""
    from propertyrl.evaluation.report import generate_report

    meta = load_run_meta(run_path)
    smoke = bool(meta.get("smoke"))
    experiment = meta["experiment"]
    agents = []
    for name in ("champion.zip", "best_select.zip", "final.zip"):
        p = run_path / name
        if p.exists():
            agents.append(ledger.agent_hash(f"sb3:{p}"))
    marks = ",".join("?" * len(agents))
    sql = f"SELECT eval_id, summary_json, path FROM eval_summaries WHERE agent_hash IN ({marks})"
    rows = query(sql, tuple(agents)) if agents else []
    comparisons = []
    for eval_id, summary_json, path in rows:
        summary = json.loads(summary_json)
        stored = pd.read_parquet(Path(path) / "games.parquet")
        specs = []
        for _, row in stored.iterrows():
            from propertyrl.evaluation.harness import GameSpec

            specs.append(GameSpec(row["ruleset_id"], int(row["seed"]), tuple(json.loads(row["seats"])),
                                  int(row["rotation"]), seed_index=int(row["seed_index"])))  # fmt: skip
        again = run_games(specs)
        same = all(
            a["winner"] == (None if pd.isna(b["winner"]) else int(b["winner"]))
            and a["placements"] == json.loads(b["placements"])
            and a["rounds"] == int(b["rounds"])
            for a, (_, b) in zip(again, stored.iterrows(), strict=True)
        )
        comparisons.append({"eval_id": eval_id, "split": summary["split"], "games": len(specs), "match": same})
    report = generate_report(experiment, smoke)
    result = {
        "run_id": meta["run_id"],
        "experiment": experiment,
        "evaluations": comparisons,
        "match": bool(comparisons) and all(c["match"] for c in comparisons),
        "report": str(report),
        "smoke": smoke,
    }
    tag = ("smoke_" if smoke else "") + meta["run_id"]
    write_json(sub_artifacts("repro") / f"repro_{tag}.json", result)
    return result


def smoke_all() -> dict[str, Any]:
    """Complete chain of all stages in small format (§9.7); the TEST ledger must stay empty."""
    from propertyrl.evaluation.horizon import calibrate_horizon
    from propertyrl.evaluation.report import generate_report
    from propertyrl.evaluation.roundrobin import run_round_robin
    from propertyrl.infra.gates import evaluate_gates
    from propertyrl.training.smoke import smoke_settings
    from propertyrl.training.sweep import run_gamma_sweep
    from propertyrl.training.train import train

    so = smoke_settings()
    ledger_before = len(ledger.entries())
    t0 = time.perf_counter()
    steps: dict[str, Any] = {}

    def stage(name: str, fn: Any) -> Any:
        start = time.perf_counter()
        log.info("smoke stage %s", name)
        value = fn()
        steps[name] = {"seconds": round(time.perf_counter() - start, 1)}
        return value

    rr = stage("round_robin", lambda: run_round_robin(so.roundrobin_seeds_per_block, smoke=True))
    hz = stage("calibrate_horizon", lambda: calibrate_horizon(so.horizon_games, smoke=True))
    sweep = stage("sweep_gamma", lambda: run_gamma_sweep(smoke=True))
    mcr = stage("train_mcr", lambda: train("mcr_official_2p", 1, smoke=True))
    agent = _agent_of(mcr, False)
    stage("evaluate_select", lambda: evaluate_agent(agent, ["random_legal", "roi_markov_v1"], "select",
                                                    so.select_eval_seeds, experiment="mcr_official_2p",
                                                    smoke=True))  # fmt: skip
    stage("evaluate_smoke", lambda: evaluate_experiment_agents("mcr_official_2p", [mcr], smoke=True))
    for abl in SMOKE_ABLATIONS:
        res = stage(f"train_{abl}", lambda abl=abl: train(abl, 1, smoke=True))
        stage(f"evaluate_{abl}", lambda abl=abl, res=res: evaluate_experiment_agents(abl, [res], smoke=True))
    sp = stage("selfplay", lambda: train("selfplay_official_2p", 1, smoke=True))
    stage("evaluate_selfplay", lambda: evaluate_experiment_agents("selfplay_official_2p", [sp], smoke=True))
    fourp = {}
    for exp4 in ("fourp_official", "fourp_single_seat_fallback", "ablation_a3_kingmaking_4p"):
        fourp[exp4] = stage(f"train_{exp4}", lambda exp4=exp4: train(exp4, 1, smoke=True))
        stage(f"evaluate_{exp4}", lambda exp4=exp4: evaluate_experiment_agents(exp4, [fourp[exp4]], smoke=True))
    km = stage("kingmaking", lambda: kingmaking_for("fourp_official", _agent_of(fourp["fourp_official"], False), True))
    reports = {}
    for name in ("mcr_official_2p", "selfplay_official_2p", "fourp_official", "gamma_sweep"):
        reports[name] = str(stage(f"report_{name}", lambda name=name: generate_report(name, smoke=True)))
    rp = stage("repro", lambda: repro(Path(mcr["run_dir"])))
    gates = stage("gates", lambda: evaluate_gates(record=True))
    result = {
        "seconds": round(time.perf_counter() - t0, 1),
        "stages": steps,
        "round_robin_strongest": rr["strongest"],
        "horizon_2p": hz["horizon_2p"],
        "gamma": sweep["gamma"],
        "mcr_run": mcr["run_id"],
        "selfplay_champion_changes": sum(1 for h in sp["champion_history"] if h["passed"]),
        "kingmaking_rate": km["kingmaking_rate"],
        "reports": reports,
        "repro_match": rp["match"],
        "gates": {g: v["status"] for g, v in gates.items()},
        "test_ledger_empty": ledger.is_empty(),
        "test_ledger_unchanged": len(ledger.entries()) == ledger_before,
        "experiments": list_experiments(),
        "strongest_baseline_used": strongest_baseline(),
        "artifacts_dir": str(artifacts_dir()),
    }
    write_json(sub_artifacts("pipeline") / "smoke_all.json", result)
    if not result["test_ledger_unchanged"]:
        raise RuntimeError("smoke pipeline wrote to the TEST ledger")
    return result
