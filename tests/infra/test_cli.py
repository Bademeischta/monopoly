"""CLI wiring (§9.7): every command parses, small commands run end-to-end against a private home."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from propertyrl.cli import build_parser, main
from propertyrl.evaluation import seeds
from propertyrl.infra.storage import read_json

COMMANDS = (
    "play", "replay", "fuzz", "markov-check", "benchmark", "calibrate-horizon", "round-robin", "power", "plan",
    "train", "sweep-gamma", "selfplay", "evaluate", "kingmaking", "report", "gates", "diagnose", "license-check",
    "repro", "pipeline", "doctor",
)  # fmt: skip


@pytest.fixture
def fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    forbidden = seeds.forbidden_seeds
    monkeypatch.setenv("PROPERTYRL_HOME", str(tmp_path))
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()
    yield tmp_path
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()


def test_all_commands_registered() -> None:
    parser = build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    assert set(COMMANDS) <= set(sub.choices)  # type: ignore[union-attr]
    for name in ("benchmark", "calibrate-horizon", "round-robin", "train", "evaluate", "report", "pipeline"):
        assert "--smoke" in sub.choices[name].format_help()  # type: ignore[union-attr]


def test_play_and_replay_roundtrip(fresh_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["play", "--seed", "3", "--p0", "greedy_v1", "--p1", "roi_markov_v1"]) == 0
    out = capsys.readouterr().out
    log_path = Path(out.strip().splitlines()[-1].split("Log: ", 1)[1])
    assert log_path.exists() and log_path.is_relative_to(fresh_home)
    assert main(["replay", "--log", str(log_path)]) == 0
    assert "Replay identisch: True" in capsys.readouterr().out


def test_replay_verify_archive(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["replay", "--verify-archive"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data and all(v["ok"] for v in data.values())


def test_power_and_freeze(fresh_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["power", "--p", "0.5", "--half-width", "0.02", "--freeze", "2p=1200,4p=250"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["n_games"] == 2401
    assert read_json(fresh_home / "artifacts" / "frozen" / "test_size.json") == {"2p": 1200, "4p": 250}


def test_fuzz_and_markov_small(fresh_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fuzz", "--ruleset", "OFFICIAL_US_CLASSIC_2008", "--decisions", "3000"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total_decisions"] >= 3000 and not data["errors"]
    assert (fresh_home / "artifacts" / "fuzz" / "fuzz_report.json").exists()
    # CLI wiring only (small sample); the acceptance check runs with 1M moves in tests/markov.
    code = main(["markov-check", "--moves", "20000", "--tolerance-pp", "1.0"])
    report = read_json(fresh_home / "artifacts" / "markov" / "markov_report.json")
    assert code == (0 if report["passed"] else 1)
    assert report["moves"] >= 20000


def test_gates_command(fresh_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["gates"])
    out = capsys.readouterr().out
    for g in ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"):
        assert f"{g}:" in out


def test_evaluate_smoke_command(fresh_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["evaluate", "--smoke", "--split", "smoke", "--agent", "greedy_v1", "--opponents", "random_legal",
                 "--n-seeds", "2", "--workers", "1"])  # fmt: skip
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["label"].startswith("SMOKE")
    assert data["opponents"]["random_legal"]["games"] == 4


def test_missing_arguments_return_usage_code(fresh_home: Path) -> None:
    assert main(["replay"]) == 2
    assert main(["train"]) == 2
    assert main(["pipeline"]) == 2


def test_evaluate_defaults_follow_experiment(fresh_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["evaluate", "--smoke", "--split", "smoke", "--agent", "greedy_v1", "--experiment", "mcr_official_2p",
                 "--n-seeds", "1", "--workers", "1"])  # fmt: skip
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    # experiment opponents: strongest_baseline (= strong_a_v1 before G3) is de-duplicated
    assert sorted(data["opponents"]) == sorted(["strong_a_v1", "strong_b_v1", "greedy_v1", "roi_markov_v1",
                                                "random_legal"])  # fmt: skip
    assert data["agent"] == "greedy_v1" and data["experiment"] == "mcr_official_2p"


def test_pipeline_reuses_existing_evaluations(fresh_home: Path) -> None:
    from propertyrl.infra.pipeline import _evaluate_once

    kw = {"opponents": ["random_legal"], "ruleset_id": "OFFICIAL_US_CLASSIC_2008", "n_players": 2,
          "label": "official", "n_seeds": 1, "workers": 1}  # fmt: skip
    first = _evaluate_once("greedy_v1", "exp_x", "smoke", True, **kw)
    second = _evaluate_once("greedy_v1", "exp_x", "smoke", True, **kw)
    assert second["eval_id"] == first["eval_id"]


def test_round_robin_policies_option() -> None:
    parser = build_parser()
    args = parser.parse_args(["round-robin", "--policies", "random_legal,strong_a_v1"])
    assert args.policies == "random_legal,strong_a_v1"
