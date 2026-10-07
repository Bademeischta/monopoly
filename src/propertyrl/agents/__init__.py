"""Agents: policy protocol, valuation primitives, delegation, benchmark policies and registry (§5)."""

from propertyrl.agents.base import (
    DELEGABLE_KINDS,
    Policy,
    anti_oscillation,
    clamp_bid,
    respond,
    respond_decision,
)
from propertyrl.agents.composite import CompositePolicy, EpsilonPolicy, WithDelegation
from propertyrl.agents.delegation import DelegationPolicy
from propertyrl.agents.external import ExternalAgentAdapter, make_external, register_external
from propertyrl.agents.greedy import GreedyPolicy
from propertyrl.agents.primitives import Valuer, landing_freq
from propertyrl.agents.random_legal import RandomLegalPolicy
from propertyrl.agents.registry import (
    BASELINES,
    BENCHMARK_POLICIES,
    TRAINING_OPPONENTS,
    cached_policy,
    clear_cache,
    make_policy,
)
from propertyrl.agents.roi_markov import RoiMarkovPolicy
from propertyrl.agents.strong_a import StrongAPolicy
from propertyrl.agents.strong_b import StrongBPolicy

__all__ = [
    "BASELINES",
    "BENCHMARK_POLICIES",
    "DELEGABLE_KINDS",
    "TRAINING_OPPONENTS",
    "CompositePolicy",
    "DelegationPolicy",
    "EpsilonPolicy",
    "ExternalAgentAdapter",
    "GreedyPolicy",
    "Policy",
    "RandomLegalPolicy",
    "RoiMarkovPolicy",
    "StrongAPolicy",
    "StrongBPolicy",
    "Valuer",
    "WithDelegation",
    "anti_oscillation",
    "cached_policy",
    "clamp_bid",
    "clear_cache",
    "landing_freq",
    "make_external",
    "make_policy",
    "register_external",
    "respond",
    "respond_decision",
]
