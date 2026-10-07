"""Equity functions (§4.9) - the single implementation used everywhere."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.state import GameState


def _building_cost(state: GameState, board: Board, seat: int) -> int:
    total = 0
    for b in range(C.N_BUILD):
        lvl = state.level[b]
        if lvl and state.owner[C.B_TO_P[b]] == seat:
            total += lvl * board.b_house_price[b]  # hotel = 5 x house price
    return total


def canonical_equity(state: GameState, board: Board, seat: int) -> int:
    """E_i = cash + printed price (unmortgaged) + half printed price (mortgaged) + building cost."""
    if state.bankrupt[seat]:
        return 0
    total = state.cash[seat]
    for p in range(C.N_PROPS):
        if state.owner[p] == seat:
            price = board.p_price[p]
            total += price // 2 if state.mortgaged[p] else price
    return total + _building_cost(state, board, seat)


def liquidation_value(state: GameState, board: Board, seat: int) -> int:
    """L_i = cash + mortgage value of unmortgaged properties + half building cost."""
    if state.bankrupt[seat]:
        return 0
    total = state.cash[seat]
    for p in range(C.N_PROPS):
        if state.owner[p] == seat and not state.mortgaged[p]:
            total += board.p_mortgage[p]
    return total + _building_cost(state, board, seat) // 2


def weighted_equity(state: GameState, board: Board, seat: int) -> float:
    """Ew_i (ablation A2): printed prices weighted 2.0 / 1.5 / 1.0 by colour-group ownership."""
    if state.bankrupt[seat]:
        return 0.0
    total = float(state.cash[seat])
    for g in range(C.N_GROUPS):
        props = C.GROUP_PROPS[g]
        owned = sum(1 for p in props if state.owner[p] == seat)
        if owned == 0:
            continue
        if g >= C.N_COLOR_GROUPS:
            weight = 1.0
        elif owned == len(props):
            weight = 2.0
        elif owned >= 2:
            weight = 1.5
        else:
            weight = 1.0
        for p in props:
            if state.owner[p] == seat:
                price = board.p_price[p]
                total += weight * (price / 2 if state.mortgaged[p] else price)
    return total + _building_cost(state, board, seat)


def all_equities(state: GameState, board: Board) -> list[int]:
    """Canonical equity of every seat."""
    return [canonical_equity(state, board, s) for s in range(state.n_players)]


def equity_shares(state: GameState, board: Board) -> list[float]:
    """E_i / sum E over active players (1/N_active if the sum is 0; 0 for bankrupt seats)."""
    eq = all_equities(state, board)
    active = [s for s in range(state.n_players) if not state.bankrupt[s]]
    total = sum(eq[s] for s in active)
    out = [0.0] * state.n_players
    for s in active:
        out[s] = eq[s] / total if total > 0 else 1.0 / len(active)
    return out
