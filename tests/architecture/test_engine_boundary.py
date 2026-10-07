"""Engine boundary: only the standard library may be imported (§4.1)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from helpers import REPO, run_python

ENGINE_DIR = REPO / "src" / "propertyrl" / "engine"
FORBIDDEN = ("numpy", "torch", "gymnasium", "pettingzoo", "stable_baselines3", "sb3_contrib", "yaml", "pydantic",
             "pandas", "scipy")  # fmt: skip


def test_fresh_interpreter_has_no_rl_modules() -> None:
    code = (
        "import sys, propertyrl.engine, propertyrl.engine.markov, propertyrl.engine.scenario\n"
        f"bad = [m for m in {FORBIDDEN!r} if m in sys.modules]\n"
        "print('BAD=' + ','.join(bad))\n"
    )
    proc = run_python(code)
    assert proc.returncode == 0, proc.stderr
    assert "BAD=\n" in proc.stdout or proc.stdout.strip() == "BAD=", proc.stdout


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_engine_sources_import_stdlib_only() -> None:
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for path in sorted(ENGINE_DIR.glob("*.py")):
        for root in _imported_roots(path):
            assert root in stdlib or root == "propertyrl", (path.name, root)


def test_engine_imports_only_engine_and_versions() -> None:
    for path in sorted(ENGINE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("propertyrl"):
                assert node.module.startswith(("propertyrl.engine", "propertyrl.versions")), (
                    path.name,
                    node.module,
                )
