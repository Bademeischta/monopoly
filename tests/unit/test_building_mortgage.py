"""Building, selling, scarcity auction and mortgages.

Rules: R-401..R-407, R-501..R-503, P-05, P-08, P-13, P-19, D-05, K-03, K-05.
"""

from __future__ import annotations

import pytest
from helpers import OFFICIAL, RESEARCH, advance, at, events_of, pre_roll, roll, scenario

from propertyrl.engine import Bid, BidLevel, IllegalActionError, TradeOffer
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.building import hotel_demand, house_demand
from propertyrl.engine.events import COUNTER_INDEX
from propertyrl.engine.mortgage import unmortgage_cost


def _pre(builder):  # type: ignore[no-untyped-def]
    eng = builder.build()
    d = advance(eng, pre_roll(0))
    return eng, d


@pytest.mark.rule("R-401")
@pytest.mark.rule("H-04")
def test_build_requires_complete_unmortgaged_group() -> None:
    _, d = _pre(scenario().own_group(0, "BRAUN"))
    assert d.legal is not None and d.legal[A.build(0)] and d.legal[A.build(1)]
    _, d = _pre(scenario().own(0, 0))
    assert d.legal is not None and not d.legal[A.build(0)]
    _, d = _pre(scenario().own(0, 0).own(0, 1, mortgaged=True))
    assert d.legal is not None and not d.legal[A.build(0)] and not d.legal[A.build(1)]


@pytest.mark.rule("R-402")
@pytest.mark.rule("H-04")
def test_even_building() -> None:
    eng, _ = _pre(scenario().own_group(0, "BRAUN"))
    eng.apply(A.build(0))
    d = eng.pending()
    assert d is not None and d.legal is not None
    assert not d.legal[A.build(0)] and d.legal[A.build(1)]
    assert eng.state.cash[0] == 1450 and eng.state.bank_houses == 31


@pytest.mark.rule("R-403")
def test_hotel_requires_four_everywhere_and_returns_houses() -> None:
    eng, d = _pre(scenario().own_group(0, "BRAUN").level(0, 4).level(1, 3))
    assert d.legal is not None and not d.legal[A.build(0)] and d.legal[A.build(1)]
    eng.apply(A.build(1))
    houses_before = eng.state.bank_houses
    eng.apply(A.build(0))
    st = eng.state
    assert st.level[0] == 5 and st.bank_hotels == 11 and st.bank_houses == houses_before + 4
    assert events_of(eng, "HOTEL_BUILT")[-1].data["price"] == 50


def _fill_houses(builder, houses: int):  # type: ignore[no-untyped-def]
    """Seat 1 holds GREEN, YELLOW, RED and ORANGE with ``houses`` houses in total (even levels)."""
    groups = ["GRUEN", "GELB", "ROT", "ORANGE"]
    left = houses
    for g in groups:
        members = C.GROUP_BUILDS[C.GROUP_ID[g]]
        builder.own_group(1, g)
        for _ in range(4):
            for b in members:
                if left > 0:
                    builder.level(b, builder._levels.get(b, 0) + 1)
                    left -= 1
    assert left == 0
    return builder


@pytest.mark.rule("R-404")
def test_build_needs_bank_stock() -> None:
    _, d = _pre(_fill_houses(scenario().own_group(0, "BRAUN"), 32))
    assert d.legal is not None and not d.legal[A.build(0)]


@pytest.mark.rule("R-405")
def test_sell_evenly_half_price() -> None:
    eng, d = _pre(scenario().own_group(0, "BRAUN").level(0, 2).level(1, 2))
    assert d.legal is not None and d.legal[A.sell(0)] and d.legal[A.sell(1)]
    eng.apply(A.sell(0))
    d = eng.pending()
    assert d is not None and d.legal is not None and not d.legal[A.sell(0)] and d.legal[A.sell(1)]
    assert eng.state.cash[0] == 1525 and eng.state.bank_houses == 32 - 3


