"""Board definition (R-002, §3.2) as validated, immutable Python objects.

The canonical data lives in ``configs/board/board_us_neutral.yaml``; the
infrastructure layer parses the YAML and passes a plain dict to
:meth:`Board.from_dict`. The engine never imports YAML itself (§4.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from propertyrl.engine import constants as C
from propertyrl.engine.errors import ConfigError


@dataclass(frozen=True, slots=True)
class Square:
    """A single board square."""

    index: int
    kind: str
    name: str
    group: str | None = None
    price: int = 0
    rents: tuple[int, ...] = ()
    house_price: int = 0
    mortgage_value: int = 0
    tax: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "index": self.index,
            "kind": self.kind,
            "name": self.name,
            "group": self.group,
            "price": self.price,
            "rents": list(self.rents),
            "house_price": self.house_price,
            "mortgage_value": self.mortgage_value,
            "tax": self.tax,
        }


class Board:
    """Immutable board with precomputed lookup tables indexed by p and b."""

    __slots__ = (
        "b_house_price",
        "b_rents",
        "board_id",
        "kind_code",
        "p_mortgage",
        "p_price",
        "p_square",
        "rail_rents",
        "squares",
        "tax_amount",
        "util_multipliers",
    )

    def __init__(self, squares: tuple[Square, ...], board_id: str = "board_us_neutral") -> None:
        self.board_id = board_id
        self.squares = squares
        self._validate()
        self.kind_code: tuple[int, ...] = tuple(C.KIND_CODE[sq.kind] for sq in squares)
        self.p_square: tuple[int, ...] = C.PROP_SQUARES
        self.p_price: tuple[int, ...] = tuple(squares[s].price for s in C.PROP_SQUARES)
        self.p_mortgage: tuple[int, ...] = tuple(squares[s].mortgage_value for s in C.PROP_SQUARES)
        self.b_house_price: tuple[int, ...] = tuple(squares[s].house_price for s in C.BUILD_SQUARES)
        self.b_rents: tuple[tuple[int, ...], ...] = tuple(squares[s].rents for s in C.BUILD_SQUARES)
        self.tax_amount: tuple[int, ...] = tuple(sq.tax for sq in squares)
        self.rail_rents: tuple[int, ...] = squares[C.RAIL_SQUARES[0]].rents
        self.util_multipliers: tuple[int, ...] = squares[C.UTIL_SQUARES[0]].rents

    def _validate(self) -> None:
        sq = self.squares
        if len(sq) != C.N_SQUARES:
            raise ConfigError(f"board must have {C.N_SQUARES} squares, got {len(sq)}")
        for i, s in enumerate(sq):
            if s.index != i:
                raise ConfigError(f"square {i} has index {s.index}")
            if s.kind not in C.SQUARE_KINDS:
                raise ConfigError(f"square {i}: unknown kind {s.kind!r}")
        props = tuple(s.index for s in sq if s.kind in (C.STREET, C.RAIL, C.UTIL))
        if props != C.PROP_SQUARES:
            raise ConfigError("property squares do not match the fixed index mapping (§3.3)")
        streets = tuple(s.index for s in sq if s.kind == C.STREET)
        if streets != C.BUILD_SQUARES:
            raise ConfigError("street squares do not match the fixed buildable mapping (§3.3)")
        for name, members in C.GROUP_SQUARES.items():
            got = tuple(s.index for s in sq if s.group == name)
            if got != members:
                raise ConfigError(f"group {name} members {got} != {members}")
        for s in sq:
            if s.kind == C.STREET:
                if len(s.rents) != 6 or s.house_price <= 0 or s.price <= 0:
                    raise ConfigError(f"street {s.index} needs 6 rents, price and house price")
                if s.house_price % 2 or s.mortgage_value <= 0:
                    raise ConfigError(f"street {s.index}: house price must be even, mortgage > 0")
            elif s.kind == C.RAIL:
                if len(s.rents) != 4 or s.price <= 0:
                    raise ConfigError(f"rail {s.index} needs 4 rents")
            elif s.kind == C.UTIL:
                if len(s.rents) != 2 or s.price <= 0:
                    raise ConfigError(f"utility {s.index} needs 2 multipliers")
            elif s.kind == C.TAX and s.tax <= 0:
                raise ConfigError(f"tax square {s.index} needs a positive amount")
        rails = {sq[s].rents for s in C.RAIL_SQUARES}
        utils = {sq[s].rents for s in C.UTIL_SQUARES}
        if len(rails) != 1 or len(utils) != 1:
            raise ConfigError("all rails (and all utilities) must share the same rent table")
        if sq[C.JAIL_SQUARE].kind != C.JAIL or sq[C.ARREST_SQUARE].kind != C.ARREST:
            raise ConfigError("jail must be square 10 and arrest square 30")
        if sq[C.GO_SQUARE].kind != C.START:
            raise ConfigError("start must be square 0")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Board:
        """Build a board from a parsed config dict (``{"board_id":..., "squares": [...]}``)."""
        try:
            raw = data["squares"]
            squares = tuple(
                Square(
                    index=int(s["index"]),
                    kind=str(s["kind"]),
                    name=str(s["name"]),
                    group=s.get("group"),
                    price=int(s.get("price", 0)),
                    rents=tuple(int(x) for x in s.get("rents", ())),
                    house_price=int(s.get("house_price", 0)),
                    mortgage_value=int(s.get("mortgage_value", 0)),
                    tax=int(s.get("tax", 0)),
                )
                for s in raw
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"invalid board data: {exc}") from exc
        return cls(squares, str(data.get("board_id", "board_us_neutral")))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {"board_id": self.board_id, "squares": [s.to_dict() for s in self.squares]}

    def name(self, square: int) -> str:
        """Neutral display name of a square."""
        return self.squares[square].name

    def prop_name(self, p: int) -> str:
        """Neutral display name of property index ``p``."""
        return self.squares[C.PROP_SQUARES[p]].name
