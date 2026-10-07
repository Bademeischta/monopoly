"""Documentation (§11, gate G0): every required document exists, is non-trivial, and the Python examples
in docs/API.md and README.md run."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
REQUIRED = (
    "RULESPEC.md", "ACTION_SCHEMA.md", "OBSERVATION_SCHEMA.md", "HEURISTICS_SPEC.md", "TEST_MATRIX.md",
    "BENCHMARK_PROTOCOL.md", "ARCHITECTURE.md", "API.md", "TRAINING_GUIDE.md", "ROADMAP.md", "RISKS.md",
    "ASSUMPTIONS.md", "LEGAL.md", "DATENSCHUTZ.md", "EXTERNAL_ANCHOR.md", "GLOSSARY.md", "IMPLEMENTATION_PLAN.md",
    "BUILD_REPORT.md",
)  # fmt: skip
PY_BLOCK = re.compile(r"```python\n(.*?)```", re.S)


@pytest.mark.parametrize("name", REQUIRED)
def test_document_exists(name: str) -> None:
    path = DOCS / name
    assert path.exists(), name
    text = path.read_text(encoding="utf-8")
    assert len(text) > 1500, name
    assert "\r\n" not in text


def test_root_documents() -> None:
    for name in ("README.md", "CHANGELOG.md", "LICENSE", "requirements.txt", "requirements-lock.txt"):
        assert (ROOT / name).exists(), name
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "<!-- legal-start -->" in readme and "<!-- legal-end -->" in readme
    assert "download.pytorch.org/whl/cpu" in readme
    assert "## 0.1.0" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_risks_and_assumptions_complete() -> None:
    risks = (DOCS / "RISKS.md").read_text(encoding="utf-8")
    for i in range(1, 37):
        assert f"R{i:02d}" in risks, i
    assumptions = (DOCS / "ASSUMPTIONS.md").read_text(encoding="utf-8")
    for i in range(1, 37):
        assert f"A-{i:02d}" in assumptions, i
    referenced = set(
        re.findall(r"A-1\d\d", "".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py")))
    )
    for ident in referenced:
        assert ident in assumptions, ident


def test_glossary_terms() -> None:
    text = (DOCS / "GLOSSARY.md").read_text(encoding="utf-8")
    for term in ("MCR", "Genuine Entscheidung", "Makroschritt", "Lernsitz", "Shared-Policy-MARL", "Delegation"):
        assert term in text, term


@pytest.mark.parametrize("doc", ["API.md", "README.md"])
def test_python_examples_run(doc: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = DOCS / doc if (DOCS / doc).exists() else ROOT / doc
    blocks = PY_BLOCK.findall(path.read_text(encoding="utf-8"))
    monkeypatch.setenv("PROPERTYRL_HOME", os.environ.get("PROPERTYRL_HOME", str(tmp_path)))
    for i, code in enumerate(blocks):
        namespace: dict[str, object] = {"__name__": f"doc_example_{i}"}
        exec(compile(code, f"{doc}#block{i}", "exec"), namespace)
