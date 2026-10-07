"""Compact text rendering of a game state (CLI play/replay)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.state import GameState


def render_text(state: GameState, board: Board) -> str:
    """Render players, cash, positions, holdings, levels, mortgages and bank stock."""
    lines = [
        f"Runde {state.round_index + 1} | Zug {state.turn_index} | aktiver Sitz {state.active_seat} | "
        f"Bank: {state.bank_houses} Haeuser, {state.bank_hotels} Hotels",
    ]
    for s in range(state.n_players):
        if state.bankrupt[s]:
            lines.append(f"  Sitz {s}: bankrott")
            continue
        flags = []
        if state.in_jail[s]:
            flags.append(f"Haft({state.jail_attempts[s]})")
        if state.jail_cards[s]:
            flags.append(f"Freikarten={state.jail_cards[s]}")
        pos = state.position[s]
        lines.append(f"  Sitz {s}: Bargeld {state.cash[s]:>6} | Feld {pos:>2} {board.name(pos):<14} {' '.join(flags)}")
        holdings = []
        for p in range(C.N_PROPS):
            if state.owner[p] != s:
                continue
            tag = board.prop_name(p)
            b = C.P_TO_B[p]
            if b >= 0 and state.level[b]:
                tag += "[H]" if state.level[b] == C.HOTEL_LEVEL else f"[{state.level[b]}]"
            if state.mortgaged[p]:
                tag += "(B)"
            holdings.append(tag)
        if holdings:
            lines.append("      " + ", ".join(holdings))
    if state.game_over:
        lines.append(f"  Spielende: Sieger {state.winner if state.winner >= 0 else 'Remis'}")
    return "\n".join(lines)
