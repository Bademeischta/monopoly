"""Trades, decision windows, game end, watchdogs and house rules (R-801, R-802, R-901, R-902, P-01, P-02,
P-14, P-16, D-01, D-03, D-06, K-01, K-04, H-01..H-09)."""

from __future__ import annotations

import dataclasses

import pytest
from helpers import (
    OFFICIAL,
    RESEARCH,
    SHORTGAME,
    advance,
    at,
    events_of,
    new_game,
    passive_response,
    pre_roll,
    roll,
    rules,
    scenario,
)

from propertyrl.engine import EngineWatchdogError, IllegalActionError, TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D


def _offer_window(builder):  # type: ignore[no-untyped-def]
    eng = builder.build()
    d = eng.pending()
    assert d is not None and d.kind == D.TRADE_OFFER and d.seat == 0
    return eng


@pytest.mark.rule("R-801")
def test_trade_cash_for_street() -> None:
    eng = _offer_window(scenario().own(1, 6))
    eng.apply([TradeOffer(0, 1, give_cash=200, get_props=(6,))])
    d = eng.pending()
    assert d is not None and d.kind == D.TRADE_RESPONSE and d.seat == 1
    assert d.context["offer"].get_props == (6,)
    eng.apply(True)
    st = eng.state
    assert st.owner[6] == 0 and st.cash == [1300, 1700]
    d = eng.pending()
    assert d is not None and d.seat == 0 and d.phase == D.PRE_ROLL


@pytest.mark.rule("R-801")
def test_trade_rails_utilities_and_jail_cards() -> None:
    eng = _offer_window(scenario().own(0, 2, 7).jail_card(1, C.DECK_A))
    eng.apply([TradeOffer(0, 1, give_props=(2, 7), get_jail_cards=1)])
    eng.apply(True)
    st = eng.state
    assert st.owner[2] == 1 and st.owner[7] == 1 and st.jail_cards == [1, 0]


@pytest.mark.rule("R-801")
@pytest.mark.rule("P-14")
def test_buildings_not_tradable() -> None:
    eng = _offer_window(scenario().own_group(1, "PINK").level(5, 1))
    with pytest.raises(IllegalActionError):
        eng.apply([TradeOffer(0, 1, give_cash=10, get_props=(6,))])
    with pytest.raises(IllegalActionError):
        eng.apply([TradeOffer(0, 1, give_cash=10, get_props=(9,))])  # unbuilt street of a built group
    eng.apply([])  # the decision is still pending after the illegal answers


@pytest.mark.rule("P-02")
@pytest.mark.rule("P-14")
@pytest.mark.rule("H-05")
def test_offer_limits_and_validation() -> None:
    eng = _offer_window(scenario().own(1, 6, 8, 9))
    three = [TradeOffer(0, 1, give_cash=1, get_props=(p,)) for p in (6, 8, 9)]
    with pytest.raises(IllegalActionError):
        eng.apply(three)
    for bad in (
        TradeOffer(0, 1, give_cash=1501, get_props=(6,)),  # more cash than held (no loans, H-05)
        TradeOffer(0, 0, give_cash=1),  # to self
        TradeOffer(1, 0, give_cash=1),  # proposer is not the window owner
        TradeOffer(0, 1),  # empty
        TradeOffer(0, 1, give_jail_cards=1),  # card not held
        TradeOffer(0, 1, give_props=(6,)),  # property not owned
        TradeOffer(0, 1, give_cash=-5, get_props=(6,)),
    ):
        with pytest.raises(IllegalActionError):
            eng.apply([bad])
    with pytest.raises(IllegalActionError):
        eng.apply("not a list")
    eng.apply([TradeOffer(0, 1, give_cash=1, get_props=(6,)), TradeOffer(0, 1, give_cash=1, get_props=(8,))])
    assert eng.pending().kind == D.TRADE_RESPONSE  # type: ignore[union-attr]


@pytest.mark.rule("P-14")
@pytest.mark.rule("R-802")
def test_interest_affordability() -> None:
    eng = _offer_window(scenario().own(0, 26, mortgaged=True).cash(1, 10))
    with pytest.raises(IllegalActionError):
        eng.apply([TradeOffer(0, 1, give_props=(26,))])
    eng.apply([TradeOffer(0, 1, give_cash=10, give_props=(26,))])
    eng.apply(True)
    assert eng.state.cash[1] == 2 and eng.state.owner[26] == 1


