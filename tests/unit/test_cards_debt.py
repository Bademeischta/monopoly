"""Cards, payments, debt phase and bankruptcy (R-601..R-612, R-701..R-705, P-06, P-07, P-12)."""

from __future__ import annotations

import pytest
from helpers import OFFICIAL, advance, events_of, pre_roll, roll, scenario

from propertyrl.engine import Bid
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D


def _card(deck: int, card: str, start: int, dice: tuple[int, int], n: int = 2, **kw):  # type: ignore[no-untyped-def]
    b = scenario(OFFICIAL, n=n).position(0, start).dice(dice, *kw.pop("extra_dice", ())).cards(deck, [card])
    for fn, args in kw.items():
        getattr(b, fn)(*args)
    return b


@pytest.mark.rule("R-602")
@pytest.mark.rule("R-601")
def test_advance_to_with_salary() -> None:
    eng = _card(C.DECK_A, "A03", 31, (2, 3)).build()
    roll(eng, 0)
    st = eng.state
    assert st.position[0] == 24 and st.cash[0] == 1700
    d = eng.pending()
    assert d is not None and d.phase == D.BUY_PHASE and d.context["p"] == 16
    a03 = eng.decks.index_of(C.DECK_A, "A03")
    assert st.deck_a[-1] == a03 and st.deck_cycle_drawn_a == 1 << a03


@pytest.mark.rule("R-602")
def test_advance_without_passing_start() -> None:
    eng = _card(C.DECK_A, "A01", 31, (2, 3)).build()
    roll(eng, 0)
    assert eng.state.position[0] == 39 and eng.state.cash[0] == 1500


@pytest.mark.rule("R-602")
@pytest.mark.rule("H-02")
def test_advance_to_start() -> None:
    eng = _card(C.DECK_B, "B01", 14, (1, 2)).build()
    roll(eng, 0)
    assert eng.state.position[0] == 0 and eng.state.cash[0] == 1700  # salary once, never doubled


@pytest.mark.rule("R-603")
def test_nearest_rail_double_rent() -> None:
    eng = _card(C.DECK_A, "A05", 3, (1, 3)).own(1, 10).build()
    roll(eng, 0)
    assert eng.state.position[0] == 15 and eng.state.cash[0] == 1450 and eng.state.cash[1] == 1550


@pytest.mark.rule("R-603")
@pytest.mark.rule("P-11")
def test_nearest_rail_double_rent_counts_mortgaged_rails() -> None:
    eng = _card(C.DECK_A, "A06", 3, (1, 3)).own(1, 10).own(1, 2, mortgaged=True).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1400


@pytest.mark.rule("R-603")
def test_nearest_rail_over_start_unowned_buy() -> None:
    eng = _card(C.DECK_A, "A05", 31, (2, 3)).build()
    roll(eng, 0)
    d = eng.pending()
    assert eng.state.position[0] == 5 and eng.state.cash[0] == 1700
    assert d is not None and d.phase == D.BUY_PHASE and d.context["p"] == 2


@pytest.mark.rule("R-604")
def test_nearest_util_new_roll_times_ten() -> None:
    eng = _card(C.DECK_A, "A07", 17, (2, 3), extra_dice=[(4, 5)]).own(1, 20).build()
    roll(eng, 0)
    assert eng.state.position[0] == 28 and eng.state.cash[0] == 1500 - 90


@pytest.mark.rule("R-604")
def test_nearest_util_over_start() -> None:
    eng = _card(C.DECK_A, "A07", 31, (2, 3)).build()
    roll(eng, 0)
    d = eng.pending()
    assert eng.state.position[0] == 12 and eng.state.cash[0] == 1700
    assert d is not None and d.context["p"] == 7


@pytest.mark.rule("R-605")
def test_move_back_from_36_draws_deck_b() -> None:
    eng = _card(C.DECK_A, "A10", 31, (2, 3)).cards(C.DECK_B, ["B02"]).build()
    roll(eng, 0)
    assert eng.state.position[0] == 33 and eng.state.cash[0] == 1700
    assert [e.data["card"] for e in events_of(eng, "CARD_DRAWN")] == ["A10", "B02"]
    assert not events_of(eng, "SALARY")


@pytest.mark.rule("R-605")
def test_move_back_never_crosses_start() -> None:
    eng = _card(C.DECK_A, "A10", 3, (1, 3)).build()
    roll(eng, 0)
    assert eng.state.position[0] == 4 and eng.state.cash[0] == 1300
    assert not events_of(eng, "SALARY")


