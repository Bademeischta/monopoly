"""Golden games: YAML scenarios with DiceScript, card order, scripted responses and expected end states."""

from __future__ import annotations

from pathlib import Path

import pytest
from golden_runner import SCENARIOS, check, load, run


def test_at_least_19_scenarios() -> None:
    assert len(SCENARIOS) >= 19


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_golden(path: Path) -> None:
    spec = load(path)
    eng = run(spec)
    check(eng, spec["expect"])
