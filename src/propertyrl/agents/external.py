"""ExternalAgentAdapter: interface for attaching an external agent after a license check (§5.8).

Only the interface is part of PropertyRL (no foreign code, no download). See docs/EXTERNAL_ANCHOR.md.
A missing adapter simply removes the external anchor; no gate depends on it.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from propertyrl.agents.base import Policy
from propertyrl.engine import Bid, BidLevel, TradeOffer
from propertyrl.engine.errors import ConfigError
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState


class ExternalAgentAdapter(Policy):
    """Translate PublicState -> external state and external actions -> PropertyRL responses.

    Implementations must document every rule deviation of the external simulator (for instance,
    simulators that treat doubles like ordinary rolls) in docs/EXTERNAL_ANCHOR.md.
    """

    name = "external"

    @abstractmethod
    def translate_state(self, view: PublicState) -> Any:
        """Convert the public view into the external agent's state representation."""
        raise NotImplementedError

    @abstractmethod
    def translate_action(self, external_action: Any, view: PublicState, legal: list[bool]) -> int:
        """Convert an external action into a legal PropertyRL action id."""
        raise NotImplementedError

    @abstractmethod
    def external_decide(self, external_state: Any, rng: AgentRng) -> Any:
        """Ask the external agent for its action."""
        raise NotImplementedError

    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        return self.translate_action(self.external_decide(self.translate_state(view), rng), view, legal)

    @abstractmethod
    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        raise NotImplementedError

    @abstractmethod
    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        raise NotImplementedError

    @abstractmethod
    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        raise NotImplementedError

    @abstractmethod
    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        raise NotImplementedError


_ADAPTERS: dict[str, type[ExternalAgentAdapter]] = {}


def register_external(name: str, cls: type[ExternalAgentAdapter]) -> None:
    """Register an adapter class (done by the user after the license check)."""
    _ADAPTERS[name] = cls


def make_external(name: str) -> ExternalAgentAdapter:
    """Instantiate a registered adapter; ConfigError if none is registered."""
    if name not in _ADAPTERS:
        raise ConfigError(f"no external agent adapter registered under {name!r} (see docs/EXTERNAL_ANCHOR.md)")
    return _ADAPTERS[name]()
