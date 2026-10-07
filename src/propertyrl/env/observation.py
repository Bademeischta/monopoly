"""Ego-centric observation encoder (§6.4): 517 float32 features in [0, 1], obs_version o1.0+hash.

Slot 0 is the observing seat, slots 1-3 the opponents in turn order starting at the next seat.
The schema is a list of named blocks; the dimension is computed, never hard-coded.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from propertyrl.engine import constants as C
from propertyrl.engine.board import Board
from propertyrl.engine.decisions import PHASE_INDEX, PHASES
from propertyrl.engine.equity import canonical_equity, liquidation_value
from propertyrl.engine.hashing import sha256_hex
from propertyrl.engine.rent import rent_now
from propertyrl.engine.ruleset import Ruleset
from propertyrl.engine.state import GameState
from propertyrl.versions import OBS_VERSION_BASE

MAX_SLOTS = 4
CASH_LOG_SCALE = 30000.0
RENT_SCALE = 2000.0
JAIL_ATTEMPT_SCALE = 3.0
JAIL_CARD_SCALE = 2.0
LEVEL_SCALE = 5.0
DOUBLES_SCALE = 2.0
PROP_FEATURES = 10
PLAYER_FEATURES = 47
NORMALIZATION = {
    "cash_log_scale": CASH_LOG_SCALE,
    "rent_scale": RENT_SCALE,
    "jail_attempt_scale": JAIL_ATTEMPT_SCALE,
    "jail_card_scale": JAIL_CARD_SCALE,
    "level_scale": LEVEL_SCALE,
    "doubles_scale": DOUBLES_SCALE,
    "bank_houses_scale": 32,
    "bank_hotels_scale": 12,
    "active_players_scale": MAX_SLOTS,
}
_LOG_CASH = math.log1p(CASH_LOG_SCALE)


def _blocks() -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    pos = 0

    def add(name: str, size: int, description: str, normalization: str) -> None:
        nonlocal pos
        blocks.append(
            {
                "name": name,
                "start": pos,
                "stop": pos + size,
                "description": description,
                "normalization": normalization,
            }
        )
        pos += size

    for p in range(C.N_PROPS):
        add(
            f"property_p{p:02d}",
            PROP_FEATURES,
            f"Besitzrecht p{p} (Feld {C.PROP_SQUARES[p]}): Besitzer one-hot 5 (Bank, ich, Gegner 1-3), belastet, "
            "Stufe/5, Besitzer hält ganze Gruppe, rent_now/2000, interest_prepaid aktiv",
            "one-hot; 0/1; level/5 (Bahn/Werk 0); 0/1; min(1, Miete/2000), Bank/belastet 0; 0/1",
        )
    for k in range(MAX_SLOTS):
        add(
            f"player_slot{k}",
            PLAYER_FEATURES,
            f"Spieler-Slot {k} ({'ich' if k == 0 else f'Gegner {k}'}): aktiv, Bargeld, Position one-hot 40, in Haft, "
            "Haftversuche/3, Freikarten/2, Equity-Anteil, Liquidationswert",
            "0/1; min(1, log1p(cash)/log1p(30000)); one-hot; 0/1; /3; /2; E_i/Summe E der Aktiven; "
            "min(1, log1p(L)/log1p(30000))",
        )
    add("phase", len(PHASES), "Phase one-hot: " + ", ".join(PHASES), "one-hot")
    add("active_seat_rel", MAX_SLOTS, "aktiver Sitz relativ zum Beobachter one-hot", "one-hot")
    add("doubles_count", 1, "Pasch-Zähler des aktiven Spielers", "/2")
    add("bank_houses", 1, "Bankhäuser", "/32")
    add("bank_hotels", 1, "Bankhotels", "/12")
    add("active_players", 1, "aktive Spieler", "/4")
    add("is_short_game", 1, "Kurzspiel-Variante (D-06)", "0/1")
    add("remaining_rounds", 1, "verbleibende Runden / max_rounds (nur Kurzspiel, sonst 0)", "[0, 1]")
    add("deck_a_drawn", C.DECK_SIZE, "im aktuellen Zyklus gezogene Karten Deck A (Bit je Kartenindex)", "0/1")
    add("deck_b_drawn", C.DECK_SIZE, "im aktuellen Zyklus gezogene Karten Deck B (Bit je Kartenindex)", "0/1")
    return blocks


SCHEMA = _blocks()
OBS_DIM = SCHEMA[-1]["stop"]
OBS_VERSION = f"{OBS_VERSION_BASE}+{sha256_hex({'schema': SCHEMA, 'norm': NORMALIZATION})[:12]}"
_OFF = {b["name"]: b["start"] for b in SCHEMA}
_PROP0 = _OFF["property_p00"]
_SLOT0 = _OFF["player_slot0"]
_PHASE = _OFF["phase"]
_ACTIVE_REL = _OFF["active_seat_rel"]
_DOUBLES = _OFF["doubles_count"]
_HOUSES = _OFF["bank_houses"]
_HOTELS = _OFF["bank_hotels"]
_ACTIVE = _OFF["active_players"]
_SHORT = _OFF["is_short_game"]
_REMAINING = _OFF["remaining_rounds"]
_DECK_A = _OFF["deck_a_drawn"]
_DECK_B = _OFF["deck_b_drawn"]


def obs_schema() -> list[dict[str, Any]]:
    """Named blocks with slice, description and normalisation."""
    return [dict(b) for b in SCHEMA]


def slot_order(seat: int, n_players: int) -> list[int]:
    """Seats in slot order: observer first, then opponents in turn order (at most 4 slots)."""
    return [(seat + k) % n_players for k in range(min(n_players, MAX_SLOTS))]


def encode(state: GameState, board: Board, ruleset: Ruleset, seat: int, phase: str) -> np.ndarray:
    """Encode ``state`` from the perspective of ``seat`` at a decision of ``phase``."""
    obs = np.zeros(OBS_DIM, dtype=np.float32)
    n = state.n_players
    slots = slot_order(seat, n)
    rel = {s: k for k, s in enumerate(slots)}
    owner = state.owner
    # Properties.
    for p in range(C.N_PROPS):
        base = _PROP0 + p * PROP_FEATURES
        o = owner[p]
        if o < 0:
            obs[base] = 1.0
        elif o in rel:
            obs[base + 1 + rel[o]] = 1.0
        if state.mortgaged[p]:
            obs[base + 5] = 1.0
        b = C.P_TO_B[p]
        if b >= 0:
            obs[base + 6] = state.level[b] / LEVEL_SCALE
        if o >= 0:
            group = C.GROUP_PROPS[C.P_GROUP[p]]
            if all(owner[q] == o for q in group):
                obs[base + 7] = 1.0
            if not state.mortgaged[p]:
                obs[base + 8] = min(1.0, rent_now(state, board, p) / RENT_SCALE)
        if state.interest_prepaid[p] >= 0:
            obs[base + 9] = 1.0
    # Players.
    equities = [canonical_equity(state, board, s) for s in range(n)]
    total = sum(equities[s] for s in range(n) if not state.bankrupt[s])
    for k, s in enumerate(slots):
        if state.bankrupt[s]:
            continue
        base = _SLOT0 + k * PLAYER_FEATURES
        obs[base] = 1.0
        obs[base + 1] = min(1.0, math.log1p(state.cash[s]) / _LOG_CASH)
        obs[base + 2 + state.position[s]] = 1.0
        obs[base + 42] = 1.0 if state.in_jail[s] else 0.0
        obs[base + 43] = state.jail_attempts[s] / JAIL_ATTEMPT_SCALE
        obs[base + 44] = bin(state.jail_cards[s]).count("1") / JAIL_CARD_SCALE
        obs[base + 45] = equities[s] / total if total > 0 else 0.0
        obs[base + 46] = min(1.0, math.log1p(liquidation_value(state, board, s)) / _LOG_CASH)
    # Global.
    if phase in PHASE_INDEX:
        obs[_PHASE + PHASE_INDEX[phase]] = 1.0
    if state.active_seat in rel:
        obs[_ACTIVE_REL + rel[state.active_seat]] = 1.0
    obs[_DOUBLES] = state.doubles_count / DOUBLES_SCALE
    obs[_HOUSES] = state.bank_houses / ruleset.bank_houses if ruleset.bank_houses else 0.0
    obs[_HOTELS] = state.bank_hotels / ruleset.bank_hotels if ruleset.bank_hotels else 0.0
    obs[_ACTIVE] = state.n_active() / MAX_SLOTS
    if ruleset.short_game:
        obs[_SHORT] = 1.0
        obs[_REMAINING] = max(0.0, min(1.0, (ruleset.max_rounds - state.round_index) / ruleset.max_rounds))
    for i in range(C.DECK_SIZE):
        if (state.deck_cycle_drawn_a >> i) & 1:
            obs[_DECK_A + i] = 1.0
        if (state.deck_cycle_drawn_b >> i) & 1:
            obs[_DECK_B + i] = 1.0
    return obs
