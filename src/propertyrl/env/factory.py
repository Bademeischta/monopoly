"""Picklable environment factories for DummyVecEnv / SubprocVecEnv (§6.7)."""

from __future__ import annotations

import functools
import multiprocessing
import sys
from collections.abc import Callable
from typing import Any

import gymnasium as gym
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecEnv

from propertyrl.env.core import EnvConfig
from propertyrl.env.multi_seat import PropertyMultiSeatEnv
from propertyrl.env.single_agent import PropertySingleAgentEnv


def make_env(config_dict: dict[str, Any], rank: int, base_seed: int, multi_seat: bool = False) -> gym.Env[Any, Any]:
    """Top-level (picklable) factory: one Monitor-wrapped environment for worker ``rank``."""
    import torch

    torch.set_num_threads(1)
    cfg = EnvConfig.from_dict(config_dict)
    env: gym.Env[Any, Any] = PropertyMultiSeatEnv(cfg, rank) if multi_seat else PropertySingleAgentEnv(cfg, rank)
    env.reset(seed=base_seed + rank)
    return Monitor(env)


def env_fns(config: EnvConfig, n_envs: int, base_seed: int, multi_seat: bool = False) -> list[Callable[[], Any]]:
    """One picklable thunk per worker."""
    cfg = config.to_dict()
    return [functools.partial(make_env, cfg, rank, base_seed, multi_seat) for rank in range(n_envs)]


def default_start_method() -> str:
    """'spawn' on Windows, 'forkserver' where available, else 'spawn'."""
    if sys.platform == "win32":
        return "spawn"
    return "forkserver" if "forkserver" in multiprocessing.get_all_start_methods() else "spawn"


def make_vec_env(
    config: EnvConfig,
    n_envs: int,
    base_seed: int,
    vec_env: str = "dummy",
    multi_seat: bool = False,
    start_method: str | None = None,
) -> VecEnv:
    """DummyVecEnv (default) or SubprocVecEnv with a platform-appropriate start method."""
    fns = env_fns(config, n_envs, base_seed, multi_seat)
    if vec_env == "subproc":
        venv: VecEnv = SubprocVecEnv(fns, start_method=start_method or default_start_method())
    else:
        venv = DummyVecEnv(fns)
    venv.seed(base_seed)
    return venv
