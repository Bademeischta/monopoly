"""Training entry point: resolve configs, build envs/model/callbacks, run, checkpoint and resume (§7)."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from stable_baselines3.common.callbacks import CallbackList
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.common.utils import set_random_seed

from propertyrl.engine import constants as C
from propertyrl.engine.errors import ArtifactError, ConfigError
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
    require_frozen,
)
from propertyrl.infra.logging_setup import setup_logging
from propertyrl.infra.runmeta import build_run_meta, finish_run_meta, load_run_meta, new_run_id, run_dir, save_run_meta
from propertyrl.infra.storage import query, read_json, runs_dir
from propertyrl.training.budget import BudgetCallback
from propertyrl.training.callbacks import (
    CheckpointEvalCallback,
    ExplainedVarianceWarning,
    LatestSyncCallback,
    MetricsCallback,
    PFSPCallback,
    RunContext,
    checkpoint_ok,
    checkpoint_step,
    copy_checkpoint,
    latest_valid_checkpoint,
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
def frozen_gamma(default: float, smoke: bool = False) -> float:
    """gamma from artifacts/frozen/gamma.json (written by the sweep), else the default.

    Smoke runs prefer gamma_smoke.json so that the smoke chain sweep -> training is exercised (A-114).
    """
    for name in ("gamma_smoke", "gamma") if smoke else ("gamma",):
        data = read_frozen(name)
        if data and "gamma" in data:
            return float(data["gamma"])
    return float(default)


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
    if gamma is not None:
        g = float(gamma)
    else:
        g = frozen_gamma(ppo.gamma, smoke) if exp.env.gamma == "frozen" else float(exp.env.gamma)
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


def env_base_seed(seed: int, segment: int = 0) -> int:
    """Worker seed base derived from the training seed; segment k > 0 of a resumed run gets fresh games."""
    return int(u64(seed, C.STREAM_TRAIN, segment) % 1_000_000_000)


def segment_seed(seed: int, segment: int) -> int:
    """Library seed of segment ``segment`` of a run (segment 0 = the training seed itself)."""
    return seed if segment == 0 else int(u64(seed, C.STREAM_TRAIN, 1_000_000 + segment) % 2**31)


FINISHED = ("completed", "budget_stopped")


def is_finished(meta: dict[str, Any]) -> bool:
    """A run is finished when it was stopped by the budget or completed all its steps (A-140).

    A run that ended with an exception is "failed"; runs recorded as "completed" before that status existed
    are checked against their step count, so an aborted run is never reused or evaluated as finished.
    """
    status = meta.get("status")
    if status == "budget_stopped":
        return True
    return status == "completed" and int(meta.get("timesteps_done") or 0) >= int(meta.get("total_timesteps") or 0)


def is_sweep_pilot(run_id: str, experiment: str) -> bool:
    """γ-sweep pilots are stored under the MCR experiment with a ``_g<gamma>`` tag in the run id."""
    return re.match(rf"^{re.escape(experiment)}_g\d", run_id) is not None


def run_config(exp: ExperimentConfig, ppo: PPOConfig, env_cfg: EnvConfig) -> dict[str, Any]:
    """Fully resolved configuration of a run (its SHA-256 is the run's config_hash)."""
    return {"experiment": exp.model_dump(mode="json"), "ppo": ppo.model_dump(mode="json"), "env": env_cfg.to_dict()}


def experiment_runs(experiment: str, smoke: bool) -> list[dict[str, Any]]:
    """run.json of every run of ``experiment`` (newest first, sweep pilots excluded)."""
    rows = query("SELECT run_id, run_json FROM runs WHERE experiment = ? ORDER BY started DESC", (experiment,))
    out = []
    for run_id, run_json in rows:
        meta = json.loads(run_json)
        if bool(meta.get("smoke")) == smoke and not is_sweep_pilot(run_id, experiment):
            out.append(meta)
    return out


def find_checkpoint(experiment: str, seed: int | None, smoke: bool, kind: str = "best_select") -> Path | None:
    """Most recent checkpoint of a finished run of ``experiment`` (same seed preferred).

    Sweep pilots and runs that were interrupted or are still running are never used.
    """
    candidates = []
    for meta in experiment_runs(experiment, smoke):
        if not is_finished(meta):
            continue
        candidates.append((meta.get("training_seed") == seed, meta["run_id"]))
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
    wandb: bool = False,
) -> dict[str, Any]:
    """Train one run of an experiment and return a summary dict (``wandb``: optional technical metrics)."""
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
    if not smoke and resume is None:
        needed = ["horizon"] if exp.env.safety_horizon_rounds == "frozen" else []
        needed += ["strongest_baseline"] if exp.env.n_players == 2 else []
        needed += ["gamma"] if gamma is None and exp.env.gamma == "frozen" else []
        require_frozen(needed, f"training {experiment}")
    multi = exp.training.algorithm == "multiseat_ppo"
    # Segment k > 0 is the k-th resume of a run: fresh library and game seeds instead of replaying segment 0.
    segment = len(meta.get("resumes", [])) + 1 if resume is not None else 0
    seed_everything(segment_seed(seed, segment))
    full_cfg = run_config(exp, ppo, env_cfg)
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
    last = None
    if resume is not None:
        # The most advanced intact state: final.zip (written on every orderly exit) or the newest periodic
        # checkpoint; files a power-off left incomplete are skipped (A-139).
        last = latest_valid_checkpoint(rdir)
        if last is None:
            raise ConfigError(f"no intact checkpoint to resume in {rdir}")
        meta.setdefault("resumes", []).append(
            {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "checkpoint": str(last), "step": checkpoint_step(last)}
        )
    save_run_meta(meta)
    setup_logging(log_file=rdir / "train.log")
    ctx = RunContext(run_id, rdir, exp, ppo, env_cfg, seed, smoke)
    holder: dict[str, Any] = {}
    try:
        model, budget, callbacks = _prepare(ctx, meta, last, segment, multi, wandb, holder)
    except BaseException as err:
        # A run that cannot even start is never left as "running" (A-140).
        _close_envs(holder.get("venv"))
        finish_run_meta(meta, "interrupted" if isinstance(err, KeyboardInterrupt) else "failed")
        raise
    venv = holder["venv"]
    status = "completed"
    ctx.segment_start = time.monotonic()
    try:
        # On resume SB3 adds the already completed steps, so only the remainder is requested.
        remaining = ppo.total_timesteps if last is None else max(0, ppo.total_timesteps - int(model.num_timesteps))
        model.learn(
            total_timesteps=remaining,
            callback=CallbackList(callbacks),
            reset_num_timesteps=last is None,
            tb_log_name="ppo",
        )
        if budget.exceeded:
            status = "budget_stopped"
    except KeyboardInterrupt:
        status = "interrupted"
        raise
    except BaseException:
        # Never "completed": a run that died early must be resumed, not reused or evaluated (A-140).
        status = "failed"
        raise
    finally:
        _finish(model, ctx, venv, meta, status)
    return run_summary(rdir, reused=False)


