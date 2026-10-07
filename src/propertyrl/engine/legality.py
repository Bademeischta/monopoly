"""Legal action masks per phase (§3.11)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.building import place_targets
from propertyrl.engine.jail import can_pay_fine, can_use_card
from propertyrl.engine.mortgage import interest

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.game import Engine
    from propertyrl.engine.ruleset import Ruleset
    from propertyrl.engine.state import GameState


def management_mask(
    state: GameState,
    board: Board,
    ruleset: Ruleset,
    seat: int,
    mask: list[bool],
    build: bool = True,
    unmortgage: bool = True,
) -> None:
    """Set BUILD/SELL/MORTGAGE/UNMORTGAGE legality for ``seat`` into ``mask`` (in place)."""
    cash = state.cash[seat]
    owner = state.owner
    mortgaged = state.mortgaged
    level = state.level
    prepaid = state.interest_prepaid
    for g in range(C.N_GROUPS):
        props = C.GROUP_PROPS[g]
        full = True
        any_mortgaged = False
        any_owned = False
        for p in props:
            if owner[p] == seat:
                any_owned = True
                if mortgaged[p]:
                    any_mortgaged = True
            else:
                full = False
        if not any_owned:
            continue
        builds = C.GROUP_BUILDS[g]
        mx = 0
        mn = C.HOTEL_LEVEL
        for b in builds:
            lv = level[b]
            if lv > mx:
                mx = lv
            if lv < mn:
                mn = lv
        if builds:
            # R-401..R-404 building on the lowest level of a complete, unmortgaged group.
            if build and full and not any_mortgaged and mn < C.HOTEL_LEVEL:
                stock_ok = state.bank_hotels >= 1 if mn == C.HOTEL_LEVEL - 1 else state.bank_houses >= 1
                if stock_ok:
                    for b in builds:
                        if level[b] == mn and cash >= board.b_house_price[b]:
                            mask[A.BUILD_BASE + b] = True
            # R-405 selling evenly from the highest level.
            if mx > 0 and full:
                for b in builds:
                    if level[b] == mx:
                        mask[A.SELL_BASE + b] = True
        for p in props:
            if owner[p] != seat:
                continue
            if mortgaged[p]:
                if unmortgage:
                    mv = board.p_mortgage[p]
                    cost = mv if prepaid[p] >= 0 else mv + interest(ruleset, mv)
                    if cash >= cost:
                        mask[A.UNMORTGAGE_BASE + p] = True
            elif mx == 0:
                # R-501 mortgage only when no street of the group is built.
                mask[A.MORTGAGE_BASE + p] = True


def frame_mask(eng: Engine, frame: tuple[int, ...]) -> list[bool]:
    """Legal mask (106 bools) of a MAIN or DEBT decision frame."""
    state = eng.state
    board = eng.board
    rules = eng.ruleset
    mask = [False] * A.N_ACTIONS
    op = frame[0]
    seat = frame[1]
    if op == F.OP_D_WINDOW:
        wkind = frame[2]
        if wkind == F.W_PRE_ROLL:
            if state.in_jail[seat]:
                fine_ok = can_pay_fine(state, seat, rules.jail_fine)
                if rules.movement_only:
                    # TEST_MOVEMENT_ONLY fixed jail policy: always pay the fine immediately.
                    mask[A.PAY_JAIL_FINE] = fine_ok
                    mask[A.ROLL] = not fine_ok
                else:
                    mask[A.ROLL] = True
                    mask[A.PAY_JAIL_FINE] = fine_ok
                    mask[A.USE_JAIL_CARD] = can_use_card(state, seat)
            else:
                mask[A.ROLL] = True
        else:
            mask[A.END_PHASE] = True
        management_mask(state, board, rules, seat, mask)
    elif op == F.OP_D_BUY:
        p = frame[2]
        # P-09: raise money by mortgaging / selling before BUY or DECLINE.
        mask[A.BUY] = state.cash[seat] >= board.p_price[p]
        mask[A.DECLINE] = True
        management_mask(state, board, rules, seat, mask, build=False, unmortgage=False)
    elif op == F.OP_D_DEBT:
        # P-06: only MORTGAGE and SELL_BUILDING.
        management_mask(state, board, rules, seat, mask, build=False, unmortgage=False)
    elif op == F.OP_D_PLACE:
        for b in place_targets(state, board, seat, frame[2] == F.I_HOTEL):
            mask[A.BUILD_BASE + b] = True
    return mask
