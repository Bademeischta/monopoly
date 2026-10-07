"""Scarcity auction for houses and hotels (R-407, P-19, D-05, K-03, K-05)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import frames as F
from propertyrl.engine.auction import pay_premium, start_building_auction
from propertyrl.engine.building import (
    do_build,
    hotel_demand,
    house_demand,
    is_hotel_build,
    min_target_price,
)
from propertyrl.engine.decisions import ITEMS
from propertyrl.engine.events import CNT_SCARCITY_TRIGGERED

if TYPE_CHECKING:
    from propertyrl.engine.auction import AuctionState
    from propertyrl.engine.game import Engine


def demands(eng: Engine, hotel: bool) -> list[int]:
    """P-19 demand d_H (or d_T) of every seat (0 for bankrupt seats)."""
    state = eng.state
    fn = hotel_demand if hotel else house_demand
    return [0 if state.bankrupt[q] else fn(state, eng.board, q) for q in range(state.n_players)]


def try_build(eng: Engine, seat: int, b: int) -> None:
    """Handle BUILD_b in a window: build directly or start a scarcity auction (R-407, P-19)."""
    state = eng.state
    hotel = is_hotel_build(state, b)
    if eng.ruleset.scarcity_auction:
        d = demands(eng, hotel)
        stock = state.bank_hotels if hotel else state.bank_houses
        n = state.n_players
        interested = [q for q in range(n) if d[q] >= 1]
        if sum(d) > stock and len(interested) >= 2:
            # Participants: all with demand >= 1, ordered from the trigger in seat order.
            order = [(seat + k) % n for k in range(n)]
            participants = [q for q in order if d[q] >= 1]
            prices = [
                eng.board.b_house_price[b] if q == seat else min_target_price(state, eng.board, q, hotel)
                for q in participants
            ]
            eng.cnt(CNT_SCARCITY_TRIGGERED, seat)
            item = F.I_HOTEL if hotel else F.I_HOUSE
            start_building_auction(eng, item, seat, b, participants, prices)
            return
    # K-05 / no shortage: the first builder in the window gets the building.
    do_build(eng, seat, b)


def finish_building_auction(eng: Engine, a: AuctionState, winner: int, premium: int) -> None:
    """Settle a scarcity auction: premium to the bank, building placed immediately."""
    trigger = a.trigger
    if winner < 0:
        # No bids: the trigger receives the building with premium 0.
        eng.emit(
            "BUILDING_AUCTION_WON",
            trigger,
            {"item": ITEMS[a.item], "premium": 0, "no_bids": True, "b": a.target_b},
        )
        do_build(eng, trigger, a.target_b)
        return
    pay_premium(eng, winner, premium)
    eng.emit(
        "BUILDING_AUCTION_WON",
        winner,
        {"item": ITEMS[a.item], "premium": premium, "no_bids": False, "b": a.target_b},
    )
    if winner == trigger:
        do_build(eng, trigger, a.target_b)
    else:
        # Another bidder won: the trigger's BUILD is consumed; the winner places it (PLACE_BUILDING).
        eng.push((F.OP_D_PLACE, winner, a.item))


def place_mask_targets(eng: Engine, seat: int, item: int) -> list[int]:
    """Legal PLACE_BUILDING targets of the auction winner."""
    from propertyrl.engine.building import place_targets

    return place_targets(eng.state, eng.board, seat, item == F.I_HOTEL)
