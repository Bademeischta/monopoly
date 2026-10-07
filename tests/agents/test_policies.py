"""Agents: legality in random states, distinct thresholds, anti-oscillation, determinism (§5, §10)."""

from __future__ import annotations

import os
from typing import Any

import pytest
from helpers import OFFICIAL, RESEARCH, new_game, scenario

from propertyrl.agents import (
    BASELINES,
    BENCHMARK_POLICIES,
    CompositePolicy,
    DelegationPolicy,
    EpsilonPolicy,
    GreedyPolicy,
    Valuer,
    WithDelegation,
    anti_oscillation,
    clamp_bid,
    make_policy,
    respond,
    respond_decision,
)
from propertyrl.agents.external import ExternalAgentAdapter, make_external
from propertyrl.agents.heuristics import policy_params
from propertyrl.engine import (
    Bid,
    BidLevel,
    ConfigError,
    Engine,
    IllegalActionError,
    RuleViolationError,
    TradeOffer,
)
from propertyrl.engine import actions as A
from propertyrl.engine import decisions as D
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.trade import validate_offer
from propertyrl.infra.fuzz import RARE_EVENT_GENERATORS, random_response
from propertyrl.versions import HEURISTIC_VERSIONS

N_STATES = int(os.environ.get("PROPERTYRL_AGENT_STATES", "10000"))
ALL = (*BENCHMARK_POLICIES, "delegation_v1")


def _states(n: int) -> list[Engine]:
    """Random decision states from random play and rare-event start states."""
    out: list[Engine] = []
    seed = 0
    gens = sorted(RARE_EVENT_GENERATORS)
    while len(out) < n:
        if seed % 3 == 2:
            gen, rulesets, _ = RARE_EVENT_GENERATORS[gens[seed % len(gens)]]
            rs = rulesets[seed % len(rulesets)]
            eng = gen(rs, 2 if rs == RESEARCH else 3, seed, AgentRng(seed, 1)).options(check_invariants=False).build()
        else:
            eng = new_game(OFFICIAL if seed % 2 else RESEARCH, 2 if seed % 2 == 0 else 3, seed=seed,
                           check_invariants=False, log_events=False)  # fmt: skip
        rng = AgentRng(seed, 2)
        for step in range(400):
            if eng.is_over():
                break
            if step % 4 == 0:
                out.append(eng.clone(log_events=False))
            eng.apply(random_response(eng, rng))
        seed += 1
    return out[:n]


@pytest.fixture(scope="module")
def states() -> list[Engine]:
    return _states(N_STATES)


def _check_legal(eng: Engine, response: Any) -> None:
    d = eng.pending()
    assert d is not None
    if d.kind == D.TRADE_OFFER:
        assert len(response) <= 2
        for offer in response:
            assert validate_offer(eng.state, eng.board, eng.ruleset, offer, d.seat) is None
    twin = eng.clone(log_events=False)
    twin.options.check_invariants = False
    twin.apply(response)


