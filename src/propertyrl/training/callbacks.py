"""Training callbacks (§7.5): metrics, checkpoints, SELECT evaluation, curriculum, PFSP, snapshots,
champion gate, latest sync and explained-variance warning."""

from __future__ import annotations

import logging
import shutil
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

from propertyrl.agents.registry import clear_cache
from propertyrl.engine.errors import ArtifactError
from propertyrl.engine.hashing import sha256_bytes
from propertyrl.env.core import EnvConfig
from propertyrl.env.observation import OBS_VERSION
from propertyrl.evaluation.duplicate import duplicate_specs, summarize
from propertyrl.evaluation.harness import default_workers, run_games
from propertyrl.evaluation.seeds import subset
from propertyrl.infra.config import ExperimentConfig, PPOConfig, read_frozen
from propertyrl.infra.storage import atomic_path, read_json, record_checkpoint, write_json
from propertyrl.training.curriculum import CurriculumController
from propertyrl.training.selfplay import SnapshotPool, champion_gate, pfsp_weights
from propertyrl.versions import (
    ACTION_VERSION,
    CHECKPOINT_SCHEMA_VERSION,
    ENGINE_VERSION,
    ENV_VERSION,
    EVENT_SCHEMA_VERSION,
)

log = logging.getLogger(__name__)


@dataclass
class RunContext:
    """Mutable state of one training run shared by all callbacks (persisted in training_state.json)."""

    run_id: str
    run_dir: Path
    experiment: ExperimentConfig
    ppo: PPOConfig
    env_cfg: EnvConfig
    seed: int
    smoke: bool
    curriculum: CurriculumController | None = None
    pool: SnapshotPool | None = None
    champion: str | None = None
    champion_vs_a: dict[int, float] = field(default_factory=dict)
    champion_history: list[dict[str, Any]] = field(default_factory=list)
    pfsp: dict[str, list[float]] = field(default_factory=dict)
    best_select: float = -1.0
    best_select_path: str | None = None
    checkpoints: list[str] = field(default_factory=list)
    select_history: list[dict[str, Any]] = field(default_factory=list)
    ev_history: list[float] = field(default_factory=list)
    episode_steps: list[int] = field(default_factory=list)
    episode_durations: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    eval_games: int = 0
    #: Training hours of earlier segments of a resumed run (the 12 h budget covers all segments, A-140).
    hours_before: float = 0.0
    segment_start: float = field(default_factory=time.monotonic)

    @property
    def n_players(self) -> int:
        return self.env_cfg.n_players

    @property
    def ruleset_id(self) -> str:
        return self.env_cfg.ruleset

    @property
    def eval_pool(self) -> str:
        """Smoke runs only ever use SMOKE seeds."""
        return "SMOKE" if self.smoke else "SELECT"

    def state_path(self) -> Path:
        return self.run_dir / "training_state.json"

    def training_hours(self) -> float:
        """Training hours of all segments of this run so far."""
        return self.hours_before + (time.monotonic() - self.segment_start) / 3600.0

    def save_state(self) -> None:
        """Persist everything needed for --resume."""
        write_json(
            self.state_path(),
            {
                "curriculum": self.curriculum.state() if self.curriculum else None,
                "pool": self.pool.state() if self.pool else None,
                "champion": self.champion,
                "champion_vs_a": {str(k): v for k, v in self.champion_vs_a.items()},
                "champion_history": self.champion_history,
                "pfsp": self.pfsp,
                "best_select": self.best_select,
                "best_select_path": self.best_select_path,
                "checkpoints": self.checkpoints,
                "select_history": self.select_history,
                "ev_history": self.ev_history,
                "episode_steps": self.episode_steps,
                "episode_durations": self.episode_durations,
                "warnings": self.warnings,
                "eval_games": self.eval_games,
                "training_hours": self.training_hours(),
            },
        )

    def load_state(self) -> None:
        """Restore from training_state.json (resume)."""
        if not self.state_path().exists():
            return
        data = read_json(self.state_path())
        if self.curriculum and data.get("curriculum"):
            self.curriculum.load(data["curriculum"])
        if data.get("pool"):
            self.pool = SnapshotPool(int(data["pool"]["max_size"]), list(data["pool"]["paths"]))
        self.champion = data.get("champion")
        self.champion_vs_a = {int(k): float(v) for k, v in data.get("champion_vs_a", {}).items()}
        self.champion_history = list(data.get("champion_history", []))
        self.pfsp = {k: list(v) for k, v in data.get("pfsp", {}).items()}
        self.best_select = float(data.get("best_select", -1.0))
        self.best_select_path = data.get("best_select_path")
        self.checkpoints = list(data.get("checkpoints", []))
        self.select_history = list(data.get("select_history", []))
        self.ev_history = list(data.get("ev_history", []))
        self.episode_steps = [int(x) for x in data.get("episode_steps", [])]
        self.episode_durations = [int(x) for x in data.get("episode_durations", [])]
        self.warnings = list(data.get("warnings", []))
        self.eval_games = int(data.get("eval_games", 0))
        self.hours_before = float(data.get("training_hours", 0.0))
        self._drop_damaged_checkpoints()

    def _drop_damaged_checkpoints(self) -> None:
        """Forget checkpoints a power-off left incomplete, so a resume never loads them (A-139)."""
        if self.best_select_path and not checkpoint_ok(Path(self.best_select_path)):
            copy = self.run_dir / "best_select.zip"  # e.g. the run directory was restored to another path
            if checkpoint_ok(copy):
                self.best_select_path = str(copy)
            else:
                log.warning("best_select checkpoint %s is damaged; the next SELECT evaluation picks a new one",
                            self.best_select_path)  # fmt: skip
                self.best_select, self.best_select_path = -1.0, None
        self.checkpoints = [c for c in self.checkpoints if checkpoint_ok(Path(c))]
        if self.pool is not None:
            valid = [p for p in self.pool.paths if checkpoint_ok(Path(p))]
            if len(valid) != len(self.pool.paths):
                log.warning("dropping %d damaged snapshots from the pool", len(self.pool.paths) - len(valid))
                self.pool = SnapshotPool(self.pool.max_size, valid)
            champion = (self.champion or "").split(":", 1)[-1]
            if champion and not checkpoint_ok(Path(champion)):
                fallback = self.run_dir / "champion.zip"
                self.champion = f"sb3:{fallback}" if checkpoint_ok(fallback) else (
                    f"sb3:{valid[-1]}" if valid else None)  # fmt: skip
                log.warning("champion checkpoint %s is damaged; using %s", champion, self.champion)


