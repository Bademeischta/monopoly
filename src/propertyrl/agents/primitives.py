"""Deterministic valuation primitives shared by all heuristics (§5.2)."""

from __future__ import annotations

import functools
import math
from collections.abc import Sequence

from propertyrl.engine import TradeOffer, markov
from propertyrl.engine import constants as C
from propertyrl.engine.rent import rent_now as _engine_rent_now
from propertyrl.engine.view import PublicState
from propertyrl.infra.config import load_decks

JAIL_LEAVE = markov.JAIL_LEAVE
JAIL_STAY = markov.JAIL_STAY
JAIL_CARD_VALUE = 50.0


@functools.lru_cache(maxsize=4)
def landing_freq(jail_policy: str = JAIL_LEAVE) -> tuple[float, ...]:
    """Expected rest events per opponent turn on every square (§4.11 b), cached per jail policy."""
    return tuple(markov.landing_frequencies(load_decks(), jail_policy))


class _Hypo:
    """Minimal state view (owner, mortgaged, level) for hypothetical rent computations."""

    __slots__ = ("level", "mortgaged", "owner")

    def __init__(self, owner: Sequence[int], mortgaged: Sequence[bool], level: Sequence[int]) -> None:
        self.owner = owner
        self.mortgaged = mortgaged
        self.level = level


