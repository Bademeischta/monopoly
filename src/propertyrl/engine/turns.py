"""Turn sequencing and decision windows (§3.10, P-01, P-02, P-13, P-15, R-110, D-01, D-03, D-06)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import frames as F
from propertyrl.engine.trade import trades_enabled

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine


def turn_start_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_TURN_START: begin the turn of ``seat`` and schedule its windows."""
    seat = frame[1]
    state = eng.state
    if state.bankrupt[seat]:
        eng.push((F.OP_NEXT_TURN, seat))
        return
    # P-15: the round counter increases when the turn passes to a seat with smaller or equal index.
    if state.turn_index > 0 and seat <= state.active_seat:
        state.round_index += 1
    if eng.ruleset.short_game and state.round_index >= eng.ruleset.max_rounds:
        # D-06: the short game ends after max_rounds; winner by canonical equity.
        eng.finish_game(by_rounds=True)
        return
    state.active_seat = seat
    state.turn_index += 1
    state.seat_turn_counter[seat] += 1
    state.doubles_count = 0
    state.roll_in_turn = 0
    state.util_rolls = 0
    state.turn_events = 0
    eng.emit("TURN_STARTED", seat, {"turn": state.turn_index, "round": state.round_index})
    official = eng.ruleset.official_windows
    trading = trades_enabled(eng)
    eng.push((F.OP_NEXT_TURN, seat))
    if official:
        eng.push((F.OP_OOT, seat))
    # OFFICIAL: offers at the start of every window (P-02); RESEARCH: only before rolling (D-03).
    eng.push((F.OP_WINDOW, seat, F.W_POST_MOVE, 1 if (official and trading) else 0))
    eng.push((F.OP_WINDOW, seat, F.W_PRE_ROLL, 1 if trading else 0))


def window_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_WINDOW: open a management window (P-01), optionally preceded by trade offers."""
    _, seat, wkind, offers = frame
    state = eng.state
    if state.bankrupt[seat]:
        return
    state.window_counter += 1
    state.window_seat = seat
    state.window_kind = wkind
    state.window_actions = []
    state.ctx_decisions = 0
    eng.emit("WINDOW_OPENED", seat, {"window": F.WINDOW_NAMES[wkind], "id": state.window_counter})
    eng.push((F.OP_D_WINDOW, seat, wkind))
    if offers and state.n_active() > 1:
        eng.push((F.OP_D_TRADE_OFFER, seat, wkind))


def close_window(eng: Engine, seat: int) -> None:
    """Close the current window; P-13 principal-only option of this seat expires."""
    state = eng.state
    for p in range(len(state.owner)):
        if state.owner[p] == seat and state.interest_prepaid[p] >= 0:
            state.interest_prepaid[p] = -1
    eng.emit("WINDOW_CLOSED", seat, {"id": state.window_counter})
    state.window_seat = -1
    state.window_kind = -1


def oot_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_OOT: out-of-turn windows for every other active player in seat order (P-01 c)."""
    seat = frame[1]
    state = eng.state
    n = state.n_players
    others = [(seat + k) % n for k in range(1, n)]
    trading = trades_enabled(eng)
    for s in reversed(others):
        if not state.bankrupt[s]:
            eng.push((F.OP_WINDOW, s, F.W_OUT_OF_TURN, 1 if trading else 0))


def next_turn_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_NEXT_TURN: hand over to the next active seat (R-110, bankrupt seats skipped)."""
    seat = frame[1]
    state = eng.state
    n = state.n_players
    for k in range(1, n + 1):
        s = (seat + k) % n
        if not state.bankrupt[s]:
            eng.push((F.OP_TURN_START, s))
            return
