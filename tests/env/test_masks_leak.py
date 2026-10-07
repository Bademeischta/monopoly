"""Mask test (CI 100,000 masked random steps, gate 1,000,000) and observation leak test (§6.4, G2)."""

from __future__ import annotations

import os

import numpy as np
from envhelpers import cfg
from helpers import OFFICIAL, scenario

from propertyrl.engine import constants as C
from propertyrl.env import PropertySingleAgentEnv, encode
from propertyrl.env.opponents import OpponentConfig

MASK_STEPS = int(os.environ.get("PROPERTYRL_MASK_STEPS", "100000"))


def test_masked_random_steps_never_illegal() -> None:
    configs = [
        cfg(n_players=2, opponents=OpponentConfig(mode="fixed", fixed=("random_legal",), epsilon=0.0)),
        cfg(n_players=4, opponents=OpponentConfig(mode="fixed", fixed=("strong_b_v1", "random_legal"))),
        cfg(ruleset="RESEARCH_2P_BOUNDED_V1"),
    ]
    rng = np.random.default_rng(0)
    steps = 0
    illegal = 0
    k = 0
    while steps < MASK_STEPS:
        env = PropertySingleAgentEnv(configs[k % len(configs)], rank=k)
        env.reset(seed=1000 + k)
        k += 1
        for _ in range(MASK_STEPS // 6 + 1):
            mask = env.action_masks()
            assert mask.any()
            action = int(rng.choice(np.flatnonzero(mask)))
            _, _, term, trunc, info = env.step(action)
            illegal += info["illegal_actions"]
            steps += 1
            if term or trunc:
                env.reset()
            if steps >= MASK_STEPS:
                break
    assert illegal == 0 and steps >= MASK_STEPS


def test_illegal_action_raises() -> None:
    import pytest

    from propertyrl.engine import IllegalActionError

    env = PropertySingleAgentEnv(cfg())
    env.reset(seed=1)
    mask = env.action_masks()
    bad = int(np.flatnonzero(~mask)[0])
    with pytest.raises(IllegalActionError):
        env.step(bad)


def test_observation_does_not_leak_hidden_information() -> None:
    eng = scenario(OFFICIAL, n=3).own_group(0, "BRAUN", 2).build()
    for _ in range(3):
        eng.apply(eng.pending().legal_actions()[0] if eng.pending().legal else [])  # type: ignore[union-attr]
    st = eng.state
    base = [encode(st, eng.board, eng.ruleset, s, "PRE_ROLL") for s in range(3)]
    other = st.copy()
    other.rng_epoch = 99
    other.game_seed = 12345
    undrawn = [i for i, c in enumerate(other.deck_a) if not (other.deck_cycle_drawn_a >> c) & 1]
    cards = [other.deck_a[i] for i in undrawn]
    for i, c in zip(undrawn, reversed(cards), strict=True):
        other.deck_a[i] = c
    other.deck_b = list(reversed(other.deck_b))
    for s in range(3):
        assert np.array_equal(base[s], encode(other, eng.board, eng.ruleset, s, "PRE_ROLL"))
    # The drawn-card mask is public and does change the observation.
    other.deck_cycle_drawn_a ^= 1
    assert not np.array_equal(base[0], encode(other, eng.board, eng.ruleset, 0, "PRE_ROLL"))
    assert C.DECK_SIZE == 16
