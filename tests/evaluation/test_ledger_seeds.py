"""Seed pools (§8.1) and the TEST ledger (§8.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from propertyrl.engine.errors import ConfigError, SeedLedgerError
from propertyrl.evaluation import ledger, seeds
from propertyrl.evaluation.evaluate import evaluate_agent
from propertyrl.infra.config import load_seeds_config


@pytest.fixture
def fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    forbidden = seeds.forbidden_seeds
    monkeypatch.setenv("PROPERTYRL_HOME", str(tmp_path))
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()
    yield tmp_path
    seeds._load_cached.cache_clear()
    forbidden.cache_clear()


def test_pools_disjoint_sized_and_checksummed(fresh_home: Path) -> None:
    cfg = load_seeds_config()
    pools = seeds.load_pools()
    for name in seeds.POOL_ORDER:
        assert len(pools[name]) == cfg.pools[name].size
        assert all(0 <= s < 2**63 for s in pools[name])
    seeds.check_disjoint(pools)
    all_seeds = [s for p in pools.values() for s in p]
    assert len(all_seeds) == len(set(all_seeds))
    checks = json.loads((fresh_home / "artifacts" / "seeds" / "checksums.json").read_text(encoding="utf-8"))
    assert checks == seeds.pool_checksums()
    assert pools == seeds.generate_pools()


def test_check_disjoint_detects_overlap() -> None:
    with pytest.raises(SeedLedgerError):
        seeds.check_disjoint({"SELECT": [1, 2], "TEST": [2, 3]})
    with pytest.raises(SeedLedgerError):
        seeds.check_disjoint({"SELECT": [1, 1]})


def test_tampered_pool_is_rejected(fresh_home: Path) -> None:
    seeds.load_pools()
    path = fresh_home / "artifacts" / "seeds" / "test.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[0] += 1
    path.write_text(json.dumps(data), encoding="utf-8")
    seeds._load_cached.cache_clear()
    with pytest.raises(SeedLedgerError, match="checksum"):
        seeds.load_pools()


def test_subsets_and_train_seeds(fresh_home: Path) -> None:
    cfg = load_seeds_config()
    for name, (lo, hi) in cfg.subsets.items():
        assert 0 <= lo < hi <= cfg.pools["SELECT"].size
        assert seeds.subset("SELECT", name) == seeds.load_pools()["SELECT"][lo:hi]
    forbidden = seeds.forbidden_seeds()
    for episode in range(200):
        s, counter = seeds.train_seed(1, 0, episode)
        assert s not in forbidden
        assert counter >= episode


def test_train_seed_skips_collisions(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first, _ = seeds.train_seed(4, 2, 10)
    monkeypatch.setattr(seeds, "forbidden_seeds", lambda: frozenset({first}))
    s, counter = seeds.train_seed(4, 2, 10)
    assert s != first
    assert counter == 11


def test_ledger_refuses_second_test(fresh_home: Path) -> None:
    h = ledger.agent_hash("strong_a_v1")
    assert ledger.is_empty()
    ledger.record(h, "exp", "OFFICIAL_US_CLASSIC_2008", 1200, "r1")
    assert not ledger.is_empty()
    with pytest.raises(SeedLedgerError):
        ledger.check(h)
    with pytest.raises(SeedLedgerError):
        ledger.record(h, "exp", "OFFICIAL_US_CLASSIC_2008", 1200, "r2")
    ledger.record(h, "exp", "OFFICIAL_US_CLASSIC_2008", 1200, "r3", force=True)
    rows = ledger.entries(h)
    assert [r["forced"] for r in rows] == [0, 1]
    other = ledger.agent_hash("greedy_v1")
    assert other != h
    ledger.check(other)


def test_agent_hash_of_checkpoint_is_file_hash(fresh_home: Path) -> None:
    ckpt = fresh_home / "model.zip"
    ckpt.write_bytes(b"abc")
    h1 = ledger.agent_hash(f"sb3:{ckpt}")
    ckpt.write_bytes(b"abd")
    assert ledger.agent_hash(f"sb3:{ckpt}") != h1


def test_smoke_never_touches_test_split(fresh_home: Path) -> None:
    with pytest.raises(ConfigError):
        evaluate_agent("random_legal", ["greedy_v1"], "test", smoke=True)
    summary = evaluate_agent("random_legal", ["greedy_v1"], "smoke", n_seeds=2, workers=1, experiment="t")
    assert summary["smoke"] is True
    assert summary["n_games"] == 4
    assert summary["label"].startswith("SMOKE")
    assert ledger.is_empty()


def _freeze_g3(home: Path) -> None:
    frozen = home / "artifacts" / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    (frozen / "horizon.json").write_text(json.dumps({"horizon_2p": 300, "horizon_4p": 300}), encoding="utf-8")
    (frozen / "strongest_baseline.json").write_text(json.dumps({"policy": "strong_a_v1"}), encoding="utf-8")


def test_test_split_needs_frozen_g3_artifacts(fresh_home: Path) -> None:
    with pytest.raises(ConfigError, match="horizon"):
        evaluate_agent("random_legal", ["greedy_v1"], "test", n_seeds=1, workers=1, experiment="t")
    assert ledger.is_empty()


def test_test_split_records_ledger_once(fresh_home: Path) -> None:
    _freeze_g3(fresh_home)
    summary = evaluate_agent("random_legal", ["greedy_v1"], "test", n_seeds=1, workers=1, experiment="t")
    assert summary["split"] == "test"
    assert len(ledger.entries(summary["agent_hash"])) == 1
    with pytest.raises(SeedLedgerError):
        evaluate_agent("random_legal", ["greedy_v1"], "test", n_seeds=1, workers=1, experiment="t")
    test_pool = set(seeds.load_pools()["TEST"])
    select_pool = set(seeds.load_pools()["SELECT"])
    assert not (test_pool & select_pool)


def test_test_summary_and_ledger_commit_together(fresh_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An interruption between the summary row and the ledger row leaves neither (one transaction, A-139)."""
    import propertyrl.evaluation.evaluate as evaluate_mod

    _freeze_g3(fresh_home)

    def interrupted(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(evaluate_mod, "record_eval_summary", interrupted)
    with pytest.raises(KeyboardInterrupt):
        evaluate_agent("random_legal", ["greedy_v1"], "test", n_seeds=1, workers=1, experiment="t")
    assert ledger.is_empty()
    (eval_dir,) = (fresh_home / "artifacts" / "eval").iterdir()
    assert (eval_dir / "games.parquet").exists()  # games were stored before the database transaction
    monkeypatch.undo()
    monkeypatch.setenv("PROPERTYRL_HOME", str(fresh_home))
    summary = evaluate_agent("random_legal", ["greedy_v1"], "test", n_seeds=1, workers=1, experiment="t")
    assert len(ledger.entries(summary["agent_hash"])) == 1


def test_stored_evaluation_is_found_only_for_identical_settings(fresh_home: Path) -> None:
    from propertyrl.evaluation.evaluate import stored_evaluation

    done = evaluate_agent("random_legal", ["greedy_v1"], "select", n_seeds=2, workers=1, experiment="t")
    again = stored_evaluation("random_legal", ["greedy_v1"], "select", n_seeds=2, experiment="t")
    assert again is not None and again["eval_id"] == done["eval_id"]
    assert stored_evaluation("random_legal", ["greedy_v1"], "select", n_seeds=3, experiment="t") is None
    assert stored_evaluation("random_legal", ["roi_markov_v1"], "select", n_seeds=2, experiment="t") is None
    assert stored_evaluation("greedy_v1", ["greedy_v1"], "select", n_seeds=2, experiment="t") is None


def test_seed_pools_rebuild_after_torn_write(fresh_home: Path) -> None:
    pools = seeds.load_pools()
    seeds._load_cached.cache_clear()
    (fresh_home / "artifacts" / "seeds" / "select.json").write_bytes(b"\x00" * 64)  # power-off remains
    assert seeds.load_pools() == pools
    seeds._load_cached.cache_clear()
    assert seeds.load_pools() == pools  # the file was rewritten
    seeds._load_cached.cache_clear()
    checks = fresh_home / "artifacts" / "seeds" / "checksums.json"
    checks.write_text(json.dumps({"SELECT": "0" * 64}), encoding="utf-8")
    (fresh_home / "artifacts" / "seeds" / "test.json").write_text("[1, 2", encoding="utf-8")
    with pytest.raises(SeedLedgerError):  # a readable but different checksum is never overwritten silently
        seeds.load_pools()


def test_resolve_agent_specs(tmp_path: Path) -> None:
    from propertyrl.evaluation.evaluate import resolve_agent

    ckpt = tmp_path / "best_select.zip"
    assert resolve_agent(str(ckpt)) == f"sb3:{ckpt.resolve()}"
    assert resolve_agent(f"sb3:{ckpt}") == f"sb3:{ckpt}"
    assert resolve_agent(f"snapshot:{ckpt}") == f"snapshot:{ckpt}"
    assert resolve_agent("strong_a_v1") == "strong_a_v1"
    with pytest.raises(ConfigError):
        resolve_agent("experiment:mcr_official_2p:99")
