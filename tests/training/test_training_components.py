"""Curriculum, snapshot pool, PFSP, champion gate, smoke overrides, budget and resume (§6.9, §7.5–§7.10)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from propertyrl.evaluation import seeds
from propertyrl.infra.config import load_experiment, load_ppo_config
from propertyrl.infra.runmeta import load_run_meta
from propertyrl.training.budget import BudgetCallback, estimate_hours, eval_hours
from propertyrl.training.curriculum import CurriculumController
from propertyrl.training.selfplay import SnapshotPool, champion_gate, pfsp_weights
from propertyrl.training.smoke import apply_smoke, smoke_settings

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


def test_curriculum_threshold_and_steps() -> None:
    cc = CurriculumController(
        [
            {"opponents": ["random_legal"], "threshold": 0.8, "max_steps": 1000},
            {"opponents": ["roi_markov_v1"], "threshold": 0.6, "max_steps": 1000},
            {"opponents": ["strong_a_v1", "strong_b_v1"]},
        ]
    )
    assert cc.opponents == ["random_legal"]
    assert not cc.update(100, 0.79)
    assert cc.update(200, 0.80)
    assert cc.stage == 1 and cc.stage_start_step == 200
    assert not cc.update(1100, None)
    assert cc.update(1200, None)  # step budget of the stage used up
    assert cc.final and cc.opponents == ["strong_a_v1", "strong_b_v1"]
    assert not cc.update(10**9, 1.0)
    assert [h["reason"] for h in cc.history] == ["threshold", "steps"]
    clone = CurriculumController(cc.stages)
    clone.load(cc.state())
    assert clone.state() == cc.state()


def test_snapshot_pool_even_thinning() -> None:
    pool = SnapshotPool(max_size=5)
    removed: list[str] = []
    for step in range(0, 10_000, 1000):
        removed += pool.add(f"/r/snapshots/snap_{step:010d}.zip")
    assert len(pool.paths) == 5
    assert len(removed) == 5
    # the newest snapshots are always kept, the oldest one stays as anchor
    assert pool.paths[-1].endswith("snap_0000009000.zip")
    assert pool.paths[0].endswith("snap_0000000000.zip")
    steps = [SnapshotPool._step(p) for p in pool.paths]
    assert steps == sorted(steps)


def test_pfsp_weights() -> None:
    w = pfsp_weights({"weak": [9, 10], "strong": [1, 10], "new": [0, 0]})
    assert w["strong"] > w["new"] > w["weak"]
    assert w["new"] == pytest.approx(0.25)
    assert w["weak"] == pytest.approx((1 - 10 / 12) ** 2)


def test_champion_gate_rules(fresh_home: Path) -> None:
    block = seeds.subset("SMOKE", start=0, end=3)
    res = champion_gate("random_legal", "strong_a_v1", "OFFICIAL_US_CLASSIC_2008", [block, block], 2.0, workers=1)
    assert not res["passed"]
    assert len(res["blocks"]) == 1  # stops after a failed first block
    assert res["blocks"][0]["wilson_lower"] <= 0.5


def test_smoke_overrides_reduce_sizes() -> None:
    so = smoke_settings()
    exp, ppo = apply_smoke(load_experiment("mcr_official_2p"), load_ppo_config())
    assert ppo.total_timesteps == so.mcr_timesteps
    assert ppo.n_envs == so.n_envs and ppo.batch_size == so.batch_size
    assert len(exp.training.seeds) == so.training_seeds
    assert [s.get("max_steps") for s in exp.opponents.curriculum_stages][:2] == so.curriculum_thresholds
    exp2, ppo2 = apply_smoke(load_experiment("ablation_a0_terminal"), load_ppo_config())
    assert ppo2.total_timesteps == so.other_timesteps


def test_budget_helpers() -> None:
    assert estimate_hours(3600, 1.0) == pytest.approx(1.0)
    assert eval_hours(7200, 2.0) == pytest.approx(1.0)
    cb = BudgetCallback(0.0)
    cb.start -= 1.0
    assert cb._on_step() is False
    assert cb.exceeded


def test_resume_continues_interrupted_run(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class InterruptingBudget(BudgetCallback):
        calls = 0

        def _on_step(self) -> bool:
            InterruptingBudget.calls += 1
            if InterruptingBudget.calls == 300:
                raise KeyboardInterrupt
            return super()._on_step()

    monkeypatch.setattr(train_mod, "BudgetCallback", InterruptingBudget)
    with pytest.raises(KeyboardInterrupt):
        train_mod.train("mcr_official_2p", 1, smoke=True, timesteps=1024)
    runs = list((fresh_home / "runs").iterdir())
    assert len(runs) == 1
    meta = load_run_meta(runs[0])
    assert meta["status"] == "interrupted"
    assert (runs[0] / "final.zip").exists()
    done_before = int(meta["timesteps_done"])
    assert 0 < done_before < 1024
    monkeypatch.setattr(train_mod, "BudgetCallback", BudgetCallback)
    res: dict[str, Any] = train_mod.train("", 0, resume=runs[0])
    assert res["run_id"] == meta["run_id"]
    assert res["status"] == "completed"
    assert 1024 <= res["timesteps"] < 1024 + 2 * 512
    assert load_run_meta(runs[0])["status"] == "completed"
