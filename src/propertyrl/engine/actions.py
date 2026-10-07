"""Flat Tier-1 action space Discrete(106) (§6.5, action_version a1.0)."""

from __future__ import annotations

from typing import Final

from propertyrl.engine import constants as C

ROLL: Final = 0
BUY: Final = 1
DECLINE: Final = 2
END_PHASE: Final = 3
PAY_JAIL_FINE: Final = 4
USE_JAIL_CARD: Final = 5
BUILD_BASE: Final = 6
SELL_BASE: Final = 28
MORTGAGE_BASE: Final = 50
UNMORTGAGE_BASE: Final = 78
N_ACTIONS: Final = 106

_SIMPLE_NAMES: Final = ("ROLL", "BUY", "DECLINE", "END_PHASE", "PAY_JAIL_FINE", "USE_JAIL_CARD")


def build(b: int) -> int:
    """Action id of BUILD_b."""
    return BUILD_BASE + b


def sell(b: int) -> int:
    """Action id of SELL_BUILDING_b."""
    return SELL_BASE + b


def mortgage(p: int) -> int:
    """Action id of MORTGAGE_p."""
    return MORTGAGE_BASE + p


def unmortgage(p: int) -> int:
    """Action id of UNMORTGAGE_p."""
    return UNMORTGAGE_BASE + p


def decode(action: int) -> tuple[str, int]:
    """Decode an action id into (type name, index) with index -1 for simple actions."""
    if not 0 <= action < N_ACTIONS:
        raise ValueError(f"action id {action} out of range")
    if action < BUILD_BASE:
        return _SIMPLE_NAMES[action], -1
    if action < SELL_BASE:
        return "BUILD", action - BUILD_BASE
    if action < MORTGAGE_BASE:
        return "SELL_BUILDING", action - SELL_BASE
    if action < UNMORTGAGE_BASE:
        return "MORTGAGE", action - MORTGAGE_BASE
    return "UNMORTGAGE", action - UNMORTGAGE_BASE


def action_name(action: int) -> str:
    """Readable name such as ``BUILD_b3`` or ``MORTGAGE_p12``."""
    kind, idx = decode(action)
    if idx < 0:
        return kind
    letter = "b" if kind in ("BUILD", "SELL_BUILDING") else "p"
    return f"{kind}_{letter}{idx}"


def all_action_names() -> list[str]:
    """Names of all 106 actions in id order."""
    return [action_name(a) for a in range(N_ACTIONS)]


assert C.N_BUILD == SELL_BASE - BUILD_BASE == MORTGAGE_BASE - SELL_BASE
assert C.N_PROPS == UNMORTGAGE_BASE - MORTGAGE_BASE == N_ACTIONS - UNMORTGAGE_BASE
