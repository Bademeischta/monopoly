"""Optional Weights & Biases logging (§9.3, §14): off by default, only with ``--wandb``, technical metrics only.

The run is started in offline mode unless the user explicitly sets ``WANDB_MODE`` (for example to
``online``); nothing is sent anywhere without that explicit choice.
"""

from __future__ import annotations

import os
from typing import Any

from stable_baselines3.common.callbacks import BaseCallback

from propertyrl.engine.errors import ConfigError

#: Only scalar keys with these prefixes are forwarded (training diagnostics and game statistics).
TECHNICAL_PREFIXES = ("train/", "rollout/", "propertyrl/", "time/")


class WandbCallback(BaseCallback):
    """Forwards the SB3 logger's technical scalars to W&B at the end of every rollout."""

    def __init__(self, run_id: str, experiment: str, config: dict[str, Any], directory: str) -> None:
        super().__init__()
        try:
            import wandb
        except ImportError as exc:  # optional extra
            raise ConfigError("--wandb requires the optional extra: pip install -e .[wandb]") from exc
        self._wandb = wandb
        self._run = wandb.init(
            project="propertyrl",
            name=run_id,
            group=experiment,
            dir=directory,
            mode=os.environ.get("WANDB_MODE", "offline"),
            config=config,
        )

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> None:
        values = {
            k: float(v)
            for k, v in self.logger.name_to_value.items()
            if k.startswith(TECHNICAL_PREFIXES) and isinstance(v, (int, float))
        }
        if values:
            self._wandb.log(values, step=int(self.num_timesteps))

    def _on_training_end(self) -> None:
        self._run.finish()
