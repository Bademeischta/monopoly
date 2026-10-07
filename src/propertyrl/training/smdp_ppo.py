"""SMDP-MaskablePPO (§7.1).

``collect_rollouts`` is a copy of the method of sb3-contrib 2.9.0 (``sb3_contrib.ppo_mask.ppo_mask``);
every deviation is marked with ``# SMDP change``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch as th
from gymnasium import spaces
from sb3_contrib import MaskablePPO
from sb3_contrib.common.maskable.buffers import MaskableDictRolloutBuffer, MaskableRolloutBuffer
from sb3_contrib.common.maskable.utils import get_action_masks, is_masking_supported
from stable_baselines3.common.buffers import RolloutBuffer
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.utils import obs_as_tensor
from stable_baselines3.common.vec_env import VecEnv

from propertyrl.engine.errors import ConfigError
from propertyrl.training.buffers import DurationMaskableRolloutBuffer


class SMDPMaskablePPO(MaskablePPO):
    """MaskablePPO whose discounting uses the macro-step duration k of every transition."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("rollout_buffer_class", DurationMaskableRolloutBuffer)
        super().__init__(*args, **kwargs)

    def check_gamma(self, env_gamma: float) -> None:
        """The environment's shaping gamma must equal the algorithm's gamma (§6.6)."""
        if abs(float(env_gamma) - float(self.gamma)) > 1e-12:
            raise ConfigError(f"gamma mismatch: environment {env_gamma} != algorithm {self.gamma}")

    def collect_rollouts(
        self,
        env: VecEnv,
        callback: BaseCallback,
        rollout_buffer: RolloutBuffer,
        n_rollout_steps: int,
        use_masking: bool = True,
    ) -> bool:
        assert isinstance(rollout_buffer, (MaskableRolloutBuffer, MaskableDictRolloutBuffer)), (
            "RolloutBuffer doesn't support action masking"
        )
        assert self._last_obs is not None, "No previous observation was provided"
        self.policy.set_training_mode(False)
        n_steps = 0
        action_masks = None
        rollout_buffer.reset()

        if use_masking and not is_masking_supported(env):
            raise ValueError("Environment does not support action masking. Consider using ActionMasker wrapper")

        callback.on_rollout_start()

        while n_steps < n_rollout_steps:
            with th.no_grad():
                obs_tensor = obs_as_tensor(self._last_obs, self.device)  # type: ignore[arg-type]
                if use_masking:
                    action_masks = get_action_masks(env)
                actions, values, log_probs = self.policy(obs_tensor, action_masks=action_masks)

            actions = actions.cpu().numpy()
            new_obs, rewards, dones, infos = env.step(actions)
            # SMDP change: duration k of every transition (1 when the env reports none).
            durations = np.array([float(info.get("duration", 1) or 1) for info in infos], dtype=np.float32)

            self.num_timesteps += env.num_envs

            callback.update_locals(locals())
            if not callback.on_step():
                return False

            self._update_info_buffer(infos, dones)
            n_steps += 1

            if isinstance(self.action_space, spaces.Discrete):
                actions = actions.reshape(-1, 1)

            for idx, done in enumerate(dones):
                if (
                    done
                    and infos[idx].get("terminal_observation") is not None
                    and infos[idx].get("TimeLimit.truncated", False)
                ):
                    terminal_obs = self.policy.obs_to_tensor(infos[idx]["terminal_observation"])[0]
                    with th.no_grad():
                        terminal_value = self.policy.predict_values(terminal_obs)[0]
                    # SMDP change: bootstrap with gamma**k instead of gamma.
                    rewards[idx] += (self.gamma ** durations[idx]) * terminal_value

            # SMDP change: durations are stored alongside every step.
            if isinstance(rollout_buffer, DurationMaskableRolloutBuffer):
                rollout_buffer.add(
                    self._last_obs,
                    actions,
                    rewards,
                    self._last_episode_starts,
                    values,
                    log_probs,
                    action_masks=action_masks,
                    durations=durations,
                )
            else:
                rollout_buffer.add(
                    self._last_obs,  # type: ignore[arg-type]
                    actions,
                    rewards,
                    self._last_episode_starts,  # type: ignore[arg-type]
                    values,
                    log_probs,
                    action_masks=action_masks,
                )
            self._last_obs = new_obs  # type: ignore[assignment]
            self._last_episode_starts = dones

        with th.no_grad():
            values = self.policy.predict_values(obs_as_tensor(new_obs, self.device))  # type: ignore[arg-type]

        rollout_buffer.compute_returns_and_advantage(last_values=values, dones=dones)

        callback.on_rollout_end()

        return True
