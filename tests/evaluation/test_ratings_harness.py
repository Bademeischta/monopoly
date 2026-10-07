"""Ratings (§8.6), round-robin ranking (§8.9), duplicate harness (§8.3/§8.4), horizon (§8.10), kingmaking (§8.8)."""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

import pytest

from propertyrl.evaluation import seeds
from propertyrl.evaluation.duplicate import agent_seat, duplicate_specs, per_seed_scores, score, summarize
from propertyrl.evaluation.harness import GameSpec, play_game, run_games
from propertyrl.evaluation.horizon import calibrate
from propertyrl.evaluation.kingmaking import KingmakingParams, run_kingmaking
from propertyrl.evaluation.metrics import agent_metrics, seat_win_rates
from propertyrl.evaluation.ratings import elo, openskill
from propertyrl.evaluation.roundrobin import copeland, run_round_robin, significant_cycles


@pytest.fixture
def fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    forbidden = seeds.forbidden_seeds
    monkeypatch.setenv("PROPERTYRL_HOME", str(tmp_path))
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()
    yield tmp_path
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()


def _rec(seats: list[str], winner: int | None, placements: list[int], truncated: bool = False) -> dict[str, Any]:
    return {
        "seats": seats,
        "winner": winner,
        "placements": placements,
        "truncated": truncated,
        "n_players": len(seats),
        "rotation": 0,
        "seed": 1,
        "seed_index": 0,
        "rounds": 10,
    }


def test_elo_conserves_points_and_orders() -> None:
    records = [_rec(["a", "b"], 0, [1, 2]) for _ in range(20)] + [_rec(["b", "a"], 1, [2, 1]) for _ in range(20)]
    ratings = elo(records)
    assert ratings["a"] > 1500 > ratings["b"]
    assert ratings["a"] + ratings["b"] == pytest.approx(3000.0)
    draws = elo([_rec(["a", "b"], None, [1, 2], truncated=True) for _ in range(10)])
    assert draws["a"] == pytest.approx(1500.0) and draws["b"] == pytest.approx(1500.0)
    assert elo(records, seed=3) == elo(records, seed=3)


def test_openskill_orders_by_placements() -> None:
    records = [_rec(["a", "b", "c", "d"], 0, [1, 2, 3, 4]) for _ in range(30)]
    ratings = openskill(records)
    ordinals = [ratings[x]["ordinal"] for x in "abcd"]
    assert ordinals == sorted(ordinals, reverse=True)
    # identical policies in several seats are not rated against themselves
    assert openskill([_rec(["a", "a"], 0, [1, 2])])["a"]["mu"] == pytest.approx(25.0)


def test_copeland_and_cycles() -> None:
    pols = ["x", "y", "z"]
    strong = {"win_rate": 0.8, "wilson_lower": 0.7, "wilson_upper": 0.9}
    pairs = {("x", "y"): strong, ("y", "z"): strong, ("x", "z"): strong}
    ranking = copeland(pairs, pols)
    assert [r[0] for r in ranking] == ["x", "y", "z"]
    assert [r[1] for r in ranking] == [2, 1, 0]
    assert significant_cycles(pairs, pols) == []
    weak_back = {"win_rate": 0.2, "wilson_lower": 0.1, "wilson_upper": 0.3}
    cyclic = {("x", "y"): strong, ("y", "z"): strong, ("x", "z"): weak_back}
    assert significant_cycles(cyclic, pols) == [("x", "y", "z")]
    insignificant = {"win_rate": 0.45, "wilson_lower": 0.4, "wilson_upper": 0.5}
    assert significant_cycles({("x", "y"): strong, ("y", "z"): strong, ("x", "z"): insignificant}, pols) == []


def test_duplicate_specs_rotations() -> None:
    two = duplicate_specs("A", ["B"], [11, 12], "OFFICIAL_US_CLASSIC_2008", 2)
    assert [(s.seed, s.seats, s.rotation) for s in two] == [
        (11, ("A", "B"), 0),
        (11, ("B", "A"), 1),
        (12, ("A", "B"), 0),
        (12, ("B", "A"), 1),
    ]
    four = duplicate_specs("A", ["B", "C", "D"], [5], "OFFICIAL_US_CLASSIC_2008", 4)
    assert len(four) == 4
    assert sorted(s.seats.index("A") for s in four) == [0, 1, 2, 3]
    for s in four:
        # cyclic rotation keeps the relative order A, B, C, D
        i = s.seats.index("A")
        assert [s.seats[(i + k) % 4] for k in range(4)] == ["A", "B", "C", "D"]


