"""Policy registry: name/spec -> factory (§5.7). Specs are plain strings so workers can rebuild policies."""

from __future__ import annotations

from collections.abc import Callable

from propertyrl.agents.base import Policy
from propertyrl.agents.composite import EpsilonPolicy, WithDelegation
from propertyrl.agents.delegation import DelegationPolicy
from propertyrl.agents.greedy import GreedyPolicy
from propertyrl.agents.random_legal import RandomLegalPolicy
from propertyrl.agents.roi_markov import RoiMarkovPolicy
from propertyrl.agents.strong_a import StrongAPolicy
from propertyrl.agents.strong_b import StrongBPolicy
from propertyrl.engine.errors import ConfigError

BASELINES: dict[str, Callable[[], Policy]] = {
    "random_legal": RandomLegalPolicy,
    "greedy_v1": GreedyPolicy,
    "roi_markov_v1": RoiMarkovPolicy,
    "strong_a_v1": StrongAPolicy,
    "strong_b_v1": StrongBPolicy,
    "delegation_v1": DelegationPolicy,
}
BENCHMARK_POLICIES = ("random_legal", "greedy_v1", "roi_markov_v1", "strong_a_v1", "strong_b_v1")
#: greedy_v1 is never a training opponent (A-32).
TRAINING_OPPONENTS = ("random_legal", "roi_markov_v1", "strong_a_v1", "strong_b_v1")
_CACHE: dict[str, Policy] = {}


def make_policy(spec: str) -> Policy:
    """Build a policy from a spec string.

    Supported: baseline names, ``with_delegation:<spec>``, ``epsilon:<eps>:<spec>``,
    ``sb3:<path>`` (deterministic), ``sb3s:<path>`` / ``snapshot:<path>`` / ``latest:<path>`` (stochastic),
    ``external:<name>``.
    """
    if spec in BASELINES:
        return BASELINES[spec]()
    head, _, rest = spec.partition(":")
    if head == "with_delegation":
        return WithDelegation(make_policy(rest), DelegationPolicy())
    if head == "epsilon":
        eps, _, inner = rest.partition(":")
        return EpsilonPolicy(make_policy(inner), float(eps))
    if head in ("sb3", "sb3s", "snapshot", "latest"):
        from propertyrl.agents.sb3_agent import SB3Agent

        return SB3Agent(rest, deterministic=head == "sb3", spec_prefix=head)
    if head == "external":
        from propertyrl.agents.external import make_external

        return make_external(rest)
    raise ConfigError(f"unknown policy spec {spec!r}")


def cached_policy(spec: str) -> Policy:
    """Process-wide cached policy instance (policies are stateless between games)."""
    pol = _CACHE.get(spec)
    if pol is None:
        pol = make_policy(spec)
        _CACHE[spec] = pol
    return pol


def clear_cache() -> None:
    """Drop cached policies (e.g. after a snapshot file was replaced)."""
    _CACHE.clear()
