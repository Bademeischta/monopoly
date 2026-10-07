"""Code-quality rules: module size, no print in library code, no placeholders, public exports (§Qualität)."""

from __future__ import annotations

import ast
import importlib

from helpers import REPO

SRC = REPO / "src" / "propertyrl"
ALLOWED_PLACEHOLDER_FILES = {"external.py", "base.py"}


def test_modules_below_800_lines() -> None:
    too_long = []
    for path in SRC.rglob("*.py"):
        n = len(path.read_text(encoding="utf-8").splitlines())
        if n >= 800:
            too_long.append((str(path.relative_to(REPO)), n))
    assert not too_long, too_long


def test_no_print_in_library_code() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "cli.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert not offenders, offenders


def test_no_placeholders() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in ("TO" + "DO", "FIX" + "ME", "NotImplemented" + "Error"):
            if marker in text and path.name not in ALLOWED_PLACEHOLDER_FILES:
                offenders.append(f"{path.relative_to(REPO)}: {marker}")
    assert not offenders, offenders


def test_files_utf8_lf() -> None:
    for root in ("src", "tests", "configs", "docs", "tools"):
        for path in (REPO / root).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yaml", ".md", ".json", ".jsonl"}:
                data = path.read_bytes()
                assert b"\r\n" not in data, path
                data.decode("utf-8")


def test_public_api_exports() -> None:
    for pkg in ("engine", "agents", "env", "training", "evaluation", "infra"):
        mod = importlib.import_module(f"propertyrl.{pkg}")
        exported = getattr(mod, "__all__", [])
        assert exported, pkg
        for name in exported:
            assert hasattr(mod, name), (pkg, name)
