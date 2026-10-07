"""Archived replays must reproduce their expected state hash exactly (§4.10)."""

from __future__ import annotations

import pytest

from propertyrl.engine import read_log, replay_log
from propertyrl.infra.archive import ARCHIVE_DIR, ARCHIVE_SPECS
from propertyrl.infra.storage import read_json

EXPECTED = read_json(ARCHIVE_DIR / "expected_hashes.json")


def test_at_least_six_archived_logs() -> None:
    assert len(EXPECTED) >= 6
    assert {s.name for s in ARCHIVE_SPECS} == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_archived_replay(name: str) -> None:
    log = read_log(ARCHIVE_DIR / f"{name}.jsonl")
    assert log["header"]["final_state_hash"] == EXPECTED[name]
    eng = replay_log(log)
    assert eng.state_hash() == EXPECTED[name]
