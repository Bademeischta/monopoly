"""Every curated mutant must be killed by its test subset (run in a subprocess, §10)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from mutants import MUTANTS

REPO = Path(__file__).resolve().parents[2]


def _run(tests: list[str], mutant: str | None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PROPERTYRL_MUTANT", None)
    if mutant is not None:
        env["PROPERTYRL_MUTANT"] = mutant
    env.pop("COV_CORE_SOURCE", None)
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-p", "no:randomly", *tests]
    return subprocess.run(cmd, cwd=str(REPO), env=env, capture_output=True, text=True, timeout=600)


def test_at_least_17_mutants() -> None:
    assert len(MUTANTS) >= 17


def test_target_tests_pass_without_mutant() -> None:
    tests = sorted({t for _, ts in MUTANTS.values() for t in ts})
    proc = _run(tests, None)
    assert proc.returncode == 0, proc.stdout[-3000:]


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_mutant_killed(name: str) -> None:
    proc = _run(MUTANTS[name][1], name)
    # Return code 1 = tests ran and failed (2-5 would be usage/collection errors).
    assert proc.returncode == 1, (name, proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
