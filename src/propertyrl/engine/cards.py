"""Card decks (§3.4): effect types with parameters and neutral own texts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from propertyrl.engine import constants as C
from propertyrl.engine.errors import ConfigError

ADVANCE_TO = "ADVANCE_TO"
NEAREST_RAIL = "NEAREST_RAIL"
NEAREST_UTIL = "NEAREST_UTIL"
MOVE_BACK = "MOVE_BACK"
SEND_TO_JAIL = "SEND_TO_JAIL"
JAIL_FREE = "JAIL_FREE"
COLLECT = "COLLECT"
PAY = "PAY"
PAY_EACH = "PAY_EACH"
COLLECT_EACH = "COLLECT_EACH"
REPAIRS = "REPAIRS"

EFFECT_TYPES = (
    ADVANCE_TO,
    NEAREST_RAIL,
    NEAREST_UTIL,
    MOVE_BACK,
    SEND_TO_JAIL,
    JAIL_FREE,
    COLLECT,
    PAY,
    PAY_EACH,
    COLLECT_EACH,
    REPAIRS,
)
#: Number of integer parameters per effect type.
EFFECT_ARITY = {
    ADVANCE_TO: 1,
    NEAREST_RAIL: 0,
    NEAREST_UTIL: 0,
    MOVE_BACK: 1,
    SEND_TO_JAIL: 0,
    JAIL_FREE: 0,
    COLLECT: 1,
    PAY: 1,
    PAY_EACH: 1,
    COLLECT_EACH: 1,
    REPAIRS: 2,
}
#: Integer codes for fast dispatch.
E_ADVANCE_TO, E_NEAREST_RAIL, E_NEAREST_UTIL, E_MOVE_BACK, E_SEND_TO_JAIL, E_JAIL_FREE = range(6)
E_COLLECT, E_PAY, E_PAY_EACH, E_COLLECT_EACH, E_REPAIRS = range(6, 11)
EFFECT_CODE = {name: i for i, name in enumerate(EFFECT_TYPES)}
#: Movement effects (used by the approximate Markov chain, §4.11 b).
MOVEMENT_EFFECTS = (ADVANCE_TO, NEAREST_RAIL, NEAREST_UTIL, MOVE_BACK, SEND_TO_JAIL)


@dataclass(frozen=True, slots=True)
class Card:
    """A single card: identifier, deck, effect type with parameters and neutral text."""

    card_id: str
    deck: int
    effect: str
    params: tuple[int, ...]
    text: str

    @property
    def code(self) -> int:
        """Integer effect code."""
        return EFFECT_CODE[self.effect]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {"id": self.card_id, "effect": self.effect, "params": list(self.params), "text": self.text}


class Decks:
    """Both card decks; index ``i`` of a deck tuple is the card's stable index."""

    __slots__ = ("a", "b", "codes", "jail_free_index", "params")

    def __init__(self, a: tuple[Card, ...], b: tuple[Card, ...]) -> None:
        self.a = a
        self.b = b
        for deck_idx, deck in ((C.DECK_A, a), (C.DECK_B, b)):
            if len(deck) != C.DECK_SIZE:
                raise ConfigError(f"deck {deck_idx} must have {C.DECK_SIZE} cards (V5), got {len(deck)}")
            jail = [i for i, c in enumerate(deck) if c.effect == JAIL_FREE]
            if len(jail) != 1:
                raise ConfigError(f"deck {deck_idx} must contain exactly one JAIL_FREE card")
            for c in deck:
                if c.effect not in EFFECT_ARITY:
                    raise ConfigError(f"card {c.card_id}: unknown effect {c.effect}")
                if len(c.params) != EFFECT_ARITY[c.effect]:
                    raise ConfigError(f"card {c.card_id}: wrong number of parameters")
                if c.effect == ADVANCE_TO and not 0 <= c.params[0] < C.N_SQUARES:
                    raise ConfigError(f"card {c.card_id}: target out of range")
        self.codes: tuple[tuple[int, ...], tuple[int, ...]] = (
            tuple(c.code for c in a),
            tuple(c.code for c in b),
        )
        self.params: tuple[tuple[tuple[int, ...], ...], tuple[tuple[int, ...], ...]] = (
            tuple(c.params for c in a),
            tuple(c.params for c in b),
        )
        self.jail_free_index: tuple[int, int] = (
            next(i for i, c in enumerate(a) if c.effect == JAIL_FREE),
            next(i for i, c in enumerate(b) if c.effect == JAIL_FREE),
        )

    def deck(self, idx: int) -> tuple[Card, ...]:
        """Return deck ``idx`` (0 = A, 1 = B)."""
        return self.a if idx == C.DECK_A else self.b

    def index_of(self, deck_idx: int, card_id: str) -> int:
        """Index of card ``card_id`` within deck ``deck_idx``."""
        for i, c in enumerate(self.deck(deck_idx)):
            if c.card_id == card_id:
                return i
        raise ConfigError(f"unknown card id {card_id!r} in deck {deck_idx}")

    @classmethod
    def from_dicts(cls, deck_a: dict[str, Any], deck_b: dict[str, Any]) -> Decks:
        """Build both decks from parsed config dicts (``{"cards": [...]}``)."""

        def parse(data: dict[str, Any], deck_idx: int) -> tuple[Card, ...]:
            try:
                return tuple(
                    Card(
                        card_id=str(c["id"]),
                        deck=deck_idx,
                        effect=str(c["effect"]),
                        params=tuple(int(x) for x in c.get("params", ())),
                        text=str(c["text"]),
                    )
                    for c in data["cards"]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ConfigError(f"invalid deck data: {exc}") from exc

        return cls(parse(deck_a, C.DECK_A), parse(deck_b, C.DECK_B))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {"a": [c.to_dict() for c in self.a], "b": [c.to_dict() for c in self.b]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Decks:
        """Inverse of :meth:`to_dict`."""
        return cls.from_dicts({"cards": data["a"]}, {"cards": data["b"]})
