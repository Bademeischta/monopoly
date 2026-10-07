"""PettingZoo AEC environment (§6.8): every seat is an agent; delegation and auto-skip inside."""

from __future__ import annotations

from typing import Any

import numpy as np
from gymnasium import spaces
from pettingzoo import AECEnv

from propertyrl.agents.registry import make_policy
from propertyrl.engine import actions as A
from propertyrl.engine.render_text import render_text
from propertyrl.env.core import DecisionCore, EnvConfig
from propertyrl.env.observation import OBS_DIM


class PropertyAECEnv(AECEnv):  # type: ignore[misc]
    """Canonical multi-agent interface: ``player_0`` ... ``player_{n-1}``."""

    metadata = {"render_modes": ["ansi"], "name": "propertyrl_aec_v0", "is_parallelizable": False}

    def __init__(
        self,
        config: EnvConfig | dict[str, Any] | None = None,
        delegations: dict[str, str] | None = None,
        render_mode: str | None = None,
    ) -> None:
        super().__init__()
        if config is None:
            cfg = EnvConfig()
        elif isinstance(config, dict):
            cfg = EnvConfig.from_dict(config)
        else:
            cfg = config
        self.cfg = cfg
        self.render_mode = render_mode
        self.core = DecisionCore(cfg)
        self.core.all_learning = True
        n = cfg.n_players
        self.possible_agents = [f"player_{i}" for i in range(n)]
        self._obs_spaces = {
            a: spaces.Dict(
                {
                    "observation": spaces.Box(0.0, 1.0, (OBS_DIM,), np.float32),
                    "action_mask": spaces.Box(0, 1, (A.N_ACTIONS,), np.int8),
                }
            )
            for a in self.possible_agents
        }
        self._act_spaces = {a: spaces.Discrete(A.N_ACTIONS) for a in self.possible_agents}
        for agent, name in (delegations or {}).items():
            self.core.seat_delegation[self.possible_agents.index(agent)] = make_policy(name)
        self.agents: list[str] = []
        self.rewards: dict[str, float] = {}
        self._cumulative_rewards: dict[str, float] = {}
        self.terminations: dict[str, bool] = {}
        self.truncations: dict[str, bool] = {}
        self.infos: dict[str, dict[str, Any]] = {}
        self.agent_selection = self.possible_agents[0]
        self._skip_agent_selection: str | None = None

    def observation_space(self, agent: str) -> spaces.Space[Any]:
        return self._obs_spaces[agent]

    def action_space(self, agent: str) -> spaces.Space[Any]:
        return self._act_spaces[agent]

    @staticmethod
    def _seat(agent: str) -> int:
        return int(agent.rsplit("_", 1)[1])

    def observe(self, agent: str) -> dict[str, np.ndarray]:
        seat = self._seat(agent)
        mask = np.zeros(A.N_ACTIONS, dtype=np.int8)
        if self.core.current == seat and agent == self.agent_selection:
            mask = self.core.legal_mask().astype(np.int8)
        return {"observation": self.core.observe(seat), "action_mask": mask}

    def reset(self, seed: int | None = None, options: dict[str, Any] | None = None) -> None:
        self.core.start(seed)
        self.agents = list(self.possible_agents)
        self.rewards = {a: 0.0 for a in self.agents}
        self._cumulative_rewards = {a: 0.0 for a in self.agents}
        self.terminations = {a: False for a in self.agents}
        self.truncations = {a: False for a in self.agents}
        self.infos = {a: {} for a in self.agents}
        self._skip_agent_selection = None
        assert self.core.current is not None
        self.agent_selection = self.possible_agents[self.core.current]

    def step(self, action: Any) -> None:
        agent = self.agent_selection
        if self.terminations[agent] or self.truncations[agent]:
            self._was_dead_step(action)
            return
        self._cumulative_rewards[agent] = 0.0
        closed = self.core.act(int(action))
        self.rewards = {a: 0.0 for a in self.agents}
        for c in closed:
            name = self.possible_agents[c.seat]
            if name in self.rewards:
                self.rewards[name] += c.reward
                self.infos[name] = {"duration": c.duration}
        st = self.core.engine.state
        for a in self.agents:
            if st.bankrupt[self._seat(a)]:
                self.terminations[a] = True
        if self.core.episode_over:
            for a in self.agents:
                if self.core.truncated:
                    self.truncations[a] = True
                else:
                    self.terminations[a] = True
        nxt = self.possible_agents[self.core.current] if self.core.current is not None else None
        dead = [a for a in self.agents if self.terminations[a] or self.truncations[a]]
        if dead:
            self._skip_agent_selection = nxt
            self.agent_selection = dead[0]
        elif nxt is not None:
            self.agent_selection = nxt
        self._accumulate_rewards()

    def render(self) -> str | None:
        if self.core.eng is None:
            return None
        return render_text(self.core.engine.state, self.core.board)

    def close(self) -> None:
        """Nothing to release."""
