"""strong_a_v1: roi_markov_v1 plus dynamic reserve, blocking purchases, level-3 targets and trading (§5.4)."""

from __future__ import annotations

from typing import Any

from propertyrl.agents.base import anti_oscillation, legal_ids
from propertyrl.agents.heuristics import (
    builds,
    cash_after_trade,
    cash_offers_for_missing,
    mortgage_smallest_income,
    policy_params,
    policy_version,
    sell_from_weakest_group,
    swap_offers_for_missing,
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


class StrongAPolicy(RoiMarkovPolicy):
    """Balanced strong heuristic."""

    name = "strong_a_v1"

    def __init__(self) -> None:
        self.params = policy_params(self.name)
        self.version = policy_version(self.name)
        self.horizon = int(self.params["horizon_rounds"])

    def reserve(self, valuer: Valuer, view: PublicState) -> int:
        """Dynamic reserve(150)."""
        return valuer.reserve(view.seat, int(self.params["reserve_min"]))

    def wants_buy(self, valuer: Valuer, view: PublicState, p: int, reserve: int) -> bool:
        """ROI rule plus buying to block an opponent's group."""
        if super().wants_buy(valuer, view, p, reserve):
            return True
        price = view.board.p_price[p]
        return (
            bool(self.params["buy_to_block"])
            and view.cash[view.seat] - price >= reserve
            and valuer.blocks_group(view.seat, p)
        )

    def _monopolies_below(self, view: PublicState, level: int) -> list[int]:
        me = view.seat
        out = []
        for g in range(C.N_COLOR_GROUPS):
            props = C.GROUP_PROPS[g]
            if all(view.owner[q] == me and not view.mortgaged[q] for q in props):
                if min(view.level[b] for b in C.GROUP_BUILDS[g]) < level:
                    out.append(g)
        return out

    def management(self, valuer: Valuer, view: PublicState, legal: list[bool], cands: list[int], reserve: int) -> int:
        me = view.seat
        cash = view.cash[me]
        target = int(self.params["build_target_level"])
        bd = view.board
        # Phase 1: bring every monopoly to the target level (largest rent gain first).
        phase1 = [
            a for a in builds(cands)
            if view.level[a - A.BUILD_BASE] < target and cash - bd.b_house_price[a - A.BUILD_BASE] >= reserve
        ]  # fmt: skip
        if phase1:
            return max(phase1, key=lambda a: (valuer.level_income_gain(me, a - A.BUILD_BASE), -a))
        # Voluntary mortgage only if it brings a group to the target level right away.
        m = self._mortgage_for_target(valuer, view, cands, reserve, target)
        if m >= 0:
            return m
        # Phase 2: houses 4 and hotels with an extra reserve, once all monopolies reached the target.
        if not self._monopolies_below(view, target):
            extra = int(self.params["hotel_extra_reserve"])
            phase2 = [a for a in builds(cands) if cash - bd.b_house_price[a - A.BUILD_BASE] >= reserve + extra]
            if phase2:
                return max(phase2, key=lambda a: (valuer.level_income_gain(me, a - A.BUILD_BASE)
                                                  / bd.b_house_price[a - A.BUILD_BASE], -a))  # fmt: skip
        factor = float(self.params["unmortgage_reserve_factor"])
        um = [a for a in unmortgages(cands) if cash - unmortgage_cost(view, a - A.UNMORTGAGE_BASE) >= factor * reserve]
        if um:
            return max(um, key=lambda a: (valuer.marginal_income(me, a - A.UNMORTGAGE_BASE), -a))
        return -1

    def _mortgage_for_target(
        self, valuer: Valuer, view: PublicState, cands: list[int], reserve: int, target: int
    ) -> int:
        me = view.seat
        cash = view.cash[me]
        bd = view.board
        for g in self._monopolies_below(view, target):
            if view.bank_houses <= 0:
                break
            cost = sum(
                (target - view.level[b]) * bd.b_house_price[b] for b in C.GROUP_BUILDS[g] if view.level[b] < target
            )
            if cash - reserve >= cost:
                continue
            capacity = sum(
                bd.p_mortgage[a - A.MORTGAGE_BASE]
                for a in cands
                if A.MORTGAGE_BASE <= a < A.UNMORTGAGE_BASE and C.P_GROUP[a - A.MORTGAGE_BASE] != g
            )
            if cash - reserve + capacity >= cost:
                m = mortgage_smallest_income(valuer, view, cands, exclude_group=g)
                if m >= 0:
                    return m
        return -1

    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        valuer = self.valuer(view)
        reserve = self.reserve(valuer, view)
        max_offers = int(self.params["max_offers"])
        offers = cash_offers_for_missing(valuer, view, float(self.params["offer_factor"]), reserve, max_offers)
        if len(offers) < max_offers:
            covered = {p for o in offers for p in o.get_props}
            offers += swap_offers_for_missing(valuer, view, max_offers - len(offers), covered)
        return offers[:max_offers]

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        valuer = self.valuer(view)
        me = view.seat
        if cash_after_trade(view, offer) < self.reserve(valuer, view):
            return False
        mine = valuer.trade_completes_group(me, offer)
        theirs = valuer.trade_completes_group(offer.proposer, offer)
        if mine:
            return True  # own group complete: accepted whether the proposer completes too or not
        return not theirs and valuer.value_ratio(offer, me) >= float(self.params["accept_ratio"])

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        valuer = self.valuer(view)
        ids = anti_oscillation(view, legal_ids(legal)) or legal_ids(legal)
        m = mortgage_smallest_income(valuer, view, ids)
        if m >= 0:
            return m
        s = sell_from_weakest_group(valuer, view, ids)
        return s if s >= 0 else ids[0]


__all__ = ["StrongAPolicy"]
