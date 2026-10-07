"""Board, card and ruleset data (R-001, R-002, R-003, §3.2-§3.4, V-points)."""

from __future__ import annotations

import pytest
from helpers import MOVEMENT, OFFICIAL, RESEARCH, SHORTGAME, board, decks, new_game, rules

from propertyrl.engine import Engine, EngineOptions, RuleViolationError
from propertyrl.engine import constants as C
from propertyrl.engine.board import Board
from propertyrl.engine.cards import Decks
from propertyrl.engine.errors import ConfigError

# Index | price | rents | house price | mortgage (copy of §3.2 for verification)
STREETS = {
    1: (60, (2, 10, 30, 90, 160, 250), 50, 30),
    3: (60, (4, 20, 60, 180, 320, 450), 50, 30),
    6: (100, (6, 30, 90, 270, 400, 550), 50, 50),
    8: (100, (6, 30, 90, 270, 400, 550), 50, 50),
    9: (120, (8, 40, 100, 300, 450, 600), 50, 60),
    11: (140, (10, 50, 150, 450, 625, 750), 100, 70),
    13: (140, (10, 50, 150, 450, 625, 750), 100, 70),
    14: (160, (12, 60, 180, 500, 700, 900), 100, 80),
    16: (180, (14, 70, 200, 550, 750, 950), 100, 90),
    18: (180, (14, 70, 200, 550, 750, 950), 100, 90),
    19: (200, (16, 80, 220, 600, 800, 1000), 100, 100),
    21: (220, (18, 90, 250, 700, 875, 1050), 150, 110),
    23: (220, (18, 90, 250, 700, 875, 1050), 150, 110),
    24: (240, (20, 100, 300, 750, 925, 1100), 150, 120),
    26: (260, (22, 110, 330, 800, 975, 1150), 150, 130),
    27: (260, (22, 110, 330, 800, 975, 1150), 150, 130),
    29: (280, (24, 120, 360, 850, 1025, 1200), 150, 140),
    31: (300, (26, 130, 390, 900, 1100, 1275), 200, 150),
    32: (300, (26, 130, 390, 900, 1100, 1275), 200, 150),
    34: (320, (28, 150, 450, 1000, 1200, 1400), 200, 160),
    37: (350, (35, 175, 500, 1100, 1300, 1500), 200, 175),
    39: (400, (50, 200, 600, 1400, 1700, 2000), 200, 200),
}
KINDS = {0: "START", 2: "CARD_B", 4: "TAX", 5: "RAIL", 7: "CARD_A", 10: "JAIL", 12: "UTIL", 15: "RAIL",
         17: "CARD_B", 20: "REST", 22: "CARD_A", 25: "RAIL", 28: "UTIL", 30: "ARREST", 33: "CARD_B",
         35: "RAIL", 36: "CARD_A", 38: "TAX"}  # fmt: skip
DECK_A = ["ADVANCE_TO 39", "ADVANCE_TO 0", "ADVANCE_TO 24", "ADVANCE_TO 11", "NEAREST_RAIL", "NEAREST_RAIL",
          "NEAREST_UTIL", "COLLECT 50", "JAIL_FREE", "MOVE_BACK 3", "SEND_TO_JAIL", "REPAIRS 25 100",
          "PAY 15", "ADVANCE_TO 5", "PAY_EACH 50", "COLLECT 150"]  # fmt: skip
DECK_B = ["ADVANCE_TO 0", "COLLECT 200", "PAY 50", "COLLECT 50", "JAIL_FREE", "SEND_TO_JAIL", "COLLECT 100",
          "COLLECT 20", "COLLECT_EACH 10", "COLLECT 100", "PAY 100", "PAY 50", "COLLECT 25", "REPAIRS 40 115",
          "COLLECT 10", "COLLECT 100"]  # fmt: skip


@pytest.mark.rule("R-002")
def test_board_matches_spec() -> None:
    bd = board()
    for idx, (price, rents, hp, mv) in STREETS.items():
        sq = bd.squares[idx]
        assert sq.kind == "STREET"
        assert (sq.price, sq.rents, sq.house_price, sq.mortgage_value) == (price, rents, hp, mv)
    for idx, kind in KINDS.items():
        assert bd.squares[idx].kind == kind
    for rail in (5, 15, 25, 35):
        assert bd.squares[rail].price == 200 and bd.squares[rail].rents == (25, 50, 100, 200)
        assert bd.squares[rail].mortgage_value == 100
    for util in (12, 28):
        assert bd.squares[util].price == 150 and bd.squares[util].rents == (4, 10)
        assert bd.squares[util].mortgage_value == 75
    assert bd.squares[4].tax == 200 and bd.squares[38].tax == 100


