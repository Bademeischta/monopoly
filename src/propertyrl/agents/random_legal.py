"""random_legal: uniformly random legal play (also the fuzzing agent, §5.4)."""

from __future__ import annotations

from typing import Any

from propertyrl.agents.base import Policy, legal_ids
from propertyrl.agents.heuristics import policy_params, policy_version
from propertyrl.engine import Bid, BidLevel, TradeOffer
from propertyrl.engine import decisions as D
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState


class RandomLegalPolicy(Policy):
    """Uniform over legal actions; no offers; accepts with probability 0.5; random bids."""

    name = "random_legal"

    def __init__(self) -> None:
        self.params = policy_params(self.name)
        self.version = policy_version(self.name)

    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        return rng.choice(legal_ids(legal))

    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        return []

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        return rng.random() < float(self.params["accept_probability"])

    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        if auction["format"] == D.FORMAT_SEALED:
            choices: list[int | None] = [i for i, ok in enumerate(auction["legal_levels"]) if ok]
            return BidLevel(rng.choice([*choices, None]))
        if rng.random() < float(self.params["pass_probability"]):
            return Bid(None)
        lo = auction["min_bid"]
        high = auction["high_bid"] if auction["high_bid"] is not None else 0
        hi = min(auction["max_bid"], high + auction["ref_price"])
        if hi < lo:
            return Bid(None)
        return Bid(rng.randint(lo, hi))

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        return rng.choice(legal_ids(legal))
