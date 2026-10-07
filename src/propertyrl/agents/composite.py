"""Policy composition: CompositePolicy (learning seat), WithDelegation (ablation), EpsilonPolicy (§5.5, §5.6)."""

from __future__ import annotations

from typing import Any

from propertyrl.agents.base import Policy, legal_ids
from propertyrl.engine import Bid, BidLevel, TradeOffer
from propertyrl.engine import decisions as D
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState


class CompositePolicy(Policy):
    """MAIN decisions from ``main``; all delegated kinds from ``delegated``."""

    def __init__(self, main: Policy, delegated: Policy, delegated_kinds: tuple[str, ...]) -> None:
        self.main = main
        self.delegated = delegated
        self.kinds = frozenset(delegated_kinds)
        self.name = f"composite({main.name}+{delegated.name})"
        self.version = f"{main.version}+{delegated.version}"

    def _for(self, kind: str) -> Policy:
        return self.delegated if kind in self.kinds else self.main

    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        kind = "MAIN_BUY" if view.phase == D.BUY_PHASE else "MAIN"
        return self._for(kind).act_main(view, legal, rng)

    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        return self._for("TRADE_OFFER").propose_trades(view, rng)

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        return self._for("TRADE_RESPONSE").respond_trade(view, offer, rng)

    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        return self._for("AUCTION_BID").bid(view, auction, rng)

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        return self._for("DEBT").liquidate(view, legal, debt, rng)

    def spec(self) -> str:
        return f"composite:{self.main.spec()}+{self.delegated.spec()}"


class WithDelegation(CompositePolicy):
    """Benchmark policy whose delegable kinds are replaced by the delegation (ablation 'shared delegation')."""

    def __init__(self, policy: Policy, delegation: Policy, delegated_kinds: tuple[str, ...] | None = None) -> None:
        kinds = delegated_kinds or ("TRADE_OFFER", "TRADE_RESPONSE", "AUCTION_BID", "DEBT")
        super().__init__(policy, delegation, kinds)
        self.name = f"{policy.name}+{delegation.name}"

    def spec(self) -> str:
        return f"with_delegation:{self.main.spec()}"


class EpsilonPolicy(Policy):
    """With probability ``epsilon`` a MAIN decision is replaced by a uniformly random legal action."""

    def __init__(self, inner: Policy, epsilon: float) -> None:
        self.inner = inner
        self.epsilon = float(epsilon)
        self.name = inner.name
        self.version = inner.version

    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        if self.epsilon > 0 and rng.random() < self.epsilon:
            return rng.choice(legal_ids(legal))
        return self.inner.act_main(view, legal, rng)

    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        return self.inner.propose_trades(view, rng)

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        return self.inner.respond_trade(view, offer, rng)

    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        return self.inner.bid(view, auction, rng)

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        return self.inner.liquidate(view, legal, debt, rng)

    def spec(self) -> str:
        return f"epsilon:{self.epsilon}:{self.inner.spec()}"

    def reset(self) -> None:
        self.inner.reset()
