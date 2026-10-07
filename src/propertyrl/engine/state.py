"""Compact, cheaply copyable game state (§4.2).

Only flat fields of ``int``, ``bool``, ``tuple`` and ``list[int]`` plus the
continuation stack (a list of int tuples), an optional auction record and the
pending trade offers. ``copy()`` duplicates the lists; tuples are immutable.
"""

from __future__ import annotations

from typing import Any

from propertyrl.engine import constants as C
from propertyrl.engine.auction import AuctionState
from propertyrl.engine.events import N_COUNTERS
from propertyrl.engine.hashing import sha256_hex
from propertyrl.engine.trade import TradeOffer

_LIST_FIELDS = (
    "cash",
    "position",
    "in_jail",
    "jail_attempts",
    "jail_cards",
    "bankrupt",
    "bankruptcy_order",
    "owner",
    "mortgaged",
    "interest_prepaid",
    "level",
    "deck_a",
    "deck_b",
    "seat_turn_counter",
    "window_actions",
    "placements",
    "final_equities",
    "stack",
    "offers",
    "ledger_in",
    "ledger_out",
    "counters",
    "rest_counts",
)
_SCALAR_FIELDS = (
    "game_seed",
    "n_players",
    "doubles_count",
    "bank_houses",
    "bank_hotels",
    "deck_cycle_drawn_a",
    "deck_cycle_drawn_b",
    "active_seat",
    "turn_index",
    "round_index",
    "window_counter",
    "window_seat",
    "window_kind",
    "decision_index",
    "phase",
    "last_dice",
    "game_over",
    "winner",
    "rng_epoch",
    "roll_in_turn",
    "util_rolls",
    "ctx_decisions",
    "turn_events",
    "event_seq",
    "script_pos",
    "current_offer",
    "offer_phase",
    "ended_by_rounds",
)


class GameState:
    """Mutable game state; all mutation happens inside the engine."""

    __slots__ = (*_LIST_FIELDS, *_SCALAR_FIELDS, "auction")

    def __init__(self, n_players: int, game_seed: int, starting_cash: int, houses: int, hotels: int) -> None:
        n = n_players
        self.game_seed = game_seed
        self.n_players = n
        self.cash: list[int] = [starting_cash] * n
        self.position: list[int] = [0] * n
        self.in_jail: list[bool] = [False] * n
        self.jail_attempts: list[int] = [0] * n
        self.doubles_count = 0
        self.jail_cards: list[int] = [0] * n
        self.bankrupt: list[bool] = [False] * n
        self.bankruptcy_order: list[int] = []
        self.owner: list[int] = [C.BANK] * C.N_PROPS
        self.mortgaged: list[bool] = [False] * C.N_PROPS
        self.interest_prepaid: list[int] = [-1] * C.N_PROPS
        self.level: list[int] = [0] * C.N_BUILD
        self.bank_houses = houses
        self.bank_hotels = hotels
        self.deck_a: list[int] = list(range(C.DECK_SIZE))
        self.deck_b: list[int] = list(range(C.DECK_SIZE))
        self.deck_cycle_drawn_a = 0
        self.deck_cycle_drawn_b = 0
        self.active_seat = 0
        self.seat_turn_counter: list[int] = [0] * n
        self.turn_index = 0
        self.round_index = 0
        self.window_counter = 0
        self.window_seat = -1
        self.window_kind = -1
        self.window_actions: list[tuple[int, int]] = []
        self.decision_index = 0
        self.phase = ""
        self.last_dice: tuple[int, int] = (0, 0)
        self.game_over = False
        self.winner = -1
        self.placements: list[int] = [0] * n
        self.final_equities: list[int] = [0] * n
        self.rng_epoch = 0
        # Internal continuation machinery.
        self.stack: list[tuple[int, ...]] = []
        self.auction: AuctionState | None = None
        self.offers: list[TradeOffer] = []
        self.current_offer: TradeOffer | None = None
        self.offer_phase = ""
        self.roll_in_turn = 0
        self.util_rolls = 0
        self.ctx_decisions = 0
        self.turn_events = 0
        self.event_seq = 0
        self.script_pos = 0
        self.ended_by_rounds = False
        self.ledger_in: list[int] = [0] * n
        self.ledger_out: list[int] = [0] * n
        self.counters: list[int] = [0] * (N_COUNTERS * n)
        self.rest_counts: list[int] = [0] * C.N_SQUARES

    def copy(self) -> GameState:
        """Return an independent copy (list fields duplicated)."""
        new = object.__new__(GameState)
        for name in _SCALAR_FIELDS:
            object.__setattr__(new, name, getattr(self, name))
        for name in _LIST_FIELDS:
            object.__setattr__(new, name, list(getattr(self, name)))
        new.auction = self.auction.copy() if self.auction is not None else None
        return new

    # ------------------------------------------------------------------ views
    def active_players(self) -> list[int]:
        """Seats that are not bankrupt, in seat order."""
        return [i for i in range(self.n_players) if not self.bankrupt[i]]

    def n_active(self) -> int:
        """Number of non-bankrupt seats."""
        return self.n_players - len(self.bankruptcy_order)

    def counter(self, name_index: int, seat: int) -> int:
        """Value of counter ``name_index`` for ``seat``."""
        return self.counters[name_index * self.n_players + seat]

    @property
    def pending(self) -> dict[str, Any]:
        """Decision context: continuation stack, auction and trade offer queue."""
        return {
            "stack": [list(f) for f in self.stack],
            "auction": self.auction.to_dict() if self.auction is not None else None,
            "offers": [o.to_dict() for o in self.offers],
            "current_offer": self.current_offer.to_dict() if self.current_offer is not None else None,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        """Complete canonical dict of the state (basis of :meth:`state_hash`)."""
        out: dict[str, Any] = {}
        for name in _SCALAR_FIELDS:
            val = getattr(self, name)
            if isinstance(val, tuple):
                val = list(val)
            elif isinstance(val, TradeOffer):
                val = val.to_dict()
            out[name] = val
        for name in _LIST_FIELDS:
            val = getattr(self, name)
            if name == "offers":
                out[name] = [o.to_dict() for o in val]
            elif name in ("stack", "window_actions"):
                out[name] = [list(x) for x in val]
            else:
                out[name] = list(val)
        out["auction"] = self.auction.to_dict() if self.auction is not None else None
        return out

    @classmethod
    def from_canonical_dict(cls, d: dict[str, Any]) -> GameState:
        """Inverse of :meth:`to_canonical_dict` (used to replay scenario-based games)."""
        new = object.__new__(GameState)
        for name in _SCALAR_FIELDS:
            object.__setattr__(new, name, d[name])
        for name in _LIST_FIELDS:
            object.__setattr__(new, name, list(d[name]))
        new.last_dice = (int(d["last_dice"][0]), int(d["last_dice"][1]))
        new.stack = [tuple(f) for f in d["stack"]]
        new.window_actions = [(int(a), int(b)) for a, b in d["window_actions"]]
        new.offers = [TradeOffer.from_dict(o) for o in d["offers"]]
        new.current_offer = TradeOffer.from_dict(d["current_offer"]) if d["current_offer"] else None
        new.auction = AuctionState.from_dict(d["auction"]) if d["auction"] else None
        return new

    def state_hash(self) -> str:
        """SHA-256 over the canonical JSON with sorted keys."""
        return sha256_hex(self.to_canonical_dict())