# ---------------------------------------------------------------------------- checkpoint helpers
def checkpoint_metadata(ctx: RunContext, path: Path, step: int, kind: str) -> dict[str, Any]:
    """Metadata JSON stored next to every checkpoint zip."""
    return {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "obs_version": OBS_VERSION,
        "action_version": ACTION_VERSION,
        "env_version": ENV_VERSION,
        "engine_version": ENGINE_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "env_config": ctx.env_cfg.to_dict(),
        "experiment": ctx.experiment.name,
        "run_id": ctx.run_id,
        "seed": ctx.seed,
        "step": step,
        "kind": kind,
        "smoke": ctx.smoke,
        "model_hash": sha256_bytes(path.read_bytes()),
    }


def save_checkpoint(model: Any, ctx: RunContext, path: Path, kind: str, winrate: float | None = None) -> Path:
    """Save model zip plus metadata JSON (each atomically, zip first) and register it in the database.

    The metadata carries the SHA-256 of the complete zip, so a pair torn by a power-off is detected by
    :func:`checkpoint_ok` and never resumed from (A-139).
    """
    zip_path = path if path.suffix == ".zip" else path.with_suffix(".zip")
    with atomic_path(zip_path) as tmp:
        model.save(str(tmp))
    meta = checkpoint_metadata(ctx, zip_path, int(model.num_timesteps), kind)
    write_json(zip_path.with_suffix(".json"), meta)
    record_checkpoint(ctx.run_id, int(model.num_timesteps), zip_path, meta["model_hash"], kind, winrate)
    return zip_path


def copy_checkpoint(src: Path, dst: Path) -> None:
    """Copy a checkpoint zip together with its metadata JSON (each atomically)."""
    for s, d in ((src, dst), (src.with_suffix(".json"), dst.with_suffix(".json"))):
        with atomic_path(d) as tmp:
            shutil.copyfile(s, tmp)


def checkpoint_ok(path: Path) -> bool:
    """True if ``path`` and its metadata JSON exist and the zip matches the stored model hash."""
    meta_path = path.with_suffix(".json")
    if not path.exists() or not meta_path.exists():
        return False
    try:
        meta = read_json(meta_path)
        return isinstance(meta, dict) and meta.get("model_hash") == sha256_bytes(path.read_bytes())
    except (ArtifactError, OSError):
        return False


def checkpoint_step(path: Path) -> int:
    """Training step stored in a checkpoint's metadata."""
    return int(read_json(path.with_suffix(".json"))["step"])


