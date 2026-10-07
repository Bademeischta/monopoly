"""Rewards (§6.6): terminal utility, PBRS (A1), terminal-only (A0), Purdue-like level reward (A2),
PBRS plus kingmaking malus (A3, 4P only)."""

from __future__ import annotations

from dataclasses import dataclass

from propertyrl.engine.board import Board
from propertyrl.engine.equity import canonical_equity, weighted_equity
from propertyrl.engine.state import GameState

VARIANTS = ("A0", "A1", "A2", "A3")


def equity_share(state: GameState, board: Board, seat: int) -> tuple[float, int]:
    """(E_i / sum E of the active players, N_active); 1/N_active if the sum is 0."""
    active = [s for s in range(state.n_players) if not state.bankrupt[s]]
    n_active = len(active)
    if seat not in active or n_active == 0:
        return 0.0, max(1, n_active)
    total = sum(canonical_equity(state, board, s) for s in active)
    if total <= 0:
        return 1.0 / n_active, n_active
    return canonical_equity(state, board, seat) / total, n_active


def potential(state: GameState, board: Board, seat: int, beta: float) -> float:
    """Phi_i(s) = beta * (E_i / sum E - 1 / N_active); 0 at terminal states (handled by callers)."""
    share, n_active = equity_share(state, board, seat)
    return beta * (share - 1.0 / n_active)


def weighted_level(state: GameState, board: Board, seat: int) -> float:
    """Ew_i / sum Ew - 1 / N_active (A2)."""
    active = [s for s in range(state.n_players) if not state.bankrupt[s]]
    if seat not in active:
        return 0.0
    total = sum(weighted_equity(state, board, s) for s in active)
    share = weighted_equity(state, board, seat) / total if total > 0 else 1.0 / len(active)
    return share - 1.0 / len(active)


def terminal_reward(
    n_players: int, placement: int, winner: int | None, seat: int, table_4p: tuple[float, ...]
) -> float:
    """2P: +1 win, -1 loss, 0 draw. More players: placement utility (default +1, +1/3, -1/3, -1)."""
    if n_players == 2:
        if winner is None:
            return 0.0
        return 1.0 if winner == seat else -1.0
    idx = min(max(placement, 1), len(table_4p)) - 1
    return float(table_4p[idx])


def is_hopeless(state: GameState, board: Board, seat: int) -> bool:
    """A3 proxy for 'no realistic chance': last by equity and share < 0.5 x the leader's share."""
    active = [s for s in range(state.n_players) if not state.bankrupt[s]]
    if seat not in active or len(active) < 2:
        return False
    eq = {s: canonical_equity(state, board, s) for s in active}
    total = sum(eq.values())
    if total <= 0:
        return False
    if eq[seat] > min(eq.values()):
        return False
    return eq[seat] / total < 0.5 * max(eq.values()) / total


@dataclass(frozen=True)
class RewardSpec:
    """Reward configuration of one environment."""

    variant: str = "A1"
    gamma: float = 0.995
    beta: float = 1.0
    beta2: float = 0.01
    kingmaking_malus: float = 0.1
    smdp: bool = True
    terminal_4p: tuple[float, ...] = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)

    def __post_init__(self) -> None:
        if self.variant not in VARIANTS:
            raise ValueError(f"unknown reward variant {self.variant}")

    def discount(self, duration: int) -> float:
        """gamma**k with SMDP, gamma otherwise (ablation without SMDP: k = 1)."""
        return self.gamma ** (duration if self.smdp else 1)

    def transition_reward(
        self,
        terminal: float,
        terminated: bool,
        phi_start: float,
        phi_end: float,
        duration: int,
        level_end: float,
        extra: float,
    ) -> float:
        """Reward of one macro step for a learning seat (phi_end ignored when terminated)."""
        if self.variant == "A0":
            return terminal
        if self.variant == "A2":
            return terminal + (0.0 if terminated else self.beta2 * level_end)
        phi_next = 0.0 if terminated else phi_end
        shaped = terminal + self.discount(duration) * phi_next - phi_start
        if self.variant == "A3":
            shaped += extra
        return shaped
