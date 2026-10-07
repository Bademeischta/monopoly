"""strong_b_v1: aggressive heuristic - buy always, build maximally, small reserve (§5.4)."""

from __future__ import annotations

from typing import Any

from propertyrl.agents.base import legal_ids
from propertyrl.agents.heuristics import (
    builds,
    cash_after_trade,
    cash_offers_for_missing,
    leave_jail,
    mortgage_smallest_income,
    mortgages,
    policy_params,
    policy_version,
    sells,
    unmortgage_cost,
    unmortgages,
)
from propertyrl.agents.primitives import Valuer
from propertyrl.agents.roi_markov import RoiMarkovPolicy
from propertyrl.engine import TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState


class StrongBPolicy(RoiMarkovPolicy):
    """Aggressive strong heuristic."""

    name = "strong_b_v1"

    def __init__(self) -> None:
        self.params = policy_params(self.name)
        self.version = policy_version(self.name)
        self.horizon = int(self.params["horizon_rounds"])

    def wants_buy(self, valuer: Valuer, view: PublicState, p: int, reserve: int) -> bool:
        """Always buy when cash suffices."""
        return view.cash[view.seat] >= view.board.p_price[p]

    def management(self, valuer: Valuer, view: PublicState, legal: list[bool], cands: list[int], reserve: int) -> int:
        me = view.seat
        cash = view.cash[me]
        bd = view.board
        affordable = [a for a in builds(cands) if cash - bd.b_house_price[a - A.BUILD_BASE] >= reserve]
        hotels = [a for a in affordable if view.level[a - A.BUILD_BASE] == C.HOTEL_LEVEL - 1]
        if hotels:
            return hotels[0]
        if affordable:
            return max(affordable, key=lambda a: (valuer.level_income_gain(me, a - A.BUILD_BASE)
                                                  / bd.b_house_price[a - A.BUILD_BASE], -a))  # fmt: skip
        # Mortgage outside the build groups if that makes a build affordable.
        wanted = builds(cands)
        if wanted:
            cheapest = min(bd.b_house_price[a - A.BUILD_BASE] for a in wanted)
            groups = {C.B_GROUP[a - A.BUILD_BASE] for a in wanted}
            options = [a for a in mortgages(cands) if C.P_GROUP[a - A.MORTGAGE_BASE] not in groups]
            if options and cash + max(bd.p_mortgage[a - A.MORTGAGE_BASE] for a in options) - cheapest >= reserve:
                m = mortgage_smallest_income(valuer, view, options)
                if m >= 0:
                    return m
        if not builds(legal_ids(legal)):
            minimum = int(self.params["unmortgage_min_cash"])
            um = [a for a in unmortgages(cands) if cash - unmortgage_cost(view, a - A.UNMORTGAGE_BASE) >= minimum]
            if um:
                return max(um, key=lambda a: (valuer.marginal_income(me, a - A.UNMORTGAGE_BASE), -a))
        return -1

    def jail(self, valuer: Valuer, view: PublicState, legal: list[bool]) -> int:
        """Leave immediately: card, then fine, else roll."""
        return leave_jail(legal)

    def place(self, valuer: Valuer, view: PublicState, legal: list[bool]) -> int:
        """Highest reachable level first, ties by best_build_target."""
        targets = [a - A.BUILD_BASE for a in legal_ids(legal)]
        top = max(view.level[b] for b in targets)
        best = valuer.best_build_target(view.seat, [b for b in targets if view.level[b] == top])
        return A.BUILD_BASE + (best if best >= 0 else targets[0])

    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        valuer = self.valuer(view)
        return cash_offers_for_missing(
            valuer,
            view,
            float(self.params["offer_factor"]),
            self.reserve(valuer, view),
            int(self.params["max_offers"]),
        )

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        valuer = self.valuer(view)
        me = view.seat
        if cash_after_trade(view, offer) < 0:
            return False
        mine = valuer.trade_completes_group(me, offer)
        theirs = valuer.trade_completes_group(offer.proposer, offer)
        if theirs and not mine:
            return False
        return valuer.value_ratio(offer, me) >= float(self.params["accept_ratio"])

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        valuer = self.valuer(view)
        ids = legal_ids(legal)
        s = sells(ids)
        if s:
            return min(s, key=lambda a: (view.level[a - A.SELL_BASE], a))
        m = mortgage_smallest_income(valuer, view, ids)
        return m if m >= 0 else ids[0]


__all__ = ["StrongBPolicy"]
