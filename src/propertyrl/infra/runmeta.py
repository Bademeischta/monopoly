"""Run metadata (§9.2): versions, seeds, hashes, packages and hardware for runs/<run_id>/run.json."""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import time
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from propertyrl.engine.errors import ArtifactError
from propertyrl.engine.hashing import sha256_bytes
from propertyrl.infra.config import REPO_ROOT, load_seeds_config
from propertyrl.infra.storage import query, read_json, record_run, runs_dir, write_json
from propertyrl.versions import HEURISTIC_VERSIONS, all_versions

log = logging.getLogger(__name__)

PACKAGES = (
    "numpy",
    "scipy",
    "pandas",
    "pyarrow",
    "pydantic",
    "PyYAML",
    "gymnasium",
    "pettingzoo",
    "stable-baselines3",
    "sb3-contrib",
    "torch",
    "openskill",
    "tensorboard",
    "matplotlib",
    "psutil",
)


def git_commit() -> tuple[str, bool]:
    """(commit hash, dirty flag); ('nogit', False) without git."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        return commit, bool(status)
    except (OSError, subprocess.SubprocessError):
        return "nogit", False


def package_versions() -> dict[str, str]:
    """Installed versions of the runtime dependencies."""
    out = {}
    for name in PACKAGES:
        try:
            out[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            out[name] = "missing"
    return out


def lock_hash() -> str:
    """SHA-256 of requirements-lock.txt ('missing' if absent)."""
    path = REPO_ROOT / "requirements-lock.txt"
    return sha256_bytes(path.read_bytes()) if path.exists() else "missing"


def hardware() -> dict[str, Any]:
    """CPU model, cores, RAM and GPU (if visible to torch)."""
    import psutil

    info: dict[str, Any] = {
        "cpu_model": platform.processor() or platform.machine(),
        "cores_logical": os.cpu_count(),
        "cores_physical": psutil.cpu_count(logical=False),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 2),
        "platform": platform.platform(),
    }
    try:
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("model name"):
                    info["cpu_model"] = line.split(":", 1)[1].strip()
                    break
    except OSError:
        info["cpu_model"] = platform.processor() or "unknown"
    try:
        import torch

        info["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:
        info["gpu"] = None
    return info


def new_run_id(experiment: str, seed: int, smoke: bool) -> str:
    """Unique run id (a counter separates runs started by one process within the same second)."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = "_smoke" if smoke else ""
    base = f"{experiment}_s{seed}_{stamp}_{os.getpid()}"
    run_id, n = f"{base}{suffix}", 1
    while (runs_dir() / run_id).exists():
        run_id, n = f"{base}-{n}{suffix}", n + 1
    return run_id


def build_run_meta(
    run_id: str,
    experiment: str,
    ruleset_id: str,
    config_hash: str,
    training_seed: int,
    total_timesteps: int,
    budget_hours: float,
    smoke: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Complete run.json content."""
    from propertyrl.evaluation.seeds import pool_checksums

    commit, dirty = git_commit()
    seeds = load_seeds_config()
    meta: dict[str, Any] = {
        "run_id": run_id,
        "experiment": experiment,
        "git_commit": commit,
        "git_dirty": dirty,
        "ruleset_id": ruleset_id,
        **all_versions(),
        "heuristic_versions": dict(HEURISTIC_VERSIONS),
        "config_hash": config_hash,
        "master_seed": seeds.master_seed,
        "training_seed": training_seed,
        "evaluation_seed": {"master_seed": seeds.master_seed, "pools": {k: v.pool_id for k, v in seeds.pools.items()}},
        "seed_pool_checksums": pool_checksums(),
        "python_version": sys.version,
        "packages": package_versions(),
        "requirements_lock_sha256": lock_hash(),
        "hardware": hardware(),
        "start_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "start_time_unix": time.time(),
        "end_time": None,
        "end_time_unix": None,
        "budget_hours": budget_hours,
        "total_timesteps": total_timesteps,
        "smoke": smoke,
        "status": "running",
        "warnings": [],
    }
    if extra:
        meta.update(extra)
    return meta


def run_dir(run_id: str) -> Path:
    """runs/<run_id>/."""
    path = runs_dir() / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_run_meta(meta: dict[str, Any]) -> Path:
    """Write run.json and mirror it into the database."""
    path = run_dir(meta["run_id"]) / "run.json"
    write_json(path, meta)
    record_run(meta["run_id"], meta["experiment"], meta["status"], bool(meta["smoke"]), meta)
    return path


def finish_run_meta(meta: dict[str, Any], status: str, **updates: Any) -> None:
    """Set end time and status and persist."""
    meta["end_time"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta["end_time_unix"] = time.time()
    meta["status"] = status
    meta.update(updates)
    save_run_meta(meta)


def load_run_meta(path: Path) -> dict[str, Any]:
    """Read run.json from a run directory (or the file itself); a damaged file falls back to the database copy."""
    p = path / "run.json" if path.is_dir() else path
    try:
        data: dict[str, Any] = read_json(p)
    except ArtifactError:
        rows = query("SELECT run_json FROM runs WHERE run_id = ?", (p.parent.name,))
        if not rows:
            raise
        log.warning("%s is damaged; using the copy in the database", p)
        data = json.loads(rows[0][0])
    return data
