"""Robustness against Ctrl-C, crashes and power-offs (A-139, A-140): atomic files, run status, resume, reuse."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from propertyrl.engine.errors import ArtifactError, ConfigError
from propertyrl.evaluation import seeds
from propertyrl.infra.config import read_frozen
from propertyrl.infra.runmeta import load_run_meta
from propertyrl.infra.storage import atomic_path, read_json, write_json
from propertyrl.training.budget import BudgetCallback
from propertyrl.training.callbacks import checkpoint_ok, latest_valid_checkpoint

train_mod = importlib.import_module("propertyrl.training.train")


@pytest.fixture
def fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    forbidden = seeds.forbidden_seeds
    monkeypatch.setenv("PROPERTYRL_HOME", str(tmp_path))
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()
    yield tmp_path
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()


def _failing_budget(at_call: int, exc: type[BaseException]) -> type[BudgetCallback]:
    class FailingBudget(BudgetCallback):
        calls = 0

        def _on_step(self) -> bool:
            FailingBudget.calls += 1
            if FailingBudget.calls == at_call:
                raise exc("simulated")
            return super()._on_step()

    return FailingBudget


def test_atomic_path_keeps_old_file_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "frozen" / "horizon.json"
    write_json(target, {"horizon_2p": 140})
    with pytest.raises(RuntimeError), atomic_path(target) as tmp:
        tmp.write_text('{"horizon_2p": 1', encoding="utf-8")  # half written when the crash happens
        raise RuntimeError("crash")
    assert read_json(target) == {"horizon_2p": 140}
    assert sorted(p.name for p in target.parent.iterdir()) == ["horizon.json"]  # no temporary file left


def test_damaged_json_names_file_and_repair_command(fresh_home: Path) -> None:
    frozen = fresh_home / "artifacts" / "frozen"
    frozen.mkdir(parents=True)
    (frozen / "horizon.json").write_bytes(b"\x00" * 100)  # what a power-off leaves behind
    with pytest.raises(ArtifactError, match=r"horizon\.json.*propertyrl calibrate-horizon"):
        read_frozen("horizon")


def test_is_finished_requires_all_steps() -> None:
    meta = {"status": "completed", "timesteps_done": 4096, "total_timesteps": 4096}
    assert train_mod.is_finished(meta)
    # runs recorded as "completed" after an exception (before the "failed" status existed) are unfinished
    assert not train_mod.is_finished({**meta, "timesteps_done": 512})
    assert train_mod.is_finished({**meta, "status": "budget_stopped", "timesteps_done": 512})
    for status in ("failed", "interrupted", "running"):
        assert not train_mod.is_finished({**meta, "status": status})


def test_crash_marks_run_failed_and_pipeline_resumes_it(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An exception other than Ctrl-C must never produce a "completed" run that is reused or evaluated; the
    weights at the time of the exception are kept apart and the run continues from the last periodic checkpoint."""
    monkeypatch.setattr(train_mod, "BudgetCallback", _failing_budget(1500, RuntimeError))
    with pytest.raises(RuntimeError):
        train_mod.train("mcr_official_2p", 1, smoke=True, timesteps=4096)
    (run,) = list((fresh_home / "runs").iterdir())
    meta = load_run_meta(run)
    assert meta["status"] == "failed"
    assert 2048 < int(meta["timesteps_done"]) < 4096
    assert checkpoint_ok(run / "failed.zip") and not (run / "final.zip").exists()
    assert train_mod.find_checkpoint("mcr_official_2p", 1, True) is None
    assert latest_valid_checkpoint(run) == run / "checkpoints" / "ckpt_0000002048.zip"
    monkeypatch.setattr(train_mod, "BudgetCallback", BudgetCallback)
    res = train_mod.train_or_reuse("mcr_official_2p", 1, smoke=True, timesteps=4096)
    assert res["run_id"] == run.name and res["status"] == "completed" and not res["reused"]
    meta = load_run_meta(run)
    assert [r["step"] for r in meta["resumes"]] == [2048]
    assert meta["training_hours"] > 0
    assert train_mod.find_checkpoint("mcr_official_2p", 1, True) is not None