def test_scores_and_summary() -> None:
    win = _rec(["A", "B"], 0, [1, 2])
    loss = _rec(["B", "A"], 0, [1, 2])
    trunc = _rec(["A", "B"], None, [2, 1], truncated=True)
    assert score(win, "A") == 1.0
    assert score(loss, "A") == 0.0
    assert score(trunc, "A") == 0.5
    assert score(trunc, "A", sensitivity=True) == 0.0
    same = _rec(["A", "A"], 1, [2, 1])
    same["rotation"] = 1
    assert agent_seat(same, "A") == 1
    s = summarize([win, loss, trunc], "A", bootstrap_reps=200)
    assert s["games"] == 3
    assert s["win_rate"] == pytest.approx(0.5)
    assert s["truncation_rate"] == pytest.approx(1 / 3)
    assert per_seed_scores([win, loss], "A") == {0: 0.5}
    with pytest.raises(ValueError):
        agent_seat(win, "C")


def test_play_game_and_parallel_equality(fresh_home: Path) -> None:
    specs = duplicate_specs(
        "greedy_v1", ["roi_markov_v1"], seeds.subset("SMOKE", start=0, end=2), "OFFICIAL_US_CLASSIC_2008"
    )
    serial = [play_game(s) for s in specs]
    parallel = run_games(specs, workers=2, chunksize=1)
    strip = ("runtime_s",)
    assert [{k: v for k, v in r.items() if k not in strip} for r in serial] == [
        {k: v for k, v in r.items() if k not in strip} for r in parallel
    ]
    for r in serial:
        assert sorted(r["placements"]) == [1, 2]
        assert r["truncated"] or r["winner"] in (0, 1)
    metrics = agent_metrics(serial, "greedy_v1")
    assert set(metrics["placement_distribution"]) == {1, 2}
    assert len(seat_win_rates(serial)) == 2


def test_safety_horizon_truncates(fresh_home: Path) -> None:
    rec = play_game(GameSpec("OFFICIAL_US_CLASSIC_2008", 7, ("random_legal", "random_legal"), 0, 3))
    assert rec["truncated"]
    assert rec["winner"] is None
    assert sorted(rec["placements"]) == [1, 2]


def test_horizon_formula(fresh_home: Path) -> None:
    res = calibrate(n_games=6, n_players=2, smoke=True, workers=1)
    assert res["games"] == 6
    if res["natural_games"] >= 2:
        assert res["horizon"] == math.ceil(res["median_rounds"] + 2 * res["sd_rounds"])
        assert res["sd_rounds"] >= 0
        assert isinstance(statistics.median([1, 2]), float)
    assert res["passed"] == (res["truncation_rate"] < 0.05)


def test_round_robin_smoke_writes_frozen_file(fresh_home: Path) -> None:
    res = run_round_robin(seeds_per_block=2, smoke=True, workers=1, policies=["random_legal", "greedy_v1"])
    assert set(res["blocks"]) == {"block1", "block2"}
    assert res["strongest"] in ("random_legal", "greedy_v1")
    assert (fresh_home / "artifacts" / "frozen" / "strongest_baseline_smoke.json").exists()
    assert not (fresh_home / "artifacts" / "frozen" / "strongest_baseline.json").exists()
    assert not (fresh_home / "artifacts" / "roundrobin" / "latest.json").exists()  # read by the real report


def test_kingmaking_small(fresh_home: Path) -> None:
    specs = duplicate_specs("greedy_v1", ["roi_markov_v1"] * 3, seeds.subset("SMOKE", start=0, end=1),
                            "OFFICIAL_US_CLASSIC_2008", 4)  # fmt: skip
    params = KingmakingParams(games=1, points_per_game=1, alternatives=2, rollouts=2, max_rollout_decisions=20_000)
    res = run_kingmaking(specs, params)
    assert res["games"] == 1
    assert all(0.0 <= w <= 1.0 for w in res["ws_values"])
    assert 0.0 <= res["kingmaking_rate"] <= 1.0
