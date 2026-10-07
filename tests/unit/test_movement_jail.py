"""Movement, salary, doubles and jail (R-101..R-110, P-15, P-17, P-18, A-102)."""

from __future__ import annotations

import pytest
from helpers import (
    MOVEMENT,
    OFFICIAL,
    advance,
    at,
    events_of,
    new_game,
    pre_roll,
    roll,
    scenario,
)

from propertyrl.engine import Bid, RuleViolationError
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D


@pytest.mark.rule("R-101")
def test_roll_moves_by_sum() -> None:
    eng = scenario().dice((1, 2)).build()
    roll(eng, 0)
    d = eng.pending()
    assert d is not None and d.phase == D.BUY_PHASE and d.context["p"] == C.SQUARE_TO_P[3]
    assert eng.state.position[0] == 3
    assert events_of(eng, "DICE_ROLLED")[-1].data["dice"] == [1, 2]
    assert events_of(eng, "MOVED")[-1].data["steps"] == 3


@pytest.mark.rule("R-102")
def test_salary_when_passing_start() -> None:
    eng = scenario().position(0, 38).dice((1, 2)).build()
    roll(eng, 0)
    assert eng.state.position[0] == 1
    assert eng.state.cash[0] == 1700
    assert len(events_of(eng, "SALARY")) == 1


@pytest.mark.rule("R-102")
def test_salary_when_landing_on_start() -> None:
    eng = scenario().position(0, 35).dice((2, 3)).build()
    roll(eng, 0)
    assert eng.state.position[0] == 0
    assert eng.state.cash[0] == 1700


@pytest.mark.rule("R-102")
@pytest.mark.rule("R-105")
def test_arrest_square_no_salary() -> None:
    eng = scenario().position(0, 25).dice((2, 3)).build()
    roll(eng, 0)
    st = eng.state
    assert st.position[0] == C.JAIL_SQUARE and st.in_jail[0]
    assert st.cash[0] == 1500
    assert not events_of(eng, "SALARY")
    # A-102: the turn's movement ends, the post-move window still follows.
    d = advance(eng, at(0, D.POST_MOVE, D.MAIN))
    assert d.legal is not None and d.legal[A.END_PHASE]


@pytest.mark.rule("R-103")
@pytest.mark.rule("P-01")
def test_doubles_roll_again_without_window() -> None:
    eng = scenario().position(0, 4).dice((2, 2), (1, 2)).build()
    roll(eng, 0)
    windows_before = len(events_of(eng, "WINDOW_OPENED"))
    d = advance(eng, lambda d: d.phase == D.BUY_PHASE and eng.state.position[0] == 11)
    assert d.seat == 0
    assert len(events_of(eng, "DICE_ROLLED")) == 2
    assert len(events_of(eng, "WINDOW_OPENED")) == windows_before


@pytest.mark.rule("R-104")
def test_third_double_goes_to_jail_without_moving() -> None:
    eng = scenario().position(0, 4).dice((1, 1), (1, 1), (2, 2)).build()
    roll(eng, 0)
    d = advance(eng, at(0, D.POST_MOVE, D.MAIN))
    st = eng.state
    assert st.in_jail[0] and st.position[0] == C.JAIL_SQUARE
    assert st.doubles_count == 0
    assert d.kind == D.MAIN
    moved = [e.data["to"] for e in events_of(eng, "MOVED")]
    assert moved == [6, 8]


@pytest.mark.rule("R-104")
def test_third_double_movement_only_ruleset() -> None:
    eng = scenario(MOVEMENT).dice((1, 1), (2, 2), (3, 3)).build()
    roll(eng, 0)
    assert eng.state.position[0] == C.JAIL_SQUARE and eng.state.in_jail[0]
    assert eng.state.rest_counts[2] == 1 and eng.state.rest_counts[6] == 1 and eng.state.rest_counts[10] == 1


@pytest.mark.rule("R-109")
def test_just_visiting() -> None:
    eng = scenario().position(0, 6).dice((1, 3)).build()
    roll(eng, 0)
    assert eng.state.position[0] == C.JAIL_SQUARE
    assert not eng.state.in_jail[0]


