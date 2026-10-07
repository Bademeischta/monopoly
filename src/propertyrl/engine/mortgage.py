"""Mortgages (R-501, R-502, R-503, P-05, P-13)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C
from propertyrl.engine.events import CNT_MORTGAGES, CNT_UNMORTGAGES

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.game import Engine
    from propertyrl.engine.ruleset import Ruleset
    from propertyrl.engine.state import GameState


def interest(ruleset: Ruleset, mortgage_value: int) -> int:
    """P-05: 10 % interest rounded up to a whole number."""
    return C.ceil_div(mortgage_value * ruleset.mortgage_interest_percent, 100)


def group_has_buildings(state: GameState, p: int) -> bool:
    """True if any street of p's colour group carries a building."""
    for b in C.GROUP_BUILDS[C.P_GROUP[p]]:
        if state.level[b] > 0:
            return True
    return False


def can_mortgage(state: GameState, seat: int, p: int) -> bool:
    """R-501: own, unmortgaged, and no building anywhere in the colour group."""
    return state.owner[p] == seat and not state.mortgaged[p] and not group_has_buildings(state, p)


def unmortgage_cost(state: GameState, board: Board, ruleset: Ruleset, p: int) -> int:
    """R-502 principal plus 10 % interest; principal only while interest_prepaid is active (P-13)."""
    mv = board.p_mortgage[p]
    if state.interest_prepaid[p] >= 0:
        return mv
    return mv + interest(ruleset, mv)


def can_unmortgage(state: GameState, board: Board, ruleset: Ruleset, seat: int, p: int) -> bool:
    """UNMORTGAGE_p legality: own, mortgaged and cash covers the cost."""
    return (
        state.owner[p] == seat and state.mortgaged[p] and state.cash[seat] >= unmortgage_cost(state, board, ruleset, p)
    )


def do_mortgage(eng: Engine, seat: int, p: int) -> None:
    """R-501: mortgage p; the bank pays the mortgage value."""
    state = eng.state
    state.mortgaged[p] = True
    state.interest_prepaid[p] = -1
    mv = eng.board.p_mortgage[p]
    eng.transfer(C.BANK, seat, mv, "MORTGAGE")
    eng.cnt(CNT_MORTGAGES, seat)
    eng.emit("PROPERTY_MORTGAGED", seat, {"p": p, "amount": mv})


def do_unmortgage(eng: Engine, seat: int, p: int) -> None:
    """R-502 / P-13: repay the mortgage."""
    state = eng.state
    cost = unmortgage_cost(state, eng.board, eng.ruleset, p)
    principal_only = state.interest_prepaid[p] >= 0
    eng.transfer(seat, C.BANK, cost, "UNMORTGAGE")
    state.mortgaged[p] = False
    state.interest_prepaid[p] = -1
    eng.cnt(CNT_UNMORTGAGES, seat)
    eng.emit("PROPERTY_UNMORTGAGED", seat, {"p": p, "amount": cost, "principal_only": principal_only})


def receive_mortgaged(eng: Engine, receiver: int, p: int) -> int:
    """R-503: set the P-13 option marker on a received mortgaged property; return the interest due."""
    state = eng.state
    state.interest_prepaid[p] = state.window_counter
    return interest(eng.ruleset, eng.board.p_mortgage[p])