def test_trade_rejected_changes_nothing() -> None:
    eng = _offer_window(scenario().own(1, 6))
    eng.apply([TradeOffer(0, 1, give_cash=200, get_props=(6,))])
    eng.apply(False)
    assert eng.state.owner[6] == 1 and eng.state.cash == [1500, 1500]
    assert events_of(eng, "TRADE_REJECTED")[-1].data["stale"] is False


@pytest.mark.rule("P-02")
def test_stale_second_offer_dropped() -> None:
    eng = _offer_window(scenario(OFFICIAL, n=3).own(0, 6))
    eng.apply([TradeOffer(0, 1, get_cash=100, give_props=(6,)), TradeOffer(0, 2, get_cash=50, give_props=(6,))])
    eng.apply(True)
    d = eng.pending()
    assert d is not None and d.kind == D.MAIN and d.seat == 0
    assert events_of(eng, "TRADE_REJECTED")[-1].data["stale"] is True
    assert eng.state.owner[6] == 1


@pytest.mark.rule("P-02")
@pytest.mark.rule("K-04")
def test_counter_offer_in_own_window() -> None:
    eng = scenario().dice((1, 2)).build()
    d = advance(eng, at(1, D.OUT_OF_TURN, D.TRADE_OFFER))
    assert d.context["max_offers"] == 2


@pytest.mark.rule("P-01")
def test_official_window_sequence() -> None:
    eng = scenario().dice((1, 2)).build()
    seq = []
    while True:
        d = eng.pending()
        assert d is not None
        seq.append((d.seat, d.kind, d.phase))
        if d.seat == 1 and d.phase == D.PRE_ROLL and d.kind == D.TRADE_OFFER:
            break
        eng.apply(passive_response(eng))
    assert seq == [
        (0, D.TRADE_OFFER, D.PRE_ROLL),
        (0, D.MAIN, D.PRE_ROLL),
        (0, D.MAIN, D.BUY_PHASE),
        (0, D.AUCTION_BID, D.BUY_PHASE),
        (1, D.AUCTION_BID, D.BUY_PHASE),
        (0, D.TRADE_OFFER, D.POST_MOVE),
        (0, D.MAIN, D.POST_MOVE),
        (1, D.TRADE_OFFER, D.OUT_OF_TURN),
        (1, D.MAIN, D.OUT_OF_TURN),
        (1, D.TRADE_OFFER, D.PRE_ROLL),
    ]


@pytest.mark.rule("D-01")
@pytest.mark.rule("D-03")
def test_research_windows_and_offers() -> None:
    eng = scenario(RESEARCH).dice((1, 2), (1, 3), (2, 3)).build()
    seq = []
    for _ in range(40):
        d = eng.pending()
        assert d is not None
        seq.append((d.seat, d.kind, d.phase, eng.state.active_seat))
        if len([s for s in seq if s[1] == D.MAIN and s[2] == D.PRE_ROLL]) == 3:
            break
        eng.apply(passive_response(eng))
    assert all(p != D.OUT_OF_TURN for _, _, p, _ in seq)
    offers = [(s, p, act) for s, k, p, act in seq if k == D.TRADE_OFFER]
    assert offers and all(s == act and p == D.PRE_ROLL for s, p, act in offers)


@pytest.mark.rule("D-06")
def test_short_game_ends_by_equity() -> None:
    eng = scenario(SHORTGAME, max_rounds=1).dice((1, 2), (1, 3)).build()
    while not eng.is_over():
        eng.apply(passive_response(eng))
    res = eng.result()
    assert res.ended_by_rounds and res.winner == 0 and res.placements == [1, 2]
    assert res.final_equities == [1500, 1300]


@pytest.mark.rule("D-06")
def test_short_game_tie_is_draw() -> None:
    eng = scenario(SHORTGAME, max_rounds=1).dice((2, 3), (2, 3)).build()
    while not eng.is_over():
        eng.apply(passive_response(eng))
    res = eng.result()
    assert res.winner is None and res.placements == [1, 1]