def _prepare(
    ctx: RunContext,
    meta: dict[str, Any],
    last: Path | None,
    segment: int,
    multi: bool,
    wandb: bool,
    holder: dict[str, Any],
) -> tuple[Any, BudgetCallback, list[Any]]:
    """Environments (stored in ``holder`` so the caller can close them on failure), model and callbacks."""
    exp, ppo, env_cfg, seed, rdir = ctx.experiment, ctx.ppo, ctx.env_cfg, ctx.seed, ctx.run_dir
    if exp.opponents.mode == "curriculum":
        ctx.curriculum = CurriculumController([dict(s) for s in exp.opponents.curriculum_stages])
    if exp.opponents.mode in ("selfplay", "fourp"):
        ctx.pool = SnapshotPool(exp.opponents.pool_max)
    if last is not None:
        ctx.load_state()
    if ctx.curriculum is not None:
        env_cfg.opponents.stage = ctx.curriculum.stage
    if ctx.pool is not None:
        env_cfg.opponents.snapshots = tuple(ctx.pool.paths)
    venv = make_vec_env(env_cfg, ppo.n_envs, env_base_seed(seed, segment), ppo.vec_env, multi_seat=multi)
    holder["venv"] = venv
    algo: type[SMDPMaskablePPO] = MultiSeatSMDPMaskablePPO if multi else SMDPMaskablePPO
    tb = str(rdir / "tb")
    kwargs = dict(
        n_steps=ppo.n_steps, batch_size=ppo.batch_size, n_epochs=ppo.n_epochs, learning_rate=ppo.learning_rate,
        gamma=ppo.gamma, gae_lambda=ppo.gae_lambda, clip_range=ppo.clip_range, ent_coef=ppo.ent_coef,
        vf_coef=ppo.vf_coef, max_grad_norm=ppo.max_grad_norm, device=device_of(ppo), seed=seed, verbose=0,
        tensorboard_log=tb,
    )  # fmt: skip
    if last is not None:
        from propertyrl.agents.sb3_agent import read_metadata

        read_metadata(last)
        model = algo.load(str(last), env=venv, device=device_of(ppo), tensorboard_log=tb)
        # load() re-seeds everything with the run's original seed; segment k > 0 continues with fresh seeds
        # instead of replaying the first games of the run (A-140).
        model.set_random_seed(segment_seed(seed, segment))
    else:
        model = algo("MlpPolicy", venv, policy_kwargs=policy_kwargs(ppo), **kwargs)
        if exp.training.init_from:
            src = find_checkpoint(exp.training.init_from, seed, ctx.smoke)
            if src is None:
                raise ConfigError(f"no checkpoint of {exp.training.init_from} found to start {exp.name}")
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
    # The 12 h budget covers all segments of a resumed run (A-140).
    budget = BudgetCallback(max(0.0, ppo.budget_hours - ctx.hours_before))
    callbacks = [MetricsCallback(ctx), CheckpointEvalCallback(ctx), budget,
                 ExplainedVarianceWarning(ctx, ppo.total_timesteps)]  # fmt: skip
    if exp.opponents.mode in ("selfplay", "fourp", "fourp_fallback"):
        callbacks.append(PFSPCallback(ctx))
    if wandb:
        from propertyrl.training.wandb_logging import WandbCallback

        technical = {"experiment": exp.name, "seed": seed, "config_hash": meta["config_hash"], **kwargs}
        callbacks.append(WandbCallback(ctx.run_id, exp.name, {k: str(v) for k, v in technical.items()}, str(rdir)))
    if exp.opponents.mode == "fourp_fallback":
        latest = save_checkpoint(model, ctx, rdir / "latest.zip", "latest")
        venv.env_method("reload_opponents", {"latest_path": str(latest)})
        callbacks.append(LatestSyncCallback(ctx))
    return model, budget, callbacks


