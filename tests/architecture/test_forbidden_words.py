"""No protected names from original editions in code, configs, docs or README (§10, §14)."""

from __future__ import annotations

import re
from pathlib import Path

from helpers import REPO

# The list is assembled from fragments so that this file itself never needs an exclusion hack.
FORBIDDEN = [
    "Mono" + "poly", "Has" + "bro", "Parker " + "Brothers", "Board" + "walk", "Park " + "Place",
    "Mediterranean " + "Avenue", "Baltic " + "Avenue", "Marvin " + "Gardens", "Reading " + "Railroad",
    "Short " + "Line", "Cha" + "nce", "Community " + "Chest", "Free " + "Parking", "Schloss" + "allee",
    "Park" + "straße", "Bad" + "straße", "Turm" + "straße", "Opern" + "platz", "Ereignis" + "feld",
    "Gemeinschafts" + "feld",
]  # fmt: skip
PATTERN = re.compile(r"\b(" + "|".join(re.escape(w) for w in FORBIDDEN) + r")\b")
SUFFIXES = {".py", ".yaml", ".yml", ".md", ".toml", ".txt", ".json", ".cfg"}


def _files() -> list[Path]:
    out = []
    for root in ("src", "configs", "docs", "tools", ".github"):
        for path in (REPO / root).rglob("*"):
            if path.is_file() and path.suffix in SUFFIXES and path.name != "LEGAL.md":
                out.append(path)
    for name in ("README.md", "CHANGELOG.md", "pyproject.toml"):
        if (REPO / name).exists():
            out.append(REPO / name)
    return out


def _strip_legal_section(text: str) -> str:
    start, end = "<!-- legal-start -->", "<!-- legal-end -->"
    while start in text and end in text:
        a = text.index(start)
        b = text.index(end, a) + len(end)
        text = text[:a] + text[b:]
    return text


def test_no_forbidden_words() -> None:
    hits = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.name == "README.md":
            text = _strip_legal_section(text)
        for m in PATTERN.finditer(text):
            hits.append(f"{path.relative_to(REPO)}: {m.group(0)}")
    assert not hits, hits


def test_pattern_detects_words() -> None:
    assert PATTERN.search("a " + FORBIDDEN[0] + " b")
    assert not PATTERN.search("Gewinn" + FORBIDDEN[10].lower())