def test_setup_failure_marks_run_failed(fresh_home: Path) -> None:
    """A run that cannot even start (here: self-play without a finished MCR run) is not left as "running"."""
    with pytest.raises(ConfigError, match="no checkpoint of mcr_official_2p"):
        train_mod.train("selfplay_official_2p", 1, smoke=True)
    (run,) = list((fresh_home / "runs").iterdir())
    assert load_run_meta(run)["status"] == "failed"


def test_newest_attempt_decides(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An interrupted `train --new` retry (same configuration) is resumed instead of reusing the older run."""
    old = train_mod.train("mcr_official_2p", 1, smoke=True, timesteps=4096)
    monkeypatch.setattr(train_mod, "BudgetCallback", _failing_budget(1500, KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        train_mod.train("mcr_official_2p", 1, smoke=True, timesteps=4096)
    monkeypatch.setattr(train_mod, "BudgetCallback", BudgetCallback)
    (newer,) = [p.name for p in (fresh_home / "runs").iterdir() if p.name != old["run_id"]]
    res = train_mod.train_or_reuse("mcr_official_2p", 1, smoke=True, timesteps=4096)
    assert res["run_id"] == newer and res["status"] == "completed" and not res["reused"]


def test_new_run_ids_are_unique(fresh_home: Path) -> None:
    from propertyrl.infra.runmeta import new_run_id, run_dir

    first = new_run_id("mcr_official_2p", 1, False)
    run_dir(first)
    second = new_run_id("mcr_official_2p", 1, False)
    assert first != second and second.startswith(first)


def test_resume_skips_damaged_final_checkpoint(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A final.zip torn by a power-off falls back to the newest intact periodic checkpoint."""
    monkeypatch.setattr(train_mod, "BudgetCallback", _failing_budget(1500, KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        train_mod.train("mcr_official_2p", 1, smoke=True, timesteps=4096)
    (run,) = list((fresh_home / "runs").iterdir())
    final = run / "final.zip"
    assert checkpoint_ok(final)
    final.write_bytes(final.read_bytes()[:100])  # torn zip
    assert not checkpoint_ok(final)
    fallback = latest_valid_checkpoint(run)
    assert fallback is not None and fallback.name.startswith("ckpt_")
    monkeypatch.setattr(train_mod, "BudgetCallback", BudgetCallback)
    res = train_mod.train_or_reuse("mcr_official_2p", 1, smoke=True, timesteps=4096)
    assert res["run_id"] == run.name and res["status"] == "completed"
    assert load_run_meta(run)["resumes"][0]["checkpoint"] == str(fallback)
    assert checkpoint_ok(final)


def test_no_intact_checkpoint_starts_a_new_run(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(train_mod, "BudgetCallback", _failing_budget(100, KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        train_mod.train("mcr_official_2p", 1, smoke=True, timesteps=1024)
    (run,) = list((fresh_home / "runs").iterdir())
    (run / "final.zip").write_bytes(b"\x00" * 64)
    with pytest.raises(ConfigError, match="no intact checkpoint"):
        train_mod.train("", 0, resume=run)
    monkeypatch.setattr(train_mod, "BudgetCallback", BudgetCallback)
    res = train_mod.train_or_reuse("mcr_official_2p", 1, smoke=True, timesteps=1024)
    assert res["run_id"] != run.name and res["status"] == "completed"


def test_sweep_pilots_are_reused_but_never_taken_as_main_run(fresh_home: Path) -> None:
    first = train_mod.train_or_reuse("mcr_official_2p", 1, smoke=True, gamma=0.99, timesteps=512, run_tag="g0.99")
    again = train_mod.train_or_reuse("mcr_official_2p", 1, smoke=True, gamma=0.99, timesteps=512, run_tag="g0.99")
    assert again["reused"] and again["run_id"] == first["run_id"]
    assert again["ev_history"] == first["ev_history"]
    assert again["episode_steps"] == first["episode_steps"] and again["best_select"] == first["best_select"]
    main = train_mod.train_or_reuse("mcr_official_2p", 1, smoke=True, gamma=0.99, timesteps=512)
    assert main["run_id"] != first["run_id"] and not main["reused"]


def test_real_training_needs_frozen_artifacts(fresh_home: Path) -> None:
    with pytest.raises(ConfigError, match=r"horizon\.json.*strongest_baseline\.json.*gamma\.json"):
        train_mod.train("mcr_official_2p", 1)
    assert not (fresh_home / "runs").exists() or not list((fresh_home / "runs").iterdir())


def test_cli_train_reuses_and_resumes(monkeypatch: pytest.MonkeyPatch) -> None:
    from propertyrl import cli

    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(train_mod, "train_or_reuse", lambda e, s, **k: calls.append(("reuse", s)) or {"run_id": e})
    monkeypatch.setattr(train_mod, "train", lambda e, s, **k: calls.append(("new", s)) or {"run_id": e})
    assert cli.main(["train", "--experiment", "mcr_official_2p", "--seed", "1"]) == 0
    assert cli.main(["train", "--experiment", "mcr_official_2p", "--seed", "2", "--new"]) == 0
    assert calls == [("reuse", 1), ("new", 2)]


def test_round_robin_ignores_frozen_horizon(fresh_home: Path) -> None:
    """G3 precedes the horizon calibration; a re-run after horizon.json exists reproduces the result (A-141)."""
    from propertyrl.evaluation.roundrobin import run_round_robin

    pols = ["random_legal", "greedy_v1"]
    before = run_round_robin(seeds_per_block=2, smoke=True, workers=1, policies=pols)
    write_json(fresh_home / "artifacts" / "frozen" / "horizon.json", {"horizon_2p": 3, "horizon_4p": 3})
    after = run_round_robin(seeds_per_block=2, smoke=True, workers=1, policies=pols)
    assert after["blocks"] == before["blocks"] and before["safety_horizon_rounds"] == 300
    state = json.loads((fresh_home / "artifacts" / "frozen" / "strongest_baseline_smoke.json").read_text("utf-8"))
    assert state["policy"] == before["strongest"]


def test_snapshot_thinning_keeps_the_champion(fresh_home: Path) -> None:
    """Thinning the pool must never delete the current champion's file (spec "sb3:<path>" vs pool path)."""
    from types import SimpleNamespace

    from propertyrl.training.callbacks import CheckpointEvalCallback, RunContext
    from propertyrl.training.selfplay import SnapshotPool

    exp, ppo, env_cfg = train_mod.resolve("selfplay_official_2p", 1, smoke=True)
    ctx = RunContext("r", fresh_home / "runs" / "r", exp, ppo, env_cfg, 1, True)
    ctx.pool = SnapshotPool(max_size=2)

    class Model:
        num_timesteps = 0

        def save(self, path: str) -> None:
            Path(path).write_bytes(f"weights {self.num_timesteps}".encode())

        def get_env(self) -> Any:
            return SimpleNamespace(env_method=lambda *args, **kwargs: None)

    cb = CheckpointEvalCallback(ctx)
    cb.model = Model()
    cb.gate = lambda candidate, t: None  # the champion gate itself is tested elsewhere
    for step in (100, 200, 300):
        cb.model.num_timesteps = step
        cb.snapshot(step)
        if step == 200:
            ctx.champion = f"sb3:{ctx.pool.paths[-1]}"
    champion = Path(ctx.champion.split(":", 1)[1])
    assert champion.name == "snap_0000000200.zip" and str(champion) not in ctx.pool.paths  # thinned out
    assert checkpoint_ok(champion)  # but still on disk for the next gate
