"""Scan the test-suite for rule-ID markers and golden scenarios (used by docs generation and coverage tests)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
_MARK = re.compile(r'pytest\.mark\.rule\(\s*"([A-Z]-\d{2,3})"\s*\)')
_DEF = re.compile(r"^\s*def (test_\w+)")
_ID = re.compile(r"\b([RPKDH])-(\d{2,3})\b")


def scan_tests(tests_dir: Path | None = None) -> dict[str, list[str]]:
    """Map rule ID -> list of test references (``path::test`` or golden scenario files)."""
    root = tests_dir or REPO / "tests"
    out: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        pending: list[str] = []
        rel = path.relative_to(REPO).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            pending.extend(_MARK.findall(line))
            m = _DEF.match(line)
            if m:
                for rid in pending:
                    out.setdefault(rid, []).append(f"{rel}::{m.group(1)}")
                pending = []
    for path in sorted((root / "golden" / "scenarios").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for rid in data.get("rules", []):
            out.setdefault(rid, []).append(path.relative_to(REPO).as_posix())
    return out


def rulespec_ids(path: Path | None = None) -> list[str]:
    """All R/P/K/D/H IDs defined in docs/RULESPEC.md (first column of the rule tables)."""
    text = (path or REPO / "docs" / "RULESPEC.md").read_text(encoding="utf-8")
    ids: list[str] = []
    for line in text.splitlines():
        if line.startswith("| ") and not line.startswith("| ID"):
            cell = line.split("|")[1].strip()
            m = _ID.fullmatch(cell)
            if m and cell not in ids:
                ids.append(cell)
    return ids
