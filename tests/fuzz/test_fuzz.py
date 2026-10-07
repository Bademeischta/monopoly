"""CI fuzz: 100,000 decisions per configuration plus rare-event fuzz and event coverage (§10)."""

from __future__ import annotations

import os
from collections import Counter

import pytest
from rare_events import RARE_EVENT_TYPES, rare_event_fuzz

from propertyrl.engine.events import EVENT_TYPES
from propertyrl.infra.fuzz import FUZZ_CONFIGS, fuzz

CI_DECISIONS = int(os.environ.get("PROPERTYRL_FUZZ_DECISIONS", "100000"))
RARE_DECISIONS = int(os.environ.get("PROPERTYRL_RARE_DECISIONS", "100000"))
_SEEN: Counter[str] = Counter()


@pytest.mark.parametrize(("ruleset", "players"), FUZZ_CONFIGS, ids=[f"{r}-{n}p" for r, n in FUZZ_CONFIGS])
def test_fuzz_config(ruleset: str, players: int) -> None:
    report = fuzz(ruleset, players, CI_DECISIONS, seed=1)
    assert report.decisions == CI_DECISIONS
    assert not report.errors
    assert report.games >= 1
    _SEEN.update(report.event_counts)


@pytest.mark.rule("R-601")
def test_rare_event_fuzz() -> None:
    report = rare_event_fuzz(RARE_DECISIONS, seed=1)
    assert not report.errors
    for etype in RARE_EVENT_TYPES:
        assert report.event_counts.get(etype, 0) >= 100, (etype, report.event_counts.get(etype, 0))
    _SEEN.update(report.event_counts)


def test_event_coverage() -> None:
    """Every event type appears in fuzz, rare-event fuzz and golden games together."""
    from pathlib import Path

    import yaml
    from golden_runner import run

    counts: Counter[str] = Counter()
    counts.update(fuzz("OFFICIAL_US_CLASSIC_2008", 4, 20_000, seed=7).event_counts)
    counts.update(rare_event_fuzz(20_000, seed=7).event_counts)
    for path in sorted((Path(__file__).resolve().parents[1] / "golden" / "scenarios").glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            eng = run(yaml.safe_load(fh))
        counts.update(e.type for e in eng.events)
    missing = [t for t in EVENT_TYPES if counts.get(t, 0) == 0]
    assert not missing, missing