@pytest.mark.rule("R-110")
@pytest.mark.rule("R-704")
def test_turn_order_skips_bankrupt() -> None:
    eng = scenario(OFFICIAL, n=3).bankrupt(1).build()
    advance(eng, lambda d: len(events_of(eng, "TURN_STARTED")) >= 5)
    seats = [e.seat for e in events_of(eng, "TURN_STARTED")][:5]
    assert seats == [0, 2, 0, 2, 0]


@pytest.mark.rule("P-15")
def test_round_counter() -> None:
    eng = scenario(OFFICIAL, n=3).bankrupt(1).build()
    advance(eng, lambda d: len(events_of(eng, "TURN_STARTED")) >= 3)
    rounds = [e.data["round"] for e in events_of(eng, "TURN_STARTED")][:3]
    assert rounds == [0, 0, 1]


@pytest.mark.rule("P-10")
def test_seat_zero_starts() -> None:
    eng = new_game(OFFICIAL, 4, seed=99)
    d = eng.pending()
    assert d is not None and d.seat == 0
    assert eng.state.active_seat == 0


@pytest.mark.rule("R-106")
def test_jail_options_first_attempt() -> None:
    eng = scenario().jail(0, 0).build()
    d = advance(eng, pre_roll(0))
    assert d.phase == D.JAIL_PRE_ROLL
    assert d.legal is not None
    assert d.legal[A.ROLL] and d.legal[A.PAY_JAIL_FINE] and not d.legal[A.USE_JAIL_CARD]


@pytest.mark.rule("R-106")
def test_no_fine_payment_on_third_attempt_but_card_ok() -> None:
    eng = scenario().jail(0, 2).jail_card(0, C.DECK_B).build()
    d = advance(eng, pre_roll(0))
    assert d.legal is not None
    assert not d.legal[A.PAY_JAIL_FINE] and d.legal[A.USE_JAIL_CARD] and d.legal[A.ROLL]


@pytest.mark.rule("R-106")
def test_fine_requires_cash() -> None:
    eng = scenario().jail(0, 0).cash(0, 49).build()
    d = advance(eng, pre_roll(0))
    assert d.legal is not None and not d.legal[A.PAY_JAIL_FINE]


@pytest.mark.rule("R-106")
def test_jail_doubles_frees_and_moves_once() -> None:
    eng = scenario().jail(0, 0).dice((3, 3)).build()
    roll(eng, 0)
    st = eng.state
    assert not st.in_jail[0] and st.position[0] == 16 and st.jail_attempts[0] == 0
    # No further roll: the DiceScript has a single pair and is not exhausted.
    advance(eng, at(1, D.OUT_OF_TURN, D.MAIN))
    assert len(events_of(eng, "DICE_ROLLED")) == 1


@pytest.mark.rule("R-106")
def test_jail_failed_roll_stays() -> None:
    eng = scenario().jail(0, 0).dice((1, 2)).build()
    roll(eng, 0)
    st = eng.state
    assert st.in_jail[0] and st.jail_attempts[0] == 1 and st.position[0] == C.JAIL_SQUARE
    d = advance(eng, at(0, D.POST_MOVE, D.MAIN))
    assert d.legal is not None and d.legal[A.END_PHASE]


@pytest.mark.rule("R-107")
def test_third_failure_pays_and_moves() -> None:
    eng = scenario().jail(0, 2).dice((1, 2)).build()
    roll(eng, 0)
    st = eng.state
    assert not st.in_jail[0] and st.position[0] == 13
    assert st.cash[0] == 1450
    assert events_of(eng, "JAIL_FINE_PAID")


@pytest.mark.rule("P-17")
@pytest.mark.rule("R-107")
def test_third_failure_debt_phase() -> None:
    eng = scenario().jail(0, 2).cash(0, 20).own(0, 0).dice((1, 2)).build()
    roll(eng, 0)
    d = eng.pending()
    assert d is not None and d.kind == D.DEBT and d.context["creditor"] == C.BANK and d.context["amount"] == 50
    assert d.legal_actions() == [A.mortgage(0)]
    eng.apply(A.mortgage(0))
    st = eng.state
    assert st.cash[0] == 0 and not st.in_jail[0] and st.position[0] == 13
    d2 = eng.pending()
    assert d2 is not None and d2.phase == D.BUY_PHASE and d2.legal is not None and not d2.legal[A.BUY]


