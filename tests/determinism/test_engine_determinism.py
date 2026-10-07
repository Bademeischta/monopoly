"""Engine determinism and the duplicate property of the dice (§4.3, §10)."""

from __future__ import annotations

from helpers import OFFICIAL, events_of, new_game

from propertyrl.engine.rng import AgentRng
from propertyrl.infra.fuzz import random_response


def _dice_by_key(seed: int, policy_seed: int) -> dict[tuple[int, int, int], list[int]]:
    eng = new_game(OFFICIAL, 2, seed=seed, check_invariants=False)
    rng = AgentRng(policy_seed, 3)
    for _ in range(1500):
        if eng.is_over():
            break
        eng.apply(random_response(eng, rng))
    return {(e.seat, e.data["turn"], e.data["throw"]): e.data["dice"] for e in events_of(eng, "DICE_ROLLED")}


def test_dice_independent_of_decisions() -> None:
    a = _dice_by_key(2024, 1)
    b = _dice_by_key(2024, 2)
    common = set(a) & set(b)
    assert len(common) > 50
    assert all(a[k] == b[k] for k in common)


def test_same_seed_same_policy_same_hash() -> None:
    def play() -> str:
        eng = new_game(OFFICIAL, 4, seed=77, check_invariants=False)
        rng = AgentRng(77, 3)
        for _ in range(2000):
            if eng.is_over():
                break
            eng.apply(random_response(eng, rng))
        return eng.state_hash()

    assert play() == play()