class Valuer:
    """Valuation primitives for one public view (results cached per instance)."""

    def __init__(self, view: PublicState, horizon: int = 10, jail_policy: str = JAIL_LEAVE) -> None:
        self.view = view
        self.board = view.board
        self.horizon = horizon
        self.freq = landing_freq(jail_policy)
        self.n_active = view.n_active()
        self.mult = max(1, self.n_active - 1)
        self._income: dict[int, float] = {}

    # ------------------------------------------------------------------ rents and income
    def rent_now(self, p: int, owner: Sequence[int] | None = None, levels: Sequence[int] | None = None) -> int:
        """Current rent on landing (utilities with expected dice 7); 0 for bank-owned or mortgaged."""
        v = self.view
        hypo = _Hypo(owner if owner is not None else v.owner, v.mortgaged, levels if levels is not None else v.level)
        return _engine_rent_now(hypo, self.board, p)  # type: ignore[arg-type]

    def expected_rent(self, p: int, owner: Sequence[int] | None = None, levels: Sequence[int] | None = None) -> float:
        """landing_freq[square(p)] x rent_now(p)."""
        return self.freq[C.PROP_SQUARES[p]] * self.rent_now(p, owner, levels)

    def income_per_round(
        self, player: int, owner: Sequence[int] | None = None, levels: Sequence[int] | None = None
    ) -> float:
        """Sum of expected rents over own unmortgaged properties x (active players - 1)."""
        if owner is None and levels is None and player in self._income:
            return self._income[player]
        own = owner if owner is not None else self.view.owner
        total = 0.0
        mortgaged = self.view.mortgaged
        for p in range(C.N_PROPS):
            if own[p] == player and not mortgaged[p]:
                total += self.expected_rent(p, own, levels)
        total *= self.mult
        if owner is None and levels is None:
            self._income[player] = total
        return total

    def marginal_income(self, player: int, p: int) -> float:
        """income_per_round with p minus without p (captures group doubling)."""
        own = list(self.view.owner)
        if own[p] == player:
            without = list(own)
            without[p] = C.BANK
            return self.income_per_round(player) - self.income_per_round(player, without)
        with_p = list(own)
        with_p[p] = player
        return self.income_per_round(player, with_p) - self.income_per_round(player)

    def base_income_per_round(self, p: int) -> float:
        """Income of p held alone, unbuilt and unmortgaged (ROI primitive of roi_markov_v1)."""
        own = [C.BANK] * C.N_PROPS
        own[p] = 0
        hypo = _Hypo(own, [False] * C.N_PROPS, [0] * C.N_BUILD)
        return self.freq[C.PROP_SQUARES[p]] * _engine_rent_now(hypo, self.board, p) * self.mult  # type: ignore[arg-type]

    # ------------------------------------------------------------------ groups
    def owns_rest_of_group(self, player: int, p: int) -> bool:
        """True if ``player`` holds every other property of p's colour group."""
        g = C.P_GROUP[p]
        if g >= C.N_COLOR_GROUPS:
            return False
        return all(self.view.owner[q] == player for q in C.GROUP_PROPS[g] if q != p)

    def completes_group(self, player: int, p: int) -> bool:
        """True if acquiring p gives ``player`` a complete colour group."""
        return self.view.owner[p] != player and self.owns_rest_of_group(player, p)

    def blocks_group(self, player: int, p: int) -> bool:
        """True if an opponent holds (group size - 1) properties of p's colour group."""
        g = C.P_GROUP[p]
        if g >= C.N_COLOR_GROUPS:
            return False
        props = C.GROUP_PROPS[g]
        for opp in range(self.view.n_players):
            if opp == player or self.view.bankrupt[opp]:
                continue
            if sum(1 for q in props if self.view.owner[q] == opp) == len(props) - 1:
                return True
        return False

    def group_income(self, player: int, g: int, owner: Sequence[int], levels: Sequence[int]) -> float:
        """Income per round of the unmortgaged streets of group g for ``player``."""
        total = 0.0
        for q in C.GROUP_PROPS[g]:
            if owner[q] == player and not self.view.mortgaged[q]:
                total += self.expected_rent(q, owner, levels)
        return total * self.mult

    def asset_value(self, player: int, p: int) -> float:
        """Printed price (x0.5 if mortgaged) + H x marginal income (+ group-completion bonus)."""
        price = self.board.p_price[p]
        value = price * (0.5 if self.view.mortgaged[p] else 1.0) + self.horizon * self.marginal_income(player, p)
        if self.owns_rest_of_group(player, p):
            g = C.P_GROUP[p]
            own = list(self.view.owner)
            own[p] = player
            levels3 = list(self.view.level)
            for b in C.GROUP_BUILDS[g]:
                levels3[b] = max(levels3[b], 3)
            gain = self.group_income(player, g, own, levels3) - self.group_income(player, g, own, self.view.level)
            value += 0.5 * self.horizon * gain
        return value

    # ------------------------------------------------------------------ trades and reserves
    def value_ratio(self, offer: TradeOffer, player: int) -> float:
        """(value received + cash received - immediate interest) / (value given + cash given)."""
        rules = self.view.ruleset
        if player == offer.recipient:
            recv_props, give_props = offer.give_props, offer.get_props
            recv_cash, give_cash = offer.give_cash, offer.get_cash
            recv_cards, give_cards = offer.give_jail_cards, offer.get_jail_cards
        else:
            recv_props, give_props = offer.get_props, offer.give_props
            recv_cash, give_cash = offer.get_cash, offer.give_cash
            recv_cards, give_cards = offer.get_jail_cards, offer.give_jail_cards
        interest = sum(
            C.ceil_div(self.board.p_mortgage[p] * rules.mortgage_interest_percent, 100)
            for p in recv_props
            if self.view.mortgaged[p]
        )
        received = sum(self.asset_value(player, p) for p in recv_props)
        received += recv_cash + JAIL_CARD_VALUE * bin(recv_cards).count("1") - interest
        given = sum(self.asset_value(player, p) for p in give_props)
        given += give_cash + JAIL_CARD_VALUE * bin(give_cards).count("1")
        if given <= 0:
            return math.inf
        return received / given

    def trade_completes_group(self, player: int, offer: TradeOffer) -> bool:
        """True if the trade gives ``player`` a complete colour group it did not have before."""
        own = list(self.view.owner)
        before = self._complete_groups(player, own)
        for p in offer.give_props:
            own[p] = offer.recipient
        for p in offer.get_props:
            own[p] = offer.proposer
        return bool(self._complete_groups(player, own) - before)

    @staticmethod
    def _complete_groups(player: int, owner: Sequence[int]) -> set[int]:
        return {g for g in range(C.N_COLOR_GROUPS) if all(owner[q] == player for q in C.GROUP_PROPS[g])}

    def max_opp_rent(self, player: int) -> int:
        """Highest current rent of an opponent's property."""
        best = 0
        for p in range(C.N_PROPS):
            o = self.view.owner[p]
            if o >= 0 and o != player and not self.view.bankrupt[o]:
                best = max(best, self.rent_now(p))
        return best

    def reserve(self, player: int, r_min: int) -> int:
        """reserve(R_min) = max(R_min, ceil(0.25 x max_opp_rent))."""
        return max(r_min, math.ceil(0.25 * self.max_opp_rent(player)))

    def opponent_expected_rent(self, player: int) -> float:
        """Sum of expected rents over all opponents' properties (one landing perspective)."""
        total = 0.0
        for p in range(C.N_PROPS):
            o = self.view.owner[p]
            if o >= 0 and o != player and not self.view.bankrupt[o]:
                total += self.expected_rent(p)
        return total

    # ------------------------------------------------------------------ building
    def level_income_gain(self, player: int, b: int) -> float:
        """Increase of income_per_round if street b were one level higher."""
        levels = list(self.view.level)
        if levels[b] >= C.HOTEL_LEVEL:
            return 0.0
        levels[b] += 1
        return self.income_per_round(player, None, levels) - self.income_per_round(player)

    def build_targets(self, player: int, hotel: bool | None = None, cash: int | None = None) -> list[int]:
        """Structurally legal, affordable building targets (bank stock ignored; ``hotel`` filters the kind)."""
        v = self.view
        budget = v.cash[player] if cash is None else cash
        out = []
        for g in range(C.N_COLOR_GROUPS):
            props = C.GROUP_PROPS[g]
            if not all(v.owner[q] == player and not v.mortgaged[q] for q in props):
                continue
            builds = C.GROUP_BUILDS[g]
            mn = min(v.level[b] for b in builds)
            if mn >= C.HOTEL_LEVEL:
                continue
            is_hotel = mn == C.HOTEL_LEVEL - 1
            if hotel is not None and is_hotel != hotel:
                continue
            for b in builds:
                if v.level[b] == mn and self.board.b_house_price[b] <= budget:
                    out.append(b)
        return sorted(out)

    def best_build_target(self, player: int, candidates: Sequence[int] | None = None) -> int:
        """Build target with maximal level_income_gain / house price (ties: smallest b); -1 if none."""
        cands = list(candidates) if candidates is not None else self.build_targets(player)
        best, best_score = -1, -math.inf
        for b in sorted(cands):
            score = self.level_income_gain(player, b) / self.board.b_house_price[b]
            if score > best_score:
                best, best_score = b, score
        return best

    def building_premium_value(self, player: int, target: int | None = None, hotel: bool | None = None) -> float:
        """max(0, H x level_income_gain(b*) - house price(b*)) with b* the given or best target."""
        b = target if target is not None and target >= 0 else self.best_build_target(
            player, self.build_targets(player, hotel=hotel))  # fmt: skip
        if b < 0:
            return 0.0
        return max(0.0, self.horizon * self.level_income_gain(player, b) - self.board.b_house_price[b])

    def groups_needing(self, player: int, p: int) -> int:
        """Colour group id of p if ``player`` owns size - 1 of it (missing exactly p); else -1."""
        g = C.P_GROUP[p]
        if g >= C.N_COLOR_GROUPS or self.view.owner[p] == player:
            return -1
        return g if self.owns_rest_of_group(player, p) else -1
