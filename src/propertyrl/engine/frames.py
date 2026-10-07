"""Continuation-stack opcodes and small enumerations of the engine state machine.

A frame is a tuple of ints ``(opcode, *args)``. Automatic frames are executed
by the engine loop; decision frames stay on top of the stack until answered.
"""

from __future__ import annotations

from typing import Final

# Automatic frames.
OP_TURN_START: Final = 1  # (op, seat)
OP_WINDOW: Final = 2  # (op, seat, wkind, offers)
OP_TRADE_PRESENT: Final = 3  # (op,)
OP_ROLL: Final = 4  # (op, seat)
OP_JAIL_ROLL: Final = 5  # (op, seat)
OP_AFTER_ROLL: Final = 6  # (op, seat, reroll)
OP_MOVE_BY: Final = 7  # (op, seat, steps)
OP_MOVE_TO: Final = 8  # (op, seat, target, mode)
OP_LAND: Final = 9  # (op, seat, mode)
OP_AUCTION_START: Final = 10  # (op, p, starter, origin)
OP_PAY: Final = 11  # (op, debtor, creditor, amount, reason, bank_on_bankrupt)
OP_BANKRUPT: Final = 12  # (op, debtor, creditor)
OP_DRAW: Final = 13  # (op, seat, deck)
OP_SEND_JAIL: Final = 14  # (op, seat)
OP_LEAVE_JAIL: Final = 15  # (op, seat)
OP_OOT: Final = 16  # (op, active_seat)
OP_NEXT_TURN: Final = 17  # (op, seat)
# Decision frames.
OP_D_WINDOW: Final = 20  # (op, seat, wkind)
OP_D_TRADE_OFFER: Final = 21  # (op, seat, wkind)
OP_D_TRADE_RESPONSE: Final = 22  # (op,)
OP_D_BUY: Final = 23  # (op, seat, p)
OP_D_AUCTION: Final = 24  # (op,)
OP_D_DEBT: Final = 25  # (op, debtor, creditor, amount, reason, bank_on_bankrupt)
OP_D_PLACE: Final = 26  # (op, seat, item)

DECISION_OPS: Final = frozenset(
    (OP_D_WINDOW, OP_D_TRADE_OFFER, OP_D_TRADE_RESPONSE, OP_D_BUY, OP_D_AUCTION, OP_D_DEBT, OP_D_PLACE)
)

# Window kinds.
W_PRE_ROLL: Final = 0
W_POST_MOVE: Final = 1
W_OUT_OF_TURN: Final = 2
WINDOW_NAMES: Final = ("PRE_ROLL", "POST_MOVE", "OUT_OF_TURN")

# Landing modes.
LAND_NORMAL: Final = 0
LAND_NEAREST_RAIL: Final = 1
LAND_NEAREST_UTIL: Final = 2

# Auction origins.
ORIGIN_DECLINE: Final = 0
ORIGIN_BANK: Final = 1
ORIGIN_SCARCITY: Final = 2

# Auction item codes (frames and auction state use ints).
I_PROPERTY: Final = 0
I_HOUSE: Final = 1
I_HOTEL: Final = 2

# Payment reasons.
REASONS: Final = (
    "RENT",
    "TAX",
    "CARD",
    "JAIL_FINE",
    "INTEREST",
    "REPAIRS",
    "PURCHASE",
    "AUCTION",
    "BUILD",
    "SELL",
    "MORTGAGE",
    "UNMORTGAGE",
    "SALARY",
    "TRADE",
    "BANKRUPTCY",
    "SCARCITY_PREMIUM",
    "CARD_EACH",
)
REASON_INDEX: Final = {r: i for i, r in enumerate(REASONS)}
R_RENT: Final = REASON_INDEX["RENT"]
R_TAX: Final = REASON_INDEX["TAX"]
R_CARD: Final = REASON_INDEX["CARD"]
R_JAIL_FINE: Final = REASON_INDEX["JAIL_FINE"]
R_INTEREST: Final = REASON_INDEX["INTEREST"]
R_REPAIRS: Final = REASON_INDEX["REPAIRS"]
R_CARD_EACH: Final = REASON_INDEX["CARD_EACH"]
