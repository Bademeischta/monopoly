"""Target criteria Z3/Z4/Z5 (§8.4) on synthetic stored evaluations, and the gates that read them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from propertyrl.evaluation import seeds
from propertyrl.evaluation.criteria import load_records, z3, z4, z5
from propertyrl.evaluation.duplicate import summarize
from propertyrl.evaluation.evaluate import records_frame
from propertyrl.infra import gates
from propertyrl.infra.storage import record_eval_summary


@pytest.fixture
def fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    forbidden = seeds.forbidden_seeds
    monkeypatch.setenv("PROPERTYRL_HOME", str(tmp_path))
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()
    yield tmp_path
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()


def _game2(agent: str, opp: str, seed_index: int, rotation: int, agent_wins: bool) -> dict[str, Any]:
    seats = [agent, opp] if rotation == 0 else [opp, agent]
    agent_seat = seats.index(agent)
    winner = agent_seat if agent_wins else 1 - agent_seat
    placements = [1 if s == winner else 2 for s in range(2)]
    return {"seed": 1000 + seed_index, "seed_index": seed_index, "rotation": rotation, "ruleset_id": "R",
            "n_players": 2, "seats": seats, "winner": winner, "placements": placements, "rounds": 50,
            "decisions": 900, "truncated": False}  # fmt: skip


def _store(home: Path, eval_id: str, experiment: str, split: str, agent: str, groups: dict[str, list[dict[str, Any]]],
           smoke: bool = False) -> None:  # fmt: skip
    path = home / "artifacts" / "eval" / eval_id
    path.mkdir(parents=True, exist_ok=True)
    records = [r for recs in groups.values() for r in recs]
    records_frame(records).to_parquet(path / "games.parquet", index=False)
    summary = {"eval_id": eval_id, "agent": agent, "split": split, "experiment": experiment,
               "strongest_baseline": "strong_a_v1",
               "opponents": {k: summarize(v, agent, bootstrap_reps=500) for k, v in groups.items()}}  # fmt: skip
    record_eval_summary(eval_id, f"hash_{agent}", experiment, split, "R", 10, len(records), list(groups), summary,
                        path, smoke)  # fmt: skip


def _duel(agent: str, opp: str, n_seeds: int, win_share: float) -> list[dict[str, Any]]:
    games = []
    wins = round(win_share * 2 * n_seeds)
    for i in range(n_seeds):
        for rot in (0, 1):
            games.append(_game2(agent, opp, i, rot, len(games) < wins))
    return games


def test_records_roundtrip(fresh_home: Path) -> None:
    games = _duel("sb3:/x/a.zip", "strong_a_v1", 3, 0.5)
    _store(fresh_home, "e1", "mcr_official_2p", "test", "sb3:/x/a.zip", {"strong_a_v1": games})
    loaded = load_records(fresh_home / "artifacts" / "eval" / "e1")
    assert [(r["seats"], r["winner"], r["placements"]) for r in loaded] == [
        (g["seats"], g["winner"], g["placements"]) for g in games
    ]


def test_z3_pass_and_fail(fresh_home: Path) -> None:
    for k in range(3):
        agent = f"sb3:/runs/mcr_official_2p_s{k}/best_select.zip"
        _store(fresh_home, f"t{k}", "mcr_official_2p", "test", agent,
               {"strong_a_v1": _duel(agent, "strong_a_v1", 200, 0.62)})  # fmt: skip
    res = z3()
    assert res["evaluated"] and len(res["agents"]) == 3
    assert res["pooled"]["games"] == 1200
    assert res["pooled"]["win_rate"] == pytest.approx(0.62, abs=0.005)
    assert res["pooled"]["lower"] > 0.5
    assert res["passed"]
    assert gates.evaluate_gates("G5")["G5"]["status"] == gates.PASS
    # one seed with a point estimate below 50 % fails Z3 although the pool is above 50 %
    weak = "sb3:/runs/mcr_official_2p_s0/best_select.zip"
    _store(fresh_home, "t0b", "mcr_official_2p", "test", weak, {"strong_a_v1": _duel(weak, "strong_a_v1", 200, 0.45)})
    res2 = z3()
    assert len(res2["agents"]) == 3  # newest evaluation per agent hash
    assert not res2["passed"]
    assert gates.evaluate_gates("G5")["G5"]["status"] == gates.FAIL


def test_z3_requires_three_seeds(fresh_home: Path) -> None:
    agent = "sb3:/runs/mcr_official_2p_s1/best_select.zip"
    _store(fresh_home, "only", "mcr_official_2p", "test", agent, {"strong_a_v1": _duel(agent, "strong_a_v1", 200, 0.9)})
    assert not z3()["passed"]


def test_z4_components(fresh_home: Path) -> None:
    mcr = "sb3:/runs/mcr_official_2p_s1/best_select.zip"
    _store(
        fresh_home,
        "m",
        "mcr_official_2p",
        "test",
        mcr,
        {"strong_a_v1": _duel(mcr, "strong_a_v1", 100, 0.60), "strong_b_v1": _duel(mcr, "strong_b_v1", 100, 0.60)},
    )
    champ = "sb3:/runs/selfplay/champion.zip"
    snap = "sb3:/runs/selfplay/snapshots/snap_0000200000.zip"
    _store(fresh_home, "c", "selfplay_official_2p", "test", champ, {
        "strong_a_v1": _duel(champ, "strong_a_v1", 100, 0.59),
        "strong_b_v1": _duel(champ, "strong_b_v1", 100, 0.62),
        mcr: _duel(champ, mcr, 300, 0.60),
        snap: _duel(champ, snap, 100, 0.55),
    })  # fmt: skip
    res = z4()
    c = res["champions"][0]
    assert c["a_passed"] and c["b_passed"] and c["c_passed"]
    assert res["passed"]
    assert gates.evaluate_gates("G6")["G6"]["status"] == gates.PASS
    _store(fresh_home, "c2", "selfplay_official_2p", "test", champ, {
        "strong_a_v1": _duel(champ, "strong_a_v1", 100, 0.55),  # 5 pp below the MCR agent
        "strong_b_v1": _duel(champ, "strong_b_v1", 100, 0.62),
        mcr: _duel(champ, mcr, 300, 0.60),
        snap: _duel(champ, snap, 100, 0.55),
    })  # fmt: skip
    res2 = z4()
    assert not res2["champions"][0]["b_passed"] and not res2["passed"]


def _game4(agent: str, opps: list[str], seed_index: int, rotation: int, agent_place: int) -> dict[str, Any]:
    base = [agent, *opps]
    seats = [base[(k - rotation) % 4] for k in range(4)]
    others = [p for p in (1, 2, 3, 4) if p != agent_place]
    placements = []
    it = iter(others)
    for spec in seats:
        placements.append(agent_place if spec == agent else next(it))
    winner = placements.index(1)
    return {"seed": 5000 + seed_index, "seed_index": seed_index, "rotation": rotation, "ruleset_id": "R",
            "n_players": 4, "seats": seats, "winner": winner, "placements": placements, "rounds": 80,
            "decisions": 3000, "truncated": False}  # fmt: skip


def test_z5(fresh_home: Path) -> None:
    agent = "sb3:/runs/fourp/best_select.zip"
    opps = ["strong_a_v1", "strong_b_v1", "roi_markov_v1"]
    games = []
    for i in range(250):
        for rot in range(4):
            games.append(_game4(agent, opps, i, rot, 1 if (i + rot) % 5 < 2 else 3))
    _store(fresh_home, "f", "fourp_official", "test", agent, {"+".join(opps): games})
    res = z5()
    a = res["agents"][0]
    assert a["first_place_rate"] == pytest.approx(0.4)
    assert a["wilson_lower"] > 0.25
    assert set(a["rotations"]) == {0, 1, 2, 3}
    assert all(d["upper"] < 0 for d in a["placement_differences"].values())
    assert res["passed"]
    assert gates.evaluate_gates("G7")["G7"]["status"] == gates.PASS


def test_report_contains_criteria_and_holm(fresh_home: Path) -> None:
    from propertyrl.evaluation.report import generate_report

    for k in range(3):
        agent = f"sb3:/runs/mcr_official_2p_s{k}/best_select.zip"
        _store(fresh_home, f"r{k}", "mcr_official_2p", "test", agent, {
            "strong_a_v1": _duel(agent, "strong_a_v1", 300, 0.6),
            "greedy_v1": _duel(agent, "greedy_v1", 50, 0.7),
            "strong_b_v1": _duel(agent, "strong_b_v1", 50, 0.55),
        })  # fmt: skip
    path = generate_report("mcr_official_2p")
    text = path.read_text(encoding="utf-8")
    assert "### Z3" in text and "Z3 erfüllt: True" in text
    assert "p (Holm)" in text
    assert "(ungesehene Policy)" in text
    assert "## Gate-Status G0–G8" in text
    assert "SMOKE" not in text.split("## Gate-Status")[0]
