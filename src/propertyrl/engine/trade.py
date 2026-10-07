"""Trades (R-801, R-802, R-503, P-02, P-14, D-03, K-01)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.events import (
    CNT_OFFERS_ACCEPTED,
    CNT_OFFERS_RECEIVED,
    CNT_TRADES_EXECUTED,
    CNT_TRADES_OFFERED,
)

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.game import Engine
    from propertyrl.engine.ruleset import Ruleset
    from propertyrl.engine.state import GameState


@dataclass(frozen=True, slots=True)
class TradeOffer:
    """A complete trade offer from ``proposer`` to exactly one ``recipient``.

    ``give_*`` flows from proposer to recipient, ``get_*`` from recipient to proposer.
    Jail cards are bit masks (deck A = 1, deck B = 2).
    """

    proposer: int
    recipient: int
    give_cash: int = 0
    get_cash: int = 0
    give_props: tuple[int, ...] = ()
    get_props: tuple[int, ...] = ()
    give_jail_cards: int = 0
    get_jail_cards: int = 0

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "proposer": self.proposer,
            "recipient": self.recipient,
            "give_cash": self.give_cash,
            "get_cash": self.get_cash,
            "give_props": list(self.give_props),
            "get_props": list(self.get_props),
            "give_jail_cards": self.give_jail_cards,
            "get_jail_cards": self.get_jail_cards,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TradeOffer:
        """Inverse of :meth:`to_dict`."""
        return cls(
            proposer=int(d["proposer"]),
            recipient=int(d["recipient"]),
            give_cash=int(d.get("give_cash", 0)),
            get_cash=int(d.get("get_cash", 0)),
            give_props=tuple(int(x) for x in d.get("give_props", ())),
            get_props=tuple(int(x) for x in d.get("get_props", ())),
            give_jail_cards=int(d.get("give_jail_cards", 0)),
            get_jail_cards=int(d.get("get_jail_cards", 0)),
        )

    def is_empty(self) -> bool:
        """True if nothing at all is exchanged."""
        return not (
            self.give_cash
            or self.get_cash
            or self.give_props
            or self.get_props
            or self.give_jail_cards
            or self.get_jail_cards
        )


def _interest_on(state: GameState, board: Board, ruleset: Ruleset, props: tuple[int, ...]) -> int:
    total = 0
    for p in props:
        if state.mortgaged[p]:
            total += C.ceil_div(board.p_mortgage[p] * ruleset.mortgage_interest_percent, 100)
    return total


def validate_offer(state: GameState, board: Board, ruleset: Ruleset, offer: TradeOffer, proposer: int) -> str | None:
    """Check R-801/R-802/P-14; return a reason string if illegal, ``None`` if legal."""
    if not isinstance(offer, TradeOffer):
        return "not a TradeOffer"
    n = state.n_players
    p, r = offer.proposer, offer.recipient
    if p != proposer:
        return "proposer must be the window owner"
    if not (0 <= r < n) or r == p:
        return "invalid recipient"
    if state.bankrupt[p] or state.bankrupt[r]:
        return "bankrupt participant"
    for val in (offer.give_cash, offer.get_cash, offer.give_jail_cards, offer.get_jail_cards):
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            return "amounts must be non-negative integers"
    if offer.is_empty():
        return "empty trade"
    all_props = tuple(offer.give_props) + tuple(offer.get_props)
    if len(set(all_props)) != len(all_props):
        return "duplicate property"
    for prop in all_props:
        if not isinstance(prop, int) or not 0 <= prop < C.N_PROPS:
            return "invalid property index"
    for prop in offer.give_props:
        if state.owner[prop] != p:
            return f"proposer does not own p{prop}"
    for prop in offer.get_props:
        if state.owner[prop] != r:
            return f"recipient does not own p{prop}"
    # P-14 / R-801: no building in the colour groups of traded streets.
    for prop in all_props:
        for b in C.GROUP_BUILDS[C.P_GROUP[prop]]:
            if state.level[b] > 0:
                return f"group of p{prop} has buildings"
    if offer.give_cash > state.cash[p] or offer.get_cash > state.cash[r]:
        return "cash exceeds the payer's cash"
    if offer.give_jail_cards & ~state.jail_cards[p] or offer.get_jail_cards & ~state.jail_cards[r]:
        return "jail card not held"
    if offer.give_jail_cards > 3 or offer.get_jail_cards > 3:
        return "invalid jail card mask"
    # P-14 / R-503: receivers of mortgaged properties must pay the interest from cash after the trade.
    cash_r = state.cash[r] - offer.get_cash + offer.give_cash
    cash_p = state.cash[p] - offer.give_cash + offer.get_cash
    if _interest_on(state, board, ruleset, offer.give_props) > cash_r:
        return "recipient cannot pay interest on mortgaged properties"
    if _interest_on(state, board, ruleset, offer.get_props) > cash_p:
        return "proposer cannot pay interest on mortgaged properties"
    return None


def trades_enabled(eng: Engine) -> bool:
    """True if the ruleset has any trade protocol and engine options do not disable trading."""
    return eng.ruleset.trade_protocol != "none" and not eng.ruleset.movement_only


def handle_offers(eng: Engine, seat: int, response: Any, phase: str) -> list[dict[str, Any]]:
    """Apply a TRADE_OFFER response (P-02: at most 2 offers, each P-14 legal)."""
    if not isinstance(response, (list, tuple)):
        raise eng.illegal("TRADE_OFFER expects a list of TradeOffer", seat)
    if len(response) > C.MAX_OFFERS_PER_WINDOW:
        raise eng.illegal(f"more than {C.MAX_OFFERS_PER_WINDOW} offers", seat)
    state = eng.state
    for offer in response:
        reason = validate_offer(state, eng.board, eng.ruleset, offer, seat)
        if reason is not None:
            raise eng.illegal(f"illegal trade offer: {reason}", seat)
    state.offers = list(response)
    state.offer_phase = phase
    if response:
        eng.push((F.OP_TRADE_PRESENT,))
    return [o.to_dict() for o in response]


def present_next(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_TRADE_PRESENT: re-validate the next queued offer and ask the recipient."""
    state = eng.state
    if not state.offers:
        state.current_offer = None
        return
    offer = state.offers.pop(0)
    if state.offers:
        eng.push((F.OP_TRADE_PRESENT,))
    reason = validate_offer(state, eng.board, eng.ruleset, offer, offer.proposer)
    eng.cnt(CNT_TRADES_OFFERED, offer.proposer)
    if reason is not None:
        eng.emit("TRADE_REJECTED", offer.recipient, {"offer": offer.to_dict(), "stale": True, "reason": reason})
        return
    state.current_offer = offer
    eng.cnt(CNT_OFFERS_RECEIVED, offer.recipient)
    eng.emit("TRADE_OFFERED", offer.proposer, {"offer": offer.to_dict()})
    eng.push((F.OP_D_TRADE_RESPONSE,))


