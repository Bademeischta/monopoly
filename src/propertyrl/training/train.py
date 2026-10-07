"""Training entry point: resolve configs, build envs/model/callbacks, run, checkpoint and resume (§7)."""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from stable_baselines3.common.callbacks import CallbackList
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.common.utils import set_random_seed

from propertyrl.engine import constants as C
from propertyrl.engine.errors import ConfigError
from propertyrl.engine.rng import u64
from propertyrl.env.core import EnvConfig
from propertyrl.env.factory import make_vec_env
from propertyrl.env.opponents import OpponentConfig
from propertyrl.infra.config import (
    ExperimentConfig,
    PPOConfig,
    config_hash,
    load_experiment,
    load_ppo_config,
    load_ruleset,
    read_frozen,
)
from propertyrl.infra.logging_setup import setup_logging
from propertyrl.infra.runmeta import build_run_meta, finish_run_meta, load_run_meta, new_run_id, run_dir, save_run_meta
from propertyrl.infra.storage import query, runs_dir
from propertyrl.training.budget import BudgetCallback
from propertyrl.training.callbacks import (
    CheckpointEvalCallback,
    ExplainedVarianceWarning,
    LatestSyncCallback,
    MetricsCallback,
    PFSPCallback,
    RunContext,
    copy_checkpoint,
    save_checkpoint,
)
from propertyrl.training.curriculum import CurriculumController
from propertyrl.training.multiseat_ppo import MultiSeatSMDPMaskablePPO
from propertyrl.training.selfplay import SnapshotPool
from propertyrl.training.smdp_ppo import SMDPMaskablePPO
from propertyrl.training.smoke import apply_smoke

log = logging.getLogger(__name__)


class LayerNormExtractor(BaseFeaturesExtractor):
    """Optional LayerNorm on the observation (ppo layer_norm option)."""

    def __init__(self, observation_space: Any) -> None:
        dim = int(np.prod(observation_space.shape))
        super().__init__(observation_space, features_dim=dim)
        self.norm = torch.nn.LayerNorm(dim)

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        return self.norm(observations)


# ---------------------------------------------------------------------------- configuration
def frozen_gamma(default: float) -> float:
    """gamma from artifacts/frozen/gamma.json (written by the sweep), else the default."""
    data = read_frozen("gamma")
    return float(data["gamma"]) if data and "gamma" in data else float(default)


def resolve(
    experiment: str | ExperimentConfig,
    seed: int,
    smoke: bool = False,
    gamma: float | None = None,
    timesteps: int | None = None,
) -> tuple[ExperimentConfig, PPOConfig, EnvConfig]:
    """Fully resolved experiment, PPO and environment configuration of one run."""
    exp = load_experiment(experiment) if isinstance(experiment, str) else experiment
    ppo = load_ppo_config()
    if exp.training.ppo_overrides:
        ppo = ppo.model_copy(update=exp.training.ppo_overrides)
    if smoke:
        exp, ppo = apply_smoke(exp, ppo)
    g = gamma if gamma is not None else (frozen_gamma(ppo.gamma) if exp.env.gamma == "frozen" else float(exp.env.gamma))
    upd: dict[str, Any] = {"gamma": g, "n_envs": max(1, min(ppo.n_envs, os.cpu_count() or 1))}
    if timesteps is not None:
        upd["total_timesteps"] = int(timesteps)
    ppo = ppo.model_copy(update=upd)
    rules = load_ruleset(exp.env.ruleset, _n_players=exp.env.n_players)
    horizon = rules.safety_horizon_rounds if exp.env.safety_horizon_rounds == "frozen" else int(
        exp.env.safety_horizon_rounds)  # fmt: skip
    max_rounds = None
    if exp.env.max_rounds == "frozen":
        max_rounds = rules.max_rounds
    elif isinstance(exp.env.max_rounds, int):
        max_rounds = exp.env.max_rounds
    o = exp.opponents
    stages = tuple(tuple(st["opponents"]) for st in o.curriculum_stages)
    opp = OpponentConfig(
        mode=o.mode,
        fixed=tuple(o.fixed),
        stages=stages,
        stage=0,
        epsilon=o.epsilon_train,
        shared_delegation=o.shared_delegation,
        baselines=tuple(o.baselines),
        recent=o.recent_snapshots,
        p_recent=o.p_recent,
        p_old=o.p_old,
        p_baseline=o.p_baseline,
        extra_learning_prob=o.extra_learning_seat_prob,
    )
    env = EnvConfig(
        ruleset=exp.env.ruleset,
        n_players=exp.env.n_players,
        reward_variant=exp.env.reward_variant,
        gamma=g,
        beta=exp.env.beta,
        beta2=exp.env.beta2,
        kingmaking_malus=exp.env.kingmaking_malus,
        terminal_rewards_4p=tuple(exp.env.terminal_rewards_4p),
        auto_skip=exp.env.auto_skip,
        smdp=exp.env.smdp,
        delegation=exp.env.delegation,
        delegated_kinds=tuple(exp.env.delegated_kinds),
        trade_enabled=exp.env.trade_enabled,
        safety_horizon_rounds=horizon,
        max_rounds=max_rounds,
        opponents=opp,
    )
    return exp, ppo, env


