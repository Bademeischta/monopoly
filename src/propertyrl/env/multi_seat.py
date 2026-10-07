"""Multi-seat Gymnasium environment for shared-policy MARL with several learning seats per game (§6.10)."""

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


class PropertyMultiSeatEnv(gym.Env[np.ndarray, np.int64]):
    """Every learning seat shares the policy; rewards are reported per seat in ``info["closed"]``.

    ``reward`` is always 0.0. A transition of seat s closes when s reaches its next genuine decision
    (then ``info["seat"] == s``), when s goes bankrupt, or when the game ends or is truncated.
    """

    metadata = {"render_modes": ["ansi"]}

    def __init__(self, config: EnvConfig | dict[str, Any] | None = None, rank: int = 0, render_mode: str | None = None):
        super().__init__()
        if config is None:
            cfg = EnvConfig()
        elif isinstance(config, dict):
            cfg = EnvConfig.from_dict(config)
        else:
            cfg = config
        self.cfg = cfg
        self.rank = rank
        self.render_mode = render_mode
        self.core = DecisionCore(cfg, worker=rank)
        self.observation_space = spaces.Box(0.0, 1.0, (OBS_DIM,), np.float32)
        self.action_space = MaskedDiscrete(A.N_ACTIONS, mask_fn=self._mask_or_none)
        self._seat = -1
        self._started = False

    def _mask_or_none(self) -> np.ndarray | None:
        if not self._started or self.core.current is None:
            return None
        return self.core.legal_mask()

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        closed = self.core.start(seed)
        self._started = True
        seat = self.core.current
        assert seat is not None
        self._seat = seat
        info = {
            "seat": seat,
            "closed": [c.to_dict() for c in closed],
            "game_seed": self.core.game_seed,
            "learning_seats": list(self.core.learning),
            "restarts": self.core.restarts,
        }
        return self.core.observe(seat), info

    def step(self, action: Any) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        acting = self._seat
        closed = self.core.act(int(action))
        info: dict[str, Any] = {
            "closed": [c.to_dict() for c in closed],
            "game_seed": self.core.game_seed,
            "illegal_actions": self.core.illegal_actions,
        }
        if self.core.episode_over:
            truncated = self.core.truncated
            terminated = not truncated
            info["seat"] = -1
            info["episode_stats"] = {s: self.core.episode_info(s) for s in self.core.learning}
            info["opponent_ids"] = dict(self.core.plan.opponent_ids) if self.core.plan else {}
            obs = self.core.observe(acting)
            return obs, 0.0, terminated, truncated, info
        seat = self.core.current
        assert seat is not None
        self._seat = seat
        info["seat"] = seat
        return self.core.observe(seat), 0.0, False, False, info

    def action_masks(self) -> np.ndarray:
        """Legal-action mask of ``info["seat"]``."""
        return self.core.legal_mask()

    def render(self) -> str | None:  # type: ignore[override]
        if self.core.eng is None:
            return None
        return render_text(self.core.engine.state, self.core.board)

    def set_opponent_weights(self, weights: dict[str, float]) -> None:
        """PFSP weights for old snapshots."""
        self.core.sampler.set_weights(weights)

    def reload_opponents(self, manifest: dict[str, Any]) -> None:
        """Reload the snapshot list / latest policy file."""
        self.core.sampler.reload(manifest)

    def set_curriculum_stage(self, stage: int) -> None:
        """Switch the curriculum stage (0-based)."""
        self.core.sampler.set_stage(stage)
