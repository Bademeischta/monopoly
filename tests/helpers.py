"""Shared helpers (drivers, factories) for the PropertyRL test-suite."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from propertyrl.engine import Bid, BidLevel, Engine, EngineOptions, ScenarioBuilder
from propertyrl.engine import actions as A
from propertyrl.engine import decisions as D
from propertyrl.engine.board import Board
from propertyrl.engine.cards import Decks
from propertyrl.engine.ruleset import Ruleset
from propertyrl.infra.config import load_board, load_decks, load_ruleset

OFFICIAL = "OFFICIAL_US_CLASSIC_2008"
RESEARCH = "RESEARCH_2P_BOUNDED_V1"
SHORTGAME = "RESEARCH_2P_SHORTGAME_V1"
MOVEMENT = "TEST_MOVEMENT_ONLY"
REPO = Path(__file__).resolve().parents[1]


def rules(ruleset_id: str = OFFICIAL, **overrides: Any) -> Ruleset:
    """Ruleset without frozen horizon (tests must not depend on artifacts)."""
    return load_ruleset(ruleset_id, use_frozen_horizon=False, **overrides)


def board() -> Board:
    """The standard board."""
    return load_board()


def decks() -> Decks:
    """The standard decks."""
    return load_decks()


def new_game(ruleset_id: str = OFFICIAL, n: int = 2, seed: int = 1, **opts: Any) -> Engine:
    """New engine with invariant checks enabled by default."""
    opts.setdefault("check_invariants", True)
    return Engine.new(rules(ruleset_id), board(), decks(), n, seed, EngineOptions(**opts))


def scenario(ruleset_id: str = OFFICIAL, n: int = 2, seed: int = 0, **overrides: Any) -> ScenarioBuilder:
    """ScenarioBuilder for the given ruleset."""
    return ScenarioBuilder(rules(ruleset_id, **overrides), board(), decks(), n, seed)


def passive_response(eng: Engine) -> Any:
    """A neutral response: roll, end windows, decline, pass, reject, liquidate first legal."""
    d = eng.pending()
    assert d is not None
    if d.kind == D.MAIN:
        assert d.legal is not None
        if d.phase in (D.PRE_ROLL, D.JAIL_PRE_ROLL) and d.legal[A.ROLL]:
            return A.ROLL
        if d.phase in (D.POST_MOVE, D.OUT_OF_TURN):
            return A.END_PHASE
        if d.phase == D.BUY_PHASE:
            return A.DECLINE
        return d.legal_actions()[0]
    if d.kind == D.DEBT:
        return d.legal_actions()[0]
    if d.kind == D.TRADE_OFFER:
        return []
    if d.kind == D.TRADE_RESPONSE:
        return False
    if d.context["format"] == D.FORMAT_SEALED:
        return BidLevel(None)
    return Bid(None)


def advance(
    eng: Engine,
    until: Callable[[D.Decision], bool],
    responder: Callable[[Engine], Any] = passive_response,
    limit: int = 10_000,
) -> D.Decision:
    """Answer passively until ``until(decision)`` holds; return that decision."""
    for _ in range(limit):
        d = eng.pending()
        if d is None:
            raise AssertionError("game ended before the condition was met")
        if until(d):
            return d
        eng.apply(responder(eng))
    raise AssertionError("condition not reached")


def at(seat: int, phase: str | None = None, kind: str | None = None) -> Callable[[D.Decision], bool]:
    """Predicate for :func:`advance`."""

    def pred(d: D.Decision) -> bool:
        return d.seat == seat and (phase is None or d.phase == phase) and (kind is None or d.kind == kind)

    return pred


def event_types(eng: Engine) -> list[str]:
    """Types of all logged events."""
    return [e.type for e in eng.events]


def events_of(eng: Engine, etype: str) -> list[Any]:
    """All logged events of one type."""
    return [e for e in eng.events if e.type == etype]


def run_python(code: str, timeout: int = 600) -> Any:
    """Run Python code in a fresh interpreter (returns CompletedProcess)."""
    import subprocess

    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=timeout, cwd=str(REPO))


def pre_roll(seat: int) -> Callable[[D.Decision], bool]:
    """Predicate: MAIN pre-roll decision (normal or in jail) of ``seat``."""

    def pred(d: D.Decision) -> bool:
        return d.seat == seat and d.kind == D.MAIN and d.phase in (D.PRE_ROLL, D.JAIL_PRE_ROLL)

    return pred


def roll(eng: Engine, seat: int = 0) -> list[Any]:
    """Advance to the pre-roll decision of ``seat`` and roll."""
    advance(eng, pre_roll(seat))
    return eng.apply(A.ROLL)


def cash_of(eng: Engine) -> list[int]:
    """Copy of the cash vector."""
    return list(eng.state.cash)
