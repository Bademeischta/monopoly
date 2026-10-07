"""API conformance: gymnasium and SB3 check_env, PettingZoo api_test, spaces, schema, determinism (§6, G2)."""

from __future__ import annotations

import pickle
import warnings

import numpy as np
import pytest
from envhelpers import cfg
from helpers import REPO

from propertyrl.env import (
    OBS_DIM,
    OBS_VERSION,
    MaskedDiscrete,
    PropertyAECEnv,
    PropertyMultiSeatEnv,
    PropertySingleAgentEnv,
    obs_schema,
)


def test_gymnasium_check_env() -> None:
    from gymnasium.utils.env_checker import check_env

    env = PropertySingleAgentEnv(cfg())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        check_env(env, skip_render_check=True)


def test_sb3_check_env() -> None:
    from stable_baselines3.common.env_checker import check_env

    env = PropertySingleAgentEnv(cfg())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        check_env(env, warn=True)
    ms = PropertyMultiSeatEnv(cfg())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        check_env(ms, warn=True)


@pytest.mark.parametrize("n", [2, 4])
def test_pettingzoo_api(n: int) -> None:
    from pettingzoo.test import api_test

    env = PropertyAECEnv(cfg(n_players=n))
    api_test(env, num_cycles=1000, verbose_progress=False)


def test_aec_spaces_cached_and_render() -> None:
    env = PropertyAECEnv(cfg(n_players=3))
    a = env.possible_agents[1]
    assert env.observation_space(a) is env.observation_space(a)
    assert env.action_space(a) is env.action_space(a)
    env.reset(seed=3)
    assert "Sitz" in env.render()  # type: ignore[operator]
    obs = env.observe(env.agent_selection)
    assert obs["action_mask"].sum() >= 1 and obs["observation"].shape == (OBS_DIM,)


def test_aec_full_game_with_dead_steps() -> None:
    env = PropertyAECEnv(cfg(n_players=4, safety_horizon_rounds=400), delegations={"player_0": "delegation_v1"})
    env.reset(seed=5)
    rng = np.random.default_rng(0)
    steps = 0
    while env.agents and steps < 200_000:
        obs, reward, term, trunc, info = env.last()
        if term or trunc:
            env.step(None)
        else:
            legal = np.flatnonzero(obs["action_mask"])
            env.step(int(rng.choice(legal)))
        steps += 1
    assert not env.agents


def test_observation_dimension_and_schema() -> None:
    assert OBS_DIM == 517
    schema = obs_schema()
    assert schema[0]["start"] == 0 and schema[-1]["stop"] == OBS_DIM
    for a, b in zip(schema, schema[1:]):
        assert a["stop"] == b["start"]
    assert OBS_VERSION.startswith("o1.0+")
    doc = (REPO / "docs" / "OBSERVATION_SCHEMA.md").read_text(encoding="utf-8")
    assert OBS_VERSION in doc, "regenerate docs with python tools/gen_docs.py"


def test_masked_discrete_samples_legal_and_pickles() -> None:
    env = PropertySingleAgentEnv(cfg())
    env.reset(seed=11)
    for _ in range(300):
        a = env.action_space.sample()
        assert env.action_masks()[a]
        _, _, term, trunc, _ = env.step(a)
        if term or trunc:
            env.reset()
    space = pickle.loads(pickle.dumps(env.action_space))
    assert isinstance(space, MaskedDiscrete) and space._mask_fn is None
    assert 0 <= space.sample() < 106
    mask = np.zeros(106, dtype=np.int8)
    mask[7] = 1
    assert space.sample(mask=mask) == 7
    assert "MaskedDiscrete" in repr(space)


def test_observations_bounded_and_finite() -> None:
    env = PropertySingleAgentEnv(cfg(n_players=3))
    obs, _ = env.reset(seed=2)
    for _ in range(2000):
        assert obs.dtype == np.float32 and np.isfinite(obs).all() and obs.min() >= 0.0 and obs.max() <= 1.0
        obs, _, term, trunc, _ = env.step(env.action_space.sample())
        if term or trunc:
            obs, _ = env.reset()


def test_reset_seed_deterministic() -> None:
    a = PropertySingleAgentEnv(cfg(n_players=3))
    b = PropertySingleAgentEnv(cfg(n_players=3))
    oa, ia = a.reset(seed=77)
    ob, ib = b.reset(seed=77)
    assert np.array_equal(oa, ob)
    assert ia["game_seed"] == ib["game_seed"] and ia["learning_seat"] == ib["learning_seat"]
    assert a.core.plan.opponents == b.core.plan.opponents  # type: ignore[union-attr]
    oc, ic = a.reset(seed=78)
    assert ic["game_seed"] != ia["game_seed"]


def test_render_and_hooks() -> None:
    env = PropertySingleAgentEnv(cfg(opponents=None))
    assert env.render() is None
    env.reset(seed=1)
    assert isinstance(env.render(), str)
    env.set_curriculum_stage(2)
    assert env.get_curriculum_stage() == 2  # fixed mode keeps the stage but ignores it when sampling
    env.set_opponent_weights({"x": 0.5})
    env.reload_opponents({"snapshots": [], "latest_path": None})
    with pytest.raises(ValueError):
        from propertyrl.env import OpponentConfig

        PropertySingleAgentEnv(cfg(n_players=4, opponents=OpponentConfig(mode="fourp")))
