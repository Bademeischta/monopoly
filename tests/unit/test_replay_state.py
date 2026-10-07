"""State copy/hash, clone, replay, logs and invariants (§4.2, §4.7, §4.8, §4.10)."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import OFFICIAL, RESEARCH, new_game, passive_response, scenario

from propertyrl.engine import (
    Engine,
    InvariantError,
    ReplayMismatchError,
    SchemaVersionError,
    read_log,
    render_text,
    write_log,
)
from propertyrl.engine import actions as A
from propertyrl.engine.invariants import check_invariants, violations
from propertyrl.engine.rng import AgentRng


def _random_game(ruleset: str = OFFICIAL, n: int = 2, seed: int = 4, steps: int = 400, **opts: object) -> Engine:
    from fuzz_driver import random_response

    eng = new_game(ruleset, n, seed=seed, **opts)
    rng = AgentRng(seed, 99)
    for _ in range(steps):
        if eng.is_over():
            break
        eng.apply(random_response(eng, rng))
    return eng


def test_copy_is_independent() -> None:
    eng = _random_game(steps=100)
    st = eng.state
    cp = st.copy()
    assert cp.state_hash() == st.state_hash()
    cp.cash[0] += 1
    cp.stack.append((99,))
    assert cp.state_hash() != st.state_hash()
    assert st.to_canonical_dict()["cash"] != cp.to_canonical_dict()["cash"]


def test_same_seed_same_decisions_same_hash() -> None:
    a = _random_game(seed=8)
    b = _random_game(seed=8)
    assert a.state_hash() == b.state_hash()
    c = _random_game(seed=9)
    assert c.state_hash() != a.state_hash()


def test_hash_independent_of_logging() -> None:
    a = _random_game(seed=8, log_events=True)
    b = _random_game(seed=8, log_events=False)
    assert a.state_hash() == b.state_hash()
    assert not b.events and a.events


def test_replay_roundtrip(tmp_path: Path) -> None:
    eng = _random_game(seed=12, steps=600, hash_interval=7)
    log = eng.to_log()
    path = tmp_path / "game.jsonl"
    write_log(log, path)
    loaded = read_log(path)
    replayed = Engine.replay(loaded)
    assert replayed.state_hash() == eng.state_hash()


def test_replay_research_and_events(tmp_path: Path) -> None:
    eng = _random_game(RESEARCH, seed=3, steps=500)
    from propertyrl.engine.replay import replay_log

    replayed = replay_log(eng.to_log(), check_events=True)
    assert replayed.state_hash() == eng.state_hash()


def test_replay_mismatch_detected() -> None:
    eng = _random_game(seed=12, steps=300, hash_interval=1)
    log = eng.to_log()
    # Corrupt one recorded hash.
    log["decisions"][50]["h"] = "0" * 64
    with pytest.raises(ReplayMismatchError) as info:
        Engine.replay(log)
    assert info.value.decision_index == 50
    log = eng.to_log()
    log["header"]["final_state_hash"] = "f" * 64
    for entry in log["decisions"]:
        entry.pop("h", None)
    with pytest.raises(ReplayMismatchError):
        Engine.replay(log)
    log = eng.to_log()
    main = next(e for e in log["decisions"] if e["kind"] == "MAIN")
    main["r"] = 105
    with pytest.raises(ReplayMismatchError):
        Engine.replay(log)


def test_schema_version_checked() -> None:
    log = _random_game(steps=20).to_log()
    log["header"]["engine_version"] = "0.0.0"
    with pytest.raises(SchemaVersionError):
        Engine.replay(log)
    log["header"]["engine_version"] = log["header"]["engine_version"]
    log = _random_game(steps=20).to_log()
    log["header"]["log_schema_version"] = "l0"
    with pytest.raises(SchemaVersionError):
        Engine.replay(log)


def test_clone_without_reseed_continues_identically() -> None:
    from fuzz_driver import random_response

    eng = _random_game(seed=21, steps=200)
    twin = eng.clone()
    r1, r2 = AgentRng(5, 5), AgentRng(5, 5)
    for _ in range(200):
        if eng.is_over():
            break
        eng.apply(random_response(eng, r1))
        twin.apply(random_response(twin, r2))
    assert eng.state_hash() == twin.state_hash()


def test_clone_with_reseed_changes_dice_keeps_public_cards() -> None:
    eng = _random_game(seed=21, steps=200)
    twin = eng.clone(reseed=777)
    st, ts = eng.state, twin.state
    assert ts.rng_epoch == 777 and st.rng_epoch == 0
    for deck, tdeck, mask in (
        (st.deck_a, ts.deck_a, st.deck_cycle_drawn_a),
        (st.deck_b, ts.deck_b, st.deck_cycle_drawn_b),
    ):
        assert sorted(deck) == sorted(tdeck)
        for i, card in enumerate(deck):
            if (mask >> card) & 1:
                assert tdeck[i] == card
    twin.state.cash[0] += 0
    assert twin.state.cash == st.cash


def test_public_view_hides_secrets() -> None:
    eng = _random_game(steps=50)
    view = eng.public_view(0)
    assert not hasattr(view, "deck_a") and not hasattr(view, "game_seed") and not hasattr(view, "rng_epoch")
    with pytest.raises(AttributeError):
        view.cash = (0,)  # type: ignore[misc]


def test_invariant_violations_detected() -> None:
    eng = scenario().own_group(0, "BRAUN").level(0, 1).build()
    check_invariants(eng)
    eng.state.level[1] = 3
    eng.state.bank_houses -= 3
    assert any("uneven" in v for v in violations(eng))
    with pytest.raises(InvariantError) as info:
        check_invariants(eng)
    assert info.value.game_log is not None
    eng.state.level[1] = 0
    eng.state.bank_houses += 3
    eng.state.cash[0] -= 1
    assert any("ledger" in v for v in violations(eng))
    eng.state.cash[0] = -5
    assert any("negative cash" in v for v in violations(eng))
    eng.state.cash[0] = 1500
    eng.state.deck_a.pop()
    assert any("deck 0" in v for v in violations(eng))


def test_invariants_bank_stock_and_mortgage_in_built_group() -> None:
    eng = scenario().own_group(0, "BRAUN").level(0, 1).build()
    eng.state.bank_hotels = 11
    assert any("hotels" in v for v in violations(eng))
    eng.state.bank_hotels = 12
    eng.state.mortgaged[1] = True
    assert any("mortgage in built group" in v for v in violations(eng))


def test_render_text() -> None:
    eng = (
        scenario(OFFICIAL, n=3)
        .own_group(0, "BRAUN")
        .level(0, 5)
        .level(1, 4)
        .own(1, 2, mortgaged=True)
        .jail(2)
        .bankrupt(2)
        .build()
    )
    text = render_text(eng.state, eng.board)
    assert "Braun-1[H]" in text and "Bahn-1(B)" in text and "bankrott" in text


def test_legal_mask_and_result_api() -> None:
    eng = new_game(OFFICIAL, 2, seed=1)
    eng.apply([])
    mask = eng.legal_mask()
    assert len(mask) == 106 and mask[A.ROLL]
    res = eng.result()
    assert res.winner is None and res.decisions == 1
    while not eng.is_over() and eng.state.decision_index < 200:
        eng.apply(passive_response(eng))
    assert eng.legal_mask() == mask or len(eng.legal_mask()) == 106