def test_index_mappings() -> None:
    assert C.PROP_SQUARES == (1, 3, 5, 6, 8, 9, 11, 12, 13, 14, 15, 16, 18, 19, 21, 23, 24, 25, 26, 27, 28,
                              29, 31, 32, 34, 35, 37, 39)  # fmt: skip
    assert C.BUILD_SQUARES == (
        1,
        3,
        6,
        8,
        9,
        11,
        13,
        14,
        16,
        18,
        19,
        21,
        23,
        24,
        26,
        27,
        29,
        31,
        32,
        34,
        37,
        39,
    )
    assert C.GROUP_SQUARES["HELLBLAU"] == (6, 8, 9)
    assert C.GROUP_SQUARES["BAHN"] == (5, 15, 25, 35)
    for b, sq in enumerate(C.BUILD_SQUARES):
        assert C.PROP_SQUARES[C.B_TO_P[b]] == sq
        assert C.P_TO_B[C.B_TO_P[b]] == b


@pytest.mark.rule("R-601")
def test_decks_match_spec() -> None:
    dk = decks()
    for deck, spec in ((dk.a, DECK_A), (dk.b, DECK_B)):
        assert len(deck) == 16
        for card, want in zip(deck, spec, strict=True):
            got = " ".join([card.effect, *map(str, card.params)])
            assert got == want, card.card_id
    assert [c.card_id for c in dk.a] == [f"A{i:02d}" for i in range(1, 17)]
    assert [c.card_id for c in dk.b] == [f"B{i:02d}" for i in range(1, 17)]


def test_verification_points_documented() -> None:
    vp = rules(OFFICIAL).verification_points
    assert set(vp) == {"V1", "V2", "V3", "V4", "V5", "V6"}
    assert decks().b[11].params == (50,)  # V1
    assert board().squares[38].tax == 100  # V2
    assert board().squares[4].tax == 200  # V3
    assert decks().a[12].params == (15,)  # V4


@pytest.mark.rule("R-001")
def test_starting_cash() -> None:
    eng = new_game(OFFICIAL, 4)
    assert eng.state.cash == [1500] * 4
    assert eng.ruleset.starting_cash == 1500


@pytest.mark.rule("R-003")
@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7, 8])
def test_player_count_official(n: int) -> None:
    eng = new_game(OFFICIAL, n)
    assert eng.state.n_players == n


@pytest.mark.rule("R-003")
@pytest.mark.parametrize("n", [1, 9])
def test_player_count_out_of_range(n: int) -> None:
    with pytest.raises(RuleViolationError):
        Engine.new(rules(OFFICIAL), board(), decks(), n, 1, EngineOptions())


@pytest.mark.rule("D-04")
def test_research_is_two_player_only() -> None:
    for rs in (RESEARCH, SHORTGAME, MOVEMENT):
        with pytest.raises(RuleViolationError):
            Engine.new(rules(rs), board(), decks(), 3, 1, EngineOptions())


def test_board_validation_errors() -> None:
    data = board().to_dict()
    data["squares"] = data["squares"][:-1]
    with pytest.raises(ConfigError):
        Board.from_dict(data)
    data = board().to_dict()
    data["squares"][1]["kind"] = "TAX"
    with pytest.raises(ConfigError):
        Board.from_dict(data)
    assert Board.from_dict(board().to_dict()).to_dict() == board().to_dict()


def test_deck_validation_errors() -> None:
    d = decks().to_dict()
    d["a"] = d["a"][:15]
    with pytest.raises(ConfigError):
        Decks.from_dict(d)
    d = decks().to_dict()
    d["b"][0]["effect"] = "JAIL_FREE"
    with pytest.raises(ConfigError):
        Decks.from_dict(d)


def test_test_hooks_require_flag() -> None:
    with pytest.raises(RuleViolationError):
        Engine.new(rules(OFFICIAL), board(), decks(), 2, 1, EngineOptions(dice_script=((1, 2),)))
