"""Shared fixtures for the PropertyRL test-suite."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Every test session runs against a private PROPERTYRL_HOME (artifacts/runs/reports),
# set before any test module imports propertyrl infrastructure.
if "PROPERTYRL_HOME" not in os.environ:
    os.environ["PROPERTYRL_HOME"] = tempfile.mkdtemp(prefix="prl_home_")

# Mutation testing: apply a curated mutant before any test runs (tests/mutation/mutants.py).
_MUTANT = os.environ.get("PROPERTYRL_MUTANT")
if _MUTANT:
    sys.path.insert(0, str(TESTS_DIR / "mutation"))
    import mutants as _mutants

    _mutants.apply(_MUTANT)
