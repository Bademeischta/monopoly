"""Policy protocol, response dispatch and shared helpers (§5.1)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from propertyrl.engine import Bid, BidLevel, Engine, TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState

#: Delegable decision kinds (§6.1). MAIN_BUY = MAIN decisions in phase BUY (ablation N4).
DELEGABLE_KINDS = ("TRADE_OFFER", "TRADE_RESPONSE", "AUCTION_BID", "DEBT", "MAIN_BUY")


class Policy(ABC):
    """A complete game policy. Policies only see :class:`PublicState` and are stateless between games."""

    name: str = "policy"
    version: str = "h1.0"

    @abstractmethod
    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        """Answer a MAIN decision (all MAIN phases including BUY and PLACE_BUILDING)."""

    @abstractmethod
    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        """Trade offers at the start of an own window (at most 2)."""

    @abstractmethod
    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        """Accept or reject an offer."""

    @abstractmethod
    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        """Bid in a property or scarcity auction."""

    @abstractmethod
    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        """Answer a DEBT decision (MORTGAGE or SELL_BUILDING)."""

    def spec(self) -> str:
        """Registry specification string (used by multiprocessing workers)."""
        return self.name

    def reset(self) -> None:  # noqa: B027 - optional hook
        """Called at game start; heuristics are stateless and keep the default."""


def clamp_bid(response: Bid | BidLevel, ctx: dict[str, Any]) -> Bid | BidLevel:
    """Limit a bid to the highest legal bid of the context; pass if the own limit is below the minimum."""
    if ctx["format"] == D.FORMAT_SEALED:
        if not isinstance(response, BidLevel) or response.index is None:
            return BidLevel(None)
        legal = ctx["legal_levels"]
        for i in range(min(response.index, len(legal) - 1), -1, -1):
            if legal[i]:
                return BidLevel(i)
        return BidLevel(None)
    if not isinstance(response, Bid) or response.amount is None:
        return Bid(None)
    amount = min(response.amount, ctx["max_bid"])
    if amount < ctx["min_bid"]:
        return Bid(None)
    return Bid(amount)


def ascending_bid(ctx: dict[str, Any], limit: float, step: int) -> Bid:
    """Raise by ``step`` (at least the minimum bid) while the result stays <= ``limit``; else pass."""
    lo = ctx["min_bid"]
    high = ctx["high_bid"]
    amount = lo if high is None else max(lo, high + step)
    if amount > math.floor(limit) or amount > ctx["max_bid"]:
        return Bid(None)
    return Bid(amount)


def sealed_bid(ctx: dict[str, Any], limit: float) -> BidLevel:
    """Highest legal sealed level whose amount is <= ``limit``; else pass."""
    best: int | None = None
    for i, (amount, ok) in enumerate(zip(ctx["levels"], ctx["legal_levels"], strict=True)):
        if ok and amount <= limit:
            best = i
    return BidLevel(best)


def bid_up_to(ctx: dict[str, Any], limit: float, step: int = 1) -> Bid | BidLevel:
    """Bid up to ``limit`` in either auction format."""
    if ctx["format"] == D.FORMAT_SEALED:
        return sealed_bid(ctx, limit)
    return ascending_bid(ctx, limit, step)


def legal_ids(legal: list[bool]) -> list[int]:
    """Indices of legal actions."""
    return [i for i, ok in enumerate(legal) if ok]


def filter_oscillation(window_actions: Sequence[tuple[int, int]], seat: int, actions: list[int]) -> list[int]:
    """Drop actions that would undo an action of ``seat`` in the current window (§5.1)."""
    mortgaged_now: set[int] = set()
    unmortgaged_now: set[int] = set()
    built_groups: set[int] = set()
    sold_groups: set[int] = set()
    for s, a in window_actions:
        if s != seat:
            continue
        if A.MORTGAGE_BASE <= a < A.UNMORTGAGE_BASE:
            mortgaged_now.add(a - A.MORTGAGE_BASE)
        elif a >= A.UNMORTGAGE_BASE:
            unmortgaged_now.add(a - A.UNMORTGAGE_BASE)
        elif A.BUILD_BASE <= a < A.SELL_BASE:
            built_groups.add(C.B_GROUP[a - A.BUILD_BASE])
        elif A.SELL_BASE <= a < A.MORTGAGE_BASE:
            sold_groups.add(C.B_GROUP[a - A.SELL_BASE])
    if not (mortgaged_now or unmortgaged_now or built_groups or sold_groups):
        return list(actions)
    out = []
    for a in actions:
        if a >= A.UNMORTGAGE_BASE and a - A.UNMORTGAGE_BASE in mortgaged_now:
            continue
        if A.MORTGAGE_BASE <= a < A.UNMORTGAGE_BASE and a - A.MORTGAGE_BASE in unmortgaged_now:
            continue
        if A.SELL_BASE <= a < A.MORTGAGE_BASE and C.B_GROUP[a - A.SELL_BASE] in built_groups:
            continue
        if A.BUILD_BASE <= a < A.SELL_BASE and C.B_GROUP[a - A.BUILD_BASE] in sold_groups:
            continue
        out.append(a)
    return out


def anti_oscillation(view: PublicState, actions: list[int]) -> list[int]:
    """Drop actions that would undo an action of this seat in the current window (§5.1)."""
    return filter_oscillation(view.window_actions, view.seat, actions)


def filtered_mask(window_actions: Sequence[tuple[int, int]], seat: int, legal: Sequence[bool]) -> list[bool]:
    """Legal mask with anti-oscillation applied (falls back to ``legal`` if nothing would remain)."""
    ids = [i for i, ok in enumerate(legal) if ok]
    kept = filter_oscillation(window_actions, seat, ids)
    if not kept:
        return list(legal)
    out = [False] * len(legal)
    for a in kept:
        out[a] = True
    return out


def finish_action(view: PublicState, legal: list[bool]) -> int:
    """The action that ends the current window/phase (ROLL, END_PHASE, DECLINE) or the first legal one."""
    for a in (A.ROLL, A.END_PHASE, A.DECLINE):
        if legal[a]:
            return a
    return legal_ids(legal)[0]


def decision_kind_key(d: D.Decision) -> str:
    """Delegation key of a decision (MAIN in phase BUY -> MAIN_BUY)."""
    if d.kind == D.MAIN and d.phase == D.BUY_PHASE:
        return "MAIN_BUY"
    return d.kind


def respond(policy: Policy, eng: Engine, rng: AgentRng, view: PublicState | None = None) -> Any:
    """Ask ``policy`` for the response to the engine's pending decision."""
    d = eng.pending()
    if d is None:
        raise ValueError("no pending decision")
    v = view if view is not None else eng.public_view(d.seat)
    return respond_decision(policy, d, v, rng)


def respond_decision(policy: Policy, d: D.Decision, view: PublicState, rng: AgentRng) -> Any:
    """Dispatch a decision to the matching policy method (with bid clamping)."""
    if d.kind == D.MAIN:
        assert d.legal is not None
        return policy.act_main(view, d.legal, rng)
    if d.kind == D.DEBT:
        assert d.legal is not None
        return policy.liquidate(view, d.legal, d.context, rng)
    if d.kind == D.TRADE_OFFER:
        return policy.propose_trades(view, rng)[: C.MAX_OFFERS_PER_WINDOW]
    if d.kind == D.TRADE_RESPONSE:
        return bool(policy.respond_trade(view, d.context["offer"], rng))
    return clamp_bid(policy.bid(view, d.context, rng), d.context)
