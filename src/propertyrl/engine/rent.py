"""Rent computation (R-301 to R-307, P-11)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.state import GameState


def owns_full_group(state: GameState, owner: int, group: int) -> bool:
    """True if ``owner`` holds every property of ``group`` (mortgaged or not)."""
    for p in C.GROUP_PROPS[group]:
        if state.owner[p] != owner:
            return False
    return True


def count_owned(state: GameState, owner: int, group: int) -> int:
    """Number of properties of ``group`` held by ``owner`` (P-11: mortgaged ones count)."""
    n = 0
    for p in C.GROUP_PROPS[group]:
        if state.owner[p] == owner:
            n += 1
    return n


def street_rent(state: GameState, board: Board, p: int, level: int | None = None) -> int:
    """R-301/R-302 rent of a street at its current (or the given) level, ignoring mortgage status."""
    b = C.P_TO_B[p]
    lvl = state.level[b] if level is None else level
    rents = board.b_rents[b]
    if lvl == 0:
        base = rents[0]
        # R-301 double rent with the whole colour group, even if another street is mortgaged.
        if owns_full_group(state, state.owner[p], C.P_GROUP[p]):
            return 2 * base
        return base
    # R-302 rent with houses / hotel.
    return rents[lvl]


def rail_rent(state: GameState, board: Board, p: int) -> int:
    """R-303 rail rent by number of rails held (P-11 mortgaged rails count)."""
    n = count_owned(state, state.owner[p], C.RAIL_GROUP)
    return board.rail_rents[n - 1]


def util_multiplier(state: GameState, board: Board, p: int) -> int:
    """R-304 utility multiplier (4 or 10) by number of utilities held (P-11)."""
    n = count_owned(state, state.owner[p], C.UTIL_GROUP)
    return board.util_multipliers[n - 1]


def rent_due(state: GameState, board: Board, p: int, dice_total: int) -> int:
    """Rent owed when landing on p with a regular move; 0 for bank-owned or mortgaged (R-305)."""
    if state.owner[p] < 0 or state.mortgaged[p]:
        return 0
    g = C.P_GROUP[p]
    if g == C.RAIL_GROUP:
        return rail_rent(state, board, p)
    if g == C.UTIL_GROUP:
        return util_multiplier(state, board, p) * dice_total
    return street_rent(state, board, p)


def rent_now(state: GameState, board: Board, p: int, expected_dice: int = 7) -> int:
    """Current rent on landing with an expected dice sum for utilities (heuristic primitive)."""
    return rent_due(state, board, p, expected_dice)
