"""Compute budget (§7.11): wall-clock watchdog for training runs and run-time estimates."""

from __future__ import annotations

import logging
import time

from stable_baselines3.common.callbacks import BaseCallback

log = logging.getLogger(__name__)


class BudgetCallback(BaseCallback):
    """Stops training cleanly once the wall-clock budget is exceeded (a checkpoint is written by the caller)."""

    def __init__(self, budget_hours: float, verbose: int = 0) -> None:
        super().__init__(verbose)
        self.budget_s = budget_hours * 3600.0
        self.start = time.monotonic()
        self.exceeded = False

    def _on_training_start(self) -> None:
        self.start = time.monotonic()

    def elapsed_hours(self) -> float:
        """Hours since training start."""
        return (time.monotonic() - self.start) / 3600.0

    def _on_step(self) -> bool:
        if time.monotonic() - self.start > self.budget_s:
            if not self.exceeded:
                log.warning("compute budget of %.2f h exceeded; stopping training", self.budget_s / 3600)
            self.exceeded = True
            return False
        return True


def estimate_hours(total_timesteps: int, steps_per_second: float) -> float:
    """Training time estimate from a measured throughput."""
    return total_timesteps / max(steps_per_second, 1e-9) / 3600.0


def eval_hours(n_games: int, games_per_second: float) -> float:
    """Evaluation time estimate from a measured game throughput."""
    return n_games / max(games_per_second, 1e-9) / 3600.0
