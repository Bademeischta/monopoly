"""Remaining engine branches: equity, validation, ledger, invariants, direct frame calls and API errors."""

from __future__ import annotations

import pytest
from helpers import (
    OFFICIAL,
    RESEARCH,
    advance,
    board,
    decks,
    new_game,
    passive_response,
    pre_roll,
    rules,
    scenario,
)

from propertyrl.engine import Bid, ConfigError, Engine, EngineOptions, IllegalActionError, RuleViolationError
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine import frames as F
from propertyrl.engine.auction import AuctionState
from propertyrl.engine.board import Board
from propertyrl.engine.building import count_buildings, min_target_price, place_targets, sell_all_buildings
from propertyrl.engine.debt import bankrupt_frame, has_liquidation, next_active_after, pay_frame
from propertyrl.engine.equity import (
    all_equities,
    canonical_equity,
    equity_shares,
    liquidation_value,
    weighted_equity,
)
from propertyrl.engine.events import Event
from propertyrl.engine.hashing import sha256_bytes, sha256_hex
from propertyrl.engine.invariants import violations
from propertyrl.engine.ledger import Ledger
from propertyrl.engine.replay import check_versions, read_log
from propertyrl.engine.ruleset import Ruleset
from propertyrl.engine.state import GameState
from propertyrl.engine.trade import TradeOffer, trades_enabled, validate_offer


def test_equity_functions() -> None:
    eng = scenario(OFFICIAL, n=3).own_group(0, "BRAUN", 2).own(0, 2, mortgaged=True).own(1, 6, 8).bankrupt(2).build()
    st, bd = eng.state, eng.board
    # cash 1500 + 60 + 60 + 100 (half of rail) + 4 houses x 50
    assert canonical_equity(st, bd, 0) == 1500 + 120 + 100 + 200
    # cash + mortgage values of unmortgaged (30 + 30) + half building cost (100)
    assert liquidation_value(st, bd, 0) == 1500 + 60 + 100
    assert weighted_equity(st, bd, 0) == 1500 + 2.0 * 120 + 1.0 * 100 + 200
    assert weighted_equity(st, bd, 1) == 1500 + 1.5 * 280
    assert canonical_equity(st, bd, 2) == 0 and liquidation_value(st, bd, 2) == 0 and weighted_equity(st, bd, 2) == 0
    shares = equity_shares(st, bd)
    assert shares[2] == 0.0 and abs(sum(shares) - 1.0) < 1e-12
    assert all_equities(st, bd)[1] == 1780


def test_equity_share_zero_total() -> None:
    eng = scenario().cash(0, 0).cash(1, 0).build()
    assert equity_shares(eng.state, eng.board) == [0.5, 0.5]


def test_board_validation_branches() -> None:
    base = board().to_dict()

    def broken(mut) -> None:  # type: ignore[no-untyped-def]
        d = board().to_dict()
        mut(d["squares"])
        with pytest.raises(ConfigError):
            Board.from_dict(d)

    broken(lambda s: s[3].__setitem__("index", 7))
    broken(lambda s: s[3].__setitem__("kind", "PLANET"))
    broken(lambda s: s[2].__setitem__("kind", "STREET"))
    broken(lambda s: s[1].__setitem__("group", "PINK"))
    broken(lambda s: s[1].__setitem__("rents", [1, 2]))
    broken(lambda s: s[1].__setitem__("house_price", 51))
    broken(lambda s: s[5].__setitem__("rents", [25]))
    broken(lambda s: s[12].__setitem__("rents", [4]))
    broken(lambda s: s[4].__setitem__("tax", 0))
    broken(lambda s: s[15].__setitem__("rents", [30, 60, 120, 240]))
    broken(lambda s: s[0].__setitem__("kind", "REST"))
    with pytest.raises(ConfigError):
        Board.from_dict({"squares": [{"index": "x"}]})
    assert base["board_id"] == "board_us_neutral" and board().name(39) == "Dunkelblau-2"


