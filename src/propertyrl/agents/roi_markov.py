"""roi_markov_v1: return-on-investment buying with Markov landing frequencies (§5.4)."""

from __future__ import annotations

import math
from typing import Any

from propertyrl.agents.base import Policy, anti_oscillation, bid_up_to, finish_action, legal_ids
from propertyrl.agents.heuristics import (
    best_build_action,
    builds,
    leave_jail,
    mortgage_smallest_income,
    place_best,
    policy_params,
    policy_version,
    roi_threshold,
    scarcity_target,
    sells,
    unmortgage_cost,
    unmortgages,
)
from propertyrl.agents.primitives import Valuer
from propertyrl.engine import Bid, BidLevel, TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState


class RoiMarkovPolicy(Policy):
    """Buys by ROI threshold, builds by rent gain per house price, keeps a fixed reserve."""

    name = "roi_markov_v1"

    def __init__(self) -> None:
        self.params = policy_params(self.name)
        self.version = policy_version(self.name)
        self.horizon = int(self.params["horizon_rounds"])

    # ------------------------------------------------------------------ parameters
    def valuer(self, view: PublicState) -> Valuer:
        """Valuation primitives for this view."""
        return Valuer(view, self.horizon)

    def reserve(self, valuer: Valuer, view: PublicState) -> int:
        """Cash reserve (fixed for roi_markov_v1)."""
        return int(self.params["reserve"])

    def wants_buy(self, valuer: Valuer, view: PublicState, p: int, reserve: int) -> bool:
        """Purchase rule: ROI >= theta with reserve, or completing an own group."""
        me = view.seat
        price = view.board.p_price[p]
        cash = view.cash[me]
        if valuer.completes_group(me, p) and cash >= price:
            return True
        return cash - price >= reserve and valuer.base_income_per_round(p) / price >= roi_threshold(valuer)

    # ------------------------------------------------------------------ MAIN
    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        valuer = self.valuer(view)
        if view.phase == D.PLACE_BUILDING:
            return self.place(valuer, view, legal)
        reserve = self.reserve(valuer, view)
        if view.phase == D.BUY_PHASE:
            return self.buy_phase(valuer, view, legal, reserve)
        cands = anti_oscillation(view, legal_ids(legal))
        action = self.management(valuer, view, legal, cands, reserve)
        if action >= 0:
            return action
        if view.phase == D.JAIL_PRE_ROLL:
            return self.jail(valuer, view, legal)
        return finish_action(view, legal)

    def buy_phase(self, valuer: Valuer, view: PublicState, legal: list[bool], reserve: int) -> int:
        """BUY / raise money for a completing purchase (P-09) / DECLINE."""
        p = int(view.context["p"])
        me = view.seat
        if legal[A.BUY] and self.wants_buy(valuer, view, p, reserve):
            return A.BUY
        if valuer.completes_group(me, p) and view.cash[me] < view.board.p_price[p]:
            cands = anti_oscillation(view, legal_ids(legal))
            m = mortgage_smallest_income(valuer, view, cands, exclude_group=C.P_GROUP[p])
            if m >= 0:
                return m
        return A.DECLINE

    def management(self, valuer: Valuer, view: PublicState, legal: list[bool], cands: list[int], reserve: int) -> int:
        """Build, then unmortgage; -1 if nothing to do."""
        me = view.seat
        cash = view.cash[me]
        affordable = [a for a in builds(cands) if cash - view.board.b_house_price[a - A.BUILD_BASE] >= reserve]
        b = best_build_action(valuer, view, affordable)
        if b >= 0:
            return b
        factor = float(self.params["unmortgage_reserve_factor"])
        um = [a for a in unmortgages(cands) if cash - unmortgage_cost(view, a - A.UNMORTGAGE_BASE) >= factor * reserve]
        if um:
            return max(um, key=lambda a: (valuer.marginal_income(me, a - A.UNMORTGAGE_BASE), -a))
        return -1

    def jail(self, valuer: Valuer, view: PublicState, legal: list[bool]) -> int:
        """Stay (roll) while opponents' expected rent is high, otherwise leave."""
        if valuer.opponent_expected_rent(view.seat) >= float(self.params["jail_stay_threshold"]):
            return A.ROLL
        return leave_jail(legal)

    def place(self, valuer: Valuer, view: PublicState, legal: list[bool]) -> int:
        """PLACE_BUILDING via best_build_target."""
        return place_best(valuer, view, legal)

    # ------------------------------------------------------------------ other kinds
    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        return []

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        return False

    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        valuer = self.valuer(view)
        if auction["item"] == D.ITEM_PROPERTY:
            limit = float(self.params["auction_factor"]) * valuer.asset_value(view.seat, int(auction["p"]))
            return bid_up_to(auction, limit)
        hotel = auction["item"] == D.ITEM_HOTEL
        bpv = valuer.building_premium_value(view.seat, scarcity_target(view, auction), hotel=hotel)
        return bid_up_to(auction, math.floor(float(self.params["scarcity_factor"]) * bpv))

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        valuer = self.valuer(view)
        ids = legal_ids(legal)
        m = mortgage_smallest_income(valuer, view, ids)
        if m >= 0:
            return m
        s = sells(ids)
        return min(s, key=lambda a: (self._loss(valuer, view, a - A.SELL_BASE), a))

    @staticmethod
    def _loss(valuer: Valuer, view: PublicState, b: int) -> float:
        """Income lost by selling one level on b."""
        levels = list(view.level)
        levels[b] -= 1
        return valuer.income_per_round(view.seat) - valuer.income_per_round(view.seat, None, levels)
