"""Multi-seat collector (§7.2): several learning seats per game share one policy.

Every env column yields one row per step; rewards, durations and successors arrive later through
``info["closed"]``. Rows still open at the end of a rollout are excluded from the loss.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch as th
from gymnasium import spaces
from sb3_contrib.common.maskable.utils import get_action_masks, is_masking_supported
from stable_baselines3.common.buffers import RolloutBuffer
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.utils import explained_variance, obs_as_tensor
from stable_baselines3.common.vec_env import VecEnv

from propertyrl.training.buffers import LAST, NO_NEXT, SeatChainRolloutBuffer
from propertyrl.training.smdp_ppo import SMDPMaskablePPO


class MultiSeatSMDPMaskablePPO(SMDPMaskablePPO):
    """Shared-policy MARL with individual rewards per learning seat (parameter sharing)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("rollout_buffer_class", SeatChainRolloutBuffer)
        super().__init__(*args, **kwargs)
        self._last_seats: np.ndarray | None = None

    def _reset_seats(self, env: VecEnv) -> np.ndarray:
        infos = getattr(env, "reset_infos", None) or [{} for _ in range(env.num_envs)]
        return np.array([int(info.get("seat", -1)) for info in infos], dtype=np.int64)

    def _setup_learn(self, *args: Any, **kwargs: Any) -> Any:
        out = super()._setup_learn(*args, **kwargs)
        assert self.env is not None
        self._last_seats = self._reset_seats(self.env)
        return out

    def collect_rollouts(  # noqa: C901
        self,
        env: VecEnv,
        callback: BaseCallback,
        rollout_buffer: RolloutBuffer,
        n_rollout_steps: int,
        use_masking: bool = True,
    ) -> bool:
        assert isinstance(rollout_buffer, SeatChainRolloutBuffer), "MultiSeat PPO needs a SeatChainRolloutBuffer"
        assert self._last_obs is not None, "No previous observation was provided"
        if use_masking and not is_masking_supported(env):
            raise ValueError("Environment does not support action masking")
        if self._last_seats is None:
            self._last_seats = self._reset_seats(env)
        self.policy.set_training_mode(False)
        rollout_buffer.reset()
        callback.on_rollout_start()
        n_envs = env.num_envs
        open_rows: list[dict[int, int]] = [{} for _ in range(n_envs)]
        zeros = np.zeros(n_envs, dtype=np.float32)
        new_obs: Any = self._last_obs
        dones = np.zeros(n_envs, dtype=bool)
        for t in range(n_rollout_steps):
            with th.no_grad():
                obs_tensor = obs_as_tensor(self._last_obs, self.device)  # type: ignore[arg-type]
                action_masks = get_action_masks(env) if use_masking else None
                actions, values, log_probs = self.policy(obs_tensor, action_masks=action_masks)
            actions = actions.cpu().numpy()
            new_obs, _rewards, dones, infos = env.step(actions)
            self.num_timesteps += n_envs
            callback.update_locals(locals())
            if not callback.on_step():
                return False
            self._update_info_buffer(infos, dones)
            stored_actions = actions.reshape(-1, 1) if isinstance(self.action_space, spaces.Discrete) else actions
            rollout_buffer.add(
                self._last_obs, stored_actions, zeros, zeros, values, log_probs, action_masks=action_masks
            )
            for e in range(n_envs):
                acting = int(self._last_seats[e])
                rollout_buffer.seats[t, e] = acting
                open_rows[e][acting] = t
                info = infos[e]
                new_seat = int(info.get("seat", -1))
                for c in info.get("closed", []):
                    row = open_rows[e].pop(int(c["seat"]), None)
                    if row is None:
                        continue  # opened in an earlier rollout: dropped
                    reward = float(c["reward"])
                    duration = int(c["duration"])
                    if c["truncated"] and c.get("terminal_observation") is not None:
                        term_obs = self.policy.obs_to_tensor(c["terminal_observation"])[0]
                        with th.no_grad():
                            term_value = float(self.policy.predict_values(term_obs)[0])
                        reward += float(self.gamma) ** duration * term_value
                    done = bool(c["terminated"] or c["truncated"])
                    if not done and int(c["seat"]) == new_seat and not dones[e]:
                        nxt = t + 1 if t + 1 < n_rollout_steps else LAST
                    else:
                        nxt = NO_NEXT
                    rollout_buffer.close_row(row, e, reward, duration, done, nxt)
                if dones[e]:
                    open_rows[e].clear()
                    reset_infos = getattr(env, "reset_infos", None)
                    new_seat = int(reset_infos[e].get("seat", -1)) if reset_infos else -1
                self._last_seats[e] = new_seat
            self._last_obs = new_obs
            self._last_episode_starts = dones
        with th.no_grad():
            last_values = self.policy.predict_values(obs_as_tensor(new_obs, self.device))  # type: ignore[arg-type]
        rollout_buffer.compute_returns_and_advantage(last_values=last_values, dones=dones)
        callback.on_rollout_end()
        return True

    def train(self) -> None:
        """PPO update on valid rows; explained variance recomputed on valid rows only."""
        super().train()
        buf = self.rollout_buffer
        if isinstance(buf, SeatChainRolloutBuffer):
            valid = buf.swap_and_flatten(buf.valid.reshape(buf.buffer_size, buf.n_envs, 1)).reshape(-1) > 0.5
            if valid.any():
                ev = explained_variance(buf.values.flatten()[valid], buf.returns.flatten()[valid])
                self.logger.record("train/explained_variance", ev)
            self.logger.record("train/valid_row_fraction", buf.valid_fraction())