def policy_kwargs(ppo: PPOConfig) -> dict[str, Any]:
    """Network architecture of the MLP policy."""
    kwargs: dict[str, Any] = {
        "net_arch": {"pi": list(ppo.net_arch_pi), "vf": list(ppo.net_arch_vf)},
        "activation_fn": torch.nn.ReLU if ppo.activation == "relu" else torch.nn.Tanh,
        "ortho_init": ppo.ortho_init,
    }
    if ppo.layer_norm:
        kwargs["features_extractor_class"] = LayerNormExtractor
    return kwargs


def device_of(ppo: PPOConfig) -> str:
    """'cpu' by default; 'auto' picks CUDA only when available and explicitly configured."""
    if ppo.device == "cpu":
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def seed_everything(seed: int) -> None:
    """Python random, numpy, torch and SB3 seeds (§7.4)."""
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    set_random_seed(seed)


def env_base_seed(seed: int) -> int:
    """Worker seed base derived from the training seed."""
    return int(u64(seed, C.STREAM_TRAIN, 0) % 1_000_000_000)


def find_checkpoint(experiment: str, seed: int | None, smoke: bool, kind: str = "best_select") -> Path | None:
    """Most recent checkpoint of a finished run of ``experiment`` (same seed preferred)."""
    rows = query("SELECT run_id, run_json FROM runs WHERE experiment = ? ORDER BY started DESC", (experiment,))
    import json

    candidates = []
    for run_id, run_json in rows:
        meta = json.loads(run_json)
        if bool(meta.get("smoke")) != smoke:
            continue
        candidates.append((meta.get("training_seed") == seed, run_id))
    candidates.sort(key=lambda x: not x[0])
    for _, run_id in candidates:
        base = runs_dir() / run_id
        for name in (f"{kind}.zip", "final.zip"):
            if (base / name).exists():
                return base / name
    return None