def handle_response(eng: Engine, response: Any) -> bool:
    """Apply a TRADE_RESPONSE (accept/reject)."""
    state = eng.state
    offer = state.current_offer
    assert offer is not None
    if not isinstance(response, bool):
        raise eng.illegal("TRADE_RESPONSE expects bool", offer.recipient)
    state.current_offer = None
    if not response:
        eng.emit("TRADE_REJECTED", offer.recipient, {"offer": offer.to_dict(), "stale": False})
        return False
    eng.cnt(CNT_OFFERS_ACCEPTED, offer.recipient)
    eng.emit("TRADE_ACCEPTED", offer.recipient, {"offer": offer.to_dict()})
    execute(eng, offer)
    return True


def execute(eng: Engine, offer: TradeOffer) -> None:
    """Execute a validated trade including R-503 immediate interest."""
    from propertyrl.engine.mortgage import receive_mortgaged

    state = eng.state
    p, r = offer.proposer, offer.recipient
    if offer.give_cash:
        eng.transfer(p, r, offer.give_cash, "TRADE")
    if offer.get_cash:
        eng.transfer(r, p, offer.get_cash, "TRADE")
    interest_due = [0, 0]
    for receiver, props in ((r, offer.give_props), (p, offer.get_props)):
        for prop in props:
            state.owner[prop] = receiver
            state.interest_prepaid[prop] = -1
            if state.mortgaged[prop]:
                interest_due[0 if receiver == r else 1] += receive_mortgaged(eng, receiver, prop)
    state.jail_cards[p] = (state.jail_cards[p] & ~offer.give_jail_cards) | offer.get_jail_cards
    state.jail_cards[r] = (state.jail_cards[r] & ~offer.get_jail_cards) | offer.give_jail_cards
    for receiver, amount in ((r, interest_due[0]), (p, interest_due[1])):
        if amount:
            eng.transfer(receiver, C.BANK, amount, "INTEREST")
            eng.emit("INTEREST_PAID", receiver, {"amount": amount, "source": "trade"})
    eng.cnt(CNT_TRADES_EXECUTED, p)
    eng.cnt(CNT_TRADES_EXECUTED, r)
    eng.emit("TRADE_EXECUTED", p, {"offer": offer.to_dict()})
