"""Building and selling buildings (R-401 to R-406, P-08) plus demand helpers for P-19."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C
from propertyrl.engine.events import CNT_BUILD_SPEND, CNT_HOTELS, CNT_HOUSES, CNT_SOLD

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.game import Engine
    from propertyrl.engine.state import GameState


def group_buildable(state: GameState, seat: int, group: int) -> bool:
    """R-401: the seat owns the complete colour group and no member is mortgaged."""
    if group >= C.N_COLOR_GROUPS:
        return False
    for p in C.GROUP_PROPS[group]:
        if state.owner[p] != seat or state.mortgaged[p]:
            return False
    return True


def can_build_level(levels: list[int], state: GameState, seat: int, b: int, hotel_ok: bool, house_ok: bool) -> bool:
    """R-401/R-402/R-403 structural legality of building on b given a level vector."""
    g = C.B_GROUP[b]
    if not group_buildable(state, seat, g):
        return False
    lvl = levels[b]
    if lvl >= C.HOTEL_LEVEL:
        return False
    # R-402 even building: only on the lowest level of the group.
    for m in C.GROUP_BUILDS[g]:
        if levels[m] < lvl:
            return False
    if lvl == C.HOTEL_LEVEL - 1:
        # R-403: all streets on >= 4 is implied by lvl being the group minimum.
        return hotel_ok
    return house_ok


def can_build(state: GameState, board: Board, seat: int, b: int) -> bool:
    """BUILD_b legality including R-404 bank stock and cash >= house price."""
    if state.cash[seat] < board.b_house_price[b]:
        return False
    return can_build_level(state.level, state, seat, b, state.bank_hotels >= 1, state.bank_houses >= 1)


def is_hotel_build(state: GameState, b: int) -> bool:
    """True if building on b would place a hotel."""
    return state.level[b] == C.HOTEL_LEVEL - 1


def can_sell(state: GameState, seat: int, b: int) -> bool:
    """R-405: sell evenly from the highest level of the group downwards."""
    lvl = state.level[b]
    if lvl <= 0 or state.owner[C.B_TO_P[b]] != seat:
        return False
    for m in C.GROUP_BUILDS[C.B_GROUP[b]]:
        if state.level[m] > lvl:
            return False
    return True


def do_build(eng: Engine, seat: int, b: int) -> None:
    """Place one house or hotel on b and pay the house price to the bank."""
    state = eng.state
    price = eng.board.b_house_price[b]
    eng.transfer(seat, C.BANK, price, "BUILD")
    eng.cnt(CNT_BUILD_SPEND, seat, price)
    if state.level[b] == C.HOTEL_LEVEL - 1:
        # R-403: hotel costs one house price; the four houses return to the bank.
        state.level[b] = C.HOTEL_LEVEL
        state.bank_hotels -= 1
        state.bank_houses += 4
        eng.cnt(CNT_HOTELS, seat)
        eng.emit("HOTEL_BUILT", seat, {"b": b, "price": price})
    else:
        state.level[b] += 1
        state.bank_houses -= 1
        eng.cnt(CNT_HOUSES, seat)
        eng.emit("HOUSE_BUILT", seat, {"b": b, "level": state.level[b], "price": price})


def do_sell(eng: Engine, seat: int, b: int) -> None:
    """R-405/R-406/P-08: sell one building level on b (hotel may sell down the whole group)."""
    state = eng.state
    price = eng.board.b_house_price[b]
    half = price // 2
    if state.level[b] == C.HOTEL_LEVEL:
        if state.bank_houses >= 4:
            # R-406 hotel back to four houses.
            state.level[b] = C.HOTEL_LEVEL - 1
            state.bank_houses -= 4
            state.bank_hotels += 1
            eng.transfer(C.BANK, seat, half, "SELL")
            eng.cnt(CNT_SOLD, seat)
            eng.emit("BUILDING_SOLD", seat, {"b": b, "level": state.level[b], "refund": half})
            return
        _sell_down_group(eng, seat, b)
        return
    state.level[b] -= 1
    state.bank_houses += 1
    eng.transfer(C.BANK, seat, half, "SELL")
    eng.cnt(CNT_SOLD, seat)
    eng.emit("BUILDING_SOLD", seat, {"b": b, "level": state.level[b], "refund": half})


def sell_down_target(state: GameState, b: int) -> int:
    """P-08: highest uniform level of b's group that the bank house stock allows."""
    members = C.GROUP_BUILDS[C.B_GROUP[b]]
    houses_on = [state.level[m] if state.level[m] < C.HOTEL_LEVEL else 0 for m in members]
    for target in range(C.HOTEL_LEVEL - 1, -1, -1):
        needed = sum(target - h for h in houses_on)
        if needed <= state.bank_houses:
            return target
    return 0


