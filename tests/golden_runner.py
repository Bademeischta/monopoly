"""Runner for golden-game YAML scenarios (shared by golden tests and event coverage)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from helpers import advance, passive_response, scenario

from propertyrl.engine import Bid, BidLevel, Engine, TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.invariants import check_invariants

SCENARIO_DIR = Path(__file__).resolve().parent / "golden" / "scenarios"
SCENARIOS = sorted(SCENARIO_DIR.glob("*.yaml"))
_ACTION_BY_NAME = {A.action_name(a): a for a in range(A.N_ACTIONS)}
_DECK = {"A": C.DECK_A, "B": C.DECK_B}


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


def build(spec: dict[str, Any]) -> Engine:
    setup = spec.get("setup", {})
    b = scenario(spec["ruleset"], n=spec.get("players", 2), seed=spec.get("seed", 0), **setup.get("overrides", {}))
    for seat, amount in setup.get("cash", {}).items():
        b.cash(int(seat), amount)
    for item in setup.get("own", []):
        b.own(item["seat"], *item["props"], mortgaged=item.get("mortgaged", False))
    for item in setup.get("groups", []):
        b.own_group(item["seat"], item["group"], item.get("level", 0))
    for bi, lvl in setup.get("levels", {}).items():
        b.level(int(bi), lvl)
    for seat, sq in setup.get("positions", {}).items():
        b.position(int(seat), sq)
    for seat, attempts in setup.get("jail", {}).items():
        b.jail(int(seat), attempts)
    for item in setup.get("jail_cards", []):
        b.jail_card(item["seat"], _DECK[item["deck"]])
    for seat in setup.get("bankrupt", []):
        b.bankrupt(seat)
    if "dice" in setup:
        b.dice(*[tuple(p) for p in setup["dice"]])
    for deck, ids in setup.get("cards", {}).items():
        b.cards(_DECK[deck], ids)
    b.active(setup.get("active", 0))
    if "round" in setup:
        b.round(setup["round"])
    return b.build()


def _matches(d: D.Decision, cond: dict[str, Any]) -> bool:
    return all(
        (key == "seat" and d.seat == val) or (key == "kind" and d.kind == val) or (key == "phase" and d.phase == val)
        for key, val in cond.items()
    )


def response(eng: Engine, do: Any) -> Any:
    d = eng.pending()
    assert d is not None
    if isinstance(do, str):
        if do == "pass":
            return BidLevel(None) if d.context.get("format") == D.FORMAT_SEALED else Bid(None)
        if do == "accept":
            return True
        if do == "reject":
            return False
        if do == "no_offer":
            return []
        return _ACTION_BY_NAME[do]
    if "bid" in do:
        return Bid(int(do["bid"]))
    if "level" in do:
        return BidLevel(int(do["level"]))
    if "offer" in do:
        return [
            TradeOffer(
                proposer=d.seat,
                recipient=o["recipient"],
                give_cash=o.get("give_cash", 0),
                get_cash=o.get("get_cash", 0),
                give_props=tuple(o.get("give_props", ())),
                get_props=tuple(o.get("get_props", ())),
                give_jail_cards=o.get("give_jail_cards", 0),
                get_jail_cards=o.get("get_jail_cards", 0),
            )
            for o in do["offer"]
        ]
    raise AssertionError(f"unknown step {do!r}")


def run(spec: dict[str, Any]) -> Engine:
    eng = build(spec)
    for step in spec.get("steps", []):
        if "until" in step:
            advance(eng, lambda d, c=step["until"]: _matches(d, c))
        elif "expect_pending" in step:
            d = eng.pending()
            assert d is not None and _matches(d, step["expect_pending"]), (d, step)
        elif "legal" in step or "illegal" in step:
            d = eng.pending()
            assert d is not None and d.legal is not None
            for name in step.get("legal", []):
                assert d.legal[_ACTION_BY_NAME[name]], name
            for name in step.get("illegal", []):
                assert not d.legal[_ACTION_BY_NAME[name]], name
        elif "do" in step:
            eng.apply(response(eng, step["do"]))
        elif step.get("run_to_end"):
            while not eng.is_over():
                eng.apply(passive_response(eng))
    check_invariants(eng)
    return eng


def check(eng: Engine, expect: dict[str, Any]) -> None:
    st = eng.state
    for field in ("cash", "position", "in_jail", "jail_attempts", "jail_cards", "bankrupt"):
        for seat, val in expect.get(field, {}).items():
            assert getattr(st, field)[int(seat)] == val, (field, seat)
    for field in ("owner", "mortgaged", "level"):
        for idx, val in expect.get(field, {}).items():
            assert getattr(st, field)[int(idx)] == val, (field, idx)
    for field in ("bank_houses", "bank_hotels", "game_over"):
        if field in expect:
            assert getattr(st, field) == expect[field], field
    if "winner" in expect:
        assert eng.result().winner == expect["winner"]
    if "placements" in expect:
        assert eng.result().placements == expect["placements"]
    if "deck_sizes" in expect:
        assert [len(st.deck_a), len(st.deck_b)] == expect["deck_sizes"]
    types = [e.type for e in eng.events]
    for etype in expect.get("events", []):
        assert etype in types, etype
    for etype in expect.get("no_events", []):
        assert etype not in types, etype
    if "pending" in expect:
        d = eng.pending()
        assert d is not None and _matches(d, expect["pending"]), d