def _close_envs(venv: Any) -> None:
    if venv is None:
        return
    try:
        venv.close()
    except Exception as err:  # e.g. BrokenPipeError of SubprocVecEnv workers after a console Ctrl-C
        log.warning("closing the environments failed: %s", err)


def _finish(model: Any, ctx: RunContext, venv: Any, meta: dict[str, Any], status: str) -> None:
    """Final checkpoint, state and run.json on every exit; a failure to save marks the run as failed."""
    try:
        if status == "failed":
            # The weights at the time of an exception may be its cause (e.g. NaN after a divergence): they are kept
            # for diagnosis only, and a resume continues from the newest periodic checkpoint (A-140).
            save_checkpoint(model, ctx, ctx.run_dir / "failed.zip", "failed")
        else:
            final = save_checkpoint(model, ctx, ctx.run_dir / "final.zip", "final")
            if ctx.best_select_path is None:
                copy_checkpoint(final, ctx.run_dir / "best_select.zip")
                ctx.best_select_path = str(ctx.run_dir / "best_select.zip")
        ctx.save_state()
    except BaseException:
        status = "failed"
        raise
    finally:
        _close_envs(venv)
        finish_run_meta(
            meta, status, timesteps_done=int(model.num_timesteps), warnings=ctx.warnings,
            best_select=ctx.best_select, best_select_path=ctx.best_select_path, eval_games=ctx.eval_games,
            training_hours=ctx.training_hours(),
        )  # fmt: skip