@pytest.mark.rule("R-606")
def test_card_send_to_jail() -> None:
    eng = _card(C.DECK_A, "A11", 3, (1, 3)).build()
    roll(eng, 0)
    assert eng.state.in_jail[0] and eng.state.position[0] == 10 and eng.state.cash[0] == 1500


@pytest.mark.rule("R-607")
def test_jail_free_card_kept() -> None:
    eng = _card(C.DECK_A, "A09", 3, (1, 3)).build()
    roll(eng, 0)
    assert eng.state.jail_cards[0] == 1 and len(eng.state.deck_a) == 15


@pytest.mark.rule("R-608")
def test_collect() -> None:
    eng = _card(C.DECK_B, "B02", 14, (1, 2)).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1700


@pytest.mark.rule("R-609")
@pytest.mark.rule("V1")
def test_pay() -> None:
    eng = _card(C.DECK_B, "B12", 14, (1, 2)).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1450


@pytest.mark.rule("R-610")
def test_pay_each() -> None:
    eng = _card(C.DECK_A, "A15", 3, (1, 3), n=3).build()
    roll(eng, 0)
    assert eng.state.cash == [1400, 1550, 1550]


@pytest.mark.rule("P-07")
@pytest.mark.rule("R-610")
def test_pay_each_bankruptcy_counts_against_bank() -> None:
    # Hellblau-1 already mortgaged: no liquidation possible.
    eng = _card(C.DECK_A, "A15", 3, (1, 3), n=3).cash(0, 70).own(0, 3, mortgaged=True).build()
    roll(eng, 0)
    st = eng.state
    assert st.bankrupt[0] and st.cash[1] == 1550 and st.cash[2] == 1500
    bk = events_of(eng, "BANKRUPTCY")[-1]
    assert bk.data["creditor"] == C.BANK
    assert st.owner[3] == C.BANK and not st.mortgaged[3]  # P-12 via R-703


@pytest.mark.rule("R-611")
def test_collect_each() -> None:
    eng = _card(C.DECK_B, "B09", 14, (1, 2), n=3).build()
    roll(eng, 0)
    assert eng.state.cash == [1520, 1490, 1490]


@pytest.mark.rule("R-612")
def test_repairs_hotel_counts_as_hotel() -> None:
    eng = _card(C.DECK_A, "A12", 3, (1, 3)).own_group(0, "BRAUN").level(0, 5).level(1, 4).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1500 - (4 * 25 + 100)
    eng = _card(C.DECK_B, "B14", 14, (1, 2)).own_group(0, "BRAUN").level(0, 5).level(1, 4).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1500 - (4 * 40 + 115)


@pytest.mark.rule("R-612")
def test_repairs_without_buildings_is_free() -> None:
    eng = _card(C.DECK_A, "A12", 3, (1, 3)).build()
    roll(eng, 0)
    assert eng.state.cash[0] == 1500 and not events_of(eng, "PAYMENT")


@pytest.mark.rule("R-601")
def test_cycle_mask_resets_when_all_drawn() -> None:
    eng = _card(C.DECK_B, "B02", 14, (1, 2)).build()
    st = eng.state
    b02 = eng.decks.index_of(C.DECK_B, "B02")
    st.deck_cycle_drawn_b = ((1 << 16) - 1) & ~(1 << b02)
    roll(eng, 0)
    assert st.deck_cycle_drawn_b == 0


# ---------------------------------------------------------------------- debt and bankruptcy
@pytest.mark.rule("R-701")
@pytest.mark.rule("P-06")
@pytest.mark.rule("K-01")
def test_debt_phase_liquidate_and_pay() -> None:
    eng = scenario().own(1, 6).own(0, 0).cash(0, 5).position(0, 6).dice((2, 3)).build()
    roll(eng, 0)
    d = eng.pending()
    assert d is not None and d.kind == D.DEBT and d.context == {"creditor": 1, "amount": 10, "reason": "RENT"}
    assert d.legal_actions() == [A.mortgage(0)]  # K-01: no trade offers inside the debt phase
    eng.apply(A.mortgage(0))
    assert eng.state.cash == [25, 1510]
    assert events_of(eng, "DEBT_SETTLED")


@pytest.mark.rule("R-701")
def test_debt_sell_buildings() -> None:
    eng = scenario().own(1, 6).own_group(0, "BRAUN").level(0, 1).cash(0, 5).position(0, 6).dice((2, 3)).build()
    roll(eng, 0)
    d = eng.pending()
    assert d is not None and d.legal_actions() == [A.sell(0)]
    eng.apply(A.sell(0))
    assert eng.state.cash[0] == 20 and eng.state.level[0] == 0


