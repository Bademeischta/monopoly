"""Jail rules (R-104 to R-109, P-17, P-18)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.events import CNT_JAIL_ENTRIES

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine
    from propertyrl.engine.state import GameState


def send_jail_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_SEND_JAIL: to jail without salary (R-102, R-105, R-606); doubles counter reset."""
    seat = frame[1]
    state = eng.state
    if state.bankrupt[seat]:
        return
    state.position[seat] = C.JAIL_SQUARE
    state.in_jail[seat] = True
    state.jail_attempts[seat] = 0
    if seat == state.active_seat:
        state.doubles_count = 0
    eng.cnt(CNT_JAIL_ENTRIES, seat)
    eng.emit("JAIL_ENTERED", seat, {})


def leave_jail_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_LEAVE_JAIL: release after the third failed attempt (R-107)."""
    seat = frame[1]
    state = eng.state
    if state.bankrupt[seat]:
        return
    state.in_jail[seat] = False
    state.jail_attempts[seat] = 0
    eng.emit("JAIL_LEFT", seat, {"via": "third_attempt"})


def jail_roll_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_JAIL_ROLL: R-106 roll for doubles; R-107 third failure pays the fine and moves."""
    seat = frame[1]
    state = eng.state
    if state.bankrupt[seat]:
        return
    state.roll_in_turn += 1
    d1, d2 = eng.roll_dice(seat, 0)
    eng.emit(
        "DICE_ROLLED",
        seat,
        {"dice": [d1, d2], "throw": 0, "turn": state.seat_turn_counter[seat], "jail": True},
    )
    if d1 == d2:
        # Doubles: free, move by this roll, no further roll.
        state.in_jail[seat] = False
        state.jail_attempts[seat] = 0
        eng.emit("JAIL_LEFT", seat, {"via": "doubles"})
        eng.push((F.OP_AFTER_ROLL, seat, 0))
        eng.push((F.OP_MOVE_BY, seat, d1 + d2))
        return
    state.jail_attempts[seat] += 1
    eng.emit("JAIL_ROLL_FAILED", seat, {"attempt": state.jail_attempts[seat]})
    if state.jail_attempts[seat] >= 3:
        # R-107 / P-17: pay the fine (debt phase to the bank if needed), then move by this roll.
        eng.push((F.OP_AFTER_ROLL, seat, 0))
        eng.push((F.OP_MOVE_BY, seat, d1 + d2))
        eng.push((F.OP_LEAVE_JAIL, seat))
        eng.push((F.OP_PAY, seat, C.BANK, eng.ruleset.jail_fine, F.R_JAIL_FINE, 0))
        return
    eng.push((F.OP_AFTER_ROLL, seat, 0))


def can_pay_fine(state: GameState, seat: int, fine: int) -> bool:
    """PAY_JAIL_FINE legality: in jail, before the third attempt, cash >= fine (R-106)."""
    return state.in_jail[seat] and state.jail_attempts[seat] < 2 and state.cash[seat] >= fine


def can_use_card(state: GameState, seat: int) -> bool:
    """USE_JAIL_CARD legality: in jail and holding a card (any attempt, R-106)."""
    return state.in_jail[seat] and state.jail_cards[seat] != 0


def pay_fine(eng: Engine, seat: int) -> None:
    """PAY_JAIL_FINE: pay and continue in the normal pre-roll (P-18)."""
    state = eng.state
    fine = eng.ruleset.jail_fine
    eng.transfer(seat, C.BANK, fine, "JAIL_FINE")
    eng.emit("JAIL_FINE_PAID", seat, {"amount": fine})
    state.in_jail[seat] = False
    state.jail_attempts[seat] = 0
    eng.emit("JAIL_LEFT", seat, {"via": "fine"})


def use_card(eng: Engine, seat: int) -> None:
    """USE_JAIL_CARD: the card goes under its deck (R-601); then normal pre-roll (P-18)."""
    state = eng.state
    cards = state.jail_cards[seat]
    deck_idx = C.DECK_A if cards & C.DECK_BITS[C.DECK_A] else C.DECK_B
    state.jail_cards[seat] = cards & ~C.DECK_BITS[deck_idx]
    card = eng.decks.jail_free_index[deck_idx]
    (state.deck_a if deck_idx == C.DECK_A else state.deck_b).append(card)
    state.in_jail[seat] = False
    state.jail_attempts[seat] = 0
    eng.emit("JAIL_CARD_USED", seat, {"deck": deck_idx})
    eng.emit("JAIL_LEFT", seat, {"via": "card"})
