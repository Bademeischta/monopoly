"""Gate evaluation from artifacts (§12), compute planning (§7.11) and the license check (§9.6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from propertyrl.evaluation import seeds
from propertyrl.infra import gates
from propertyrl.infra.licenses import FORBIDDEN, check_licenses, runtime_packages, split_licenses
from propertyrl.infra.plan import plan
from propertyrl.infra.storage import write_json

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest">
<testcase classname="tests.architecture.test_rule_coverage" name="test_every_rule_id_tested"/>
<testcase classname="tests.golden.test_golden" name="test_golden[g01]"/>
<testcase classname="tests.property.test_state_machine" name="TestEngineMachine::runTest"/>
<testcase classname="tests.mutation.test_mutants_killed" name="test_mutant[m01]"/>
<testcase classname="tests.determinism.test_archived_replays" name="test_replay[a]"/>
<testcase classname="tests.fuzz.test_fuzz" name="test_event_coverage"/>
<testcase classname="tests.env.test_env_api" name="test_gymnasium_check_env"/>
<testcase classname="tests.env.test_env_api" name="test_sb3_check_env"/>
<testcase classname="tests.env.test_env_api" name="test_pettingzoo_api"/>
<testcase classname="tests.env.test_masks_leak" name="test_masked_random_steps_never_illegal[steps100000]"/>
<testcase classname="tests.env.test_vecenv" name="test_dummy_and_subproc_spawn_identical">{failure}</testcase>
<testcase classname="tests.env.test_multiseat" name="test_one_learning_seat_equivalent_to_single_env"/>
</testsuite></testsuites>
"""

COVERAGE = """<?xml version="1.0" ?>
<coverage line-rate="0.85" branch-rate="0.8">
<packages><package name="engine"><classes>
<class filename="src/propertyrl/engine/game.py">
<lines>
{lines}
</lines>
</class>
</classes></package></packages>
</coverage>
"""


@pytest.fixture
def fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    forbidden = seeds.forbidden_seeds
    monkeypatch.setenv("PROPERTYRL_HOME", str(tmp_path))
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()
    yield tmp_path
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()


def _write_reports(home: Path, failure: str = "", covered: int = 96) -> None:
    d = home / "artifacts" / "test-reports"
    d.mkdir(parents=True, exist_ok=True)
    (d / "junit.xml").write_text(JUNIT.format(failure=failure), encoding="utf-8")
    lines = []
    for i in range(100):
        hits = 1 if i < covered else 0
        branch = ' branch="true" condition-coverage="100% (2/2)"' if i < 10 else ""
        lines.append(f'<line number="{i + 1}" hits="{hits}"{branch}/>')
    (d / "coverage.xml").write_text(COVERAGE.format(lines="\n".join(lines)), encoding="utf-8")


def test_gates_without_artifacts_are_ready_not_failed(fresh_home: Path) -> None:
    res = gates.evaluate_gates()
    assert set(res) == set(gates.GATES)
    assert res["G0"]["status"] == gates.PASS  # docs are part of the repository
    for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"):
        assert res[g]["status"] == gates.READY, (g, res[g])


def test_gate_g1_g2_from_reports(fresh_home: Path) -> None:
    _write_reports(fresh_home)
    write_json(fresh_home / "artifacts" / "fuzz" / "fuzz_report.json", {
        "configs": [{"decisions": 100_000}], "total": {"decisions": 600_000, "errors": []},
        "rare_event_min_counts": {"a": 120, "b": 150},
    })  # fmt: skip
    write_json(fresh_home / "artifacts" / "markov" / "markov_report.json",
               {"moves": 1_000_000, "tolerance_pp": 0.15, "passed": True, "max_abs_diff_pp": 0.05})  # fmt: skip
    write_json(fresh_home / "artifacts" / "benchmarks" / "benchmark_x.json",
               {"engine": {"with_logging": {}, "without_logging": {}}})  # fmt: skip
    res = gates.evaluate_gates()
    assert res["G1"]["status"].startswith(gates.PASS)
    assert "CI-Größe" in res["G1"]["status"]
    assert res["G2"]["status"].startswith(gates.PASS)
    assert "CI-Größe" in res["G2"]["status"]
    cov = gates.coverage()
    assert cov is not None
    assert cov["engine_line"] == pytest.approx(0.96)
    assert cov["engine_branch"] == pytest.approx(1.0)


def test_gate_failures_detected(fresh_home: Path) -> None:
    _write_reports(fresh_home, failure='<failure message="x"/>', covered=90)
    res = gates.evaluate_gates()
    assert res["G2"]["status"] == gates.FAIL
    cov_crit = next(c for c in res["G1"]["criteria"] if c["name"] == "Coverage-Schwellen")
    assert cov_crit["status"] == gates.FAIL
    write_json(fresh_home / "artifacts" / "markov" / "markov_report.json",
               {"moves": 1_000_000, "tolerance_pp": 0.15, "passed": False, "max_abs_diff_pp": 0.5})  # fmt: skip
    assert gates.evaluate_gates("G1")["G1"]["status"] == gates.FAIL