# ---------------------------------------------------------------------------- run
def train(
    experiment: str,
    seed: int,
    smoke: bool = False,
    resume: Path | None = None,
    gamma: float | None = None,
    timesteps: int | None = None,
    run_tag: str = "",
) -> dict[str, Any]:
    """Train one run of an experiment and return a summary dict."""
    if resume is not None:
        meta = load_run_meta(resume)
        experiment = meta["experiment"]
        seed = int(meta["training_seed"])
        smoke = bool(meta["smoke"])
        gamma = meta.get("gamma")
        timesteps = int(meta["total_timesteps"])
    exp, ppo, env_cfg = resolve(experiment, seed, smoke, gamma, timesteps)
    if exp.mode == "sweep":
        raise ConfigError("use 'propertyrl sweep-gamma' for the gamma sweep experiment")
    multi = exp.training.algorithm == "multiseat_ppo"
    seed_everything(seed)
    full_cfg = {"experiment": exp.model_dump(mode="json"), "ppo": ppo.model_dump(mode="json"),
                "env": env_cfg.to_dict()}  # fmt: skip
    if resume is not None:
        run_id = meta["run_id"]
        rdir = run_dir(run_id)
        meta["status"] = "running"
    else:
        run_id = new_run_id(experiment + (f"_{run_tag}" if run_tag else ""), seed, smoke)
        rdir = run_dir(run_id)
        meta = build_run_meta(
            run_id, experiment, env_cfg.ruleset, config_hash(full_cfg), seed, ppo.total_timesteps, ppo.budget_hours,
            smoke, extra={"gamma": ppo.gamma, "config": full_cfg, "label": exp.label},
        )  # fmt: skip
    save_run_meta(meta)
    setup_logging(log_file=rdir / "train.log")
    ctx = RunContext(run_id, rdir, exp, ppo, env_cfg, seed, smoke)
    if exp.opponents.mode == "curriculum":
        ctx.curriculum = CurriculumController([dict(s) for s in exp.opponents.curriculum_stages])
    if exp.opponents.mode in ("selfplay", "fourp"):
        ctx.pool = SnapshotPool(exp.opponents.pool_max)
    if resume is not None:
        ctx.load_state()
    if ctx.curriculum is not None:
        env_cfg.opponents.stage = ctx.curriculum.stage
    if ctx.pool is not None:
        env_cfg.opponents.snapshots = tuple(ctx.pool.paths)
    venv = make_vec_env(env_cfg, ppo.n_envs, env_base_seed(seed), ppo.vec_env, multi_seat=multi)
    algo: type[SMDPMaskablePPO] = MultiSeatSMDPMaskablePPO if multi else SMDPMaskablePPO
    tb = str(rdir / "tb")
    kwargs = dict(
        n_steps=ppo.n_steps, batch_size=ppo.batch_size, n_epochs=ppo.n_epochs, learning_rate=ppo.learning_rate,
        gamma=ppo.gamma, gae_lambda=ppo.gae_lambda, clip_range=ppo.clip_range, ent_coef=ppo.ent_coef,
        vf_coef=ppo.vf_coef, max_grad_norm=ppo.max_grad_norm, device=device_of(ppo), seed=seed, verbose=0,
        tensorboard_log=tb,
    )  # fmt: skip
    if resume is not None:
        last = Path(ctx.checkpoints[-1]) if ctx.checkpoints else rdir / "final.zip"
        from propertyrl.agents.sb3_agent import read_metadata

        read_metadata(last)
        model = algo.load(str(last), env=venv, device=device_of(ppo), tensorboard_log=tb)
    else:
        model = algo("MlpPolicy", venv, policy_kwargs=policy_kwargs(ppo), **kwargs)
        if exp.training.init_from:
            src = find_checkpoint(exp.training.init_from, seed, smoke)
            if src is None:
                raise ConfigError(f"no checkpoint of {exp.training.init_from} found to start {experiment}")
            from propertyrl.agents.sb3_agent import read_metadata

            read_metadata(src)
            loaded = SMDPMaskablePPO.load(str(src), device="cpu")
            model.policy.load_state_dict(loaded.policy.state_dict())
            meta["init_from"] = str(src)
            if ctx.pool is not None and exp.mode == "selfplay":
                first = save_checkpoint(model, ctx, rdir / "snapshots" / "snap_0000000000.zip", "snapshot")
                ctx.pool.add(str(first))
                ctx.champion = f"sb3:{first}"
                copy_checkpoint(first, rdir / "champion.zip")
                venv.env_method("reload_opponents", {"snapshots": list(ctx.pool.paths)})
    model.check_gamma(env_cfg.gamma)
    budget = BudgetCallback(ppo.budget_hours)
    callbacks = [MetricsCallback(ctx), CheckpointEvalCallback(ctx), budget,
                 ExplainedVarianceWarning(ctx, ppo.total_timesteps)]  # fmt: skip
    if exp.opponents.mode in ("selfplay", "fourp", "fourp_fallback"):
        callbacks.append(PFSPCallback(ctx))
    if exp.opponents.mode == "fourp_fallback":
        latest = save_checkpoint(model, ctx, rdir / "latest.zip", "latest")
        venv.env_method("reload_opponents", {"latest_path": str(latest)})
        callbacks.append(LatestSyncCallback(ctx))
    status = "completed"
    try:
        model.learn(
            total_timesteps=ppo.total_timesteps,
            callback=CallbackList(callbacks),
            reset_num_timesteps=resume is None,
            tb_log_name="ppo",
        )
        if budget.exceeded:
            status = "budget_stopped"
    except KeyboardInterrupt:
        status = "interrupted"
        raise
    finally:
        final = save_checkpoint(model, ctx, rdir / "final.zip", "final")
        if ctx.best_select_path is None:
            copy_checkpoint(final, rdir / "best_select.zip")
            ctx.best_select_path = str(rdir / "best_select.zip")
        ctx.save_state()
        venv.close()
        finish_run_meta(
            meta, status, timesteps_done=int(model.num_timesteps), warnings=ctx.warnings,
            best_select=ctx.best_select, best_select_path=ctx.best_select_path, eval_games=ctx.eval_games,
            training_hours=budget.elapsed_hours(),
        )  # fmt: skip
    return {
        "run_id": run_id,
        "run_dir": str(rdir),
        "status": status,
        "timesteps": int(model.num_timesteps),
        "final": str(rdir / "final.zip"),
        "best_select": ctx.best_select_path,
        "best_select_win_rate": ctx.best_select,
        "champion": ctx.champion,
        "champion_history": ctx.champion_history,
        "curriculum": ctx.curriculum.state() if ctx.curriculum else None,
        "ev_history": ctx.ev_history,
        "episode_steps": ctx.episode_steps,
        "episode_durations": ctx.episode_durations,
        "select_history": ctx.select_history,
        "gamma": ppo.gamma,
    }