def test_ruleset_validation() -> None:
    base = rules().to_dict()
    for key, value in (
        ("decision_protocol", "x"),
        ("auction_protocol", "x"),
        ("trade_protocol", "x"),
        ("game_end", "x"),
        ("player_count", [1, 9]),
        ("safety_horizon_rounds", 0),
        ("starting_cash", -1),
    ):
        d = dict(base)
        d[key] = value
        with pytest.raises(ConfigError):
            Ruleset.from_dict(d)
    d = dict(base)
    d["game_end"] = "short_game"
    d["max_rounds"] = 0
    with pytest.raises(ConfigError):
        Ruleset.from_dict(d)
    d = dict(base)
    d["player_count"] = 3
    assert Ruleset.from_dict(d).player_count == (3, 3)
    with pytest.raises(ConfigError):
        Ruleset.from_dict({"ruleset_id": "x"})
    assert rules(RESEARCH).sealed and not rules(OFFICIAL).short_game


def test_deck_lookup_errors() -> None:
    with pytest.raises(ConfigError):
        decks().index_of(0, "Z99")
    assert decks().deck(1)[0].card_id == "B01"


def test_ledger_helpers() -> None:
    led = Ledger()
    led.record(C.BANK, 0, 200, "SALARY", 0)
    led.record(0, 1, 50, "RENT", 1)
    assert led.totals(2) == ([200, 50], [50, 0])
    assert led.balance(0, 1500) == 1650
    cp = led.copy()
    assert cp.to_list() == led.to_list() and cp.transactions is not led.transactions


def test_small_helpers() -> None:
    assert sha256_bytes(b"x") == sha256_bytes(b"x") and len(sha256_hex({"a": 1})) == 64
    with pytest.raises(ValueError):
        A.decode(106)
    assert A.action_name(A.unmortgage(3)) == "UNMORTGAGE_p3" and len(A.all_action_names()) == 106
    assert D.Decision(0, D.TRADE_OFFER, D.PRE_ROLL, None).legal_actions() == []
    ev = Event(1, 2, "BID", 0, {"amount": 3})
    assert Event.from_dict(ev.to_dict()) == ev
    a = AuctionState(F.I_PROPERTY, [0, 1], False, 60, "BUY", p=1)
    assert AuctionState.from_dict(a.to_dict()).to_dict() == a.to_dict()


def test_view_helpers() -> None:
    eng = scenario(OFFICIAL, n=3).bankrupt(1).build()
    view = eng.public_view(0)
    assert view.active_players() == [0, 2] and view.n_active() == 2


def test_state_roundtrip() -> None:
    eng = new_game(OFFICIAL, 3, seed=5)
    for _ in range(300):
        eng.apply(passive_response(eng))
    st = GameState.from_canonical_dict(eng.state.to_canonical_dict())
    assert st.state_hash() == eng.state_hash()
    assert eng.state.active_players() == [0, 1, 2]


def test_building_helpers() -> None:
    eng = scenario().own_group(0, "BRAUN", 4).own_group(0, "PINK", 1).build()
    st, bd = eng.state, eng.board
    assert place_targets(st, bd, 0, hotel=True) == [0, 1]
    assert place_targets(st, bd, 0, hotel=False, cash=60) == []
    assert min_target_price(st, bd, 0, hotel=False) == 100
    assert min_target_price(st, bd, 1, hotel=False) == -1
    assert count_buildings(st, 0) == (11, 0)


def test_sell_all_buildings_and_bankruptcy_frame_with_buildings() -> None:
    eng = scenario(OFFICIAL, n=3).own_group(0, "BRAUN", 5).own_group(0, "PINK", 2).build()
    st = eng.state
    bankrupt_frame(eng, (F.OP_BANKRUPT, 0, 1))
    # 2 hotels (5 units x 25) + 6 houses x 50 at half price -> cash first to the debtor, then the creditor
    assert st.bank_hotels == 12 and st.bank_houses == 32
    assert st.cash[1] == 1500 + 1500 + 250 + 300
    assert st.owner[0] == 1 and st.level == [0] * C.N_BUILD
    eng2 = scenario().own_group(0, "BRAUN", 1).build()
    assert sell_all_buildings(eng2, 1) == 0
    bankrupt_frame(eng2, (F.OP_BANKRUPT, 1, 0))  # already handled seats are ignored on repeat
    bankrupt_frame(eng2, (F.OP_BANKRUPT, 1, 0))
    assert eng2.is_over()