@pytest.mark.rule("H-09")
def test_official_has_no_round_limit() -> None:
    eng = scenario(OFFICIAL).round(10_000).dice((1, 2), (1, 3)).build()
    advance(eng, pre_roll(1))
    assert not eng.is_over()
    assert rules(OFFICIAL).game_end == "natural"


@pytest.mark.rule("P-16")
def test_window_watchdog() -> None:
    eng = scenario().own(0, 0).build()
    advance(eng, pre_roll(0))
    with pytest.raises(EngineWatchdogError) as info:
        for _ in range(1100):
            eng.apply(A.mortgage(0))
            eng.apply(A.unmortgage(0))
    assert info.value.game_log is not None and info.value.game_seed == 0


@pytest.mark.rule("P-16")
def test_turn_event_watchdog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(C, "WATCHDOG_TURN_EVENTS", 15)
    eng = scenario().own(0, 0).build()
    advance(eng, pre_roll(0))
    with pytest.raises(EngineWatchdogError):
        for _ in range(50):
            eng.apply(A.mortgage(0))
            eng.apply(A.unmortgage(0))


@pytest.mark.rule("P-16")
def test_game_decision_watchdog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(C, "WATCHDOG_GAME_DECISIONS", 30)
    eng = new_game(OFFICIAL, 2, seed=3)
    with pytest.raises(EngineWatchdogError):
        for _ in range(100):
            eng.apply(passive_response(eng))


@pytest.mark.rule("R-901")
def test_last_opponent_bankrupt_while_out_of_turn_windows_pending() -> None:
    # A-111: no payment can arise inside a window; bankruptcy with pending OOT windows ends the game at once.
    eng = scenario(OFFICIAL, n=2).own(1, 6).cash(0, 5).position(0, 6).dice((2, 3)).build()
    roll(eng, 0)
    assert eng.is_over() and eng.pending() is None
    assert not [e for e in events_of(eng, "WINDOW_OPENED") if e.data["window"] == "OUT_OF_TURN"]


def test_eight_player_game_runs() -> None:
    eng = new_game(OFFICIAL, 8, seed=11)
    for _ in range(3000):
        eng.apply(passive_response(eng))
    assert eng.state.n_players == 8 and len(set(e.seat for e in events_of(eng, "TURN_STARTED"))) == 8


@pytest.mark.rule("H-01")
def test_no_money_pot_on_rest_square() -> None:
    eng = scenario().position(0, 0).position(1, 15).dice((1, 3), (2, 3)).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1300
    roll(eng, 1)
    assert eng.state.position[1] == 20 and eng.state.cash[1] == 1500


@pytest.mark.rule("H-02")
def test_landing_on_start_single_salary() -> None:
    eng = scenario().position(0, 35).dice((2, 3)).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1700


@pytest.mark.rule("H-06")
def test_trade_objects_have_no_immunity() -> None:
    names = {f.name for f in dataclasses.fields(TradeOffer)}
    assert names == {"proposer", "recipient", "give_cash", "get_cash", "give_props", "get_props",
                     "give_jail_cards", "get_jail_cards"}  # fmt: skip


@pytest.mark.rule("H-07")
def test_rent_collected_while_owner_in_jail() -> None:
    eng = scenario().jail(1, 0).own(1, 6).position(0, 6).dice((2, 3)).build()
    roll(eng, 0)
    assert eng.state.cash[1] == 1510


@pytest.mark.rule("H-08")
def test_standard_start_no_distribution() -> None:
    eng = new_game(OFFICIAL, 4, seed=5)
    assert eng.state.cash == [1500] * 4 and set(eng.state.owner) == {C.BANK}


@pytest.mark.rule("K-01")
def test_no_trade_offer_during_debt() -> None:
    eng = scenario().own(1, 6).own(0, 0, 1).cash(0, 5).position(0, 6).dice((2, 3)).build()
    roll(eng, 0)
    kinds = []
    while eng.pending() is not None and eng.pending().kind == D.DEBT:  # type: ignore[union-attr]
        kinds.append(eng.pending().kind)  # type: ignore[union-attr]
        eng.apply(eng.pending().legal_actions()[0])  # type: ignore[union-attr]
    assert kinds == [D.DEBT]