@pytest.mark.rule("P-06")
@pytest.mark.rule("R-901")
@pytest.mark.rule("R-702")
def test_automatic_bankruptcy_to_player() -> None:
    eng = scenario().own(1, 6).cash(0, 5).position(0, 6).dice((2, 3)).jail_card(0, C.DECK_A).build()
    roll(eng, 0)
    assert eng.is_over()
    res = eng.result()
    assert res.winner == 1 and res.placements == [2, 1]
    assert eng.state.cash == [0, 1505]
    assert eng.state.jail_cards[1] == 1


@pytest.mark.rule("R-702")
@pytest.mark.rule("R-503")
def test_bankruptcy_to_player_transfers_mortgaged_with_interest() -> None:
    b = scenario(OFFICIAL, n=3).own(1, 6).own(0, 0, 1, mortgaged=True).cash(0, 5).position(0, 6).dice((2, 3))
    eng = b.jail_card(0, C.DECK_B).build()
    roll(eng, 0)
    st = eng.state
    assert st.bankrupt[0] and st.owner[0] == 1 and st.owner[1] == 1
    assert st.mortgaged[0] and st.mortgaged[1]
    assert st.cash[1] == 1500 + 5 - 3 - 3
    assert st.jail_cards[1] == 2
    assert st.interest_prepaid[0] >= 0


@pytest.mark.rule("R-702")
@pytest.mark.rule("R-503")
def test_creditor_cannot_pay_interest_cascade() -> None:
    b = scenario(OFFICIAL, n=3).own(1, 6).own(0, 0, 1, mortgaged=True).cash(0, 5).position(0, 6).dice((2, 3))
    eng = b.cash(1, 0).own(1, 26).build()
    roll(eng, 0)
    d = eng.pending()
    # Seat 1 inherited cash 5, paid the first interest (3) and owes the second one (3) to the bank.
    assert d is not None and d.seat == 1 and d.kind == D.DEBT
    assert d.context == {"creditor": C.BANK, "amount": 3, "reason": "INTEREST"}
    assert eng.state.cash[1] == 2
    assert d.legal_actions() == [A.mortgage(6), A.mortgage(26)]
    eng.apply(A.mortgage(26))
    assert eng.state.cash[1] == 2 + 175 - 3 and not eng.state.bankrupt[1]
    assert events_of(eng, "DEBT_SETTLED")


@pytest.mark.rule("R-703")
@pytest.mark.rule("P-12")
def test_bankruptcy_to_bank_auctions_unmortgaged() -> None:
    b = scenario(OFFICIAL, n=3).own(0, 0, 2, mortgaged=True).cash(0, 50).position(0, 0).dice((1, 3))
    eng = b.jail_card(0, C.DECK_B).build()
    roll(eng, 0)
    st = eng.state
    assert st.bankrupt[0] and st.owner[0] == C.BANK and not st.mortgaged[0]
    assert len(st.deck_b) == 16
    d = eng.pending()
    assert d is not None and d.kind == D.AUCTION_BID and d.context["p"] == 0
    assert d.context["participants"] == [1, 2] and d.context["origin"] == 1
    eng.apply(Bid(5))
    eng.apply(Bid(None))
    assert st.owner[0] == 1
    d = eng.pending()
    assert d is not None and d.context["p"] == 2


@pytest.mark.rule("R-704")
@pytest.mark.rule("R-902")
def test_placements_reverse_bankruptcy_order() -> None:
    eng = scenario(OFFICIAL, n=4).bankrupt(3).bankrupt(1).own(0, 6).cash(2, 5).active(2).position(2, 6)
    eng = eng.dice((2, 3)).build()
    roll(eng, 2)
    res = eng.result()
    assert eng.is_over() and res.winner == 0
    assert res.placements == [1, 3, 2, 4]


@pytest.mark.rule("R-705")
def test_bank_never_runs_out() -> None:
    eng = scenario().own(0, *range(28)).build()
    advance(eng, pre_roll(0))
    for p in range(28):
        eng.apply(A.mortgage(p))
    assert eng.state.cash[0] == 1500 + sum(eng.board.p_mortgage)


def test_starting_player_bankrupt_game_continues() -> None:
    eng = scenario(OFFICIAL, n=3).own(1, 6).cash(0, 5).position(0, 6).dice((2, 3)).build()
    roll(eng, 0)
    assert eng.state.bankrupt[0] and not eng.is_over()
    d = advance(eng, pre_roll(1))
    assert d.seat == 1
