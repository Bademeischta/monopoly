"""Helpers for environment tests."""

from __future__ import annotations

from typing import Any

from propertyrl.env import EnvConfig, OpponentConfig


def cfg(**kw: Any) -> EnvConfig:
    """Small, fast environment configuration (fixed strong opponents)."""
    opp = kw.pop("opponents", None) or OpponentConfig(mode="fixed", fixed=("strong_a_v1", "strong_b_v1"), epsilon=0.0)
    kw.setdefault("safety_horizon_rounds", 120)
    return EnvConfig(opponents=opp, **kw)
