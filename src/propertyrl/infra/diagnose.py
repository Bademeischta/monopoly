"""Diagnosis checklist for a training run (§9.6): rewards, masks, observations, entropy, EV, durations,
opponent mix and valid rows of the multi-seat buffer."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from propertyrl.env.core import EnvConfig
from propertyrl.infra.runmeta import load_run_meta
from propertyrl.infra.storage import read_json, write_json

log = logging.getLogger(__name__)


def tb_scalars(run_path: Path) -> dict[str, list[float]]:
    """All scalar series from the run's TensorBoard event files."""
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    out: dict[str, list[float]] = {}
    for event_dir in sorted({p.parent for p in (run_path / "tb").rglob("events.out.tfevents.*")}):
        acc = EventAccumulator(str(event_dir))
        acc.Reload()
        for tag in acc.Tags().get("scalars", []):
            out.setdefault(tag, []).extend(e.value for e in acc.Scalars(tag))
    return out


def _status(ok: bool, warn: bool = False) -> str:
    return "OK" if ok else ("WARN" if warn else "FAIL")


def diagnose(run_path: Path, steps: int = 2000) -> dict[str, Any]:
    """Run the checklist and write runs/<id>/diagnose.json."""
    from propertyrl.env.multi_seat import PropertyMultiSeatEnv
    from propertyrl.env.single_agent import PropertySingleAgentEnv
    from propertyrl.training.smdp_ppo import SMDPMaskablePPO

    meta = load_run_meta(run_path)
    env_cfg = EnvConfig.from_dict(meta["config"]["env"])
    multi = meta["config"]["experiment"]["training"]["algorithm"] == "multiseat_ppo"
    ckpt = run_path / "final.zip"
    model = SMDPMaskablePPO.load(str(ckpt), device="cpu") if ckpt.exists() else None
    env = PropertyMultiSeatEnv(env_cfg) if multi else PropertySingleAgentEnv(env_cfg)
    obs, info = env.reset(seed=4242)
    rewards: list[float] = []
    durations: list[int] = []
    empty_masks = 0
    illegal = 0
    obs_ok = True
    categories: Counter[str] = Counter()
    if env.core.plan:
        categories.update(env.core.plan.category.values())
    rng = np.random.default_rng(0)
    for _ in range(steps):
        mask = env.action_masks()
        if not mask.any():
            empty_masks += 1
            break
        if model is not None:
            action, _ = model.predict(obs, action_masks=mask, deterministic=False)
        else:
            action = rng.choice(np.flatnonzero(mask))
        obs, r, term, trunc, info = env.step(int(action))
        obs_ok = obs_ok and bool(np.isfinite(obs).all() and obs.min() >= 0.0 and obs.max() <= 1.0)
        illegal += int(info.get("illegal_actions", 0))
        if multi:
            for c in info.get("closed", []):
                rewards.append(float(c["reward"]))
                durations.append(int(c["duration"]))
        else:
            rewards.append(float(r))
            durations.append(int(info["duration"]))
        if term or trunc:
            obs, info = env.reset()
            if env.core.plan:
                categories.update(env.core.plan.category.values())
    scalars = tb_scalars(run_path) if (run_path / "tb").exists() else {}
    ent = scalars.get("train/entropy_loss", [])
    ev = scalars.get("train/explained_variance", [])
    valid = scalars.get("train/valid_row_fraction", [])
    rew = np.asarray(rewards) if rewards else np.zeros(1)
    checks = {
        "reward_scale": {"status": _status(abs(rew.mean()) < 1.0 and rew.std() < 2.0, True),
                         "mean": float(rew.mean()), "std": float(rew.std())},
        "masks": {"status": _status(empty_masks == 0 and illegal == 0), "empty_masks": empty_masks, "illegal": illegal},
        "observation": {"status": _status(obs_ok), "finite_and_in_unit_interval": obs_ok},
        "entropy": {"status": _status(not ent or -ent[-1] > 0.05, True), "last_entropy": -ent[-1] if ent else None},
        "explained_variance": {"status": _status(not ev or ev[-1] >= 0.3, True), "last": ev[-1] if ev else None},
        "duration_k": {"status": "OK", "mean": float(np.mean(durations)) if durations else None,
                       "max": int(max(durations)) if durations else None,
                       "histogram": dict(Counter(durations).most_common(10))},
        "opponent_mix": {"status": "OK", "categories": dict(categories)},
        "valid_rows": {"status": _status(not valid or valid[-1] >= 0.9, True), "last": valid[-1] if valid else None},
    }  # fmt: skip
    state_path = run_path / "training_state.json"
    result = {
        "run_id": meta["run_id"],
        "steps": steps,
        "checks": checks,
        "warnings": meta.get("warnings", []),
        "training_state": read_json(state_path).get("curriculum") if state_path.exists() else None,
    }
    write_json(run_path / "diagnose.json", result)
    return result