def test_payment_to_bankrupt_creditor_lapses() -> None:
    eng = scenario(OFFICIAL, n=3).bankrupt(2).build()
    pay_frame(eng, (F.OP_PAY, 0, 2, 100, F.R_RENT, 0))
    assert eng.state.cash[0] == 1500
    pay_frame(eng, (F.OP_PAY, 0, 1, 0, F.R_RENT, 0))
    assert eng.state.cash[0] == 1500
    assert next_active_after(eng.state, 1) == 0
    assert not has_liquidation(eng.state, 0)


def test_bankruptcy_to_already_bankrupt_creditor_goes_to_bank() -> None:
    eng = scenario(OFFICIAL, n=4).bankrupt(2).own(0, 6).build()
    bankrupt_frame(eng, (F.OP_BANKRUPT, 0, 2))
    assert eng.state.owner[6] == C.BANK


def test_debt_settlement_with_lapsed_creditor() -> None:
    from propertyrl.engine.debt import after_debt_action

    eng = scenario(OFFICIAL, n=3).bankrupt(2).build()
    frame = (F.OP_D_DEBT, 0, 2, 100, F.R_RENT, 0)
    eng.state.stack.append(frame)
    after_debt_action(eng, frame)
    ev = eng.events[-1]
    assert ev.type == "DEBT_SETTLED" and ev.data["lapsed"] and eng.state.cash[0] == 1500


def test_trade_validation_branches() -> None:
    eng = scenario(OFFICIAL, n=3).own(0, 26, mortgaged=True).own(1, 6).jail_card(0, 0).bankrupt(2).build()
    st, bd, rs = eng.state, eng.board, eng.ruleset
    assert validate_offer(st, bd, rs, "x", 0) == "not a TradeOffer"  # type: ignore[arg-type]
    assert validate_offer(st, bd, rs, TradeOffer(0, 2, give_cash=1), 0) == "bankrupt participant"
    assert validate_offer(st, bd, rs, TradeOffer(0, 1, give_props=(99,)), 0) == "invalid property index"
    assert validate_offer(st, bd, rs, TradeOffer(0, 1, give_props=(26, 26)), 0) == "duplicate property"
    assert validate_offer(st, bd, rs, TradeOffer(0, 1, give_jail_cards=5), 0) is not None
    st.cash[1] = 10
    reason = validate_offer(st, bd, rs, TradeOffer(1, 0, give_props=(6,), get_props=(26,)), 1)
    assert reason == "proposer cannot pay interest on mortgaged properties"
    st.cash[1] = 1500
    assert trades_enabled(eng)


def test_api_errors() -> None:
    eng = new_game(OFFICIAL, 2, seed=1)
    eng.apply([])
    with pytest.raises(IllegalActionError):
        eng.apply(True)  # bool is not an action id
    with pytest.raises(IllegalActionError):
        eng.apply(-1)
    with pytest.raises(IllegalActionError):
        eng.apply("ROLL")
    eng2 = scenario().own(1, 6).cash(0, 5).position(0, 6).dice((2, 3)).build()
    advance(eng2, pre_roll(0))
    eng2.apply(A.ROLL)
    assert eng2.is_over() and eng2.pending() is None and eng2.legal_mask() == [False] * 106
    with pytest.raises(IllegalActionError):
        eng2.apply(A.ROLL)


def test_auction_response_type_errors() -> None:
    eng = scenario().dice((1, 2)).build()
    advance(eng, pre_roll(0))
    eng.apply(A.ROLL)
    eng.apply(A.DECLINE)
    from propertyrl.engine import BidLevel

    with pytest.raises(IllegalActionError):
        eng.apply(BidLevel(1))
    with pytest.raises(IllegalActionError):
        eng.apply(Bid(True))  # type: ignore[arg-type]
    eng.apply(Bid(None))
    with pytest.raises(IllegalActionError):
        eng.apply("yes")


def test_trade_response_type_error() -> None:
    eng = scenario().own(1, 6).build()
    eng.apply([TradeOffer(0, 1, give_cash=5, get_props=(6,))])
    with pytest.raises(IllegalActionError):
        eng.apply(1)
    eng.apply(False)


def test_negative_and_uncovered_transfer() -> None:
    eng = new_game(OFFICIAL, 2, seed=1)
    with pytest.raises(RuleViolationError):
        eng.transfer(0, 1, -5, "TEST")
    with pytest.raises(RuleViolationError):
        eng.transfer(0, 1, 10**9, "TEST")
    eng.transfer(0, 1, 0, "TEST")


