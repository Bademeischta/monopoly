"""Opponent sampler (§6.9): curriculum, self-play categories with PFSP, 4P seats, fallback."""

from __future__ import annotations

from collections import Counter

import pytest

from propertyrl.engine import ConfigError
from propertyrl.engine.rng import SeededStream
from propertyrl.env import OpponentConfig, OpponentSampler


def _plans(cfg: OpponentConfig, n: int, k: int = 4000) -> list:
    sampler = OpponentSampler(cfg, n)
    return [sampler.plan(SeededStream(7, i)) for i in range(k)]


def test_curriculum_stages() -> None:
    cfg = OpponentConfig(mode="curriculum")
    sampler = OpponentSampler(cfg, 2)
    assert set(sampler.plan(SeededStream(1)).opponents.values()) == {"random_legal"}
    sampler.set_stage(1)
    assert set(sampler.plan(SeededStream(1)).opponents.values()) == {"roi_markov_v1"}
    sampler.set_stage(5)
    names = Counter(next(iter(sampler.plan(SeededStream(i)).opponents.values())) for i in range(2000))
    assert set(names) == {"strong_a_v1", "strong_b_v1"} and abs(names["strong_a_v1"] / 2000 - 0.5) < 0.05


def test_selfplay_category_mix_and_pfsp() -> None:
    snaps = tuple(f"s{i}.zip" for i in range(8))
    cfg = OpponentConfig(mode="selfplay", snapshots=snaps, weights={"s0.zip": 1.0, "s1.zip": 0.0, "s2.zip": 0.0})
    plans = _plans(cfg, 2)
    cats = Counter(next(iter(p.category.values())) for p in plans)
    assert abs(cats["recent"] / len(plans) - 0.5) < 0.04
    assert abs(cats["old"] / len(plans) - 0.3) < 0.04
    assert abs(cats["baseline"] / len(plans) - 0.2) < 0.04
    olds = Counter(next(iter(p.opponent_ids.values())) for p in plans if next(iter(p.category.values())) == "old")
    assert set(olds) == {"s0.zip"}  # PFSP weight (1-p)^2 = 0 excludes the others
    recent = {next(iter(p.opponent_ids.values())) for p in plans if next(iter(p.category.values())) == "recent"}
    assert recent == set(snaps[-5:])


def test_selfplay_empty_old_pool_goes_to_recent() -> None:
    cfg = OpponentConfig(mode="selfplay", snapshots=("a.zip", "b.zip"))
    cats = Counter(next(iter(p.category.values())) for p in _plans(cfg, 2))
    assert "old" not in cats and abs(cats["recent"] / sum(cats.values()) - 0.8) < 0.04
    cats = Counter(next(iter(p.category.values())) for p in _plans(OpponentConfig(mode="selfplay"), 2, 300))
    assert set(cats) == {"baseline"}


def test_fourp_extra_learning_seats() -> None:
    plans = _plans(OpponentConfig(mode="fourp", snapshots=("a.zip",)), 4)
    extra = sum(len(p.learning_seats) - 1 for p in plans) / (3 * len(plans))
    assert abs(extra - 0.4) < 0.03
    assert all(1 <= len(p.learning_seats) <= 4 for p in plans)


def test_fourp_fallback_latest() -> None:
    plans = _plans(OpponentConfig(mode="fourp_fallback", latest_path="latest.zip"), 4)
    assert all(len(p.learning_seats) == 1 for p in plans)
    cats = Counter(c for p in plans for c in p.category.values())
    assert abs(cats["latest"] / sum(cats.values()) - 0.4) < 0.03
    assert any("latest:latest.zip" in s for p in plans for s in p.opponents.values())


def test_greedy_is_never_a_training_opponent() -> None:
    with pytest.raises(ConfigError):
        OpponentConfig(mode="fixed", fixed=("greedy_v1",))
    with pytest.raises(ConfigError):
        OpponentConfig(mode="nope")


def test_wrapping_and_config_roundtrip() -> None:
    cfg = OpponentConfig(mode="fixed", fixed=("strong_a_v1",), epsilon=0.1, shared_delegation=True)
    sampler = OpponentSampler(cfg, 2)
    pol = sampler.policy("strong_a_v1")
    assert pol.spec() == "epsilon:0.1:with_delegation:strong_a_v1"
    assert sampler.policy("strong_a_v1") is pol
    assert OpponentConfig.from_dict(cfg.to_dict()) == cfg
