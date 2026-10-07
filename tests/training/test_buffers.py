"""SMDP and seat-chain rollout buffers against hand computations (§7.1, §7.2)."""

from __future__ import annotations

import numpy as np
import pytest
import torch as th
from gymnasium import spaces
from sb3_contrib.common.maskable.buffers import MaskableRolloutBuffer

from propertyrl.engine import ConfigError
from propertyrl.training.buffers import LAST, NO_NEXT, DurationMaskableRolloutBuffer, SeatChainRolloutBuffer

OBS = spaces.Box(0, 1, (3,), np.float32)
ACT = spaces.Discrete(4)


def _fill(buf, rewards, values, starts, durations=None) -> None:  # type: ignore[no-untyped-def]
    n, e = rewards.shape
    for t in range(n):
        kwargs = {}
        if durations is not None:
            kwargs["durations"] = durations[t]
        buf.add(
            np.zeros((e, 3), np.float32),
            np.zeros((e, 1)),
            rewards[t],
            starts[t],
            th.tensor(values[t]),
            th.zeros(e),
            action_masks=np.ones((e, 4)),
            **kwargs,
        )


def test_smdp_gae_hand_computed() -> None:
    buf = DurationMaskableRolloutBuffer(3, OBS, ACT, "cpu", gae_lambda=0.8, gamma=0.9, n_envs=1)
    rewards = np.array([[1.0], [0.0], [2.0]], np.float32)
    values = np.array([[0.5], [0.4], [0.3]], np.float32)
    starts = np.zeros((3, 1), np.float32)
    _fill(buf, rewards, values, starts, np.array([[1.0], [2.0], [3.0]]))
    buf.compute_returns_and_advantage(th.tensor([0.2]), np.array([False]))
    assert buf.advantages[:, 0] == pytest.approx([1.60813645, 1.0390784, 1.8458], abs=1e-5)
    assert buf.returns[:, 0] == pytest.approx([2.10813645, 1.4390784, 2.1458], abs=1e-5)


def test_smdp_gae_with_episode_end() -> None:
    buf = DurationMaskableRolloutBuffer(3, OBS, ACT, "cpu", gae_lambda=0.8, gamma=0.9, n_envs=1)
    rewards = np.array([[1.0], [0.0], [2.0]], np.float32)
    values = np.array([[0.5], [0.4], [0.3]], np.float32)
    starts = np.array([[0.0], [0.0], [1.0]], np.float32)
    _fill(buf, rewards, values, starts, np.array([[1.0], [2.0], [3.0]]))
    buf.compute_returns_and_advantage(th.tensor([0.2]), np.array([False]))
    assert buf.advantages[1, 0] == pytest.approx(-0.4) and buf.advantages[0, 0] == pytest.approx(0.572)


def test_duration_one_equals_maskable_ppo() -> None:
    rng = np.random.default_rng(0)
    n, e = 16, 3
    rewards = rng.normal(size=(n, e)).astype(np.float32)
    values = rng.normal(size=(n, e)).astype(np.float32)
    starts = (rng.random((n, e)) < 0.2).astype(np.float32)
    ours = DurationMaskableRolloutBuffer(n, OBS, ACT, "cpu", gae_lambda=0.95, gamma=0.99, n_envs=e)
    ref = MaskableRolloutBuffer(n, OBS, ACT, "cpu", gae_lambda=0.95, gamma=0.99, n_envs=e)
    _fill(ours, rewards, values, starts, np.ones((n, e)))
    _fill(ref, rewards, values, starts)
    last = th.tensor(rng.normal(size=e).astype(np.float32))
    dones = np.array([False, True, False])
    ours.compute_returns_and_advantage(last, dones)
    ref.compute_returns_and_advantage(last, dones)
    assert np.allclose(ours.advantages, ref.advantages, atol=1e-6)
    assert np.allclose(ours.returns, ref.returns, atol=1e-6)


def test_seat_chain_single_seat_equals_duration_buffer() -> None:
    rng = np.random.default_rng(1)
    n, e = 20, 2
    rewards = rng.normal(size=(n, e)).astype(np.float32)
    values = rng.normal(size=(n, e)).astype(np.float32)
    durations = rng.integers(1, 5, size=(n, e)).astype(np.float32)
    done = rng.random((n, e)) < 0.15
    starts = np.zeros((n, e), np.float32)
    starts[1:] = done[:-1]
    dur_buf = DurationMaskableRolloutBuffer(n, OBS, ACT, "cpu", gae_lambda=0.9, gamma=0.97, n_envs=e)
    _fill(dur_buf, rewards, values, starts, durations)
    chain = SeatChainRolloutBuffer(n, OBS, ACT, "cpu", gae_lambda=0.9, gamma=0.97, n_envs=e)
    _fill(chain, np.zeros_like(rewards), values, np.zeros_like(starts))
    for t in range(n):
        for j in range(e):
            nxt = NO_NEXT if done[t, j] else (t + 1 if t + 1 < n else LAST)
            chain.close_row(t, j, float(rewards[t, j]), int(durations[t, j]), bool(done[t, j]), nxt)
    last = th.tensor(rng.normal(size=e).astype(np.float32))
    dur_buf.compute_returns_and_advantage(last, done[-1])
    chain.compute_returns_and_advantage(last, done[-1])
    assert np.allclose(chain.advantages, dur_buf.advantages, atol=1e-5)
    assert np.allclose(chain.returns, dur_buf.returns, atol=1e-5)


def test_seat_chain_two_seats_hand_computed() -> None:
    buf = SeatChainRolloutBuffer(4, OBS, ACT, "cpu", gae_lambda=0.8, gamma=0.9, n_envs=1)
    values = np.array([[0.5], [0.6], [0.7], [0.8]], np.float32)
    _fill(buf, np.zeros((4, 1), np.float32), values, np.zeros((4, 1), np.float32))
    buf.close_row(0, 0, 0.1, 2, False, 2)
    buf.close_row(1, 0, -0.2, 1, False, 3)
    buf.close_row(2, 0, 1.0, 1, True, NO_NEXT)
    buf.compute_returns_and_advantage(th.tensor([0.9]), np.array([False]))
    assert buf.advantages[:3, 0] == pytest.approx([0.3614, -0.08, 0.3], abs=1e-6)
    assert buf.returns[:3, 0] == pytest.approx([0.8614, 0.52, 1.0], abs=1e-6)
    assert buf.valid[:, 0].tolist() == [1.0, 1.0, 1.0, 0.0]
    batches = list(buf.get(2))
    assert sum(len(b.actions) for b in batches) == 3 and all(len(b.actions) >= 2 for b in batches)
    assert buf.valid_fraction() == 0.75


def test_gamma_consistency_check() -> None:
    from propertyrl.env import EnvConfig, OpponentConfig, make_vec_env
    from propertyrl.training.smdp_ppo import SMDPMaskablePPO

    venv = make_vec_env(EnvConfig(opponents=OpponentConfig(mode="fixed", fixed=("random_legal",))), 1, 0)
    model = SMDPMaskablePPO("MlpPolicy", venv, n_steps=8, batch_size=8, gamma=0.99, device="cpu")
    model.check_gamma(0.99)
    with pytest.raises(ConfigError):
        model.check_gamma(0.995)
