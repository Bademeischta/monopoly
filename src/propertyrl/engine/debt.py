"""Payments, debt phase and bankruptcy (R-701 to R-705, P-06, P-07, P-12, P-17, R-503)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.building import can_sell, sell_all_buildings
from propertyrl.engine.events import (
    CNT_DEBT_PHASES,
    CNT_RENT_PAID,
    CNT_RENT_RECEIVED,
    CNT_TAXES,
)
from propertyrl.engine.mortgage import can_mortgage, receive_mortgaged

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine
    from propertyrl.engine.state import GameState

_EVENT_BY_REASON = {
    F.R_RENT: "RENT_PAID",
    F.R_TAX: "TAX_PAID",
    F.R_JAIL_FINE: "JAIL_FINE_PAID",
    F.R_INTEREST: "INTEREST_PAID",
}


def has_liquidation(state: GameState, seat: int) -> bool:
    """P-06: True if the seat still has a legal MORTGAGE or SELL_BUILDING action."""
    for p in range(C.N_PROPS):
        if state.owner[p] == seat and can_mortgage(state, seat, p):
            return True
    for b in range(C.N_BUILD):
        if state.level[b] and can_sell(state, seat, b):
            return True
    return False


def settle(eng: Engine, debtor: int, creditor: int, amount: int, reason: int) -> None:
    """Transfer ``amount`` from debtor to creditor and emit the matching event."""
    eng.transfer(debtor, creditor, amount, F.REASONS[reason])
    if reason == F.R_RENT:
        eng.cnt(CNT_RENT_PAID, debtor, amount)
        eng.cnt(CNT_RENT_RECEIVED, creditor, amount)
    elif reason == F.R_TAX:
        eng.cnt(CNT_TAXES, debtor, amount)
    etype = _EVENT_BY_REASON.get(reason, "PAYMENT")
    eng.emit(etype, debtor, {"to": creditor, "amount": amount, "reason": F.REASONS[reason]})


def pay_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_PAY: pay immediately or enter the debt phase (R-701, P-06)."""
    _, debtor, creditor, amount, reason, bank_on_bankrupt = frame
    state = eng.state
    if amount <= 0 or state.bankrupt[debtor]:
        return
    if creditor >= 0 and state.bankrupt[creditor]:
        # A-110: payments owed to a seat that went bankrupt in the meantime lapse.
        return
    if state.cash[debtor] >= amount:
        settle(eng, debtor, creditor, amount, reason)
        return
    eng.cnt(CNT_DEBT_PHASES, debtor)
    eng.emit(
        "DEBT_STARTED",
        debtor,
        {"to": creditor, "amount": amount, "reason": F.REASONS[reason], "cash": state.cash[debtor]},
    )
    if has_liquidation(state, debtor):
        state.ctx_decisions = 0
        state.window_actions = []
        eng.push((F.OP_D_DEBT, debtor, creditor, amount, reason, bank_on_bankrupt))
    else:
        # P-06: no liquidation action left -> automatic bankruptcy (P-07: to the bank for PAY_EACH).
        eng.push((F.OP_BANKRUPT, debtor, C.BANK if bank_on_bankrupt else creditor))


def after_debt_action(eng: Engine, frame: tuple[int, ...]) -> None:
    """After a DEBT liquidation action: pay automatically or declare bankruptcy (P-06)."""
    _, debtor, creditor, amount, reason, bank_on_bankrupt = frame
    state = eng.state
    if state.cash[debtor] >= amount:
        eng.pop()
        if creditor >= 0 and state.bankrupt[creditor]:
            eng.emit("DEBT_SETTLED", debtor, {"to": creditor, "amount": 0, "lapsed": True})
            return
        settle(eng, debtor, creditor, amount, reason)
        eng.emit("DEBT_SETTLED", debtor, {"to": creditor, "amount": amount})
        return
    if not has_liquidation(state, debtor):
        eng.pop()
        eng.push((F.OP_BANKRUPT, debtor, C.BANK if bank_on_bankrupt else creditor))


def next_active_after(state: GameState, seat: int) -> int:
    """First non-bankrupt seat after ``seat`` in seat order (cyclic); -1 if none."""
    n = state.n_players
    for k in range(1, n + 1):
        s = (seat + k) % n
        if not state.bankrupt[s]:
            return s
    return -1


def bankrupt_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_BANKRUPT: R-702 (to a player) or R-703 (to the bank)."""
    _, debtor, creditor = frame
    state = eng.state
    if state.bankrupt[debtor]:
        return
    if creditor >= 0 and state.bankrupt[creditor]:
        creditor = C.BANK
    state.bankrupt[debtor] = True
    state.bankruptcy_order.append(debtor)
    eng.emit("BANKRUPTCY", debtor, {"creditor": creditor, "cash": state.cash[debtor]})
    # R-702/R-703: buildings go to the bank at half price (proceeds to the debtor's cash first).
    sell_all_buildings(eng, debtor)
    cash = state.cash[debtor]
    props = [p for p in range(C.N_PROPS) if state.owner[p] == debtor]
    cards = state.jail_cards[debtor]
    state.jail_cards[debtor] = 0
    state.in_jail[debtor] = False
    state.jail_attempts[debtor] = 0
    interest_frames: list[tuple[int, ...]] = []
    if creditor >= 0:
        # R-702: cash, properties (R-503 for mortgaged ones) and jail cards to the creditor.
        if cash:
            eng.transfer(debtor, creditor, cash, "BANKRUPTCY")
        for p in props:
            state.owner[p] = creditor
            state.interest_prepaid[p] = -1
            if state.mortgaged[p]:
                due = receive_mortgaged(eng, creditor, p)
                interest_frames.append((F.OP_PAY, creditor, C.BANK, due, F.R_INTEREST, 1))
        state.jail_cards[creditor] |= cards
    else:
        # R-703: everything to the bank; P-12 mortgages lapse; jail cards back under their decks.
        if cash:
            eng.transfer(debtor, C.BANK, cash, "BANKRUPTCY")
        for p in props:
            state.owner[p] = C.BANK
            state.mortgaged[p] = False
            state.interest_prepaid[p] = -1
        for deck_idx in (C.DECK_A, C.DECK_B):
            if cards & C.DECK_BITS[deck_idx]:
                card = eng.decks.jail_free_index[deck_idx]
                (state.deck_a if deck_idx == C.DECK_A else state.deck_b).append(card)
    eng.emit(
        "ASSETS_TRANSFERRED",
        debtor,
        {"to": creditor, "cash": cash, "props": props, "jail_cards": cards},
    )
    # R-704/R-901: bankrupt seats leave; check the end of the game immediately.
    if eng.check_game_end():
        return
    if creditor >= 0:
        for fr in reversed(interest_frames):
            eng.push(fr)
    else:
        starter = next_active_after(state, debtor)
        for p in reversed(props):
            eng.push((F.OP_AUCTION_START, p, starter, F.ORIGIN_BANK))
