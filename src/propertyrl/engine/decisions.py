"""Decision objects and response types (§4.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

# Decision kinds.
MAIN: Final = "MAIN"
DEBT: Final = "DEBT"
TRADE_OFFER: Final = "TRADE_OFFER"
TRADE_RESPONSE: Final = "TRADE_RESPONSE"
AUCTION_BID: Final = "AUCTION_BID"
KINDS: Final = (MAIN, DEBT, TRADE_OFFER, TRADE_RESPONSE, AUCTION_BID)

# Phases (order defines the observation one-hot).
PRE_ROLL: Final = "PRE_ROLL"
JAIL_PRE_ROLL: Final = "JAIL_PRE_ROLL"
BUY_PHASE: Final = "BUY"
POST_MOVE: Final = "POST_MOVE"
OUT_OF_TURN: Final = "OUT_OF_TURN"
DEBT_PHASE: Final = "DEBT"
PLACE_BUILDING: Final = "PLACE_BUILDING"
PHASES: Final = (PRE_ROLL, JAIL_PRE_ROLL, BUY_PHASE, POST_MOVE, OUT_OF_TURN, DEBT_PHASE, PLACE_BUILDING)
PHASE_INDEX: Final = {p: i for i, p in enumerate(PHASES)}

# Auction items and formats.
ITEM_PROPERTY: Final = "PROPERTY"
ITEM_HOUSE: Final = "HOUSE"
ITEM_HOTEL: Final = "HOTEL"
ITEMS: Final = (ITEM_PROPERTY, ITEM_HOUSE, ITEM_HOTEL)
FORMAT_ASCENDING: Final = "ascending_open"
FORMAT_SEALED: Final = "sealed_7_levels"


@dataclass(frozen=True, slots=True)
class Bid:
    """OFFICIAL ascending auction response: an amount or ``None`` for a final pass."""

    amount: int | None


@dataclass(frozen=True, slots=True)
class BidLevel:
    """RESEARCH sealed auction response: a level index 0-6 or ``None`` for pass."""

    index: int | None


@dataclass(slots=True)
class Decision:
    """A pending decision of one seat.

    ``legal`` is a list of 106 bools for MAIN and DEBT decisions and ``None`` otherwise.
    """

    seat: int
    kind: str
    phase: str
    legal: list[bool] | None
    context: dict[str, Any] = field(default_factory=dict)

    def legal_actions(self) -> list[int]:
        """Indices of legal actions (MAIN/DEBT only)."""
        if self.legal is None:
            return []
        return [i for i, ok in enumerate(self.legal) if ok]
