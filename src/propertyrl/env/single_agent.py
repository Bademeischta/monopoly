"""Gymnasium environment with one learning seat (§6.7)."""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from propertyrl.engine import actions as A
from propertyrl.engine.render_text import render_text
from propertyrl.env.core import DecisionCore, EnvConfig
from propertyrl.env.observation import OBS_DIM
from propertyrl.env.spaces import MaskedDiscrete


class PropertySingleAgentEnv(gym.Env[np.ndarray, np.int64]):
    """One learning seat; opponents and delegated decisions are played inside the environment."""

    metadata = {"render_modes": ["ansi"]}

    def __init__(self, config: EnvConfig | dict[str, Any] | None = None, rank: int = 0, render_mode: str | None = None):
        super().__init__()
        if config is None:
            cfg = EnvConfig()
        elif isinstance(config, dict):
            cfg = EnvConfig.from_dict(config)
        else:
            cfg = config
        if cfg.opponents.mode == "fourp":
            raise ValueError("opponent mode 'fourp' needs PropertyMultiSeatEnv (several learning seats)")
        self.cfg = cfg
        self.rank = rank
        self.render_mode = render_mode
        self.core = DecisionCore(cfg, worker=rank)
        self.observation_space = spaces.Box(0.0, 1.0, (OBS_DIM,), np.float32)
        self.action_space = MaskedDiscrete(A.N_ACTIONS, mask_fn=self._mask_or_none)
        self._seat = 0
        self._started = False

    def _mask_or_none(self) -> np.ndarray | None:
        if not self._started or self.core.current is None:
            return None
        return self.core.legal_mask()

    # ------------------------------------------------------------------ gymnasium API
    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        self.core.start(seed)
        self._started = True
        seat = self.core.current
        assert seat is not None
        self._seat = seat
        info = {
            "game_seed": self.core.game_seed,
            "learning_seat": seat,
            "restarts": self.core.restarts,
            "duration": 0,
            "illegal_actions": 0,
        }
        return self.core.observe(seat), info

    def step(self, action: Any) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        seat = self._seat
        closed = self.core.act(int(action))
        mine = [c for c in closed if c.seat == seat]
        if len(mine) != 1:
            raise RuntimeError(f"expected exactly one closed transition for seat {seat}, got {len(mine)}")
        c = mine[0]
        info: dict[str, Any] = {
            "duration": c.duration,
            "game_seed": self.core.game_seed,
            "learning_seat": seat,
            "illegal_actions": self.core.illegal_actions,
            "restarts": self.core.restarts,
        }
        if c.truncated and c.terminal_observation is not None:
            obs = c.terminal_observation
        else:
            obs = self.core.observe(seat)
        if c.terminated or c.truncated:
            info.update(self.core.episode_info(seat))
        return obs, float(c.reward), bool(c.terminated), bool(c.truncated), info

    def action_masks(self) -> np.ndarray:
        """Legal-action mask of the current decision (bool array of length 106)."""
        return self.core.legal_mask()

    def render(self) -> str | None:  # type: ignore[override]
        if self.core.eng is None:
            return None
        return render_text(self.core.engine.state, self.core.board)

    # ------------------------------------------------------------------ callback hooks
    def set_opponent_weights(self, weights: dict[str, float]) -> None:
        """PFSP weights for old snapshots."""
        self.core.sampler.set_weights(weights)

    def reload_opponents(self, manifest: dict[str, Any]) -> None:
        """Reload the snapshot list / latest policy file."""
        self.core.sampler.reload(manifest)

    def set_curriculum_stage(self, stage: int) -> None:
        """Switch the curriculum stage (0-based)."""
        self.core.sampler.set_stage(stage)

    def get_curriculum_stage(self) -> int:
        """Current curriculum stage."""
        return self.core.sampler.cfg.stage
