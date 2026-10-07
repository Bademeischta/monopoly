"""Throughput benchmark (§9.5): engine, Gym env, DummyVecEnv and SubprocVecEnv; recommendation for n_envs."""

from __future__ import annotations

import logging
import os
import statistics
import time
from typing import Any

import numpy as np
import psutil

from propertyrl.agents.base import respond
from propertyrl.agents.registry import make_policy
from propertyrl.engine import Engine, EngineOptions
from propertyrl.engine.rng import AgentRng
from propertyrl.env.core import EnvConfig
from propertyrl.env.factory import make_vec_env
from propertyrl.env.opponents import OpponentConfig
from propertyrl.infra.config import load_setup
from propertyrl.infra.storage import record_benchmark, sub_artifacts, write_json

log = logging.getLogger(__name__)
N_ENVS_LIST = (1, 4, 8, 16, 32, 64)


def bench_engine(seconds: float, log_events: bool) -> dict[str, Any]:
    """Heuristic self-play games (strong_a vs strong_b) directly on the engine."""
    rules, board, decks = load_setup("OFFICIAL_US_CLASSIC_2008", 2)
    pols = [make_policy("strong_a_v1"), make_policy("strong_b_v1")]
    proc = psutil.Process()
    proc.cpu_percent(None)
    start = time.perf_counter()
    games = 0
    decisions = 0
    latencies = []
    seed = 0
    while time.perf_counter() - start < seconds:
        t0 = time.perf_counter()
        eng = Engine.new(rules, board, decks, 2, seed, EngineOptions(log_events=log_events))
        rngs = [AgentRng(seed, 0), AgentRng(seed, 1)]
        while not eng.is_over() and eng.state.round_index < rules.safety_horizon_rounds:
            d = eng.pending()
            assert d is not None
            eng.apply(respond(pols[d.seat], eng, rngs[d.seat]))
        decisions += eng.state.decision_index
        latencies.append(time.perf_counter() - t0)
        games += 1
        seed += 1
    elapsed = time.perf_counter() - start
    return {
        "games_per_s": games / elapsed,
        "engine_steps_per_s": decisions / elapsed,
        "agent_decisions_per_s": decisions / elapsed,
        "game_latency_p50_s": statistics.median(latencies),
        "game_latency_p95_s": float(np.quantile(latencies, 0.95)),
        "cpu_percent": proc.cpu_percent(None),
        "rss_mb": proc.memory_info().rss / 2**20,
        "games": games,
    }


def bench_vecenv(n_envs: int, vec_env: str, seconds: float) -> dict[str, Any]:
    """Masked random actions in a vectorised environment (strong opponents, no logging)."""
    from sb3_contrib.common.maskable.utils import get_action_masks

    cfg = EnvConfig(opponents=OpponentConfig(mode="fixed", fixed=("strong_a_v1", "strong_b_v1"), epsilon=0.05))
    venv = make_vec_env(cfg, n_envs, 123, vec_env=vec_env)
    rng = np.random.default_rng(0)
    try:
        venv.reset()
        steps = 0
        start = time.perf_counter()
        while time.perf_counter() - start < seconds:
            masks = get_action_masks(venv)
            actions = np.array([rng.choice(np.flatnonzero(m)) for m in masks])
            venv.step(actions)
            steps += n_envs
        elapsed = time.perf_counter() - start
    finally:
        venv.close()
    return {"n_envs": n_envs, "vec_env": vec_env, "env_steps_per_s": steps / elapsed}


def run_benchmark(seconds: float = 5.0, smoke: bool = False, max_envs: int | None = None) -> dict[str, Any]:
    """Run all measurements and write artifacts/benchmarks/benchmark_<stamp>.json."""
    cores = os.cpu_count() or 1
    env_list = [n for n in N_ENVS_LIST if n <= (max_envs or 64)]
    if smoke:
        seconds = min(seconds, 1.5)
        env_list = [1, 4]
    result: dict[str, Any] = {
        "cores": cores,
        "seconds_per_measurement": seconds,
        "smoke": smoke,
        "engine": {
            "with_logging": bench_engine(seconds, True),
            "without_logging": bench_engine(seconds, False),
        },
        "gym_dummy": [bench_vecenv(n, "dummy", seconds) for n in env_list if n <= 16],
        "subproc": [bench_vecenv(n, "subproc", seconds) for n in env_list],
    }
    candidates = result["gym_dummy"] + result["subproc"]
    best = max(candidates, key=lambda r: r["env_steps_per_s"])
    result["recommendation"] = {
        "vec_env": best["vec_env"],
        "n_envs": best["n_envs"],
        "env_steps_per_s": best["env_steps_per_s"],
        "note": "PPO-Updates kommen hinzu; ppo_default.yaml begrenzt n_envs auf die Kernzahl.",
    }
    stamp = time.strftime("%Y%m%d-%H%M%S") + ("_smoke" if smoke else "")
    path = sub_artifacts("benchmarks") / f"benchmark_{stamp}.json"
    write_json(path, result)
    record_benchmark(stamp, result)
    result["path"] = str(path)
    return result
