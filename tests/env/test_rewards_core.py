"""Rewards, SMDP durations, PBRS telescoping, delegation and ablation switches (§6.1-§6.6)."""

from __future__ import annotations

import numpy as np
import pytest
from envhelpers import cfg

from propertyrl.engine import actions as A
from propertyrl.env import EnvConfig, PropertySingleAgentEnv, RewardSpec, terminal_reward
from propertyrl.env.opponents import OpponentConfig
from propertyrl.env.rewards import equity_share, is_hopeless, potential, weighted_level


def _episode(
    env: PropertySingleAgentEnv, seed: int, policy: str = "random"
) -> tuple[float, list[tuple[float, int]], dict]:
    env.reset(seed=seed)
    phi0 = env.core.phi_now[env.core.learning[0]]
    rng = np.random.default_rng(seed)
    out: list[tuple[float, int]] = []
    while True:
        mask = env.action_masks()
        legal = np.flatnonzero(mask)
        a = int(legal[0]) if policy == "first" else int(rng.choice(legal))
        _, r, term, trunc, info = env.step(a)
        out.append((r, info["duration"]))
        if term or trunc:
            return phi0, out, info


@pytest.mark.parametrize("smdp", [True, False])
def test_pbrs_telescoping(smdp: bool) -> None:
    gamma = 0.99
    env = PropertySingleAgentEnv(cfg(gamma=gamma, smdp=smdp, safety_horizon_rounds=10_000))
    checked = 0
    for seed in range(8):
        phi0, steps, info = _episode(env, seed)
        if info["truncated"]:
            continue
        terminal = 1.0 if info["won"] else -1.0
        tau = 0
        total = 0.0
        for i, (r, k) in enumerate(steps):
            shaped = r - (terminal if i == len(steps) - 1 else 0.0)
            total += gamma**tau * shaped
            tau += k
        assert abs(total - (-phi0)) < 1e-6
        checked += 1
    assert checked >= 4


def test_smdp_durations() -> None:
    env = PropertySingleAgentEnv(cfg(smdp=True))
    _, steps, _ = _episode(env, 3)
    assert any(k > 1 for _, k in steps)
    env = PropertySingleAgentEnv(cfg(smdp=False))
    _, steps, _ = _episode(env, 3)
    assert all(k == 1 for _, k in steps)


def test_a0_terminal_only() -> None:
    env = PropertySingleAgentEnv(cfg(reward_variant="A0"))
    _, steps, info = _episode(env, 4)
    assert all(r == 0.0 for r, _ in steps[:-1])
    if not info["truncated"]:
        assert steps[-1][0] in (1.0, -1.0)


def test_a2_level_reward() -> None:
    env = PropertySingleAgentEnv(cfg(reward_variant="A2", beta2=0.01))
    _, steps, _ = _episode(env, 4)
    assert all(abs(r) <= 0.01 for r, _ in steps[:-1])
    assert any(r != 0.0 for r, _ in steps[:-1])


def test_a3_kingmaking_malus_4p() -> None:
    env = PropertySingleAgentEnv(cfg(n_players=4, reward_variant="A3", kingmaking_malus=0.1))
    _, steps, _ = _episode(env, 5)
    assert steps


def test_terminal_rewards() -> None:
    assert terminal_reward(2, 1, 0, 0, (1, 0.3, -0.3, -1)) == 1.0
    assert terminal_reward(2, 2, 0, 1, (1, 0.3, -0.3, -1)) == -1.0
    assert terminal_reward(2, 1, None, 1, (1, 0.3, -0.3, -1)) == 0.0
    assert terminal_reward(4, 2, None, 1, (1.0, 1 / 3, -1 / 3, -1.0)) == pytest.approx(1 / 3)
    spec = RewardSpec("A1", gamma=0.9, smdp=True)
    assert spec.discount(2) == pytest.approx(0.81)
    assert RewardSpec("A1", gamma=0.9, smdp=False).discount(5) == pytest.approx(0.9)
    with pytest.raises(ValueError):
        RewardSpec("A9")


