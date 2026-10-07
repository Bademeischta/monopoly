"""Every R/P/K/D/H ID in docs/RULESPEC.md has at least one test (§10)."""

from __future__ import annotations

import sys

from helpers import REPO

sys.path.insert(0, str(REPO / "tools"))

from rule_scan import rulespec_ids, scan_tests
from rulespec_data import D_RULES, H_RULES, K_RULES, P_RULES, R_RULES


def test_rulespec_contains_all_ids() -> None:
    ids = rulespec_ids()
    expected = [rid for rows in (R_RULES, P_RULES, K_RULES, D_RULES, H_RULES) for rid, _ in rows]
    assert ids == expected
    assert len([i for i in ids if i.startswith("R-")]) == 57


def test_every_rule_id_has_a_test() -> None:
    refs = scan_tests()
    missing = [rid for rid in rulespec_ids() if not refs.get(rid)]
    assert not missing, missing


def test_house_rules_have_negative_tests() -> None:
    refs = scan_tests()
    for i in range(1, 10):
        assert refs.get(f"H-{i:02d}"), i