def test_card_order_option_and_clone_logging() -> None:
    opts = EngineOptions(card_order={"A": ("A16",)}, allow_test_hooks=True)
    eng = Engine.new(rules(), board(), decks(), 2, 3, opts)
    assert eng.state.deck_a[0] == decks().index_of(0, "A16")
    quiet = eng.clone(log_events=False)
    assert not quiet.log and quiet.state_hash() == eng.state_hash()
    assert EngineOptions.from_dict(opts.to_dict()).card_order == {"A": ("A16",)}


def test_invariant_branches() -> None:
    eng = scenario(OFFICIAL, n=3).own_group(0, "BRAUN", 1).bankrupt(2).build()
    st = eng.state
    st.owner[5] = 7
    assert any("invalid owner" in v for v in violations(eng))
    st.owner[5] = 2
    assert any("bankrupt seat" in v for v in violations(eng))
    st.owner[5] = C.BANK
    st.mortgaged[5] = True
    assert any("owned by the bank" in v for v in violations(eng))
    st.mortgaged[5] = False
    st.interest_prepaid[5] = 3
    assert any("interest_prepaid" in v for v in violations(eng))
    st.interest_prepaid[5] = -1
    st.owner[1] = 1
    assert any("incomplete group" in v for v in violations(eng))
    st.owner[1] = 0
    st.position[0] = 41
    assert any("position" in v for v in violations(eng))
    st.position[0] = 0
    st.cash[2] = 5
    st.ledger_in[2] += 5
    assert any("bankrupt seat 2 still" in v for v in violations(eng))
    st.cash[2] = 0
    st.ledger_in[2] -= 5
    st.doubles_count = 3
    assert any("doubles_count" in v for v in violations(eng))
    st.doubles_count = 0
    st.bank_houses = -1
    assert any("negative bank" in v for v in violations(eng))
    st.bank_houses = 30
    st.game_over = True
    assert any("game over with more than one" in v for v in violations(eng))
    st.game_over = False
    st.stack.append((F.OP_ROLL, 0))
    assert any("no pending decision" in v for v in violations(eng))


def test_invariant_single_player_not_over() -> None:
    eng = scenario(OFFICIAL, n=3).bankrupt(2).build()
    eng.state.bankrupt[1] = True
    eng.state.bankruptcy_order.append(1)
    assert any("not over" in v for v in violations(eng))


def test_read_log_without_header(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from propertyrl.engine import SchemaVersionError

    path = tmp_path / "x.jsonl"
    path.write_text('{"type": "decision", "i": 0}\n\n', encoding="utf-8")
    with pytest.raises(SchemaVersionError):
        read_log(path)
    log = new_game(OFFICIAL, 2, seed=1).to_log()
    log["header"]["event_schema_version"] = "e0"
    with pytest.raises(SchemaVersionError):
        check_versions(log)


def test_replay_unknown_kind_and_premature_end() -> None:
    from propertyrl.engine import ReplayMismatchError
    from propertyrl.engine.replay import deserialize_response, replay_log

    with pytest.raises(ReplayMismatchError):
        deserialize_response("FOO", False, 1)
    eng = scenario().own(1, 6).cash(0, 5).position(0, 6).dice((2, 3)).build()
    advance(eng, pre_roll(0))
    eng.apply(A.ROLL)
    log = eng.to_log()
    log["decisions"].append({"i": 99, "seat": 0, "kind": "MAIN", "r": 0})
    with pytest.raises(ReplayMismatchError):
        replay_log(log)
    log = eng.to_log()
    log["decisions"][0]["seat"] = 1
    with pytest.raises(ReplayMismatchError):
        replay_log(log)


def test_scarcity_sealed_no_bids() -> None:
    eng = scenario(RESEARCH).own_group(1, "GRUEN", 4).own_group(1, "GELB", 4).own_group(1, "ORANGE")
    eng = eng.own_group(0, "BRAUN").build()
    advance(eng, pre_roll(0))
    eng.apply(A.build(0))
    from propertyrl.engine import BidLevel

    eng.apply(BidLevel(None))
    eng.apply(BidLevel(None))
    assert eng.state.level[0] == 1
