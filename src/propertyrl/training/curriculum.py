"""Curriculum controller (§6.9): random_legal -> roi_markov_v1 -> strong_a_v1/strong_b_v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CurriculumController:
    """Advances a stage when the SELECT-mini win rate reaches the threshold or the step budget is used."""

    stages: list[dict[str, Any]]
    stage: int = 0
    stage_start_step: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def opponents(self) -> list[str]:
        """Opponent pool of the current stage."""
        return list(self.stages[self.stage]["opponents"])

    @property
    def final(self) -> bool:
        """True in the last stage."""
        return self.stage >= len(self.stages) - 1

    def update(self, step: int, win_rate: float | None) -> bool:
        """Check the stage criteria at a checkpoint; returns True if the stage changed."""
        if self.final:
            return False
        cfg = self.stages[self.stage]
        threshold = cfg.get("threshold")
        max_steps = cfg.get("max_steps")
        reached = threshold is not None and win_rate is not None and win_rate >= float(threshold)
        exhausted = max_steps is not None and step - self.stage_start_step >= int(max_steps)
        if reached or exhausted:
            self.history.append(
                {"from": self.stage, "step": step, "win_rate": win_rate, "reason": "threshold" if reached else "steps"}
            )
            self.stage += 1
            self.stage_start_step = step
            return True
        return False

    def state(self) -> dict[str, Any]:
        """Serialisable state (resume)."""
        return {"stage": self.stage, "stage_start_step": self.stage_start_step, "history": list(self.history)}

    def load(self, state: dict[str, Any]) -> None:
        """Restore from :meth:`state`."""
        self.stage = int(state.get("stage", 0))
        self.stage_start_step = int(state.get("stage_start_step", 0))
        self.history = list(state.get("history", []))