def latest_valid_checkpoint(run_dir: Path) -> Path | None:
    """Most advanced intact checkpoint of a run (final.zip or a periodic checkpoint); damaged ones are skipped."""
    best: tuple[int, bool, Path] | None = None
    for path in [run_dir / "final.zip", *sorted((run_dir / "checkpoints").glob("ckpt_*.zip"))]:
        if not path.exists():
            continue
        if not checkpoint_ok(path):
            log.warning("skipping damaged checkpoint %s", path)
            continue
        key = (checkpoint_step(path), path.name == "final.zip", path)
        if best is None or key[:2] > best[:2]:
            best = key
    return best[2] if best else None


def eval_opponents(ctx: RunContext) -> list[str]:
    """SELECT opponents: the frozen strongest baseline, before G3 the current curriculum stage."""
    if ctx.n_players > 2:
        return list(ctx.experiment.evaluation.opponents[:3]) if len(ctx.experiment.evaluation.opponents) >= 3 else [
            "strong_a_v1", "strong_b_v1", "roi_markov_v1"]  # fmt: skip
    frozen = read_frozen("strongest_baseline")
    if frozen and frozen.get("policy"):
        return [str(frozen["policy"])]
    if ctx.curriculum is not None:
        return ctx.curriculum.opponents
    return ["strong_a_v1"]


def evaluate_checkpoint(ctx: RunContext, agent: str, opponents: list[str], n_seeds: int) -> dict[str, Any]:
    """Duplicate evaluation on the first ``n_seeds`` seeds of the evaluation pool (SELECT or SMOKE)."""
    seeds = subset(ctx.eval_pool, start=0, end=n_seeds)
    if ctx.n_players == 2:
        specs = []
        for k, opp in enumerate(opponents):
            chosen = seeds[k :: len(opponents)]
            specs += duplicate_specs(agent, [opp], chosen, ctx.ruleset_id, 2, index_offset=0)
    else:
        specs = duplicate_specs(agent, opponents, seeds, ctx.ruleset_id, ctx.n_players)
    workers = 1 if len(specs) <= 40 else default_workers()
    records = run_games(specs, workers=workers)
    ctx.eval_games += len(records)
    clear_cache()
    summary = summarize(records, agent, bootstrap_reps=500)
    summary["opponents"] = opponents
    return summary


# ---------------------------------------------------------------------------- callbacks
class MetricsCallback(BaseCallback):
    """Logs game metrics to TensorBoard (single and multi-seat) and aggregates PFSP statistics."""

    def __init__(self, ctx: RunContext, window: int = 200) -> None:
        super().__init__()
        self.ctx = ctx
        self.window = window
        self.results: deque[dict[str, Any]] = deque(maxlen=window)
        self.closed_rewards: deque[float] = deque(maxlen=5000)
        self.durations: deque[float] = deque(maxlen=5000)
        self._steps: np.ndarray | None = None
        self._ticks: np.ndarray | None = None

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        dones = self.locals.get("dones", np.zeros(len(infos), dtype=bool))
        if self._steps is None:
            self._steps = np.zeros(len(infos), dtype=np.int64)
            self._ticks = np.zeros(len(infos), dtype=np.int64)
        assert self._ticks is not None
        for i, info in enumerate(infos):
            self._steps[i] += 1
            dur = int(info.get("duration", 0) or 0)
            for c in info.get("closed", []):
                self.closed_rewards.append(float(c["reward"]))
                dur = max(dur, int(c["duration"]))
            self._ticks[i] += dur
            if dur:
                self.durations.append(dur)
            if not dones[i]:
                continue
            self.ctx.episode_steps.append(int(self._steps[i]))
            self.ctx.episode_durations.append(int(self._ticks[i]))
            self._steps[i] = 0
            self._ticks[i] = 0
            stats = info.get("episode_stats")
            if stats:
                for seat, st in stats.items():
                    self._record(st, int(seat))
            elif "placement" in info:
                self._record(info, int(info.get("learning_seat", 0)))
        return True

    def _record(self, info: dict[str, Any], seat: int) -> None:
        self.results.append(info)
        placements = info.get("placements") or []
        won = bool(info.get("won"))
        for opp_seat, oid in (info.get("opponent_ids") or {}).items():
            entry = self.ctx.pfsp.setdefault(str(oid), [0.0, 0.0])
            if placements and len(placements) > 2:
                entry[0] += 1.0 if placements[seat] < placements[int(opp_seat)] else 0.0
            else:
                entry[0] += 1.0 if won else 0.0
            entry[1] += 1.0

    def _on_rollout_end(self) -> None:
        if not self.results:
            return
        res = list(self.results)
        rec = self.logger.record
        rec("propertyrl/win_rate", float(np.mean([bool(r.get("won")) for r in res])))
        rec("propertyrl/mean_placement", float(np.mean([r.get("placement", 0) for r in res])))
        rec("propertyrl/rounds", float(np.mean([r.get("rounds", 0) for r in res])))
        rec("propertyrl/decisions", float(np.mean([r.get("decisions", 0) for r in res])))
        rec("propertyrl/truncation_rate", float(np.mean([bool(r.get("truncated")) for r in res])))
        rec("propertyrl/final_equity_share", float(np.mean([r.get("final_equity_share", 0.0) for r in res])))
        rec("propertyrl/illegal_actions", float(sum(int(r.get("illegal_actions", 0)) for r in res)))
        for key in ("purchases", "builds", "mortgages", "unmortgages", "trades", "auctions_won",
                    "scarcity_auctions", "jail_stay", "jail_leave", "jail_balance"):  # fmt: skip
            rec(f"propertyrl/{key}", float(np.mean([r.get("counters", {}).get(key, 0) for r in res])))
        if self.durations:
            rec("propertyrl/mean_duration_k", float(np.mean(self.durations)))
        if self.closed_rewards:
            rec("propertyrl/mean_closed_reward", float(np.mean(self.closed_rewards)))
        ev = self.logger.name_to_value.get("train/explained_variance")
        if ev is not None:
            self.ctx.ev_history.append(float(ev))


