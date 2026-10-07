"""Purchases, property auctions and rent (R-201..R-203, R-301..R-310, P-03, P-04, P-09, P-11, D-02, K-02)."""

from __future__ import annotations

import pytest
from helpers import OFFICIAL, RESEARCH, advance, at, events_of, roll, scenario

from propertyrl.engine import Bid, BidLevel, IllegalActionError
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.auction import premium_levels, property_levels


def _to_buy(builder):  # type: ignore[no-untyped-def]
    eng = builder.build()
    roll(eng, 0)
    d = eng.pending()
    assert d is not None and d.phase == D.BUY_PHASE
    return eng, d


@pytest.mark.rule("R-201")
@pytest.mark.rule("R-203")
def test_buy_at_printed_price() -> None:
    eng, d = _to_buy(scenario().dice((1, 2)))
    assert d.context["p"] == 1 and d.context["price"] == 60
    assert d.legal is not None and d.legal[A.BUY] and d.legal[A.DECLINE]
    eng.apply(A.BUY)
    assert eng.state.owner[1] == 0 and eng.state.cash[0] == 1440
    tx = [t for t in eng.ledger.transactions if t.reason == "PURCHASE"]
    assert len(tx) == 1 and tx[0].sender == 0 and tx[0].receiver == C.BANK and tx[0].amount == 60


@pytest.mark.rule("R-201")
def test_buy_with_exact_cash_leaves_zero() -> None:
    eng, d = _to_buy(scenario().cash(0, 60).dice((1, 2)))
    assert d.legal is not None and d.legal[A.BUY]
    eng.apply(A.BUY)
    assert eng.state.cash[0] == 0


@pytest.mark.rule("R-201")
def test_buy_illegal_without_cash() -> None:
    eng, d = _to_buy(scenario().cash(0, 59).dice((1, 2)))
    assert d.legal is not None and not d.legal[A.BUY] and d.legal[A.DECLINE]
    with pytest.raises(IllegalActionError):
        eng.apply(A.BUY)


@pytest.mark.rule("P-09")
def test_raise_money_before_buying() -> None:
    eng, d = _to_buy(scenario().cash(0, 50).own(0, 0).dice((1, 2)))
    assert d.legal is not None and not d.legal[A.BUY] and d.legal[A.mortgage(0)]
    assert not d.legal[A.unmortgage(0)]
    eng.apply(A.mortgage(0))
    d2 = eng.pending()
    assert d2 is not None and d2.phase == D.BUY_PHASE and d2.legal is not None and d2.legal[A.BUY]
    eng.apply(A.BUY)
    assert eng.state.cash[0] == 20 and eng.state.owner[1] == 0


@pytest.mark.rule("R-202")
@pytest.mark.rule("H-03")
def test_decline_starts_auction_no_bids_bank_keeps() -> None:
    eng, _ = _to_buy(scenario().dice((1, 2)))
    eng.apply(A.DECLINE)
    d = eng.pending()
    assert d is not None and d.kind == D.AUCTION_BID and d.seat == 0
    assert d.context["participants"] == [0, 1] and d.context["min_bid"] == 1
    eng.apply(Bid(None))
    eng.apply(Bid(None))
    assert eng.state.owner[1] == C.BANK
    assert events_of(eng, "AUCTION_NO_SALE")


@pytest.mark.rule("P-03")
@pytest.mark.rule("K-02")
def test_ascending_auction_rules() -> None:
    eng, _ = _to_buy(scenario().cash(1, 300).dice((1, 2)))
    eng.apply(A.DECLINE)
    with pytest.raises(IllegalActionError):
        eng.apply(Bid(0))  # first bid must be >= 1
    eng.apply(Bid(10))
    d = eng.pending()
    assert d is not None and d.seat == 1 and d.context["min_bid"] == 11 and d.context["max_bid"] == 300
    with pytest.raises(IllegalActionError):
        eng.apply(Bid(10))  # equal bid (tie) is not allowed in the ascending format
    with pytest.raises(IllegalActionError):
        eng.apply(Bid(301))  # K-02 bids limited to cash
    eng.apply(Bid(11))
    eng.apply(Bid(None))
    assert eng.state.owner[1] == 1 and eng.state.cash[1] == 289
    won = events_of(eng, "AUCTION_WON")[-1]
    assert won.seat == 1 and won.data["price"] == 11


@pytest.mark.rule("P-03")
def test_ascending_auction_action_cap() -> None:
    eng, _ = _to_buy(scenario().cash(0, 5000).cash(1, 5000).dice((1, 2)))
    eng.apply(A.DECLINE)
    amount = 1
    while eng.state.auction is not None:
        eng.apply(Bid(amount))
        amount += 1
    assert amount - 1 == C.AUCTION_MAX_ACTIONS
    assert eng.state.owner[1] == 1  # bid number 200 came from seat 1
    assert events_of(eng, "AUCTION_WON")[-1].data["price"] == 200


@pytest.mark.rule("D-02")
def test_sealed_auction_second_price_plus_one() -> None:
    eng, _ = _to_buy(scenario(RESEARCH).dice((1, 2)))
    assert property_levels(60) == [6, 15, 30, 45, 60, 75, 90]
    eng.apply(A.DECLINE)
    d = eng.pending()
    assert d is not None and d.context["format"] == D.FORMAT_SEALED and d.context["high_bid"] is None
    eng.apply(BidLevel(2))
    eng.apply(BidLevel(4))
    assert eng.state.owner[1] == 1 and eng.state.cash[1] == 1500 - 31


