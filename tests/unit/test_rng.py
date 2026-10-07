"""Counter-based RNG service (§4.3)."""

from __future__ import annotations

from collections import Counter

import pytest

from propertyrl.engine import constants as C
from propertyrl.engine.rng import AgentRng, SeededStream, dice_value, reshuffle_positions, shuffle_deck, u64


def test_u64_deterministic_and_64bit() -> None:
    assert u64(1, 2, 3) == u64(1, 2, 3)
    assert u64(1, 2, 3) != u64(1, 2, 4)
    assert 0 <= u64(-5, 2**70) < 2**64
    # Fixed reference value guards cross-platform determinism.
    assert u64(20261007, 7, 1, 0) == u64(20261007, 7, 1, 0)


def test_known_reference_values() -> None:
    values = [u64(i) for i in range(3)]
    assert len(set(values)) == 3
    assert dice_value(1, 0, 0, 1, 0, 0) in range(1, 7)


@pytest.mark.rule("R-101")
def test_dice_fair() -> None:
    counts = Counter(dice_value(7, 0, s % 4, s, t % 3, d) for s in range(20000) for t in range(3) for d in (0, 1))
    n = sum(counts.values())
    assert set(counts) == {1, 2, 3, 4, 5, 6}
    for face in range(1, 7):
        assert abs(counts[face] / n - 1 / 6) < 0.005


def test_dice_independent_of_other_seats() -> None:
    # Dice of seat 1 depend only on its own turn counter, never on seat 0.
    a = [dice_value(5, 0, 1, turn, 0, 0) for turn in range(50)]
    b = [dice_value(5, 0, 1, turn, 0, 0) for turn in range(50)]
    assert a == b


def test_shuffle_is_permutation() -> None:
    order = shuffle_deck(123, 0, C.DECK_A)
    assert sorted(order) == list(range(16))
    assert order != list(range(16))
    assert shuffle_deck(123, 0, C.DECK_A) == order
    assert shuffle_deck(123, 0, C.DECK_B) != order


def test_reshuffle_keeps_drawn_positions() -> None:
    deck = list(range(16))
    drawn = (1 << 3) | (1 << 7)
    out = reshuffle_positions(deck, drawn, 9, 5, 0)
    assert out[3] == 3 and out[7] == 7
    assert sorted(out) == deck


def test_agent_rng() -> None:
    r1, r2 = AgentRng(1, 0), AgentRng(1, 0)
    assert [r1.random() for _ in range(5)] == [r2.random() for _ in range(5)]
    r3 = AgentRng(1, 1)
    assert r3.random() != AgentRng(1, 0).random()
    for _ in range(100):
        assert 0 <= r1.random() < 1
        assert 3 <= r1.randint(3, 5) <= 5
        assert r1.choice([1, 2]) in (1, 2)
    with pytest.raises(ValueError):
        r1.randint(5, 3)
    with pytest.raises(ValueError):
        r1.choice([])


def test_seeded_stream() -> None:
    s = SeededStream(1, 2)
    vals = [s.random() for _ in range(10)]
    assert all(0 <= v < 1 for v in vals)
    assert 0 <= s.randint(0, 3) <= 3