def run_summary(rdir: Path, reused: bool) -> dict[str, Any]:
    """Summary of a run from run.json and training_state.json (same keys for new, resumed and reused runs)."""
    meta = load_run_meta(rdir)
    state_path = rdir / "training_state.json"
    try:
        state: dict[str, Any] = read_json(state_path) if state_path.exists() else {}
    except ArtifactError as err:
        log.warning("%s; summary built from run.json only", err)
        state = {}
    curriculum = state.get("curriculum")
    return {
        "run_id": meta["run_id"],
        "run_dir": str(rdir),
        "status": meta.get("status"),
        "timesteps": int(meta.get("timesteps_done") or 0),
        "final": str(rdir / "final.zip"),
        "best_select": state.get("best_select_path") or meta.get("best_select_path"),
        "best_select_win_rate": state.get("best_select", meta.get("best_select")),
        "champion": state.get("champion"),
        "champion_history": list(state.get("champion_history", [])),
        "curriculum": curriculum,
        "ev_history": list(state.get("ev_history", [])),
        "episode_steps": [int(x) for x in state.get("episode_steps", [])],
        "episode_durations": [int(x) for x in state.get("episode_durations", [])],
        "select_history": list(state.get("select_history", [])),
        "gamma": meta.get("gamma"),
        "reused": reused,
    }


def train_or_reuse(
    experiment: str,
    seed: int,
    smoke: bool = False,
    gamma: float | None = None,
    timesteps: int | None = None,
    run_tag: str = "",
    wandb: bool = False,
) -> dict[str, Any]:
    """Reuse a finished run with the identical configuration, resume an unfinished one, or train a new run.

    The newest run with this configuration and seed decides (an interrupted ``train --new`` retry is resumed,
    not replaced by an older finished run). Makes ``propertyrl train``, ``selfplay``, ``sweep-gamma`` and
    ``pipeline`` safe to re-run after an abort, a crash or a power-off (A-136, A-140).
    """
    exp, ppo, env_cfg = resolve(experiment, seed, smoke, gamma, timesteps)
    wanted = config_hash(run_config(exp, ppo, env_cfg))
    pilot = bool(run_tag)
    rows = query("SELECT run_id, run_json FROM runs WHERE experiment = ? ORDER BY started DESC", (experiment,))
    for run_id, raw in rows:
        meta = json.loads(raw)
        if bool(meta.get("smoke")) != smoke or is_sweep_pilot(run_id, experiment) != pilot:
            continue
        if meta.get("training_seed") != seed or meta.get("config_hash") != wanted:
            continue
        rdir = runs_dir() / run_id
        if not rdir.exists():
            continue
        if is_finished(meta) and checkpoint_ok(rdir / "final.zip"):
            log.info("reusing finished run %s for %s seed %d", run_id, experiment, seed)
            return run_summary(rdir, reused=True)
        last = latest_valid_checkpoint(rdir)
        if last is not None:
            log.info("resuming run %s at step %d for %s seed %d", run_id, checkpoint_step(last), experiment, seed)
            return train("", 0, resume=rdir, wandb=wandb)
        break  # the newest attempt has nothing to continue from: start afresh
    return train(experiment, seed, smoke=smoke, gamma=gamma, timesteps=timesteps, run_tag=run_tag, wandb=wandb)