@pytest.mark.rule("R-406")
def test_hotel_sale_back_to_four_houses() -> None:
    eng, _ = _pre(scenario().own_group(0, "BRAUN").level(0, 5).level(1, 4))
    eng.apply(A.sell(0))
    st = eng.state
    assert st.level[0] == 4 and st.bank_hotels == 12 and st.bank_houses == 32 - 8
    assert st.cash[0] == 1525


@pytest.mark.rule("P-08")
def test_hotel_sale_without_houses_sells_group_down() -> None:
    eng, _ = _pre(_fill_houses(scenario().own_group(0, "BRAUN").level(0, 5).level(1, 5), 30))
    assert eng.state.bank_houses == 2
    eng.apply(A.sell(0))
    st = eng.state
    assert st.level[0] == 1 and st.level[1] == 1
    assert st.bank_houses == 0 and st.bank_hotels == 12
    ev = events_of(eng, "GROUP_SOLD_DOWN")[-1]
    assert ev.data["units"] == 8 and ev.data["refund"] == 200
    assert st.cash[0] == 1700


@pytest.mark.rule("P-08")
def test_group_sold_down_to_zero() -> None:
    eng, _ = _pre(_fill_houses(scenario().own_group(0, "BRAUN").level(0, 5).level(1, 5), 32))
    eng.apply(A.sell(1))
    assert eng.state.level[0] == 0 and eng.state.level[1] == 0
    assert events_of(eng, "GROUP_SOLD_DOWN")[-1].data["refund"] == 250


# ---------------------------------------------------------------------- scarcity auction (P-19)
def _scarcity_builder(ruleset: str = OFFICIAL):  # type: ignore[no-untyped-def]
    # 24 houses on board (GREEN, YELLOW at 4) -> bank 8; seat 0 BRAUN + HELLBLAU, seat 1 ORANGE (demand >= 1).
    b = scenario(ruleset).own_group(1, "GRUEN", 4).own_group(1, "GELB", 4).own_group(1, "ORANGE")
    return b.own_group(0, "BRAUN").own_group(0, "HELLBLAU")


@pytest.mark.rule("R-407")
@pytest.mark.rule("P-19")
@pytest.mark.rule("K-03")
def test_demand_computation() -> None:
    eng, _ = _pre(_scarcity_builder())
    st = eng.state
    assert st.bank_houses == 8
    assert house_demand(st, eng.board, 0) == 20  # 8 brown + 12 light blue, cash suffices
    assert house_demand(st, eng.board, 1) == 12
    assert hotel_demand(st, eng.board, 1) == 6
    st.cash[1] = 250
    assert house_demand(st, eng.board, 1) == 2
    st.cash[1] = 1500


@pytest.mark.rule("P-19")
@pytest.mark.rule("R-407")
def test_scarcity_no_bids_trigger_gets_house() -> None:
    eng, _ = _pre(_scarcity_builder())
    eng.apply(A.build(0))
    d = eng.pending()
    assert d is not None and d.kind == D.AUCTION_BID and d.context["item"] == "HOUSE"
    assert d.context["participants"] == [0, 1] and d.context["min_bid"] == 0
    eng.apply(Bid(None))
    eng.apply(Bid(None))
    assert eng.state.level[0] == 1 and eng.state.cash[0] == 1450
    won = events_of(eng, "BUILDING_AUCTION_WON")[-1]
    assert won.data["no_bids"] and won.seat == 0
    d = eng.pending()
    assert d is not None and d.seat == 0 and d.phase == D.PRE_ROLL


@pytest.mark.rule("P-19")
def test_scarcity_trigger_wins_pays_premium() -> None:
    eng, _ = _pre(_scarcity_builder())
    eng.apply(A.build(0))
    eng.apply(Bid(0))
    eng.apply(Bid(5))
    eng.apply(Bid(6))
    eng.apply(Bid(None))
    assert eng.state.level[0] == 1 and eng.state.cash[0] == 1500 - 6 - 50