@pytest.mark.parametrize("name", ALL)
def test_policy_answers_legally(name: str, states: list[Engine]) -> None:
    pol = make_policy(name)
    checked = 0
    for eng in states:
        d = eng.pending()
        assert d is not None
        if name == "delegation_v1" and d.kind == D.MAIN and d.phase != D.BUY_PHASE:
            with pytest.raises(RuleViolationError):
                respond(pol, eng, AgentRng(1, d.seat))
            continue
        response = respond(pol, eng, AgentRng(checked, d.seat))
        _check_legal(eng, response)
        checked += 1
    # delegation_v1 only answers delegable kinds (trades, auctions, debt, BUY in N4).
    assert checked >= (N_STATES // 5 if name == "delegation_v1" else N_STATES)


def test_all_decision_kinds_covered(states: list[Engine]) -> None:
    kinds = {e.pending().kind for e in states}  # type: ignore[union-attr]
    phases = {e.pending().phase for e in states}  # type: ignore[union-attr]
    assert kinds == set(D.KINDS)
    assert {D.PRE_ROLL, D.JAIL_PRE_ROLL, D.BUY_PHASE, D.POST_MOVE, D.DEBT_PHASE, D.PLACE_BUILDING} <= phases


def test_thresholds_differ_pairwise() -> None:
    params = {n: policy_params(n) for n in ALL}
    for i, a in enumerate(ALL):
        for b in ALL[i + 1 :]:
            assert params[a] != params[b], (a, b)


def test_versions_match_registry() -> None:
    for name in BASELINES:
        assert make_policy(name).version == HEURISTIC_VERSIONS[name]


@pytest.mark.parametrize("name", [n for n in ALL if n not in ("random_legal", "delegation_v1")])
def test_anti_oscillation_no_watchdog(name: str) -> None:
    pol = make_policy(name)
    for seed in range(6):
        eng = new_game(OFFICIAL, 3, seed=seed, check_invariants=False, log_events=False)
        rngs = [AgentRng(seed, s) for s in range(3)]
        longest = 0
        while not eng.is_over() and eng.state.round_index < 300:
            d = eng.pending()
            assert d is not None
            eng.apply(respond(pol, eng, rngs[d.seat]))
            longest = max(longest, eng.state.ctx_decisions)
        assert longest < 200


def test_anti_oscillation_filter() -> None:
    eng = scenario().own(0, 0, 2).own_group(0, "PINK").build()
    eng.apply([])
    eng.apply(A.mortgage(0))
    eng.apply(A.build(5))
    view = eng.public_view(0)
    kept = anti_oscillation(view, [A.unmortgage(0), A.mortgage(2), A.sell(5), A.build(6), A.ROLL])
    assert kept == [A.mortgage(2), A.build(6), A.ROLL]


def test_heuristics_deterministic() -> None:
    def play() -> str:
        eng = new_game(OFFICIAL, 2, seed=42, check_invariants=False, log_events=False)
        pols = [make_policy("strong_a_v1"), make_policy("strong_b_v1")]
        rngs = [AgentRng(42, 0), AgentRng(42, 1)]
        while not eng.is_over() and eng.state.round_index < 400:
            d = eng.pending()
            assert d is not None
            eng.apply(respond(pols[d.seat], eng, rngs[d.seat]))
        return eng.state_hash()

    assert play() == play()


def test_greedy_behaviour() -> None:
    eng = scenario().dice((1, 2)).build()
    pol = GreedyPolicy()
    rng = AgentRng(0, 0)
    eng.apply(respond(pol, eng, rng))  # no offers
    eng.apply(respond(pol, eng, rng))  # ROLL
    d = eng.pending()
    assert d is not None and d.phase == D.BUY_PHASE
    assert respond(pol, eng, rng) == A.BUY
    assert pol.respond_trade(eng.public_view(0), TradeOffer(1, 0, give_cash=1000), rng) is False


def test_delegation_buy_in_n4_and_trade_rules() -> None:
    eng = scenario().dice((1, 2)).build()
    pol = DelegationPolicy()
    rng = AgentRng(0, 0)
    eng.apply([])
    eng.apply(A.ROLL)
    assert respond(pol, eng, rng) == A.BUY
    eng2 = scenario().cash(0, 200).dice((1, 2)).build()
    eng2.apply([])
    eng2.apply(A.ROLL)
    assert respond(pol, eng2, rng) == A.DECLINE
    # Completing one's own group with a fair cash offer is accepted, completing only the proposer's is not.
    eng3 = scenario().own(0, 0).own(1, 1).build()
    view = eng3.public_view(1)
    assert not pol.respond_trade(view, TradeOffer(0, 1, give_cash=400, get_props=(1,)), rng)


def test_delegation_offers_cash_for_missing_street() -> None:
    eng = scenario().own(0, 6, 8).own(1, 9).build()
    offers = DelegationPolicy().propose_trades(eng.public_view(0), AgentRng(0, 0))
    assert len(offers) == 1 and offers[0].get_props == (9,) and offers[0].give_cash > 120


def test_clamp_bid() -> None:
    ctx = {"format": D.FORMAT_ASCENDING, "min_bid": 5, "max_bid": 50}
    assert clamp_bid(Bid(80), ctx) == Bid(50)
    assert clamp_bid(Bid(3), ctx) == Bid(None)
    assert clamp_bid(BidLevel(2), ctx) == Bid(None)
    sctx = {"format": D.FORMAT_SEALED, "legal_levels": [True, True, False, False, False, False, False]}
    assert clamp_bid(BidLevel(5), sctx) == BidLevel(1)
    assert clamp_bid(Bid(5), sctx) == BidLevel(None)
    sctx["legal_levels"] = [False] * 7
    assert clamp_bid(BidLevel(3), sctx) == BidLevel(None)


def test_composites_and_epsilon() -> None:
    eng = scenario().dice((1, 2)).build()
    rng = AgentRng(0, 0)
    comp = CompositePolicy(GreedyPolicy(), DelegationPolicy(), ("TRADE_OFFER", "MAIN_BUY"))
    assert respond(comp, eng, rng) == []
    eng.apply([])
    assert respond(comp, eng, rng) == A.ROLL
    eng.apply(A.ROLL)
    assert respond(comp, eng, rng) == A.BUY
    wd = WithDelegation(make_policy("strong_a_v1"), DelegationPolicy())
    assert wd.spec() == "with_delegation:strong_a_v1" and "delegation" in wd.name
    eps = EpsilonPolicy(GreedyPolicy(), 1.0)
    assert eps.spec() == "epsilon:1.0:greedy_v1"
    d = eng.pending()
    assert d is not None
    a = respond_decision(eps, d, eng.public_view(0), AgentRng(3, 0))
    assert d.legal is not None and d.legal[a]
    assert (
        make_policy("epsilon:0.05:with_delegation:roi_markov_v1").spec() == "epsilon:0.05:with_delegation:roi_markov_v1"
    )


def test_registry_errors_and_external() -> None:
    with pytest.raises(ConfigError):
        make_policy("nope")
    with pytest.raises(ConfigError):
        make_external("gnome")
    assert issubclass(ExternalAgentAdapter, object)


def test_valuer_primitives() -> None:
    eng = scenario().own(0, 6, 8).own(1, 9).own(1, 2).build()
    v = Valuer(eng.public_view(0))
    assert v.completes_group(0, 9) and not v.completes_group(1, 9)
    assert v.blocks_group(1, 9)
    assert v.marginal_income(0, 9) > v.marginal_income(0, 0) > 0
    assert v.asset_value(0, 9) > eng.board.p_price[9]
    assert v.reserve(0, 150) == 150
    assert v.max_opp_rent(0) == 25
    offer = TradeOffer(0, 1, give_cash=100, get_props=(9,))
    assert v.trade_completes_group(0, offer) and not v.trade_completes_group(1, offer)
    assert v.value_ratio(offer, 0) > 1.0
    assert v.value_ratio(TradeOffer(0, 1, get_cash=0, give_props=()), 1) == float("inf")
    assert v.best_build_target(0) == -1 and v.building_premium_value(0) == 0.0
    eng2 = scenario().own_group(0, "ORANGE", 2).build()
    v2 = Valuer(eng2.public_view(0))
    assert v2.best_build_target(0) in (8, 9, 10) and v2.building_premium_value(0) > 0
    with pytest.raises(IllegalActionError):
        eng2.apply(A.ROLL)  # first decision is the trade offer window