def test_gate_g3_uses_frozen_files_and_smoke_evidence(fresh_home: Path) -> None:
    frozen = fresh_home / "artifacts" / "frozen"
    write_json(frozen / "strongest_baseline_smoke.json", {"policy": "strong_a_v1", "passed": True})
    g3 = gates.evaluate_gates("G3")["G3"]
    assert g3["status"] == gates.READY
    assert "Smoke-Nachweis" in g3["criteria"][0]["detail"]
    write_json(frozen / "strongest_baseline.json", {"policy": "strong_a_v1", "passed": True})
    write_json(frozen / "horizon.json", {"horizon_2p": 200, "horizon_4p": 250, "passed": True})
    assert gates.evaluate_gates("G3")["G3"]["status"] == gates.PASS


def test_plan_rows_and_warnings(fresh_home: Path) -> None:
    res = plan(["mcr_official_2p", "ablation_no_trade"], smoke=False)
    assert [r["experiment"] for r in res["runs"]] == ["mcr_official_2p", "ablation_no_trade"]
    for row in res["runs"]:
        assert row["hours_per_run"] > 0
        assert row["eval_hours_per_run"] > 0
    assert res["total_train_hours"] > 0
    assert isinstance(res["warnings"], list)
    smoke = plan(["mcr_official_2p"], smoke=True)
    assert smoke["runs"][0]["timesteps"] < res["runs"][0]["timesteps"]


def test_license_identifiers_exact() -> None:
    assert split_licenses("MIT OR Apache-2.0") == ["MIT", "Apache-2.0"]
    assert split_licenses("BSD License; MIT License") == ["BSD License", "MIT License"]
    assert "LGPL-3.0" not in FORBIDDEN
    assert "GNU Lesser General Public License v3 (LGPLv3)" not in FORBIDDEN
    assert "MPL-2.0" not in FORBIDDEN
    assert "GPL-3.0" in FORBIDDEN and "AGPL-3.0" in FORBIDDEN


def test_runtime_license_check_passes() -> None:
    pkgs = runtime_packages()
    assert "gymnasium" in pkgs and "stable-baselines3" in pkgs
    res = check_licenses()
    assert res["passed"], (res["violations"], res["unknown_not_allowlisted"])


def test_benchmark_smoke(fresh_home: Path) -> None:
    from propertyrl.infra.benchmark import run_benchmark

    res = run_benchmark(seconds=0.3, smoke=True, max_envs=1)
    assert {"with_logging", "without_logging"} <= set(res["engine"])
    assert {"with_logging", "without_logging"} <= set(res["gym_env"])
    assert res["engine"]["without_logging"]["games"] >= 1
    assert res["recommendation"]["n_envs"] == 1
    assert res["ppo"]["train_steps_per_s"] > 0
    assert Path(res["path"]).exists()
    assert gates.evaluate_gates("G2")["G2"]["criteria"][-1]["status"] == gates.PASS


def test_gate_size_mask_run_merges_reports(fresh_home: Path) -> None:
    _write_reports(fresh_home)
    env_report = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.env.test_masks_leak" name="test_masked_random_steps_never_illegal[steps1000000]"/>
</testsuite></testsuites>"""
    (fresh_home / "artifacts" / "test-reports" / "junit_env.xml").write_text(env_report, encoding="utf-8")
    crit = next(c for c in gates.gate_g2() if c["name"].startswith("0 illegale"))
    assert crit["status"] == f"{gates.PASS} (Gate-Größe)"
    assert "1,000,000" in crit["detail"]


def test_gate_g8_uses_newest_repro(fresh_home: Path) -> None:
    import os

    repro = fresh_home / "artifacts" / "repro"
    write_json(repro / "repro_zzz_old.json", {"match": False})
    write_json(repro / "repro_aaa_new.json", {"match": True})
    os.utime(repro / "repro_zzz_old.json", (1, 1))
    crit = gates.gate_g8()[0]
    assert crit["status"] == gates.PASS and crit["detail"] == "repro_aaa_new.json"


def test_horizon_gate_is_judged_on_2p(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from propertyrl.evaluation import horizon

    def fake(n_games: int, n_players: int, smoke: bool, workers: Any) -> dict[str, Any]:
        rate = 0.02 if n_players == 2 else 0.37
        return {"horizon": 100 + n_players, "truncation_rate": rate, "passed": rate < 0.05}

    monkeypatch.setattr(horizon, "calibrate", fake)
    res = horizon.calibrate_horizon(10, smoke=False, workers=1)
    assert res["passed"] is True and res["passed_4p"] is False
    g3 = gates.gate_g3()[1]
    assert g3["status"] == gates.PASS and "4P separat" in g3["detail"]
