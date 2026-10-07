"""Fixed index mappings and constants of the engine (RULESPEC §3.1, §3.3).

The property index ``p`` (0-27) and the buildable index ``b`` (0-21) are part of
the action schema and must never change without bumping the action version.
"""

from __future__ import annotations

from typing import Final

N_SQUARES: Final = 40
N_PROPS: Final = 28
N_BUILD: Final = 22
MAX_SEATS: Final = 8
MIN_SEATS: Final = 2
BANK: Final = -1

#: Square kinds.
START: Final = "START"
STREET: Final = "STREET"
RAIL: Final = "RAIL"
UTIL: Final = "UTIL"
CARD_A: Final = "CARD_A"
CARD_B: Final = "CARD_B"
TAX: Final = "TAX"
JAIL: Final = "JAIL"
REST: Final = "REST"
ARREST: Final = "ARREST"
SQUARE_KINDS: Final = (START, STREET, RAIL, UTIL, CARD_A, CARD_B, TAX, JAIL, REST, ARREST)

# Integer codes for fast dispatch.
K_START, K_STREET, K_RAIL, K_UTIL, K_CARD_A, K_CARD_B, K_TAX, K_JAIL, K_REST, K_ARREST = range(10)
KIND_CODE: Final = {name: i for i, name in enumerate(SQUARE_KINDS)}

JAIL_SQUARE: Final = 10
ARREST_SQUARE: Final = 30
GO_SQUARE: Final = 0

#: R-002/§3.3 property index -> square.
PROP_SQUARES: Final = (
    1, 3, 5, 6, 8, 9, 11, 12, 13, 14, 15, 16, 18, 19,
    21, 23, 24, 25, 26, 27, 28, 29, 31, 32, 34, 35, 37, 39,
)  # fmt: skip
#: §3.3 buildable index -> square.
BUILD_SQUARES: Final = (
    1, 3, 6, 8, 9, 11, 13, 14, 16, 18, 19, 21, 23, 24, 26, 27, 29, 31, 32, 34, 37, 39,
)  # fmt: skip

SQUARE_TO_P: Final = tuple(PROP_SQUARES.index(s) if s in PROP_SQUARES else -1 for s in range(N_SQUARES))
SQUARE_TO_B: Final = tuple(BUILD_SQUARES.index(s) if s in BUILD_SQUARES else -1 for s in range(N_SQUARES))
P_TO_B: Final = tuple(SQUARE_TO_B[s] for s in PROP_SQUARES)
B_TO_P: Final = tuple(SQUARE_TO_P[s] for s in BUILD_SQUARES)

#: Group names in board order (colour groups first, then rails and utilities).
GROUP_NAMES: Final = (
    "BRAUN", "HELLBLAU", "PINK", "ORANGE", "ROT", "GELB", "GRUEN", "DUNKELBLAU", "BAHN", "WERK",
)  # fmt: skip
COLOR_GROUPS: Final = GROUP_NAMES[:8]
GROUP_SQUARES: Final = {
    "BRAUN": (1, 3),
    "HELLBLAU": (6, 8, 9),
    "PINK": (11, 13, 14),
    "ORANGE": (16, 18, 19),
    "ROT": (21, 23, 24),
    "GELB": (26, 27, 29),
    "GRUEN": (31, 32, 34),
    "DUNKELBLAU": (37, 39),
    "BAHN": (5, 15, 25, 35),
    "WERK": (12, 28),
}
CARD_A_SQUARES: Final = (7, 22, 36)
CARD_B_SQUARES: Final = (2, 17, 33)
RAIL_SQUARES: Final = GROUP_SQUARES["BAHN"]
UTIL_SQUARES: Final = GROUP_SQUARES["WERK"]
GROUP_ID: Final = {name: i for i, name in enumerate(GROUP_NAMES)}
N_GROUPS: Final = len(GROUP_NAMES)
N_COLOR_GROUPS: Final = len(COLOR_GROUPS)

#: Group id of every property index.
P_GROUP: Final = tuple(
    next(GROUP_ID[g] for g, sq in GROUP_SQUARES.items() if PROP_SQUARES[p] in sq) for p in range(N_PROPS)
)
#: Property indices of every group.
GROUP_PROPS: Final = tuple(tuple(SQUARE_TO_P[s] for s in GROUP_SQUARES[name]) for name in GROUP_NAMES)
#: Buildable indices of every colour group (empty tuple for rails/utilities).
GROUP_BUILDS: Final = tuple(
    tuple(SQUARE_TO_B[s] for s in GROUP_SQUARES[name]) if name in COLOR_GROUPS else () for name in GROUP_NAMES
)
#: Group id of every buildable index.
B_GROUP: Final = tuple(P_GROUP[B_TO_P[b]] for b in range(N_BUILD))
RAIL_GROUP: Final = GROUP_ID["BAHN"]
UTIL_GROUP: Final = GROUP_ID["WERK"]

#: Max building level (5 = hotel).
HOTEL_LEVEL: Final = 5
#: Card deck indices (bit = 1 << index for jail card masks).
DECK_A: Final = 0
DECK_B: Final = 1
DECK_BITS: Final = (1, 2)
DECK_SIZE: Final = 16

#: RNG streams (§4.3).
STREAM_GAME: Final = 1
STREAM_DICE: Final = 2
STREAM_CARDS: Final = 3
STREAM_AGENT: Final = 4
STREAM_ROLLOUT: Final = 5
STREAM_TRAIN: Final = 6
STREAM_EVAL: Final = 7

#: Watchdogs (P-16).
WATCHDOG_WINDOW_DECISIONS: Final = 1000
WATCHDOG_TURN_EVENTS: Final = 5000
WATCHDOG_GAME_DECISIONS: Final = 2_000_000
#: P-03 bid action cap.
AUCTION_MAX_ACTIONS: Final = 200
#: P-02 / D-03 offer cap.
MAX_OFFERS_PER_WINDOW: Final = 2
#: D-02 sealed levels (percent of printed price).
SEALED_PROPERTY_LEVELS: Final = (10, 25, 50, 75, 100, 125, 150)
#: D-05 sealed premium levels (percent of the trigger target's house price).
SEALED_PREMIUM_LEVELS: Final = (0, 10, 25, 50, 75, 100, 150)


def round_half_up(numerator: int, denominator: int) -> int:
    """Integer rounding half up of ``numerator / denominator`` (A-101)."""
    return (2 * numerator + denominator) // (2 * denominator)


def ceil_div(numerator: int, denominator: int) -> int:
    """Ceiling of ``numerator / denominator`` for non-negative integers."""
    return -(-numerator // denominator)
