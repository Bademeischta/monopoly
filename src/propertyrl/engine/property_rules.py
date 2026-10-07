"""Landing resolution and purchases (R-201 to R-203, R-301 to R-310, P-09)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.events import CNT_PURCHASES
from propertyrl.engine.rent import rent_due

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine


def land_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_LAND: resolve the square the seat landed on."""
    _, seat, mode = frame
    state = eng.state
    if state.bankrupt[seat]:
        return
    sq = state.position[seat]
    kind = eng.board.kind_code[sq]
    eng.emit("LANDED", seat, {"square": sq, "mode": mode})
    rules = eng.ruleset
    if kind == C.K_ARREST:
        # R-105: to jail without salary.
        eng.push((F.OP_SEND_JAIL, seat))
        return
    if rules.movement_only:
        return
    if kind in (C.K_STREET, C.K_RAIL, C.K_UTIL):
        p = C.SQUARE_TO_P[sq]
        owner = state.owner[p]
        if owner == C.BANK:
            # R-201: purchase decision (P-09 allows raising money first).
            state.ctx_decisions = 0
            state.window_actions = []
            eng.push((F.OP_D_BUY, seat, p))
            return
        if owner == seat or state.mortgaged[p]:
            # R-306 own property, R-305 mortgaged: no rent. R-307 owner in jail still collects.
            return
        if mode == F.LAND_NEAREST_UTIL and kind == C.K_UTIL:
            # R-604: new roll times 10.
            d1, d2 = eng.roll_dice(seat, 100 + state.util_rolls)
            state.util_rolls += 1
            eng.emit(
                "DICE_ROLLED",
                seat,
                {
                    "dice": [d1, d2],
                    "throw": 99 + state.util_rolls,
                    "turn": state.seat_turn_counter[seat],
                    "util": True,
                },
            )
            amount = 10 * (d1 + d2)
        else:
            amount = rent_due(state, eng.board, p, state.last_dice[0] + state.last_dice[1])
            if mode == F.LAND_NEAREST_RAIL and kind == C.K_RAIL:
                # R-603: twice the regular rail rent.
                amount *= 2
        eng.push((F.OP_PAY, seat, owner, amount, F.R_RENT, 0))
        return
    if kind == C.K_TAX:
        # R-308 / R-309
        eng.push((F.OP_PAY, seat, C.BANK, eng.board.tax_amount[sq], F.R_TAX, 0))
        return
    if kind == C.K_CARD_A:
        eng.push((F.OP_DRAW, seat, C.DECK_A))
        return
    if kind == C.K_CARD_B:
        eng.push((F.OP_DRAW, seat, C.DECK_B))
        return
    # START, JAIL (R-109 just visiting), REST (R-310): no effect.


def buy(eng: Engine, seat: int, p: int) -> None:
    """R-201/R-203: buy at the printed price, paid to the bank."""
    state = eng.state
    price = eng.board.p_price[p]
    eng.transfer(seat, C.BANK, price, "PURCHASE")
    state.owner[p] = seat
    state.mortgaged[p] = False
    state.interest_prepaid[p] = -1
    eng.cnt(CNT_PURCHASES, seat)
    eng.emit("PROPERTY_PURCHASED", seat, {"p": p, "price": price})


def decline(eng: Engine, seat: int, p: int) -> None:
    """R-202: declined purchase starts an auction among all active players."""
    eng.emit("BUY_DECLINED", seat, {"p": p})
    eng.push((F.OP_AUCTION_START, p, seat, F.ORIGIN_DECLINE))