@pytest.mark.rule("P-17")
def test_third_failure_bankrupt_without_assets() -> None:
    eng = scenario().jail(0, 2).cash(0, 20).dice((1, 2)).build()
    roll(eng, 0)
    assert eng.is_over()
    assert eng.result().winner == 1


@pytest.mark.rule("P-18")
def test_after_fine_normal_pre_roll() -> None:
    eng = scenario().jail(0, 0).own_group(0, "BRAUN").dice((1, 2)).build()
    advance(eng, pre_roll(0))
    eng.apply(A.PAY_JAIL_FINE)
    d = eng.pending()
    assert d is not None and d.phase == D.PRE_ROLL and d.seat == 0
    assert d.legal is not None and d.legal[A.ROLL] and d.legal[A.build(0)]
    assert eng.state.cash[0] == 1450
    eng.apply(A.ROLL)
    assert eng.state.position[0] == 13


@pytest.mark.rule("P-18")
@pytest.mark.rule("R-607")
def test_use_card_returns_it_under_deck() -> None:
    eng = scenario().jail(0, 1).jail_card(0, C.DECK_A).build()
    assert len(eng.state.deck_a) == 15
    advance(eng, pre_roll(0))
    eng.apply(A.USE_JAIL_CARD)
    st = eng.state
    assert not st.in_jail[0] and st.jail_cards[0] == 0
    assert len(st.deck_a) == 16 and st.deck_a[-1] == eng.decks.jail_free_index[0]
    d = eng.pending()
    assert d is not None and d.phase == D.PRE_ROLL


@pytest.mark.rule("R-104")
def test_both_jail_cards_deck_a_used_first() -> None:
    eng = scenario().jail(0, 0).jail_card(0, C.DECK_A).jail_card(0, C.DECK_B).build()
    advance(eng, pre_roll(0))
    eng.apply(A.USE_JAIL_CARD)
    assert eng.state.jail_cards[0] == C.DECK_BITS[C.DECK_B]


@pytest.mark.rule("R-108")
@pytest.mark.rule("R-307")
def test_jailed_owner_collects_rent_and_manages() -> None:
    eng = scenario().jail(1, 0).own(1, 0).position(0, 39).dice((1, 1), (2, 3)).build()
    roll(eng, 0)
    st = eng.state
    assert st.cash[1] == 1502  # rent 2 for Braun-1 while in jail
    assert st.cash[0] == 1500 + 200 - 2
    # Jailed seat participates in the auction (R-108 bidding).
    eng.apply(A.DECLINE)
    d = eng.pending()
    assert d is not None and d.kind == D.AUCTION_BID
    assert d.context["participants"] == [0, 1]
    eng.apply(Bid(None))
    d = eng.pending()
    assert d is not None and d.seat == 1 and d.kind == D.AUCTION_BID
    eng.apply(Bid(5))
    assert eng.state.owner[3] == 1  # Hellblau-1 (p3) to the jailed bidder


@pytest.mark.rule("R-108")
def test_jailed_player_can_build_mortgage_and_trade() -> None:
    eng = scenario().jail(0, 0).own_group(0, "BRAUN").own(0, 2).build()
    d = eng.pending()
    assert d is not None and d.kind == D.TRADE_OFFER and d.phase == D.JAIL_PRE_ROLL
    eng.apply([])
    d = eng.pending()
    assert d is not None and d.legal is not None
    assert d.legal[A.build(0)] and d.legal[A.mortgage(2)]


def test_dice_script_exhaustion_is_rule_violation() -> None:
    eng = scenario().dice((1, 2)).build()
    roll(eng, 0)
    with pytest.raises(RuleViolationError):
        advance(eng, lambda d: False, limit=200)
