"""Shared building blocks of the deterministic heuristics (jail, debt, offers, building choices)."""

from __future__ import annotations

import math
from typing import Any

from propertyrl.agents.base import legal_ids
from propertyrl.agents.primitives import Valuer
from propertyrl.engine import TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine.trade import validate_offer
from propertyrl.engine.view import PublicState
from propertyrl.infra.config import load_policy_config


def policy_params(name: str) -> dict[str, Any]:
    """Parameters of configs/policies/<name>.yaml."""
    return dict(load_policy_config(name).params)


def policy_version(name: str) -> str:
    """heuristic_version of configs/policies/<name>.yaml."""
    return load_policy_config(name).heuristic_version


def of_kind(actions: list[int], base: int, size: int) -> list[int]:
    """Actions within [base, base + size)."""
    return [a for a in actions if base <= a < base + size]


def builds(actions: list[int]) -> list[int]:
    """BUILD action ids."""
    return of_kind(actions, A.BUILD_BASE, C.N_BUILD)


def sells(actions: list[int]) -> list[int]:
    """SELL_BUILDING action ids."""
    return of_kind(actions, A.SELL_BASE, C.N_BUILD)


def mortgages(actions: list[int]) -> list[int]:
    """MORTGAGE action ids."""
    return of_kind(actions, A.MORTGAGE_BASE, C.N_PROPS)


def unmortgages(actions: list[int]) -> list[int]:
    """UNMORTGAGE action ids."""
    return of_kind(actions, A.UNMORTGAGE_BASE, C.N_PROPS)


def unmortgage_cost(view: PublicState, p: int) -> int:
    """Cost of UNMORTGAGE_p (principal only while interest_prepaid is active)."""
    mv = view.board.p_mortgage[p]
    if view.interest_prepaid[p] >= 0:
        return mv
    return mv + C.ceil_div(mv * view.ruleset.mortgage_interest_percent, 100)


def leave_jail(legal: list[bool]) -> int:
    """Card first, then fine, else roll."""
    if legal[A.USE_JAIL_CARD]:
        return A.USE_JAIL_CARD
    if legal[A.PAY_JAIL_FINE]:
        return A.PAY_JAIL_FINE
    return A.ROLL


def mortgage_smallest_income(valuer: Valuer, view: PublicState, candidates: list[int], exclude_group: int = -1) -> int:
    """MORTGAGE action with the smallest marginal income (ties: smallest p); -1 if none."""
    best, best_val = -1, math.inf
    for a in mortgages(candidates):
        p = a - A.MORTGAGE_BASE
        if exclude_group >= 0 and C.P_GROUP[p] == exclude_group:
            continue
        val = valuer.marginal_income(view.seat, p)
        if val < best_val:
            best, best_val = a, val
    return best


def sell_from_weakest_group(valuer: Valuer, view: PublicState, candidates: list[int]) -> int:
    """SELL action from the group with the smallest income contribution (ties: smallest b); -1 if none."""
    best, best_val = -1, math.inf
    for a in sells(candidates):
        b = a - A.SELL_BASE
        g = C.B_GROUP[b]
        val = valuer.group_income(view.seat, g, view.owner, view.level)
        if val < best_val:
            best, best_val = a, val
    return best


def best_build_action(valuer: Valuer, view: PublicState, candidates: list[int]) -> int:
    """BUILD action with maximal level_income_gain / house price; -1 if none."""
    targets = [a - A.BUILD_BASE for a in builds(candidates)]
    b = valuer.best_build_target(view.seat, targets)
    return A.BUILD_BASE + b if b >= 0 else -1


def roi_threshold(valuer: Valuer) -> float:
    """Median over all 28 properties of base_income_per_round / price (roi_markov_v1)."""
    ratios = sorted(valuer.base_income_per_round(p) / valuer.board.p_price[p] for p in range(C.N_PROPS))
    mid = len(ratios) // 2
    return (ratios[mid - 1] + ratios[mid]) / 2.0


def cash_offers_for_missing(
    valuer: Valuer, view: PublicState, factor: float, reserve: int, max_offers: int
) -> list[TradeOffer]:
    """'Cash for the missing street' offers completing own colour groups (groups in board order)."""
    me = view.seat
    out: list[TradeOffer] = []
    cash = view.cash[me]
    for g in range(C.N_COLOR_GROUPS):
        if len(out) >= max_offers:
            break
        props = C.GROUP_PROPS[g]
        missing = [p for p in props if view.owner[p] != me]
        if len(missing) != 1:
            continue
        p = missing[0]
        opp = view.owner[p]
        if opp < 0 or view.bankrupt[opp] or any(view.level[b] for b in C.GROUP_BUILDS[g]):
            continue
        amount = math.ceil(factor * valuer.asset_value(opp, p))
        if cash - amount < reserve:
            continue
        offer = TradeOffer(me, opp, give_cash=amount, get_props=(p,))
        if validate_offer(view, view.board, view.ruleset, offer, me) is None:  # type: ignore[arg-type]
            out.append(offer)
            cash -= amount
    return out


def swap_offers_for_missing(valuer: Valuer, view: PublicState, max_offers: int, exclude: set[int]) -> list[TradeOffer]:
    """1:1 swaps for a missing street: give the cheapest own street that does not complete the opponent."""
    me = view.seat
    out: list[TradeOffer] = []
    for g in range(C.N_COLOR_GROUPS):
        if len(out) >= max_offers:
            break
        props = C.GROUP_PROPS[g]
        missing = [p for p in props if view.owner[p] != me]
        if len(missing) != 1 or missing[0] in exclude:
            continue
        p = missing[0]
        opp = view.owner[p]
        if opp < 0 or view.bankrupt[opp]:
            continue
        candidates = []
        for q in range(C.N_PROPS):
            if view.owner[q] != me or C.P_GROUP[q] == g:
                continue
            completes_opp = valuer.completes_group(opp, q)
            candidates.append((completes_opp, valuer.asset_value(me, q), q))
        for completes_opp, _, q in sorted(candidates):
            # Allowed even if it completes the opponent's group: then both complete (own group via p).
            del completes_opp
            offer = TradeOffer(me, opp, give_props=(q,), get_props=(p,))
            if validate_offer(view, view.board, view.ruleset, offer, me) is None:  # type: ignore[arg-type]
                out.append(offer)
                break
    return out


def cash_after_trade(view: PublicState, offer: TradeOffer) -> int:
    """Cash of the recipient after accepting (including immediate interest on mortgaged properties)."""
    me = view.seat
    cash = view.cash[me]
    if me == offer.recipient:
        cash += offer.give_cash - offer.get_cash
        received = offer.give_props
    else:
        cash += offer.get_cash - offer.give_cash
        received = offer.get_props
    for p in received:
        if view.mortgaged[p]:
            cash -= C.ceil_div(view.board.p_mortgage[p] * view.ruleset.mortgage_interest_percent, 100)
    return cash


def place_best(valuer: Valuer, view: PublicState, legal: list[bool]) -> int:
    """PLACE_BUILDING via best_build_target among the legal targets."""
    targets = [a - A.BUILD_BASE for a in legal_ids(legal)]
    b = valuer.best_build_target(view.seat, targets)
    return A.BUILD_BASE + (b if b >= 0 else targets[0])


def scarcity_target(view: PublicState, auction: dict[str, Any]) -> int | None:
    """b* of a scarcity auction: the trigger's chosen target, otherwise ``None`` (own best target)."""
    if auction.get("trigger") == view.seat and auction.get("target_b", -1) >= 0:
        return int(auction["target_b"])
    return None