@pytest.mark.rule("P-19")
def test_scarcity_foreign_bidder_places_in_own_group() -> None:
    eng, _ = _pre(_scarcity_builder())
    eng.apply(A.build(0))
    eng.apply(Bid(None))
    eng.apply(Bid(10))
    d = eng.pending()
    assert d is not None and d.seat == 1 and d.phase == D.PLACE_BUILDING
    assert d.legal_actions() == [A.build(8), A.build(9), A.build(10)]
    eng.apply(A.build(9))
    st = eng.state
    assert st.level[9] == 1 and st.level[0] == 0 and st.cash[1] == 1500 - 10 - 100
    d = eng.pending()
    assert d is not None and d.seat == 0 and d.phase == D.PRE_ROLL  # trigger's window continues


@pytest.mark.rule("P-19")
def test_scarcity_bid_limited_by_house_price() -> None:
    eng, _ = _pre(_scarcity_builder().cash(1, 130))
    eng.apply(A.build(0))
    eng.apply(Bid(None))
    d = eng.pending()
    assert d is not None and d.context["max_bid"] == 30 and d.context["bidder_price"] == 100
    with pytest.raises(IllegalActionError):
        eng.apply(Bid(31))


@pytest.mark.rule("P-19")
def test_no_auction_without_second_interested_player() -> None:
    eng, _ = _pre(_scarcity_builder().cash(1, 50))
    eng.apply(A.build(0))
    assert eng.state.level[0] == 1
    assert not events_of(eng, "BUILDING_AUCTION_STARTED")


@pytest.mark.rule("K-05")
def test_scarcity_auction_disabled() -> None:
    eng, _ = _pre(
        scenario(OFFICIAL, scarcity_auction=False)
        .own_group(1, "GRUEN", 4)
        .own_group(1, "GELB", 4)
        .own_group(1, "ORANGE")
        .own_group(0, "BRAUN")
    )
    eng.apply(A.build(0))
    assert eng.state.level[0] == 1 and not events_of(eng, "BUILDING_AUCTION_STARTED")


@pytest.mark.rule("D-05")
def test_scarcity_sealed_research() -> None:
    eng, _ = _pre(_scarcity_builder(RESEARCH))
    eng.apply(A.build(0))
    d = eng.pending()
    assert (
        d is not None and d.context["format"] == D.FORMAT_SEALED and d.context["levels"] == [0, 5, 13, 25, 38, 50, 75]
    )
    eng.apply(BidLevel(2))
    eng.apply(BidLevel(5))
    d = eng.pending()
    assert d is not None and d.seat == 1 and d.phase == D.PLACE_BUILDING
    assert eng.state.cash[1] == 1500 - 14  # min(50, 13 + 1)
    eng.apply(A.build(8))


@pytest.mark.rule("D-05")
def test_scarcity_sealed_single_bid_premium_zero() -> None:
    eng, _ = _pre(_scarcity_builder(RESEARCH))
    eng.apply(A.build(0))
    eng.apply(BidLevel(None))
    eng.apply(BidLevel(6))
    assert eng.state.cash[1] == 1500
    eng.apply(A.build(8))
    assert eng.state.cash[1] == 1400


@pytest.mark.rule("D-05")
def test_scarcity_sealed_tie_goes_to_trigger_order() -> None:
    eng, _ = _pre(_scarcity_builder(RESEARCH))
    eng.apply(A.build(0))
    eng.apply(BidLevel(3))
    eng.apply(BidLevel(3))
    assert eng.state.level[0] == 1 and eng.state.cash[0] == 1500 - 25 - 50


@pytest.mark.rule("P-19")
def test_hotel_scarcity() -> None:
    b = scenario().own_group(1, "GRUEN", 5).own_group(1, "GELB", 5).own_group(1, "ROT", 5).own_group(1, "ORANGE")
    b.level(8, 5).level(9, 5).level(10, 4)
    b.own_group(0, "PINK", 4)
    eng, _ = _pre(b)
    st = eng.state
    assert st.bank_hotels == 1 and hotel_demand(st, eng.board, 0) == 3 and hotel_demand(st, eng.board, 1) == 1
    houses_before = st.bank_houses
    eng.apply(A.build(5))
    d = eng.pending()
    assert d is not None and d.context["item"] == "HOTEL"
    eng.apply(Bid(None))
    eng.apply(Bid(1))
    d = eng.pending()
    assert d is not None and d.phase == D.PLACE_BUILDING and d.legal_actions() == [A.build(10)]
    eng.apply(A.build(10))
    # Hotel placed: four houses of the street return to the bank (freed houses).
    assert eng.state.level[10] == 5 and eng.state.bank_hotels == 0 and eng.state.bank_houses == houses_before + 4


