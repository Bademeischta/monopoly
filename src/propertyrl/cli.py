"""Command line interface ``propertyrl <command>`` (§9.7)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_play(a: argparse.Namespace) -> int:
    from propertyrl.agents.base import respond
    from propertyrl.agents.registry import make_policy
    from propertyrl.engine import Engine, EngineOptions, render_text, write_log
    from propertyrl.engine.rng import AgentRng
    from propertyrl.infra.config import load_setup
    from propertyrl.infra.storage import sub_artifacts

    specs = [a.p0, a.p1] + [a.others] * max(0, a.players - 2)
    rules, board, decks = load_setup(a.ruleset, a.players)
    pols = [make_policy(s) for s in specs]
    eng = Engine.new(rules, board, decks, a.players, a.seed, EngineOptions(log_events=True, hash_interval=50))
    eng.meta = {"policies": specs}
    rngs = [AgentRng(a.seed, s) for s in range(a.players)]
    last_turn = -1
    while not eng.is_over() and eng.state.round_index < rules.safety_horizon_rounds:
        st = eng.state
        if a.verbose and st.turn_index != last_turn:
            last_turn = st.turn_index
            print(render_text(st, board))
        d = eng.pending()
        assert d is not None
        eng.apply(respond(pols[d.seat], eng, rngs[d.seat]))
    print(render_text(eng.state, board))
    res = eng.result()
    path = sub_artifacts("logs") / f"play_{a.ruleset}_{a.players}p_seed{a.seed}.jsonl"
    write_log(eng.to_log(), path)
    print(f"Sieger: {res.winner} ({specs[res.winner] if res.winner is not None else 'Remis/abgeschnitten'}), "
          f"Runden: {res.rounds}, Entscheidungen: {res.decisions}")  # fmt: skip
    print(f"state_hash: {eng.state_hash()}")
    print(f"Log: {path}")
    return 0


def cmd_replay(a: argparse.Namespace) -> int:
    from propertyrl.engine import read_log, render_text, replay_log
    from propertyrl.infra.archive import regenerate, verify

    if a.regenerate:
        _print(regenerate())
        return 0
    if a.verify_archive:
        res = verify()
        _print(res)
        return 0 if all(v["ok"] for v in res.values()) else 1
    if not a.log:
        print("--log, --regenerate oder --verify-archive angeben", file=sys.stderr)
        return 2
    log = read_log(Path(a.log))
    eng = replay_log(log)
    print(render_text(eng.state, eng.board))
    print(f"state_hash: {eng.state_hash()}")
    print(f"Replay identisch: {eng.state_hash() == log['header']['final_state_hash']}")
    return 0


def cmd_fuzz(a: argparse.Namespace) -> int:
    from propertyrl.infra.fuzz import FUZZ_CONFIGS, FuzzReport, fuzz, rare_event_fuzz, run_suite
    from propertyrl.infra.storage import sub_artifacts, write_json

    per_config = a.decisions
    if a.total_decisions:
        per_config = max(1, a.total_decisions // len(FUZZ_CONFIGS))
    if a.ruleset:
        rep = fuzz(a.ruleset, a.players, per_config, a.seed)
        total = FuzzReport("total")
        total.merge(rep)
        rare = rare_event_fuzz(a.rare_decisions or per_config, a.seed) if a.rare_events else None
        if rare:
            total.merge(rare)
        result: dict[str, Any] = {"configs": [rep.to_dict()], "rare_events": rare.to_dict() if rare else None,
                                  "total": total.to_dict()}  # fmt: skip
    else:
        result = run_suite(per_config, (a.rare_decisions or per_config) if a.rare_events else 0, a.seed)
    path = sub_artifacts("fuzz") / "fuzz_report.json"
    write_json(path, result)
    _print({"total_decisions": result["total"]["decisions"], "errors": result["total"]["errors"],
            "rare_event_min_counts": result.get("rare_event_min_counts"), "report": str(path)})  # fmt: skip
    return 0 if not result["total"]["errors"] else 1


def cmd_markov(a: argparse.Namespace) -> int:
    from propertyrl.engine.markov import markov_check
    from propertyrl.infra.config import load_setup
    from propertyrl.infra.storage import sub_artifacts, write_json

    rules, board, decks = load_setup("TEST_MOVEMENT_ONLY", 2)
    res = markov_check(rules, board, decks, a.moves, a.tolerance_pp, a.seed)
    write_json(sub_artifacts("markov") / "markov_report.json", res)
    _print({k: v for k, v in res.items() if k not in ("exact", "empirical")})
    return 0 if res["passed"] else 1


def cmd_benchmark(a: argparse.Namespace) -> int:
    from propertyrl.infra.benchmark import run_benchmark

    res = run_benchmark(a.seconds, a.smoke, a.max_envs)
    _print({"recommendation": res["recommendation"], "engine": res["engine"], "path": res["path"]})
    return 0


def cmd_horizon(a: argparse.Namespace) -> int:
    from propertyrl.evaluation.horizon import calibrate_horizon
    from propertyrl.training.smoke import smoke_settings

    games = a.games or (smoke_settings().horizon_games if a.smoke else 2000)
    res = calibrate_horizon(games, a.smoke, a.workers, include_4p=not a.no_4p)
    _print({k: v for k, v in res.items()})
    return 0 if res["passed"] else 1


def cmd_round_robin(a: argparse.Namespace) -> int:
    from propertyrl.evaluation.roundrobin import run_round_robin
    from propertyrl.training.smoke import smoke_settings

    k = a.seeds_per_block or (smoke_settings().roundrobin_seeds_per_block if a.smoke else None)
    res = run_round_robin(k, a.smoke, a.workers)
    _print({"strongest": res["strongest"], "passed": res["passed"], "transitive": res["transitive"],
            "stable_top": res["stable_top"], "elo": res["elo"],
            "ranking": {b: v["ranking"] for b, v in res["blocks"].items()}})  # fmt: skip
    return 0


def cmd_power(a: argparse.Namespace) -> int:
    from propertyrl.evaluation.stats import power_n
    from propertyrl.infra.config import frozen_dir
    from propertyrl.infra.storage import write_json

    table = {f"p={p}, ±{hw * 100:.0f} pp": power_n(p, hw) for p in (0.5, 0.25) for hw in (0.03, 0.02, 0.01)}
    out: dict[str, Any] = {"n_games": power_n(a.p, a.half_width), "table": table,
                           "recommendation": {"2p_seeds": 1200, "4p_seeds": 250}}  # fmt: skip
    if a.freeze:
        sizes = dict(item.split("=") for item in a.freeze.split(","))
        frozen = {k: int(v) for k, v in sizes.items()}
        write_json(frozen_dir() / "test_size.json", frozen)
        out["frozen"] = frozen
    _print(out)
    return 0


def cmd_plan(a: argparse.Namespace) -> int:
    from propertyrl.infra.config import list_experiments
    from propertyrl.infra.plan import plan

    names = list_experiments() if a.experiments == "all" else a.experiments.split(",")
    res = plan(names, a.smoke)
    _print(res)
    return 0


def cmd_train(a: argparse.Namespace) -> int:
    from propertyrl.infra.config import load_experiment
    from propertyrl.training.train import train

    if a.resume:
        res = train("", 0, resume=Path(a.resume), wandb=a.wandb)
        _print({k: v for k, v in res.items() if k not in ("episode_steps", "episode_durations", "ev_history")})
        return 0
    if not a.experiment:
        print("--experiment oder --resume angeben", file=sys.stderr)
        return 2
    exp = load_experiment(a.experiment)
    seeds = [a.seed] if a.seed is not None else exp.training.seeds + (exp.training.extended_seeds if a.extended else [])
    if a.smoke:
        seeds = seeds[:1]
    for seed in seeds:
        res = train(a.experiment, seed, smoke=a.smoke, wandb=a.wandb)
        _print({k: v for k, v in res.items() if k not in ("episode_steps", "episode_durations", "ev_history")})
    return 0


def cmd_sweep(a: argparse.Namespace) -> int:
    from propertyrl.training.sweep import run_gamma_sweep

    res = run_gamma_sweep(smoke=a.smoke)
    _print({"gamma": res["gamma"], "pilots": res["pilots"]})
    return 0


def cmd_selfplay(a: argparse.Namespace) -> int:
    from propertyrl.training.train import train

    res = train("selfplay_official_2p", a.seed, smoke=a.smoke)
    _print({"run_id": res["run_id"], "champion": res["champion"], "gates": res["champion_history"]})
    return 0


def cmd_evaluate(a: argparse.Namespace) -> int:
    from propertyrl.evaluation.evaluate import evaluate_agent

    split = "smoke" if a.smoke and a.split != "select" else a.split
    res = evaluate_agent(a.agent, a.opponents.split(","), split, a.n_seeds, a.ruleset, a.players, a.experiment,
                         a.force_retest, a.workers, smoke=a.smoke)  # fmt: skip
    _print({"eval_id": res["eval_id"], "label": res["label"],
            "opponents": {k: {x: v[x] for x in ("games", "win_rate", "wilson_lower", "wilson_upper")}
                          for k, v in res["opponents"].items()}})  # fmt: skip
    return 0


def cmd_kingmaking(a: argparse.Namespace) -> int:
    from propertyrl.evaluation.evaluate import resolve_agent
    from propertyrl.infra.pipeline import kingmaking_for

    agent = resolve_agent(a.agent) if a.agent else None
    res = kingmaking_for(a.experiment, agent, a.smoke)
    _print({k: v for k, v in res.items() if k not in ("details", "ws_values")})
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    from propertyrl.evaluation.report import generate_report

    print(generate_report(a.experiment, a.smoke))
    return 0


def cmd_gates(a: argparse.Namespace) -> int:
    from propertyrl.infra.gates import confirm_v_points, evaluate_gates

    if a.confirm_v_points:
        print(f"V1–V6 bestätigt: {confirm_v_points()}")
    res = evaluate_gates(a.gate, record=True)
    for gate, info in res.items():
        print(f"{gate}: {info['status']}")
        for c in info["criteria"]:
            print(f"    - {c['name']}: {c['status']} ({c['detail']})")
    return 0 if all(not v["status"].startswith("FAIL") for v in res.values()) else 1


def cmd_diagnose(a: argparse.Namespace) -> int:
    from propertyrl.infra.diagnose import diagnose

    res = diagnose(Path(a.run), a.steps)
    _print(res["checks"])
    return 0


def cmd_license(a: argparse.Namespace) -> int:
    from propertyrl.infra.licenses import check_licenses

    res = check_licenses()
    _print({"packages": res["packages"], "violations": res["violations"],
            "unknown_not_allowlisted": res["unknown_not_allowlisted"], "passed": res["passed"]})  # fmt: skip
    return 0 if res["passed"] else 1


def cmd_repro(a: argparse.Namespace) -> int:
    from propertyrl.infra.pipeline import repro

    res = repro(Path(a.run))
    _print(res)
    return 0 if res["match"] else 1


def cmd_pipeline(a: argparse.Namespace) -> int:
    from propertyrl.infra.pipeline import run_experiment_pipeline, smoke_all

    if a.smoke_all:
        res = smoke_all()
    elif a.experiment:
        res = run_experiment_pipeline(a.experiment, a.smoke, a.force_retest)
    else:
        print("--experiment oder --smoke-all angeben", file=sys.stderr)
        return 2
    _print(res)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """argparse definition of all commands."""
    p = argparse.ArgumentParser(prog="propertyrl", description="PropertyRL – Simulator, RL-Training und Evaluation")
    p.add_argument("--log-level", default="WARNING")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, fn: Any, help_text: str, smoke: bool = False) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(func=fn)
        if smoke:
            sp.add_argument("--smoke", action="store_true", help="Kleinformat (SMOKE-Seeds, keine Aussagekraft)")
        return sp

    sp = add("play", cmd_play, "Textspiel zwischen Policies")
    sp.add_argument("--p0", default="strong_a_v1")
    sp.add_argument("--p1", default="strong_b_v1")
    sp.add_argument("--others", default="roi_markov_v1")
    sp.add_argument("--players", type=int, default=2)
    sp.add_argument("--ruleset", default="OFFICIAL_US_CLASSIC_2008")
    sp.add_argument("--seed", type=int, default=1)
    sp.add_argument("--verbose", action="store_true")
    sp = add("replay", cmd_replay, "Log abspielen und Hash prüfen")
    sp.add_argument("--log")
    sp.add_argument("--regenerate", action="store_true", help="archivierte Replays neu erzeugen")
    sp.add_argument("--verify-archive", action="store_true")
    sp = add("fuzz", cmd_fuzz, "Fuzzing mit Invariantenprüfung")
    sp.add_argument("--decisions", type=int, default=100_000, help="Entscheidungen je Konfiguration")
    sp.add_argument("--total-decisions", type=int, default=0, help="Gesamtzahl, auf alle Konfigurationen verteilt")
    sp.add_argument("--players", type=int, default=2)
    sp.add_argument("--ruleset")
    sp.add_argument("--rare-events", action="store_true")
    sp.add_argument("--rare-decisions", type=int, default=0)
    sp.add_argument("--seed", type=int, default=1)
    sp = add("markov-check", cmd_markov, "Markov-Abgleich in TEST_MOVEMENT_ONLY")
    sp.add_argument("--moves", type=int, default=1_000_000)
    sp.add_argument("--tolerance-pp", type=float, default=0.15)
    sp.add_argument("--seed", type=int, default=1)
    sp = add("benchmark", cmd_benchmark, "Durchsatzmessung", smoke=True)
    sp.add_argument("--seconds", type=float, default=5.0)
    sp.add_argument("--max-envs", type=int)
    sp = add("calibrate-horizon", cmd_horizon, "Safety-Horizon kalibrieren", smoke=True)
    sp.add_argument("--games", type=int)
    sp.add_argument("--workers", type=int)
    sp.add_argument("--no-4p", action="store_true")
    sp = add("round-robin", cmd_round_robin, "Baseline-Round-Robin (G3)", smoke=True)
    sp.add_argument("--seeds-per-block", type=int)
    sp.add_argument("--workers", type=int)
    sp = add("power", cmd_power, "Stichprobengröße", smoke=True)
    sp.add_argument("--p", type=float, default=0.5)
    sp.add_argument("--half-width", type=float, default=0.02)
    sp.add_argument("--freeze", help="z. B. 2p=1200,4p=250 -> artifacts/frozen/test_size.json")
    sp = add("plan", cmd_plan, "Laufzeitplanung", smoke=True)
    sp.add_argument("--experiments", default="all")
    sp = add("train", cmd_train, "Training", smoke=True)
    sp.add_argument("--experiment")
    sp.add_argument("--seed", type=int)
    sp.add_argument("--resume")
    sp.add_argument("--extended", action="store_true", help="zusätzliche Seeds für den Abschlussbericht")
    sp.add_argument("--wandb", action="store_true", help="optional: technische Metriken an W&B (Standard offline)")
    add("sweep-gamma", cmd_sweep, "γ-Sweep", smoke=True)
    sp = add("selfplay", cmd_selfplay, "Self-Play-Training", smoke=True)
    sp.add_argument("--seed", type=int, default=1)
    sp = add("evaluate", cmd_evaluate, "Duplicate-Evaluation", smoke=True)
    sp.add_argument("--split", choices=("select", "test", "smoke"), default="select")
    sp.add_argument("--agent", required=True)
    sp.add_argument("--opponents", default="strongest_baseline,strong_a_v1,strong_b_v1,greedy_v1")
    sp.add_argument("--n-seeds", type=int)
    sp.add_argument("--ruleset", default="OFFICIAL_US_CLASSIC_2008")
    sp.add_argument("--players", type=int, default=2)
    sp.add_argument("--experiment", default="adhoc")
    sp.add_argument("--force-retest", action="store_true")
    sp.add_argument("--workers", type=int)
    sp = add("kingmaking", cmd_kingmaking, "Kingmaking-Analyse (4P)", smoke=True)
    sp.add_argument("--agent")
    sp.add_argument("--experiment", default="fourp_official")
    sp = add("report", cmd_report, "Bericht erzeugen", smoke=True)
    sp.add_argument("--experiment", required=True)
    sp = add("gates", cmd_gates, "Gate-Status G0-G8")
    sp.add_argument("--gate")
    sp.add_argument("--confirm-v-points", action="store_true", help="V1–V6 als vom Nutzer geprüft vermerken (G0)")
    sp = add("diagnose", cmd_diagnose, "Diagnose-Checkliste eines Laufs", smoke=True)
    sp.add_argument("--run", required=True)
    sp.add_argument("--steps", type=int, default=2000)
    add("license-check", cmd_license, "Lizenzprüfung der Laufzeitabhängigkeiten")
    sp = add("repro", cmd_repro, "Evaluation und Report aus run.json wiederholen und vergleichen", smoke=True)
    sp.add_argument("--run", required=True)
    sp = add("pipeline", cmd_pipeline, "Experiment-Pipeline oder vollständige Smoke-Kette", smoke=True)
    sp.add_argument("--experiment")
    sp.add_argument("--smoke-all", action="store_true")
    sp.add_argument("--force-retest", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    from propertyrl.infra.logging_setup import setup_logging

    setup_logging(getattr(logging, str(args.log_level).upper(), logging.WARNING))
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
