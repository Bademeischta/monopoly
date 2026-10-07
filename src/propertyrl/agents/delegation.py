"""delegation_v1: risk-averse technical policy for delegated decision kinds of learning seats (§5.3)."""

from __future__ import annotations

import math
from typing import Any

from propertyrl.agents.base import Policy, ascending_bid, legal_ids, sealed_bid
from propertyrl.agents.heuristics import (
    cash_after_trade,
    cash_offers_for_missing,
    mortgage_smallest_income,
    policy_params,
    policy_version,
    scarcity_target,
    sell_from_weakest_group,
)
from propertyrl.agents.primitives import Valuer
from propertyrl.engine import Bid, BidLevel, RuleViolationError, TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import decisions as D
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState


class DelegationPolicy(Policy):
    """Delegation: trades, auctions, debt (and BUY in ablation N4). Never plays other MAIN phases."""

    name = "delegation_v1"

    def __init__(self) -> None:
        self.params = policy_params(self.name)
        self.version = policy_version(self.name)
        self.horizon = int(self.params["horizon_rounds"])

    def _valuer(self, view: PublicState) -> tuple[Valuer, int]:
        valuer = Valuer(view, self.horizon)
        return valuer, valuer.reserve(view.seat, int(self.params["reserve_min"]))

    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        """Only the BUY phase (ablation N4); any other phase is a programming error."""
        if view.phase != D.BUY_PHASE:
            raise RuleViolationError(f"delegation_v1 cannot decide MAIN phase {view.phase}", seat=view.seat)
        valuer, reserve = self._valuer(view)
        p = int(view.context["p"])
        price = view.board.p_price[p]
        cash = view.cash[view.seat]
        if legal[A.BUY] and (cash - price >= reserve or (valuer.completes_group(view.seat, p) and cash >= price)):
            return A.BUY
        return A.DECLINE

    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        valuer, reserve = self._valuer(view)
        return cash_offers_for_missing(
            valuer, view, float(self.params["offer_factor"]), reserve, int(self.params["max_offers"])
        )

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        valuer, reserve = self._valuer(view)
        me = view.seat
        if cash_after_trade(view, offer) < reserve:
            return False
        mine = valuer.trade_completes_group(me, offer)
        theirs = valuer.trade_completes_group(offer.proposer, offer)
        if theirs and not mine:
            return False
        ratio = valuer.value_ratio(offer, me)
        if mine and ratio >= float(self.params["accept_ratio_completing"]):
            return True
        return ratio >= float(self.params["accept_ratio"])

    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        valuer, reserve = self._valuer(view)
        me = view.seat
        cash = view.cash[me]
        frac = float(self.params["auction_step_fraction"])
        if auction["item"] == D.ITEM_PROPERTY:
            p = int(auction["p"])
            limit = min(valuer.asset_value(me, p), cash - reserve)
            if auction["format"] == D.FORMAT_SEALED:
                return sealed_bid(auction, limit)
            step = max(1, math.ceil(frac * view.board.p_price[p]))
            return ascending_bid(auction, limit, step)
        hotel = auction["item"] == D.ITEM_HOTEL
        target = scarcity_target(view, auction)
        b_star = target if target is not None else valuer.best_build_target(me, valuer.build_targets(me, hotel=hotel))
        if b_star < 0:
            return BidLevel(None) if auction["format"] == D.FORMAT_SEALED else Bid(None)
        price = view.board.b_house_price[b_star]
        bpv = valuer.building_premium_value(me, b_star)
        limit = min(math.floor(bpv / float(self.params["scarcity_divisor"])), cash - reserve - price)
        if limit < 0:
            return BidLevel(None) if auction["format"] == D.FORMAT_SEALED else Bid(None)
        if auction["format"] == D.FORMAT_SEALED:
            return sealed_bid(auction, limit)
        step = max(1, math.ceil(frac * price))
        return ascending_bid(auction, limit, step)

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        valuer, _ = self._valuer(view)
        ids = legal_ids(legal)
        m = mortgage_smallest_income(valuer, view, ids)
        if m >= 0:
            return m
        s = sell_from_weakest_group(valuer, view, ids)
        return s if s >= 0 else ids[0]
