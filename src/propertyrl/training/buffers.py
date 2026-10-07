"""Rollout buffers with SMDP durations (§7.1) and per-seat transition chains (§7.2)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import numpy as np
import torch as th
from sb3_contrib.common.maskable.buffers import MaskableRolloutBuffer, MaskableRolloutBufferSamples

LAST = -2
NO_NEXT = -1


class DurationMaskableRolloutBuffer(MaskableRolloutBuffer):
    """MaskableRolloutBuffer that discounts each transition with gamma**k (k = duration)."""

    durations: np.ndarray

    def reset(self) -> None:
        super().reset()
        self.durations = np.ones((self.buffer_size, self.n_envs), dtype=np.float32)

    def add(self, *args: Any, durations: np.ndarray | None = None, **kwargs: Any) -> None:  # type: ignore[override]
        """Store a step; ``durations`` (shape [n_envs]) defaults to 1."""
        if durations is not None:
            self.durations[self.pos] = np.asarray(durations, dtype=np.float32).reshape(self.n_envs)
        super().add(*args, **kwargs)

    def compute_returns_and_advantage(self, last_values: th.Tensor, dones: np.ndarray) -> None:
        """GAE with SMDP discounting.

        delta_t = r_t + gamma**k_t * V(s_{t+1}) * (1 - done_t) - V(s_t)
        A_t = delta_t + gamma**k_t * lambda * (1 - done_t) * A_{t+1}
        """
        last = last_values.clone().cpu().numpy().flatten()
        last_gae_lam = np.zeros(self.n_envs, dtype=np.float32)
        for step in reversed(range(self.buffer_size)):
            if step == self.buffer_size - 1:
                next_non_terminal = 1.0 - dones.astype(np.float32)
                next_values = last
            else:
                next_non_terminal = 1.0 - self.episode_starts[step + 1]
                next_values = self.values[step + 1]
            disc = np.power(self.gamma, self.durations[step])
            delta = self.rewards[step] + disc * next_values * next_non_terminal - self.values[step]
            last_gae_lam = delta + disc * self.gae_lambda * next_non_terminal * last_gae_lam
            self.advantages[step] = last_gae_lam
        self.returns = self.advantages + self.values


class SeatChainRolloutBuffer(DurationMaskableRolloutBuffer):
    """Buffer for several learning seats per env column (shared-policy MARL).

    Every env column yields one row per step; ``next_row[t, e]`` points to the row holding the next
    genuine decision of the same seat (``LAST`` = bootstrap with the last observation's value,
    ``NO_NEXT`` = none). Rows whose transition is still open at the end of the rollout are invalid.
    """

    seats: np.ndarray
    next_row: np.ndarray
    valid: np.ndarray
    row_dones: np.ndarray

    def reset(self) -> None:
        super().reset()
        shape = (self.buffer_size, self.n_envs)
        self.seats = np.full(shape, -1, dtype=np.int64)
        self.next_row = np.full(shape, NO_NEXT, dtype=np.int64)
        self.valid = np.zeros(shape, dtype=np.float32)
        self.row_dones = np.zeros(shape, dtype=np.float32)

    def close_row(self, row: int, env: int, reward: float, duration: int, done: bool, next_row: int) -> None:
        """Fill a row once its transition closed."""
        self.rewards[row, env] = reward
        self.durations[row, env] = duration
        self.row_dones[row, env] = 1.0 if done else 0.0
        self.next_row[row, env] = next_row
        self.valid[row, env] = 1.0

    def compute_returns_and_advantage(self, last_values: th.Tensor, dones: np.ndarray) -> None:
        """Backward GAE per column following each seat's chain of rows."""
        last = last_values.clone().cpu().numpy().flatten()
        adv = np.zeros((self.buffer_size, self.n_envs), dtype=np.float32)
        for e in range(self.n_envs):
            for t in reversed(range(self.buffer_size)):
                if not self.valid[t, e]:
                    continue
                nr = int(self.next_row[t, e])
                if nr == LAST:
                    v_next, a_next = float(last[e]), 0.0
                elif nr == NO_NEXT:
                    v_next, a_next = 0.0, 0.0
                else:
                    v_next = float(self.values[nr, e])
                    a_next = float(adv[nr, e]) if self.valid[nr, e] else 0.0
                not_done = 1.0 - float(self.row_dones[t, e])
                disc = float(self.gamma) ** float(self.durations[t, e])
                delta = float(self.rewards[t, e]) + disc * v_next * not_done - float(self.values[t, e])
                adv[t, e] = delta + disc * self.gae_lambda * not_done * a_next
        self.advantages = adv
        self.returns = self.advantages + self.values

    def get(self, batch_size: int | None = None) -> Generator[MaskableRolloutBufferSamples, None, None]:  # type: ignore[override]
        """Minibatches over valid rows only (tails smaller than 2 are merged into the previous batch)."""
        assert self.full, ""
        valid_flat = self.swap_and_flatten(self.valid.reshape(self.buffer_size, self.n_envs, 1)).reshape(-1)
        indices = np.flatnonzero(valid_flat > 0.5)
        indices = np.random.permutation(indices)
        if not self.generator_ready:
            for tensor in ("observations", "actions", "values", "log_probs", "advantages", "returns", "action_masks"):
                self.__dict__[tensor] = self.swap_and_flatten(self.__dict__[tensor])
            self.generator_ready = True
        total = len(indices)
        if total == 0:
            return
        if batch_size is None:
            batch_size = total
        start = 0
        while start < total:
            end = start + batch_size
            if total - end < 2:
                end = total
            yield self._get_samples(indices[start:end])
            start = end

    def valid_fraction(self) -> float:
        """Share of rows that entered the loss."""
        return float(self.valid.mean())