def test_potential_and_helpers() -> None:
    from helpers import scenario

    eng = scenario().own_group(0, "BRAUN", 1).cash(1, 100).build()
    share, n = equity_share(eng.state, eng.board, 0)
    assert n == 2 and share > 0.5
    assert potential(eng.state, eng.board, 0, 1.0) == pytest.approx(share - 0.5)
    assert weighted_level(eng.state, eng.board, 0) > 0
    assert is_hopeless(eng.state, eng.board, 1)
    assert not is_hopeless(eng.state, eng.board, 0)


def test_delegated_kinds_never_reach_the_agent() -> None:
    env = PropertySingleAgentEnv(cfg())
    env.reset(seed=6)
    for _ in range(3000):
        d = env.core.engine.pending()
        assert d is not None and d.kind in ("MAIN",) and d.seat == env.core.learning[0]
        mask = env.action_masks()
        assert mask.sum() >= 2  # auto-skip: only genuine decisions are presented
        _, _, term, trunc, _ = env.step(int(np.flatnonzero(mask)[-1]))
        if term or trunc:
            env.reset()


def test_debt_not_delegated_reaches_agent() -> None:
    env = PropertySingleAgentEnv(cfg(delegated_kinds=("TRADE_OFFER", "TRADE_RESPONSE", "AUCTION_BID")))
    kinds = set()
    env.reset(seed=8)
    for _ in range(20000):
        kinds.add(env.core.engine.pending().kind)  # type: ignore[union-attr]
        _, _, term, trunc, _ = env.step(env.action_space.sample())
        if term or trunc:
            env.reset()
    assert "DEBT" in kinds


def test_n4_buy_delegated() -> None:
    env = PropertySingleAgentEnv(
        cfg(delegated_kinds=("TRADE_OFFER", "TRADE_RESPONSE", "AUCTION_BID", "DEBT", "MAIN_BUY"))
    )
    env.reset(seed=9)
    for _ in range(3000):
        assert env.core.engine.pending().phase != "BUY"  # type: ignore[union-attr]
        _, _, term, trunc, _ = env.step(env.action_space.sample())
        if term or trunc:
            env.reset()


def test_no_trade_ablation() -> None:
    env = PropertySingleAgentEnv(
        cfg(
            trade_enabled=False,
            log_events=True,
            opponents=OpponentConfig(mode="fixed", fixed=("strong_a_v1",)),
        )
    )
    env.reset(seed=10)
    offers = 0
    for _ in range(4000):
        offers += sum(1 for e in env.core.engine.events if e.type == "TRADE_OFFERED")
        _, _, term, trunc, _ = env.step(env.action_space.sample())
        if term or trunc:
            env.reset()
    assert offers == 0


def test_safety_horizon_truncates_with_terminal_observation() -> None:
    env = PropertySingleAgentEnv(cfg(safety_horizon_rounds=3))
    env.reset(seed=12)
    while True:
        obs, r, term, trunc, info = env.step(int(np.flatnonzero(env.action_masks())[0]))
        if term or trunc:
            break
    assert trunc and not term and info["truncated"] and obs.shape == (517,)
    assert env.core.engine.state.round_index >= 3 and not env.core.engine.is_over()


def test_episode_info_fields() -> None:
    env = PropertySingleAgentEnv(cfg())
    _, _, info = _episode(env, 13)
    for key in ("winner", "placement", "rounds", "decisions", "truncated", "final_equity_share", "opponent_ids",
                "counters"):  # fmt: skip
        assert key in info
    assert set(info["counters"]) >= {
        "purchases",
        "builds",
        "mortgages",
        "trades",
        "jail_stay",
        "jail_balance",
    }


def test_env_config_roundtrip() -> None:
    c = cfg(n_players=3, reward_variant="A2")
    assert EnvConfig.from_dict(c.to_dict()) == c
    with pytest.raises(ValueError):
        EnvConfig(n_players=5)
    assert "AUCTION_BID" in EnvConfig(delegated_kinds=("DEBT",)).delegated_kinds
    assert A.N_ACTIONS == 106
