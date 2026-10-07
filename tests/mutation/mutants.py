"""Curated engine mutants applied by monkeypatching (§10). Each mutant names the tests that must kill it.

Activated in a subprocess via the environment variable ``PROPERTYRL_MUTANT`` (see tests/conftest.py).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from propertyrl.engine import actions as A
from propertyrl.engine import (
    auction,
    building,
    debt,
    game,
    jail,
    legality,
    mortgage,
    movement,
    rent,
    scarcity,
)
from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine import property_rules as PR


def patch_everywhere(original: Any, replacement: Any) -> None:
    """Replace every reference to ``original`` in engine modules and the handler table."""
    for name, module in list(sys.modules.items()):
        if not name.startswith("propertyrl.engine") or module is None:
            continue
        for attr, val in list(vars(module).items()):
            if val is original:
                setattr(module, attr, replacement)
    for op, handler in list(game._HANDLERS.items()):
        if handler is original:
            game._HANDLERS[op] = replacement


# ---------------------------------------------------------------------------- mutant implementations
def _no_group_doubling() -> None:
    patch_everywhere(rent.owns_full_group, lambda state, owner, group: False)


def _mortgage_value_is_price() -> None:
    def do_mortgage(eng: Any, seat: int, p: int) -> None:
        eng.state.mortgaged[p] = True
        eng.transfer(C.BANK, seat, eng.board.p_price[p], "MORTGAGE")

    patch_everywhere(mortgage.do_mortgage, do_mortgage)


def _no_even_building() -> None:
    original = legality.management_mask

    def management_mask(state: Any, board: Any, ruleset: Any, seat: int, mask: list[bool], build: bool = True,
                        unmortgage: bool = True) -> None:  # fmt: skip
        original(state, board, ruleset, seat, mask, build, unmortgage)
        if not build:
            return
        for g in range(C.N_COLOR_GROUPS):
            if building.group_buildable(state, seat, g):
                for b in C.GROUP_BUILDS[g]:
                    if state.level[b] < 4 and state.cash[seat] >= board.b_house_price[b] and state.bank_houses:
                        mask[A.BUILD_BASE + b] = True

    patch_everywhere(original, management_mask)


def _no_salary() -> None:
    patch_everywhere(movement._salary, lambda eng, seat: None)


def _third_double_no_jail() -> None:
    def roll_frame(eng: Any, frame: tuple[int, ...]) -> None:
        seat = frame[1]
        st = eng.state
        if st.bankrupt[seat]:
            return
        throw = st.roll_in_turn
        st.roll_in_turn += 1
        d1, d2 = eng.roll_dice(seat, throw)
        eng.emit("DICE_ROLLED", seat, {"dice": [d1, d2], "throw": throw, "turn": st.seat_turn_counter[seat]})
        doubles = d1 == d2
        if doubles:
            st.doubles_count = (st.doubles_count + 1) % 3
        eng.push((F.OP_AFTER_ROLL, seat, 1 if doubles else 0))
        eng.push((F.OP_MOVE_BY, seat, d1 + d2))

    patch_everywhere(movement.roll_frame, roll_frame)


def _interest_rounded_down() -> None:
    patch_everywhere(mortgage.interest, lambda ruleset, mv: mv * ruleset.mortgage_interest_percent // 100)


def _rent_on_mortgaged() -> None:
    original = PR.land_frame

    def land_frame(eng: Any, frame: tuple[int, ...]) -> None:
        st = eng.state
        p = C.SQUARE_TO_P[st.position[frame[1]]]
        if p >= 0 and st.mortgaged[p]:
            st.mortgaged[p] = False
            try:
                original(eng, frame)
            finally:
                st.mortgaged[p] = True
        else:
            original(eng, frame)

    patch_everywhere(original, land_frame)


def _mortgaged_rails_not_counted() -> None:
    def count_owned(state: Any, owner: int, group: int) -> int:
        return sum(1 for p in C.GROUP_PROPS[group] if state.owner[p] == owner and not state.mortgaged[p]) or 1

    patch_everywhere(rent.count_owned, count_owned)


def _util_factors_swapped() -> None:
    def util_multiplier(state: Any, board: Any, p: int) -> int:
        n = rent.count_owned(state, state.owner[p], C.UTIL_GROUP)
        return (10, 4)[n - 1]

    patch_everywhere(rent.util_multiplier, util_multiplier)


def _hotel_returns_no_houses() -> None:
    original = building.do_build

    def do_build(eng: Any, seat: int, b: int) -> None:
        hotel = eng.state.level[b] == 4
        original(eng, seat, b)
        if hotel:
            eng.state.bank_houses -= 4

    patch_everywhere(original, do_build)


def _bankruptcy_without_transfer() -> None:
    original = debt.bankrupt_frame
    patch_everywhere(original, lambda eng, frame: original(eng, (frame[0], frame[1], C.BANK)))


def _jail_card_not_returned() -> None:
    def use_card(eng: Any, seat: int) -> None:
        st = eng.state
        st.jail_cards[seat] = 0
        st.in_jail[seat] = False
        st.jail_attempts[seat] = 0

    patch_everywhere(jail.use_card, use_card)


def _third_jail_roll_no_fine() -> None:
    def jail_roll_frame(eng: Any, frame: tuple[int, ...]) -> None:
        seat = frame[1]
        st = eng.state
        st.roll_in_turn += 1
        d1, d2 = eng.roll_dice(seat, 0)
        if d1 == d2 or st.jail_attempts[seat] >= 2:
            st.in_jail[seat] = False
            st.jail_attempts[seat] = 0
            eng.push((F.OP_AFTER_ROLL, seat, 0))
            eng.push((F.OP_MOVE_BY, seat, d1 + d2))
            return
        st.jail_attempts[seat] += 1
        eng.push((F.OP_AFTER_ROLL, seat, 0))

    patch_everywhere(jail.jail_roll_frame, jail_roll_frame)


def _move_back_wrong() -> None:
    original = movement.move_back
    patch_everywhere(original, lambda eng, seat, steps: original(eng, seat, -steps))


def _research_auction_highest_price() -> None:
    def resolve(eng: Any) -> None:
        a = eng.state.auction
        valid = [(amt, i) for i, amt in enumerate(a.bids) if amt >= 0]
        if not valid:
            auction._finish(eng, -1, -1)
            return
        best = max(amt for amt, _ in valid)
        win = min(i for amt, i in valid if amt == best)
        auction._finish(eng, a.participants[win], best)

    patch_everywhere(auction._resolve_sealed, resolve)


def _sell_full_price() -> None:
    original = building.do_sell

    def do_sell(eng: Any, seat: int, b: int) -> None:
        before = eng.state.cash[seat]
        original(eng, seat, b)
        eng.transfer(C.BANK, seat, eng.state.cash[seat] - before, "SELL")

    patch_everywhere(original, do_sell)


def _no_scarcity_auction() -> None:
    patch_everywhere(scarcity.try_build, lambda eng, seat, b: building.do_build(eng, seat, b))


U = "tests/unit/"
MUTANTS: dict[str, tuple[Callable[[], None], list[str]]] = {
    "no_group_doubling": (
        _no_group_doubling,
        [U + "test_purchase_rent.py::test_base_rent_and_double_with_group"],
    ),
    "mortgage_value_is_price": (
        _mortgage_value_is_price,
        [U + "test_building_mortgage.py::test_mortgage_payout_and_group_block"],
    ),
    "no_even_building": (_no_even_building, [U + "test_building_mortgage.py::test_even_building"]),
    "no_salary": (_no_salary, [U + "test_movement_jail.py::test_salary_when_passing_start"]),
    "third_double_no_jail": (
        _third_double_no_jail,
        [U + "test_movement_jail.py::test_third_double_goes_to_jail_without_moving"],
    ),
    "interest_rounded_down": (
        _interest_rounded_down,
        [U + "test_building_mortgage.py::test_unmortgage_cost_rounded_up"],
    ),
    "rent_on_mortgaged": (_rent_on_mortgaged, [U + "test_purchase_rent.py::test_no_rent_on_mortgaged"]),
    "mortgaged_rails_not_counted": (
        _mortgaged_rails_not_counted,
        [U + "test_purchase_rent.py::test_rail_rent"],
    ),
    "util_factors_swapped": (_util_factors_swapped, [U + "test_purchase_rent.py::test_utility_rent"]),
    "hotel_returns_no_houses": (
        _hotel_returns_no_houses,
        [U + "test_building_mortgage.py::test_hotel_requires_four_everywhere_and_returns_houses"],
    ),
    "bankruptcy_without_transfer": (
        _bankruptcy_without_transfer,
        [U + "test_cards_debt.py::test_bankruptcy_to_player_transfers_mortgaged_with_interest"],
    ),
    "jail_card_not_returned": (
        _jail_card_not_returned,
        [U + "test_movement_jail.py::test_use_card_returns_it_under_deck"],
    ),
    "third_jail_roll_no_fine": (
        _third_jail_roll_no_fine,
        [U + "test_movement_jail.py::test_third_failure_pays_and_moves"],
    ),
    "move_back_wrong": (_move_back_wrong, [U + "test_cards_debt.py::test_move_back_from_36_draws_deck_b"]),
    "research_auction_highest_price": (
        _research_auction_highest_price,
        [U + "test_purchase_rent.py::test_sealed_auction_second_price_plus_one"],
    ),
    "sell_full_price": (_sell_full_price, [U + "test_building_mortgage.py::test_sell_evenly_half_price"]),
    "no_scarcity_auction": (
        _no_scarcity_auction,
        [U + "test_building_mortgage.py::test_scarcity_no_bids_trigger_gets_house"],
    ),
}


def apply(name: str) -> None:
    """Activate mutant ``name`` (raises KeyError for unknown names)."""
    MUTANTS[name][0]()
