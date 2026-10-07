"""Property auctions (R-202, P-03, D-02) and the shared bidding machinery for P-19/D-05."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.decisions import FORMAT_ASCENDING, FORMAT_SEALED, ITEMS, Bid, BidLevel
from propertyrl.engine.events import (
    CNT_AUCTION_FACE,
    CNT_AUCTION_SPEND,
    CNT_AUCTIONS_WON,
    CNT_SCARCITY_PREMIUM,
    CNT_SCARCITY_WON,
)

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine


class AuctionState:
    """State of the single running auction (property, house or hotel)."""

    __slots__ = (
        "actions",
        "bidder_price",
        "bids",
        "cursor",
        "high_bid",
        "high_bidder",
        "item",
        "origin",
        "p",
        "participants",
        "passed",
        "phase",
        "ref_price",
        "sealed",
        "target_b",
        "trigger",
    )

    def __init__(
        self,
        item: int,
        participants: list[int],
        sealed: bool,
        ref_price: int,
        phase: str,
        p: int = -1,
        trigger: int = -1,
        target_b: int = -1,
        origin: int = F.ORIGIN_DECLINE,
        bidder_price: list[int] | None = None,
    ) -> None:
        self.item = item
        self.p = p
        self.sealed = sealed
        self.participants = participants
        self.passed = [False] * len(participants)
        self.bids = [-1] * len(participants)
        self.cursor = 0
        self.high_bid = -1
        self.high_bidder = -1
        self.actions = 0
        self.trigger = trigger
        self.target_b = target_b
        self.ref_price = ref_price
        self.origin = origin
        self.bidder_price = bidder_price if bidder_price is not None else [0] * len(participants)
        self.phase = phase

    def copy(self) -> AuctionState:
        """Independent copy."""
        new = object.__new__(AuctionState)
        for name in AuctionState.__slots__:
            val = getattr(self, name)
            setattr(new, name, list(val) if isinstance(val, list) else val)
        return new

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        out: dict[str, Any] = {}
        for name in AuctionState.__slots__:
            val = getattr(self, name)
            out[name] = list(val) if isinstance(val, list) else val
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AuctionState:
        """Inverse of :meth:`to_dict`."""
        new = object.__new__(AuctionState)
        for name in AuctionState.__slots__:
            val = d[name]
            setattr(new, name, list(val) if isinstance(val, list) else val)
        return new

    @property
    def bidder(self) -> int:
        """Seat whose bid is requested."""
        return self.participants[self.cursor]


def property_levels(price: int) -> list[int]:
    """D-02 sealed bid amounts: 10..150 % of the printed price, rounded, at least 1."""
    return [max(1, C.round_half_up(pct * price, 100)) for pct in C.SEALED_PROPERTY_LEVELS]


def premium_levels(house_price: int) -> list[int]:
    """D-05 sealed premium amounts: 0..150 % of the trigger target's house price."""
    return [C.round_half_up(pct * house_price, 100) for pct in C.SEALED_PREMIUM_LEVELS]


def _ordered_from(eng: Engine, start: int) -> list[int]:
    """Active seats in seat order starting at ``start`` (cyclic)."""
    state = eng.state
    n = state.n_players
    return [(start + k) % n for k in range(n) if not state.bankrupt[(start + k) % n]]


