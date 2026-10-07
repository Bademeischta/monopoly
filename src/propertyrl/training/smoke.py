"""Smoke mode (§7.10): reduced sizes for every training, evaluation and analysis command."""

from __future__ import annotations

from typing import Any

from propertyrl.infra.config import SMOKE_LABEL, ExperimentConfig, PPOConfig, SmokeOverrides, load_smoke_overrides

MCR_EXPERIMENT = "mcr_official_2p"
__all__ = ["MCR_EXPERIMENT", "SMOKE_LABEL", "apply_smoke", "smoke_settings"]


def smoke_settings() -> SmokeOverrides:
    """The configured smoke overrides."""
    return load_smoke_overrides()


def apply_smoke(exp: ExperimentConfig, ppo: PPOConfig) -> tuple[ExperimentConfig, PPOConfig]:
    """Return copies of the experiment and PPO config with smoke sizes applied."""
    so = smoke_settings()
    timesteps = so.mcr_timesteps if exp.name == MCR_EXPERIMENT else so.other_timesteps
    ppo2 = ppo.model_copy(
        update={
            "n_envs": so.n_envs,
            "n_steps": so.n_steps,
            "batch_size": so.batch_size,
            "total_timesteps": timesteps,
            "checkpoint_interval": so.checkpoint_interval,
            "select_eval_interval": so.select_eval_interval,
            "select_eval_seeds": so.select_eval_seeds,
            "budget_hours": so.budget_hours,
        }
    )
    stages: list[dict[str, Any]] = []
    for i, stage in enumerate(exp.opponents.curriculum_stages):
        st = dict(stage)
        st["max_steps"] = so.curriculum_thresholds[i] if i < len(so.curriculum_thresholds) else None
        stages.append(st)
    opponents = exp.opponents.model_copy(
        update={
            "curriculum_stages": stages,
            "snapshot_interval": so.selfplay_snapshot_interval,
            "select_mini_seeds": so.select_mini_seeds,
        }
    )
    training = exp.training.model_copy(update={"seeds": exp.training.seeds[: so.training_seeds], "extended_seeds": []})
    update: dict[str, Any] = {"opponents": opponents, "training": training}
    if exp.sweep is not None:
        update["sweep"] = exp.sweep.model_copy(update={"timesteps": so.sweep_timesteps})
    return exp.model_copy(update=update), ppo2
