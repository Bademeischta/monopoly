"""Multi-seat environment (§6.10): equivalence with one learning seat and 4P shared-policy behaviour."""

from __future__ import annotations

import numpy as np
from envhelpers import cfg

from propertyrl.env import OpponentConfig, PropertyMultiSeatEnv, PropertySingleAgentEnv


def test_one_learning_seat_equivalent_to_single_env() -> None:
    for n in (2, 4):
        c = cfg(n_players=n, opponents=OpponentConfig(mode="fixed", fixed=("strong_a_v1", "roi_markov_v1")))
        single = PropertySingleAgentEnv(c)
        multi = PropertyMultiSeatEnv(c)
        for seed in (1, 2):
            o1, i1 = single.reset(seed=seed)
            o2, i2 = multi.reset(seed=seed)
            assert np.array_equal(o1, o2) and i1["learning_seat"] == i2["seat"]
            rng = np.random.default_rng(seed)
            while True:
                m1, m2 = single.action_masks(), multi.action_masks()
                assert np.array_equal(m1, m2)
                a = int(rng.choice(np.flatnonzero(m1)))
                o1, r1, t1, u1, inf1 = single.step(a)
                o2, r2, t2, u2, inf2 = multi.step(a)
                closed = inf2["closed"]
                assert r2 == 0.0 and len(closed) == 1
                assert closed[0]["reward"] == r1 and closed[0]["duration"] == inf1["duration"]
                assert (t1, u1) == (t2, u2)
                assert closed[0]["terminated"] == t1 and closed[0]["truncated"] == u1
                if t1 or u1:
                    break
                assert np.array_equal(o1, o2)


def test_four_player_shared_policy_closures() -> None:
    c = cfg(n_players=4, opponents=OpponentConfig(mode="fourp", extra_learning_prob=1.0, epsilon=0.0))
    env = PropertyMultiSeatEnv(c)
    obs, info = env.reset(seed=3)
    assert len(env.core.learning) == 4
    open_seats: set[int] = set()
    seat = info["seat"]
    rng = np.random.default_rng(0)
    episodes = 0
    steps = 0
    while episodes < 3 and steps < 50_000:
        open_seats.add(seat)
        obs, r, term, trunc, info = env.step(int(rng.choice(np.flatnonzero(env.action_masks()))))
        steps += 1
        assert r == 0.0
        for c_ in info["closed"]:
            assert c_["seat"] in open_seats
            open_seats.discard(c_["seat"])
            if c_["truncated"]:
                assert c_["terminal_observation"] is not None
        if term or trunc:
            assert not open_seats
            assert info["seat"] == -1 and "episode_stats" in info
            episodes += 1
            obs, info = env.reset()
            open_seats = set()
        seat = info["seat"]
        if seat >= 0:
            assert seat in env.core.learning
    assert episodes == 3


def test_multi_seat_hooks_and_render() -> None:
    env = PropertyMultiSeatEnv(cfg())
    assert env.render() is None
    env.reset(seed=1)
    assert isinstance(env.render(), str)
    env.set_curriculum_stage(1)
    env.set_opponent_weights({})
    env.reload_opponents({"snapshots": []})
    assert env.action_masks().any()
