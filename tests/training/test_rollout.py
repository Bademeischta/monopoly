"""Machine-independent PPO rollout (A-146) and gamma files tied to it."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from propertyrl.engine.errors import ConfigError
from propertyrl.evaluation import seeds
from propertyrl.infra.config import PPOConfig, load_ppo_config
from propertyrl.infra.storage import write_json
from propertyrl.versions import ENV_VERSION

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


SHAPES = [(1, (1, 512)), (2, (2, 256)), (4, (4, 128)), (6, (4, 128)), (12, (8, 64)), (16, (16, 32)), (64, (16, 32))]


@pytest.mark.parametrize(("cores", "shape"), SHAPES)
def test_rollout_is_the_same_on_every_machine(cores: int, shape: tuple[int, int]) -> None:
    ppo = load_ppo_config()
    assert ppo.rollout_size == 512
    assert train_mod.rollout_shape(ppo, cores) == shape


def test_without_rollout_size_only_the_core_count_caps() -> None:
    ppo = PPOConfig(n_envs=16, n_steps=256)
    assert train_mod.rollout_shape(ppo, 4) == (4, 256)
    assert train_mod.rollout_shape(ppo, 32) == (16, 256)


def test_resolve_applies_the_rollout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(train_mod.os, "cpu_count", lambda: 16)
    _, ppo, _ = train_mod.resolve("mcr_official_2p", 1, gamma=0.99)
    assert (ppo.n_envs, ppo.n_steps) == (16, 32)
    _, smoke, _ = train_mod.resolve("mcr_official_2p", 1, smoke=True, gamma=0.99)
    assert smoke.n_envs * smoke.n_steps == smoke.rollout_size


def test_gamma_swept_with_another_rollout_is_rejected(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(train_mod.os, "cpu_count", lambda: 16)
    gamma = fresh_home / "artifacts" / "frozen" / "gamma.json"
    write_json(gamma, {"gamma": 0.99, "env_version": ENV_VERSION})  # swept before A-146 (rollout 4096)
    with pytest.raises(ConfigError, match=r"PPO rollout 4096, not 512.*sweep-gamma"):
        train_mod.resolve("mcr_official_2p", 1)
    write_json(gamma, {"gamma": 0.999, "env_version": ENV_VERSION, "rollout_size": 512})
    assert train_mod.resolve("mcr_official_2p", 1)[1].gamma == 0.999
    assert train_mod.effective_rollout("mcr_official_2p") == 512
