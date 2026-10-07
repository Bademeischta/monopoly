"""Dice, movement and salary (R-101 to R-105, R-110, P-15)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.events import CNT_SALARY

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine


def roll_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_ROLL: R-101 roll two dice; R-103 doubles; R-104 third double -> jail without moving."""
    seat = frame[1]
    state = eng.state
    if state.bankrupt[seat]:
        return
    throw = state.roll_in_turn
    state.roll_in_turn += 1
    d1, d2 = eng.roll_dice(seat, throw)
    doubles = d1 == d2
    eng.emit(
        "DICE_ROLLED",
        seat,
        {"dice": [d1, d2], "throw": throw, "turn": state.seat_turn_counter[seat], "jail": False},
    )
    if doubles:
        state.doubles_count += 1
        if state.doubles_count >= 3:
            # R-104: third double in a row -> straight to jail, no move, turn's movement ends.
            state.doubles_count = 0
            eng.push((F.OP_AFTER_ROLL, seat, 0))
            eng.push((F.OP_SEND_JAIL, seat))
            return
    eng.push((F.OP_AFTER_ROLL, seat, 1 if doubles else 0))
    eng.push((F.OP_MOVE_BY, seat, d1 + d2))


def after_roll_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_AFTER_ROLL: record the rest event and roll again after doubles (R-103)."""
    _, seat, reroll = frame
    state = eng.state
    if state.bankrupt[seat] or state.game_over:
        return
    state.rest_counts[state.position[seat]] += 1
    if reroll and not state.in_jail[seat]:
        # No decision window between double rolls (P-01): next roll is automatic.
        eng.push((F.OP_ROLL, seat))


def _salary(eng: Engine, seat: int) -> None:
    """R-102: salary for passing or landing on START."""
    amount = eng.ruleset.salary
    eng.transfer(C.BANK, seat, amount, "SALARY")
    eng.cnt(CNT_SALARY, seat, amount)
    eng.emit("SALARY", seat, {"amount": amount})


def move_by_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_MOVE_BY: move clockwise by the dice sum (R-101) with salary (R-102)."""
    _, seat, steps = frame
    state = eng.state
    if state.bankrupt[seat]:
        return
    old = state.position[seat]
    new = (old + steps) % C.N_SQUARES
    state.position[seat] = new
    eng.emit("MOVED", seat, {"from": old, "to": new, "steps": steps})
    if old + steps >= C.N_SQUARES:
        _salary(eng, seat)
    eng.push((F.OP_LAND, seat, F.LAND_NORMAL))


def move_to_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_MOVE_TO: forward move to a target square (cards), salary when passing START."""
    _, seat, target, mode = frame
    state = eng.state
    if state.bankrupt[seat]:
        return
    old = state.position[seat]
    steps = (target - old) % C.N_SQUARES
    state.position[seat] = target
    eng.emit("MOVED", seat, {"from": old, "to": target, "steps": steps, "card": True})
    if old + steps >= C.N_SQUARES:
        _salary(eng, seat)
    eng.push((F.OP_LAND, seat, mode))


def move_back(eng: Engine, seat: int, steps: int) -> None:
    """R-605: move backwards; never collects salary."""
    state = eng.state
    old = state.position[seat]
    new = (old - steps) % C.N_SQUARES
    state.position[seat] = new
    eng.emit("MOVED", seat, {"from": old, "to": new, "steps": -steps, "card": True})
    eng.push((F.OP_LAND, seat, F.LAND_NORMAL))


def next_forward(position: int, squares: tuple[int, ...]) -> int:
    """Nearest square of ``squares`` strictly ahead of ``position`` (cyclic)."""
    for k in range(1, C.N_SQUARES + 1):
        s = (position + k) % C.N_SQUARES
        if s in squares:
            return s
    raise AssertionError("no target square")