class CheckpointEvalCallback(BaseCallback):
    """Periodic checkpoints, SELECT evaluation (best_select), curriculum control, snapshots and champion gate."""

    def __init__(self, ctx: RunContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.next_ckpt = ctx.ppo.checkpoint_interval
        self.next_select = ctx.ppo.select_eval_interval
        snap = ctx.experiment.opponents.snapshot_interval
        self.snapshot_interval = snap
        self.next_snapshot = snap

    def _on_training_start(self) -> None:
        t = int(self.model.num_timesteps)
        self.next_ckpt = (t // self.ctx.ppo.checkpoint_interval + 1) * self.ctx.ppo.checkpoint_interval
        self.next_select = (t // self.ctx.ppo.select_eval_interval + 1) * self.ctx.ppo.select_eval_interval
        self.next_snapshot = (t // self.snapshot_interval + 1) * self.snapshot_interval

    def _on_step(self) -> bool:
        t = int(self.model.num_timesteps)
        if t >= self.next_ckpt:
            self.next_ckpt += self.ctx.ppo.checkpoint_interval
            self.checkpoint(t)
        if t >= self.next_select:
            self.next_select += self.ctx.ppo.select_eval_interval
            self.select_eval(t)
        if self.ctx.pool is not None and t >= self.next_snapshot:
            self.next_snapshot += self.snapshot_interval
            self.snapshot(t)
        return True

    def checkpoint(self, t: int) -> Path:
        ctx = self.ctx
        path = save_checkpoint(self.model, ctx, ctx.run_dir / "checkpoints" / f"ckpt_{t:010d}.zip", "periodic")
        ctx.checkpoints.append(str(path))
        while len(ctx.checkpoints) > ctx.ppo.keep_checkpoints:
            old = Path(ctx.checkpoints.pop(0))
            for p in (old, old.with_suffix(".json")):
                if p.exists():
                    p.unlink()
        if ctx.curriculum is not None and not ctx.curriculum.final:
            n = ctx.experiment.opponents.select_mini_seeds
            summary = evaluate_checkpoint(ctx, f"sb3:{path}", ctx.curriculum.opponents, n)
            changed = ctx.curriculum.update(t, summary["win_rate"])
            self.logger.record("propertyrl/select_mini_win_rate", summary["win_rate"])
            if changed:
                log.info("curriculum stage -> %d at step %d", ctx.curriculum.stage, t)
                self.training_env.env_method("set_curriculum_stage", ctx.curriculum.stage)
            self.logger.record("propertyrl/curriculum_stage", ctx.curriculum.stage)
        ctx.save_state()
        return path

    def select_eval(self, t: int) -> None:
        ctx = self.ctx
        path = save_checkpoint(self.model, ctx, ctx.run_dir / "checkpoints" / "select_candidate.zip", "select")
        summary = evaluate_checkpoint(ctx, f"sb3:{path}", eval_opponents(ctx), ctx.ppo.select_eval_seeds)
        rate = summary["win_rate"]
        ctx.select_history.append({"step": t, "win_rate": rate, "opponents": summary["opponents"]})
        self.logger.record("propertyrl/select_win_rate", rate)
        if rate > ctx.best_select:
            ctx.best_select = rate
            best = ctx.run_dir / "best_select.zip"
            copy_checkpoint(path, best)
            ctx.best_select_path = str(best)
        ctx.save_state()

    def snapshot(self, t: int) -> None:
        ctx = self.ctx
        assert ctx.pool is not None
        path = save_checkpoint(self.model, ctx, ctx.run_dir / "snapshots" / f"snap_{t:010d}.zip", "snapshot")
        removed = ctx.pool.add(str(path))
        champion = (ctx.champion or "").split(":", 1)[-1]  # the champion spec carries the "sb3:" prefix
        for old in removed:
            if old != champion:
                for p in (Path(old), Path(old).with_suffix(".json")):
                    if p.exists():
                        p.unlink()
        self.training_env.env_method("reload_opponents", {"snapshots": list(ctx.pool.paths)})
        if ctx.experiment.mode == "selfplay" and ctx.champion is not None:
            self.gate(f"sb3:{path}", t)
        ctx.save_state()

    def gate(self, candidate: str, t: int) -> None:
        ctx = self.ctx
        sp = ctx.experiment.selfplay
        assert sp is not None and ctx.champion is not None
        if ctx.smoke:
            from propertyrl.training.smoke import smoke_settings

            k = smoke_settings().champion_gate_seeds
            blocks = [subset("SMOKE", start=0, end=k), subset("SMOKE", start=k, end=2 * k)]
        else:
            blocks = [subset("SELECT", start=sp.gate_block1[0], end=sp.gate_block1[1]),
                      subset("SELECT", start=sp.gate_block2[0], end=sp.gate_block2[1])]  # fmt: skip
        res = champion_gate(candidate, ctx.champion, ctx.ruleset_id, blocks, sp.gate_margin_pp, ctx.champion_vs_a)
        clear_cache()
        ctx.eval_games += sum(4 * len(b) for b in blocks)
        entry = {"step": t, "candidate": candidate, "passed": res["passed"], "blocks": res["blocks"]}
        ctx.champion_history.append(entry)
        if res["passed"]:
            ctx.champion = candidate
            ctx.champion_vs_a = {}
            copy_checkpoint(Path(candidate.split(":", 1)[1]), ctx.run_dir / "champion.zip")
        else:
            ctx.champion_vs_a = dict(res.get("champion_vs_a", {}))
        self.logger.record("propertyrl/champion_changes", sum(1 for h in ctx.champion_history if h["passed"]))


class PFSPCallback(BaseCallback):
    """Distributes PFSP weights (1 - p)^2 to all environments after each rollout."""

    def __init__(self, ctx: RunContext) -> None:
        super().__init__()
        self.ctx = ctx

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> None:
        stats = {k: [round(v[0]), round(v[1])] for k, v in self.ctx.pfsp.items()}
        self.training_env.env_method("set_opponent_weights", pfsp_weights(stats))


class LatestSyncCallback(BaseCallback):
    """4P fallback: copy the current policy to latest.zip after each rollout and reload it in the workers."""

    def __init__(self, ctx: RunContext) -> None:
        super().__init__()
        self.ctx = ctx

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> None:
        path = save_checkpoint(self.model, self.ctx, self.ctx.run_dir / "latest.zip", "latest")
        self.training_env.env_method("reload_opponents", {"latest_path": str(path)})


class ExplainedVarianceWarning(BaseCallback):
    """Warns once if explained_variance < threshold after a fraction of the budget (R10 trigger)."""

    def __init__(self, ctx: RunContext, total_timesteps: int) -> None:
        super().__init__()
        self.ctx = ctx
        self.after = ctx.ppo.ev_warning_fraction * total_timesteps
        self.warned = False

    def _on_step(self) -> bool:
        return True

    def _on_rollout_end(self) -> None:
        ev = self.logger.name_to_value.get("train/explained_variance")
        if self.warned or ev is None or self.model.num_timesteps < self.after:
            return
        if float(ev) < self.ctx.ppo.ev_warning_threshold:
            msg = f"explained_variance {float(ev):.3f} < {self.ctx.ppo.ev_warning_threshold} after " \
                  f"{self.model.num_timesteps} steps (R10)"  # fmt: skip
            log.warning(msg)
            self.ctx.warnings.append(msg)
            self.warned = True