@pytest.mark.rule("P-19")
@pytest.mark.rule("K-04")
def test_scarcity_auction_in_out_of_turn_window() -> None:
    eng = _scarcity_builder().active(1).build()
    d = advance(eng, at(0, D.OUT_OF_TURN, D.MAIN))
    assert d.legal is not None and d.legal[A.build(0)]
    eng.apply(A.build(0))
    d = eng.pending()
    assert d is not None and d.kind == D.AUCTION_BID and d.phase == D.OUT_OF_TURN


# ---------------------------------------------------------------------- mortgages
@pytest.mark.rule("R-501")
def test_mortgage_payout_and_group_block() -> None:
    eng, d = _pre(scenario().own(0, 0, 2))
    assert d.legal is not None and d.legal[A.mortgage(0)] and d.legal[A.mortgage(2)]
    eng.apply(A.mortgage(2))
    assert eng.state.cash[0] == 1600 and eng.state.mortgaged[2]
    _, d = _pre(scenario().own_group(0, "BRAUN").level(0, 1))
    assert d.legal is not None and not d.legal[A.mortgage(0)] and not d.legal[A.mortgage(1)]


@pytest.mark.rule("R-502")
@pytest.mark.rule("P-05")
def test_unmortgage_cost_rounded_up() -> None:
    eng, d = _pre(scenario().own(0, 26, mortgaged=True).cash(0, 193))
    assert d.legal is not None and d.legal[A.unmortgage(26)]
    eng.apply(A.unmortgage(26))
    assert eng.state.cash[0] == 0 and not eng.state.mortgaged[26]
    _, d = _pre(scenario().own(0, 26, mortgaged=True).cash(0, 192))
    assert d.legal is not None and not d.legal[A.unmortgage(26)]


@pytest.mark.rule("R-503")
@pytest.mark.rule("P-13")
@pytest.mark.rule("R-802")
def test_received_mortgage_interest_and_principal_option() -> None:
    eng = scenario().own(0, 26, mortgaged=True).build()
    d = eng.pending()
    assert d is not None and d.kind == D.TRADE_OFFER
    eng.apply([TradeOffer(0, 1, get_cash=100, give_props=(26,))])
    assert eng.pending().kind == D.TRADE_RESPONSE  # type: ignore[union-attr]
    eng.apply(True)
    st = eng.state
    assert st.owner[26] == 1 and st.cash[1] == 1500 - 100 - 18
    assert st.interest_prepaid[26] >= 0
    d = advance(eng, at(1, D.OUT_OF_TURN, D.MAIN))
    assert d.legal is not None and d.legal[A.unmortgage(26)]
    eng.apply(A.END_PHASE)
    assert st.interest_prepaid[26] == -1
    assert unmortgage_cost(st, eng.board, eng.ruleset, 26) == 193


@pytest.mark.rule("P-13")
def test_principal_only_repayment() -> None:
    eng = scenario().own(0, 26, mortgaged=True).build()
    eng.apply([TradeOffer(0, 1, get_cash=100, give_props=(26,))])
    eng.apply(True)
    advance(eng, at(1, D.OUT_OF_TURN, D.MAIN))
    before = eng.state.cash[1]
    eng.apply(A.unmortgage(26))
    assert before - eng.state.cash[1] == 175
    assert events_of(eng, "PROPERTY_UNMORTGAGED")[-1].data["principal_only"]


def test_roll_counts_as_window_end_for_jail_stay() -> None:
    eng = scenario().jail(0, 0).dice((1, 2)).build()
    roll(eng, 0)
    assert eng.state.counter(COUNTER_INDEX["jail_stay"], 0) == 1
