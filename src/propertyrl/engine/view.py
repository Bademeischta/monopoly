"""Public, read-only view of the game handed to policies (no deck order, no RNG, no engine)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.ruleset import Ruleset


@dataclass(frozen=True, slots=True)
class PublicState:
    """Everything a player may legitimately know at a decision point."""

    seat: int
    n_players: int
    cash: tuple[int, ...]
    position: tuple[int, ...]
    in_jail: tuple[bool, ...]
    jail_attempts: tuple[int, ...]
    jail_cards: tuple[int, ...]
    bankrupt: tuple[bool, ...]
    bankruptcy_order: tuple[int, ...]
    owner: tuple[int, ...]
    mortgaged: tuple[bool, ...]
    interest_prepaid: tuple[int, ...]
    level: tuple[int, ...]
    bank_houses: int
    bank_hotels: int
    deck_cycle_drawn_a: int
    deck_cycle_drawn_b: int
    active_seat: int
    doubles_count: int
    turn_index: int
    round_index: int
    window_counter: int
    window_actions: tuple[tuple[int, int], ...]
    phase: str
    decision_kind: str
    last_dice: tuple[int, int]
    board: Board
    ruleset: Ruleset
    game_over: bool
    context: dict[str, Any] = field(default_factory=dict)

    def active_players(self) -> list[int]:
        """Seats that are not bankrupt."""
        return [i for i in range(self.n_players) if not self.bankrupt[i]]

    def n_active(self) -> int:
        """Number of active seats."""
        return self.n_players - len(self.bankruptcy_order)