def start_property_auction(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_AUCTION_START: R-202 auction among all active players starting at the decliner (P-03)."""
    _, p, starter, origin = frame
    state = eng.state
    if state.owner[p] != C.BANK:
        return
    participants = _ordered_from(eng, starter)
    if not participants:
        return
    price = eng.board.p_price[p]
    state.auction = AuctionState(
        F.I_PROPERTY, participants, eng.ruleset.sealed, price, "BUY", p=p, trigger=starter, origin=origin
    )
    eng.emit("AUCTION_STARTED", starter, {"p": p, "participants": participants, "origin": origin})
    eng.push((F.OP_D_AUCTION,))


def start_building_auction(
    eng: Engine, item: int, trigger: int, target_b: int, participants: list[int], prices: list[int]
) -> None:
    """P-19: start a scarcity auction for one house or hotel."""
    state = eng.state
    ref = eng.board.b_house_price[target_b]
    state.auction = AuctionState(
        item,
        participants,
        eng.ruleset.sealed,
        ref,
        state.phase,
        trigger=trigger,
        target_b=target_b,
        origin=F.ORIGIN_SCARCITY,
        bidder_price=prices,
    )
    eng.emit(
        "BUILDING_AUCTION_STARTED",
        trigger,
        {"item": ITEMS[item], "b": target_b, "participants": participants},
    )
    eng.push((F.OP_D_AUCTION,))


def bid_bounds(eng: Engine) -> tuple[int, int]:
    """(min bid, max legal bid) of the current bidder in an ascending auction (max < min: pass only)."""
    a = eng.state.auction
    assert a is not None
    seat = a.bidder
    cash = eng.state.cash[seat]
    if a.item == F.I_PROPERTY:
        lo = a.high_bid + 1 if a.high_bidder >= 0 else 1
        hi = cash  # K-02 bids are limited to current cash.
    else:
        lo = a.high_bid + 1 if a.high_bidder >= 0 else 0
        hi = cash - a.bidder_price[a.cursor]
    return lo, hi


def sealed_amounts(eng: Engine) -> tuple[list[int], list[bool]]:
    """Level amounts and legality for the current sealed bidder."""
    a = eng.state.auction
    assert a is not None
    cash = eng.state.cash[a.bidder]
    if a.item == F.I_PROPERTY:
        amounts = property_levels(a.ref_price)
        return amounts, [x <= cash for x in amounts]
    amounts = premium_levels(a.ref_price)
    own = a.bidder_price[a.cursor]
    return amounts, [x + own <= cash for x in amounts]


def bid_context(eng: Engine) -> dict[str, Any]:
    """Decision context of an AUCTION_BID decision (§4.4)."""
    a = eng.state.auction
    assert a is not None
    ctx: dict[str, Any] = {
        "item": ITEMS[a.item],
        "p": a.p,
        "format": FORMAT_SEALED if a.sealed else FORMAT_ASCENDING,
        "ref_price": a.ref_price,
        "trigger": a.trigger,
        "target_b": a.target_b,
        "bidder_price": a.bidder_price[a.cursor],
        "participants": list(a.participants),
        "origin": a.origin,
    }
    if a.sealed:
        amounts, legal = sealed_amounts(eng)
        ctx.update(
            high_bid=None,
            high_bidder=None,
            levels=amounts,
            legal_levels=legal,
            min_bid=min((x for x, ok in zip(amounts, legal) if ok), default=-1),
            max_bid=max((x for x, ok in zip(amounts, legal) if ok), default=-1),
        )
    else:
        lo, hi = bid_bounds(eng)
        ctx.update(
            high_bid=a.high_bid if a.high_bidder >= 0 else None,
            high_bidder=a.high_bidder if a.high_bidder >= 0 else None,
            min_bid=lo,
            max_bid=hi,
            actions=a.actions,
        )
    return ctx


def apply_bid(eng: Engine, response: Any) -> Any:
    """Apply an AUCTION_BID response; returns its serialised form for the log."""
    a = eng.state.auction
    assert a is not None
    seat = a.bidder
    if a.sealed:
        if not isinstance(response, BidLevel):
            raise eng.illegal("sealed auction expects BidLevel", seat)
        _, legal = sealed_amounts(eng)
        if response.index is None:
            a.bids[a.cursor] = -1
        else:
            idx = response.index
            if not isinstance(idx, int) or not 0 <= idx < len(legal) or not legal[idx]:
                raise eng.illegal(f"illegal sealed bid level {idx}", seat)
            amounts, _ = sealed_amounts(eng)
            a.bids[a.cursor] = amounts[idx]
        a.actions += 1
        eng.emit("BID", seat, {"sealed": True, "submitted": response.index is not None})
        if a.cursor + 1 < len(a.participants):
            a.cursor += 1
        else:
            _resolve_sealed(eng)
        return response.index
    if not isinstance(response, Bid):
        raise eng.illegal("ascending auction expects Bid", seat)
    if response.amount is None:
        a.passed[a.cursor] = True
        eng.emit("BID", seat, {"amount": None})
    else:
        lo, hi = bid_bounds(eng)
        amt = response.amount
        if not isinstance(amt, int) or isinstance(amt, bool) or amt < lo or amt > hi:
            raise eng.illegal(f"illegal bid {amt} (allowed {lo}..{hi})", seat)
        a.high_bid = amt
        a.high_bidder = seat
        eng.emit("BID", seat, {"amount": amt})
    a.actions += 1
    _advance_ascending(eng)
    return response.amount


def _advance_ascending(eng: Engine) -> None:
    """P-03 end conditions and rotation."""
    a = eng.state.auction
    assert a is not None
    if a.actions >= C.AUCTION_MAX_ACTIONS:
        _finish(eng, a.high_bidder, a.high_bid)
        return
    n = len(a.participants)
    open_others = [i for i in range(n) if not a.passed[i] and a.participants[i] != a.high_bidder]
    if not open_others:
        _finish(eng, a.high_bidder, a.high_bid)
        return
    for k in range(1, n + 1):
        i = (a.cursor + k) % n
        if not a.passed[i] and a.participants[i] != a.high_bidder:
            a.cursor = i
            return


def _resolve_sealed(eng: Engine) -> None:
    """D-02 / D-05 resolution: highest bid wins at min(own, second + 1)."""
    a = eng.state.auction
    assert a is not None
    valid = [(amt, i) for i, amt in enumerate(a.bids) if amt >= 0]
    if not valid:
        _finish(eng, -1, -1)
        return
    best_amt = max(amt for amt, _ in valid)
    win_idx = min(i for amt, i in valid if amt == best_amt)  # tie: order from decliner / trigger
    if len(valid) == 1:
        price = 1 if a.item == F.I_PROPERTY else 0
    else:
        second = max(amt for amt, i in valid if i != win_idx)
        price = min(best_amt, second + 1)
    _finish(eng, a.participants[win_idx], price)


def _finish(eng: Engine, winner: int, price: int) -> None:
    """Settle the auction result."""
    state = eng.state
    a = state.auction
    assert a is not None
    state.auction = None
    if a.item == F.I_PROPERTY:
        p = a.p
        if winner < 0:
            eng.emit("AUCTION_NO_SALE", -1, {"p": p})
            return
        eng.transfer(winner, C.BANK, price, "AUCTION")
        state.owner[p] = winner
        state.mortgaged[p] = False
        state.interest_prepaid[p] = -1
        eng.cnt(CNT_AUCTIONS_WON, winner)
        eng.cnt(CNT_AUCTION_SPEND, winner, price)
        eng.cnt(CNT_AUCTION_FACE, winner, eng.board.p_price[p])
        eng.emit("AUCTION_WON", winner, {"p": p, "price": price})
        return
    from propertyrl.engine import scarcity

    scarcity.finish_building_auction(eng, a, winner, price)


def pay_premium(eng: Engine, winner: int, premium: int) -> None:
    """Pay the scarcity premium to the bank."""
    if premium > 0:
        eng.transfer(winner, C.BANK, premium, "SCARCITY_PREMIUM")
    eng.cnt(CNT_SCARCITY_WON, winner)
    eng.cnt(CNT_SCARCITY_PREMIUM, winner, premium)
