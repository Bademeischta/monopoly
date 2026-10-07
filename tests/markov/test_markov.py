"""Markov chains (§4.11) and the empirical comparison in TEST_MOVEMENT_ONLY (A-11, CI: 1 Mio., 0.15 pp)."""

from __future__ import annotations

import os

import pytest
from helpers import MOVEMENT, board, decks, rules

from propertyrl.engine import constants as C
from propertyrl.engine import markov

CI_MOVES = int(os.environ.get("PROPERTYRL_MARKOV_MOVES", "1000000"))


def test_exact_chain_is_stochastic() -> None:
    m = markov.exact_chain()
    assert len(m) == 120
    for row in m:
        assert abs(sum(row) - 1.0) < 1e-12


def test_exact_stationary_gauss_vs_power() -> None:
    a = markov.exact_square_frequencies("gauss")
    b = markov.exact_square_frequencies("power")
    assert abs(sum(a) - 1.0) < 1e-12
    assert a[C.ARREST_SQUARE] == 0.0
    assert max(abs(x - y) for x, y in zip(a, b, strict=True)) < 1e-10
    # Jail is the most frequent rest square of the reduced configuration.
    assert max(range(40), key=lambda i: a[i]) == C.JAIL_SQUARE


def test_approximate_chain_properties() -> None:
    leave = markov.landing_frequencies(decks(), markov.JAIL_LEAVE)
    stay = markov.landing_frequencies(decks(), markov.JAIL_STAY)
    assert 1.1 < sum(leave) < 1.25
    assert stay[C.JAIL_SQUARE] > leave[C.JAIL_SQUARE]
    assert leave[C.ARREST_SQUARE] == 0.0
    # Movement cards concentrate rests on START and their targets.
    assert leave[0] > leave[1]


@pytest.mark.rule("R-101")
@pytest.mark.rule("R-104")
def test_engine_matches_exact_chain() -> None:
    result = markov.markov_check(rules(MOVEMENT), board(), decks(), CI_MOVES, 0.15, seed=1)
    assert result["moves"] >= CI_MOVES
    assert result["passed"], result["max_abs_diff_pp"]


def test_requires_movement_ruleset() -> None:
    with pytest.raises(ValueError):
        markov.simulate_rest_frequencies(rules(), board(), decks(), 10)


def test_long_samples_span_several_games(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Samples larger than the per-game watchdog continue in fresh games instead of tripping it (P-16)."""
    from propertyrl.engine import constants as C
    from propertyrl.engine.markov import simulate_rest_frequencies
    from propertyrl.infra.config import load_setup

    monkeypatch.setattr(C, "WATCHDOG_GAME_DECISIONS", 6000)
    rules, board, decks = load_setup("TEST_MOVEMENT_ONLY", 2)
    freq, total = simulate_rest_frequencies(rules, board, decks, 20_000, seed=3)
    assert total >= 20_000
    assert abs(sum(freq) - 1.0) < 1e-9
