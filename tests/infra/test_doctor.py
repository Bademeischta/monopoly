"""`propertyrl doctor` (A-142): damaged files, interrupted runs, missing database, leftovers, next step."""

from __future__ import annotations

from pathlib import Path

import pytest

from propertyrl.cli import main
from propertyrl.evaluation import seeds
from propertyrl.infra.doctor import ERROR, INFO, WARN, doctor
from propertyrl.infra.runmeta import build_run_meta, save_run_meta
from propertyrl.infra.storage import write_json


@pytest.fixture
def fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    forbidden = seeds.forbidden_seeds
    monkeypatch.setenv("PROPERTYRL_HOME", str(tmp_path))
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()
    yield tmp_path
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()


def _levels(res: dict, item: str) -> list[str]:
    return [f["level"] for f in res["findings"] if item in f["item"]]


def test_empty_home_is_clean_and_untouched(fresh_home: Path) -> None:
    res = doctor()
    assert res["errors"] == 0
    assert res["next_step"].startswith("Schritt 4")
    assert list(fresh_home.iterdir()) == []  # read-only


def test_damaged_frozen_file_is_an_error_with_repair_command(
    fresh_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_json(fresh_home / "artifacts" / "frozen" / "strongest_baseline.json", {"policy": "strong_a_v1"})
    (fresh_home / "artifacts" / "frozen" / "horizon.json").write_bytes(b"\x00" * 32)
    res = doctor()
    assert _levels(res, "horizon.json") == [ERROR]
    (bad,) = [f for f in res["findings"] if "horizon.json" in f["item"]]
    assert "propertyrl calibrate-horizon" in bad["action"]
    (fresh_home / "artifacts" / "test-reports").mkdir(parents=True)
    (fresh_home / "artifacts" / "test-reports" / "junit.xml").write_text("<testsuites/>", encoding="utf-8")
    write_json(fresh_home / "artifacts" / "roundrobin" / "latest.json", {"strongest": "strong_a_v1"})
    assert doctor()["next_step"] == "Schritt 5: propertyrl calibrate-horizon"
    assert main(["doctor"]) == 1
    assert "FEHLER" in capsys.readouterr().out


def test_interrupted_run_and_missing_database(fresh_home: Path) -> None:
    meta = build_run_meta("mcr_official_2p_s1_20261009-120000_1", "mcr_official_2p", "OFFICIAL_US_CLASSIC_2008",
                          "abc", 1, 4096, 12.0, False)  # fmt: skip
    meta.update(status="running", timesteps_done=1000)
    save_run_meta(meta)
    res = doctor()
    (run,) = [f for f in res["findings"] if f["item"].startswith("runs/mcr_official_2p_s1")]
    assert run["level"] == WARN and "kein intakter Checkpoint" in run["detail"]
    assert "--seed 1" in run["action"]
    (fresh_home / "artifacts" / "propertyrl.db").unlink()
    res = doctor()
    assert _levels(res, "propertyrl.db") == [ERROR] and res["errors"] == 1


def test_temp_files_are_reported_and_cleaned(fresh_home: Path) -> None:
    import os
    import time

    import psutil

    dead = next(pid for pid in range(4_000_000, 4_100_000) if not psutil.pid_exists(pid))
    leftover = fresh_home / "runs" / "r" / f".final.tmp-{dead}.zip"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(b"x")
    in_flight = fresh_home / "runs" / "r" / f".training_state.tmp-{os.getpid()}.json"
    in_flight.write_bytes(b"{")  # a write of a running process must never be touched
    old = time.time() - 3600
    os.utime(leftover, (old, old))
    os.utime(in_flight, (old, old))
    (finding,) = [f for f in doctor()["findings"] if f["item"] == "Temporärdateien"]
    assert finding["level"] == INFO and finding["detail"].startswith("1 ")
    doctor(clean_temp=True)
    assert not leftover.exists() and in_flight.exists()


def test_malformed_database_is_reported_not_crashed(fresh_home: Path) -> None:
    db = fresh_home / "artifacts" / "propertyrl.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"\x00" * 4096)  # what a broken disk or a torn copy leaves behind
    res = doctor()
    assert _levels(res, "propertyrl.db") == [ERROR]
    assert res["next_step"].startswith("zuerst die Datenbank")


def test_next_step_respects_the_g4_stop_rule(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With G4 failed, doctor must never send the user to the TEST evaluation of step 7."""
    import importlib

    from propertyrl.infra.storage import record_eval_summary

    train_mod = importlib.import_module("propertyrl.training.train")

    (fresh_home / "artifacts" / "test-reports").mkdir(parents=True)
    (fresh_home / "artifacts" / "test-reports" / "junit.xml").write_text("<testsuites/>", encoding="utf-8")
    write_json(fresh_home / "artifacts" / "roundrobin" / "latest.json", {"strongest": "strong_a_v1"})
    frozen = fresh_home / "artifacts" / "frozen"
    for name, data in (("strongest_baseline", {"policy": "strong_a_v1"}), ("horizon", {"horizon_2p": 140}),
                       ("test_size", {"2p": 1200}), ("gamma", {"gamma": 0.999})):  # fmt: skip
        write_json(frozen / f"{name}.json", data)
    monkeypatch.setattr(train_mod, "find_checkpoint", lambda *args, **kwargs: fresh_home / "best_select.zip")
    summary = {"opponents": {"random_legal": {"win_rate": 0.95}, "roi_markov_v1": {"win_rate": 0.42}}}
    record_eval_summary("select_x", "h", "mcr_official_2p", "select", "OFFICIAL_US_CLASSIC_2008", 200, 800,
                        ["random_legal", "roi_markov_v1"], summary, fresh_home / "e", False)  # fmt: skip
    res = doctor()
    assert res["next_step"].startswith("Schritt 6: G4 nicht bestanden")
    summary["opponents"]["roi_markov_v1"]["win_rate"] = 0.55
    record_eval_summary("select_y", "h2", "mcr_official_2p", "select", "OFFICIAL_US_CLASSIC_2008", 200, 800,
                        ["random_legal", "roi_markov_v1"], summary, fresh_home / "e2", False)  # fmt: skip
    assert doctor()["next_step"] == "Schritt 7: propertyrl pipeline --experiment mcr_official_2p"
