"""Event schema (event_schema_version e1.0) and per-seat counters (§4.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

EVENT_TYPES: Final = (
    "GAME_STARTED",
    "TURN_STARTED",
    "WINDOW_OPENED",
    "WINDOW_CLOSED",
    "DICE_ROLLED",
    "MOVED",
    "SALARY",
    "LANDED",
    "CARD_DRAWN",
    "CARD_EFFECT",
    "PROPERTY_PURCHASED",
    "BUY_DECLINED",
    "AUCTION_STARTED",
    "BID",
    "AUCTION_WON",
    "AUCTION_NO_SALE",
    "BUILDING_AUCTION_STARTED",
    "BUILDING_AUCTION_WON",
    "RENT_PAID",
    "TAX_PAID",
    "PAYMENT",
    "HOUSE_BUILT",
    "HOTEL_BUILT",
    "BUILDING_SOLD",
    "GROUP_SOLD_DOWN",
    "PROPERTY_MORTGAGED",
    "PROPERTY_UNMORTGAGED",
    "INTEREST_PAID",
    "TRADE_OFFERED",
    "TRADE_ACCEPTED",
    "TRADE_REJECTED",
    "TRADE_EXECUTED",
    "JAIL_ENTERED",
    "JAIL_FINE_PAID",
    "JAIL_CARD_USED",
    "JAIL_ROLL_FAILED",
    "JAIL_LEFT",
    "DEBT_STARTED",
    "DEBT_SETTLED",
    "BANKRUPTCY",
    "ASSETS_TRANSFERRED",
    "GAME_ENDED",
    "DECISION",
)
EVENT_TYPE_SET: Final = frozenset(EVENT_TYPES)

#: Per-seat counters kept even when event logging is disabled (fast training mode).
COUNTER_NAMES: Final = (
    "decisions",
    "purchases",
    "auctions_won",
    "auction_spend",
    "auction_face_value",
    "houses_built",
    "hotels_built",
    "buildings_sold",
    "build_spend",
    "mortgages",
    "unmortgages",
    "trades_offered",
    "trades_executed",
    "trade_offers_received",
    "trade_offers_accepted",
    "scarcity_auctions_triggered",
    "scarcity_auctions_won",
    "scarcity_premium_paid",
    "jail_entries",
    "jail_stay",
    "jail_leave",
    "jail_income",
    "jail_expense",
    "rent_received",
    "rent_paid",
    "salary_received",
    "taxes_paid",
    "debt_phases",
)
COUNTER_INDEX: Final = {name: i for i, name in enumerate(COUNTER_NAMES)}
N_COUNTERS: Final = len(COUNTER_NAMES)

# Counter indices as module constants for the hot paths.
CNT_DECISIONS = COUNTER_INDEX["decisions"]
CNT_PURCHASES = COUNTER_INDEX["purchases"]
CNT_AUCTIONS_WON = COUNTER_INDEX["auctions_won"]
CNT_AUCTION_SPEND = COUNTER_INDEX["auction_spend"]
CNT_AUCTION_FACE = COUNTER_INDEX["auction_face_value"]
CNT_HOUSES = COUNTER_INDEX["houses_built"]
CNT_HOTELS = COUNTER_INDEX["hotels_built"]
CNT_SOLD = COUNTER_INDEX["buildings_sold"]
CNT_BUILD_SPEND = COUNTER_INDEX["build_spend"]
CNT_MORTGAGES = COUNTER_INDEX["mortgages"]
CNT_UNMORTGAGES = COUNTER_INDEX["unmortgages"]
CNT_TRADES_OFFERED = COUNTER_INDEX["trades_offered"]
CNT_TRADES_EXECUTED = COUNTER_INDEX["trades_executed"]
CNT_OFFERS_RECEIVED = COUNTER_INDEX["trade_offers_received"]
CNT_OFFERS_ACCEPTED = COUNTER_INDEX["trade_offers_accepted"]
CNT_SCARCITY_TRIGGERED = COUNTER_INDEX["scarcity_auctions_triggered"]
CNT_SCARCITY_WON = COUNTER_INDEX["scarcity_auctions_won"]
CNT_SCARCITY_PREMIUM = COUNTER_INDEX["scarcity_premium_paid"]
CNT_JAIL_ENTRIES = COUNTER_INDEX["jail_entries"]
CNT_JAIL_STAY = COUNTER_INDEX["jail_stay"]
CNT_JAIL_LEAVE = COUNTER_INDEX["jail_leave"]
CNT_JAIL_INCOME = COUNTER_INDEX["jail_income"]
CNT_JAIL_EXPENSE = COUNTER_INDEX["jail_expense"]
CNT_RENT_RECEIVED = COUNTER_INDEX["rent_received"]
CNT_RENT_PAID = COUNTER_INDEX["rent_paid"]
CNT_SALARY = COUNTER_INDEX["salary_received"]
CNT_TAXES = COUNTER_INDEX["taxes_paid"]
CNT_DEBT_PHASES = COUNTER_INDEX["debt_phases"]


@dataclass(slots=True)
class Event:
    """A single engine event."""

    seq: int
    decision_index: int
    type: str
    seat: int
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "seq": self.seq,
            "decision_index": self.decision_index,
            "type": self.type,
            "seat": self.seat,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        """Inverse of :meth:`to_dict`."""
        return cls(int(d["seq"]), int(d["decision_index"]), str(d["type"]), int(d["seat"]), dict(d["data"]))