def _sell_down_group(eng: Engine, seat: int, b: int) -> None:
    """P-08 atomic sell-down of the whole group to the highest uniform level allowed."""
    state = eng.state
    g = C.B_GROUP[b]
    members = C.GROUP_BUILDS[g]
    target = sell_down_target(state, b)
    units = 0
    for m in members:
        lvl = state.level[m]
        units += lvl - target
        if lvl == C.HOTEL_LEVEL:
            state.bank_hotels += 1
            state.bank_houses -= target
        else:
            state.bank_houses += lvl - target
        state.level[m] = target
    refund = units * (eng.board.b_house_price[b] // 2)
    eng.transfer(C.BANK, seat, refund, "SELL")
    eng.cnt(CNT_SOLD, seat, units)
    eng.emit(
        "GROUP_SOLD_DOWN",
        seat,
        {"b": b, "group": g, "target_level": target, "units": units, "refund": refund},
    )


def sell_all_buildings(eng: Engine, seat: int) -> int:
    """R-702/R-703: return all buildings of ``seat`` to the bank at half price; return the proceeds."""
    state = eng.state
    total = 0
    for b in range(C.N_BUILD):
        lvl = state.level[b]
        if lvl == 0 or state.owner[C.B_TO_P[b]] != seat:
            continue
        if lvl == C.HOTEL_LEVEL:
            state.bank_hotels += 1
        else:
            state.bank_houses += lvl
        total += lvl * (eng.board.b_house_price[b] // 2)
        state.level[b] = 0
    if total:
        eng.transfer(C.BANK, seat, total, "BANKRUPTCY")
    return total


def _demand(state: GameState, board: Board, seat: int, hotels: bool) -> int:
    """P-19 demand: buildings the seat could build in sequence with unlimited bank stock."""
    cash = state.cash[seat]
    groups = [g for g in range(C.N_COLOR_GROUPS) if group_buildable(state, seat, g)]
    if not groups:
        return 0
    levels = list(state.level)
    count = 0
    while True:
        best = -1
        best_price = 0
        for g in groups:
            members = C.GROUP_BUILDS[g]
            mn = min(levels[m] for m in members)
            if hotels:
                if mn != C.HOTEL_LEVEL - 1:
                    continue
            elif mn >= C.HOTEL_LEVEL - 1:
                continue
            for m in members:
                if levels[m] != mn:
                    continue
                price = board.b_house_price[m]
                if price > cash:
                    continue
                if best < 0 or price < best_price or (price == best_price and m < best):
                    best, best_price = m, price
        if best < 0:
            return count
        levels[best] += 1
        cash -= best_price
        count += 1


def house_demand(state: GameState, board: Board, seat: int) -> int:
    """d_H(Q) of P-19 (cheapest legal house first, ties by smallest b; hotels excluded)."""
    return _demand(state, board, seat, hotels=False)


def hotel_demand(state: GameState, board: Board, seat: int) -> int:
    """d_T(Q) of P-19 (legal, affordable hotels without bank limit)."""
    return _demand(state, board, seat, hotels=True)


def place_targets(state: GameState, board: Board, seat: int, hotel: bool, cash: int | None = None) -> list[int]:
    """Legal building targets of one kind (houses or hotels) the seat can afford with ``cash``."""
    budget = state.cash[seat] if cash is None else cash
    out = []
    for b in range(C.N_BUILD):
        if board.b_house_price[b] > budget:
            continue
        if (state.level[b] == C.HOTEL_LEVEL - 1) != hotel:
            continue
        if can_build_level(state.level, state, seat, b, state.bank_hotels >= 1, state.bank_houses >= 1):
            out.append(b)
    return out


def min_target_price(state: GameState, board: Board, seat: int, hotel: bool) -> int:
    """Smallest house price among the seat's legal targets of one kind (ignoring cash); -1 if none."""
    best = -1
    for b in range(C.N_BUILD):
        if (state.level[b] == C.HOTEL_LEVEL - 1) != hotel:
            continue
        if can_build_level(state.level, state, seat, b, state.bank_hotels >= 1, state.bank_houses >= 1):
            price = board.b_house_price[b]
            if best < 0 or price < best:
                best = price
    return best


def count_buildings(state: GameState, seat: int) -> tuple[int, int]:
    """(houses, hotels) owned by ``seat`` (a hotel counts as hotel, not houses)."""
    houses = 0
    hotels = 0
    for b in range(C.N_BUILD):
        lvl = state.level[b]
        if lvl and state.owner[C.B_TO_P[b]] == seat:
            if lvl == C.HOTEL_LEVEL:
                hotels += 1
            else:
                houses += lvl
    return houses, hotels
