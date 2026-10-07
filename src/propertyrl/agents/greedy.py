"""greedy_v1: buy everything, build everywhere, never mortgage voluntarily, no trading (§5.4).

greedy_v1 is never a training opponent and serves as the unseen evaluation policy (A-32).
"""

from __future__ import annotations

from typing import Any

from propertyrl.agents.base import Policy, anti_oscillation, bid_up_to, finish_action, legal_ids
from propertyrl.agents.heuristics import (
    builds,
    leave_jail,
    mortgages,
    policy_params,
    policy_version,
    sells,
    unmortgages,
)
from propertyrl.engine import Bid, BidLevel, TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import decisions as D
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState


class GreedyPolicy(Policy):
    """Simple greedy heuristic."""

    name = "greedy_v1"

    def __init__(self) -> None:
        self.params = policy_params(self.name)
        self.version = policy_version(self.name)

    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        if view.phase == D.PLACE_BUILDING:
            return legal_ids(legal)[0]
        if view.phase == D.BUY_PHASE:
            return A.BUY if legal[A.BUY] else A.DECLINE
        cands = anti_oscillation(view, legal_ids(legal))
        b = builds(cands)
        if b:
            return b[0]
        u = unmortgages(cands)
        if u:
            return u[0]
        if view.phase == D.JAIL_PRE_ROLL:
            return leave_jail(legal)
        return finish_action(view, legal)

    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        return []

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        return False

    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        if auction["item"] == D.ITEM_PROPERTY:
            return bid_up_to(auction, float(self.params["auction_factor_of_price"]) * auction["ref_price"])
        # Scarcity auction: premium 0 if nobody has bid yet, otherwise pass.
        if auction["format"] == D.FORMAT_SEALED:
            return BidLevel(0)
        if auction["high_bid"] is None:
            return Bid(0)
        return Bid(None)

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        ids = legal_ids(legal)
        s = sells(ids)
        if s:
            return min(s, key=lambda a: (view.board.b_house_price[a - A.SELL_BASE], a))
        m = mortgages(ids)
        return min(m, key=lambda a: (view.board.p_mortgage[a - A.MORTGAGE_BASE], a))
