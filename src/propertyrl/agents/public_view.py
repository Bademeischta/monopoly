"""Public view handed to policies and small read-only helpers on it."""

from __future__ import annotations

from propertyrl.engine import constants as C
from propertyrl.engine.view import PublicState


def own_properties(view: PublicState, seat: int | None = None) -> list[int]:
    """Property indices held by ``seat`` (default: the viewer)."""
    s = view.seat if seat is None else seat
    return [p for p in range(C.N_PROPS) if view.owner[p] == s]


def opponents(view: PublicState) -> list[int]:
    """Active seats other than the viewer, in turn order starting after the viewer."""
    n = view.n_players
    return [(view.seat + k) % n for k in range(1, n) if not view.bankrupt[(view.seat + k) % n]]


def complete_groups(view: PublicState, seat: int | None = None) -> list[int]:
    """Colour groups held completely by ``seat``."""
    s = view.seat if seat is None else seat
    return [g for g in range(C.N_COLOR_GROUPS) if all(view.owner[q] == s for q in C.GROUP_PROPS[g])]


__all__ = ["PublicState", "complete_groups", "opponents", "own_properties"]
