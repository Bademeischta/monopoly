"""DummyVecEnv and SubprocVecEnv (spawn) with masks; identical trajectories per seed (§6.7, R-25)."""

from __future__ import annotations

import numpy as np
from envhelpers import cfg
from sb3_contrib.common.maskable.utils import get_action_masks, is_masking_supported

from propertyrl.env import make_vec_env


def _rollout(vec_env: str, start_method: str | None = None, steps: int = 150) -> tuple[list, list]:
    venv = make_vec_env(cfg(), 2, base_seed=21, vec_env=vec_env, start_method=start_method)
    try:
        assert is_masking_supported(venv)
        obs = venv.reset()
        observations, rewards = [obs.copy()], []
        for _ in range(steps):
            masks = get_action_masks(venv)
            assert masks.shape == (2, 106)
            actions = np.array([int(np.flatnonzero(m)[0]) for m in masks])
            obs, rew, done, info = venv.step(actions)
            observations.append(obs.copy())
            rewards.append(rew.copy())
        return observations, rewards
    finally:
        venv.close()


def test_dummy_and_subproc_spawn_identical() -> None:
    o1, r1 = _rollout("dummy")
    o2, r2 = _rollout("subproc", "spawn")
    for a, b in zip(o1, o2, strict=True):
        assert np.array_equal(a, b)
    for a, b in zip(r1, r2, strict=True):
        assert np.allclose(a, b)


def test_multiseat_vecenv_masks() -> None:
    venv = make_vec_env(cfg(n_players=3), 2, base_seed=5, multi_seat=True)
    venv.reset()
    for _ in range(50):
        masks = get_action_masks(venv)
        venv.step(np.array([int(np.flatnonzero(m)[0]) for m in masks]))
    venv.close()