@pytest.mark.rule("D-02")
def test_sealed_auction_single_bid_price_one() -> None:
    eng, _ = _to_buy(scenario(RESEARCH).dice((1, 2)))
    eng.apply(A.DECLINE)
    eng.apply(BidLevel(None))
    eng.apply(BidLevel(6))
    assert eng.state.owner[1] == 1 and eng.state.cash[1] == 1499


@pytest.mark.rule("D-02")
def test_sealed_auction_tie_goes_to_decliner_order() -> None:
    eng, _ = _to_buy(scenario(RESEARCH).dice((1, 2)))
    eng.apply(A.DECLINE)
    eng.apply(BidLevel(3))
    eng.apply(BidLevel(3))
    assert eng.state.owner[1] == 0 and eng.state.cash[0] == 1500 - 45


@pytest.mark.rule("D-02")
@pytest.mark.rule("K-02")
def test_sealed_levels_limited_by_cash() -> None:
    eng, _ = _to_buy(scenario(RESEARCH).cash(0, 40).dice((1, 2)))
    eng.apply(A.DECLINE)
    d = eng.pending()
    assert d is not None and d.context["legal_levels"] == [True, True, True, False, False, False, False]
    with pytest.raises(IllegalActionError):
        eng.apply(BidLevel(3))
    with pytest.raises(IllegalActionError):
        eng.apply(Bid(3))  # wrong response type for the sealed format


def test_level_tables() -> None:
    assert property_levels(350) == [35, 88, 175, 263, 350, 438, 525]
    assert premium_levels(50) == [0, 5, 13, 25, 38, 50, 75]


def _rent(builder, start: int = 6, dice: tuple[int, int] = (2, 3)) -> int:  # type: ignore[no-untyped-def]
    eng = builder.position(0, start).dice(dice).build()
    before = eng.state.cash[0]
    roll(eng, 0)
    return before - eng.state.cash[0]


@pytest.mark.rule("R-301")
@pytest.mark.rule("P-04")
def test_base_rent_and_double_with_group() -> None:
    assert _rent(scenario().own(1, 6)) == 10
    assert _rent(scenario().own(1, 6, 8, 9)) == 20


@pytest.mark.rule("R-301")
def test_double_rent_even_if_other_street_mortgaged() -> None:
    assert _rent(scenario().own(1, 6, 9).own(1, 8, mortgaged=True)) == 20


@pytest.mark.rule("R-302")
def test_rent_with_houses_and_hotel() -> None:
    b = scenario().own(1, 6, 8, 9).level(5, 2).level(6, 2).level(7, 2)
    assert _rent(b) == 150
    b = scenario().own(1, 6, 8, 9).level(5, 5).level(6, 4).level(7, 4)
    assert _rent(b) == 750


@pytest.mark.rule("R-303")
@pytest.mark.rule("P-11")
@pytest.mark.parametrize(("rails", "expected"), [((2,), 25), ((2, 10), 50), ((2, 10, 17), 100), ((2, 10, 17, 25), 200)])
def test_rail_rent(rails: tuple[int, ...], expected: int) -> None:
    b = scenario().own(1, 2)
    others = [r for r in rails if r != 2]
    if others:
        b.own(1, *others, mortgaged=True)  # P-11: mortgaged rails still count
    assert _rent(b, start=0, dice=(2, 3)) == expected


@pytest.mark.rule("R-304")
def test_utility_rent() -> None:
    assert _rent(scenario().own(1, 7), start=7, dice=(2, 3)) == 20
    assert _rent(scenario().own(1, 7).own(1, 20, mortgaged=True), start=7, dice=(2, 3)) == 50


@pytest.mark.rule("R-305")
def test_no_rent_on_mortgaged() -> None:
    assert _rent(scenario().own(1, 6, mortgaged=True)) == 0


@pytest.mark.rule("R-306")
def test_no_rent_on_own_property() -> None:
    eng = scenario().own(0, 6).position(0, 6).dice((2, 3)).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1500
    d = eng.pending()
    assert d is not None and d.phase == D.POST_MOVE


@pytest.mark.rule("R-308")
@pytest.mark.rule("V3")
def test_tax_one() -> None:
    assert _rent(scenario(), start=0, dice=(1, 3)) == 200


@pytest.mark.rule("R-309")
def test_tax_two() -> None:
    assert _rent(scenario(), start=35, dice=(1, 2)) == 100


@pytest.mark.rule("R-310")
@pytest.mark.rule("H-01")
def test_rest_square_no_effect() -> None:
    eng = scenario().position(0, 15).dice((2, 3)).build()
    roll(eng, 0)
    assert eng.state.position[0] == 20 and eng.state.cash[0] == 1500
    d = advance(eng, at(0, D.POST_MOVE, D.MAIN))
    assert d.legal is not None and d.legal[A.END_PHASE]


@pytest.mark.rule("P-04")
def test_rent_paid_without_owner_decision() -> None:
    eng = scenario().own(1, 6).position(0, 6).dice((2, 3)).build()
    roll(eng, 0)
    assert eng.state.cash[1] == 1510
    d = eng.pending()
    assert d is not None and d.seat == 0
    assert events_of(eng, "RENT_PAID")[-1].data == {"to": 1, "amount": 10, "reason": "RENT"}


@pytest.mark.rule("R-202")
def test_auction_with_three_bidders_order_from_decliner() -> None:
    eng = scenario(OFFICIAL, n=3).active(1).position(1, 0).dice((1, 2)).build()
    roll(eng, 1)
    eng.apply(A.DECLINE)
    d = eng.pending()
    assert d is not None and d.context["participants"] == [1, 2, 0]
