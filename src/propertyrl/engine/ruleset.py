"""Ruleset objects (§3.9). Parsed from YAML outside the engine."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from propertyrl.engine import constants as C
from propertyrl.engine.errors import ConfigError

DECISION_PROTOCOLS = ("official_windows", "own_turn_only")
AUCTION_PROTOCOLS = ("ascending_open", "sealed_7_levels")
TRADE_PROTOCOLS = ("window_offers", "active_player_only", "none")
GAME_ENDS = ("natural", "short_game")


@dataclass(frozen=True, slots=True)
class Ruleset:
    """Immutable, validated ruleset."""

    ruleset_id: str
    source: str
    edition: str
    version: str
    player_count: tuple[int, int]
    rule_ids: tuple[str, ...]
    protocol_ids: tuple[str, ...]
    deviation_ids: tuple[str, ...]
    known_deviations: tuple[str, ...]
    house_rules: tuple[str, ...]
    decision_protocol: str
    auction_protocol: str
    trade_protocol: str
    scarcity_auction: bool
    game_end: str
    safety_horizon_rounds: int
    max_rounds: int
    verification_points: dict[str, Any] = field(default_factory=dict)
    starting_cash: int = 1500
    salary: int = 200
    jail_fine: int = 50
    mortgage_interest_percent: int = 10
    bank_houses: int = 32
    bank_hotels: int = 12
    #: TEST_MOVEMENT_ONLY: no purchases, rent, taxes or card effects; jail fine always paid.
    movement_only: bool = False

    def __post_init__(self) -> None:
        if self.decision_protocol not in DECISION_PROTOCOLS:
            raise ConfigError(f"{self.ruleset_id}: unknown decision_protocol {self.decision_protocol!r}")
        if self.auction_protocol not in AUCTION_PROTOCOLS:
            raise ConfigError(f"{self.ruleset_id}: unknown auction_protocol {self.auction_protocol!r}")
        if self.trade_protocol not in TRADE_PROTOCOLS:
            raise ConfigError(f"{self.ruleset_id}: unknown trade_protocol {self.trade_protocol!r}")
        if self.game_end not in GAME_ENDS:
            raise ConfigError(f"{self.ruleset_id}: unknown game_end {self.game_end!r}")
        lo, hi = self.player_count
        if not (C.MIN_SEATS <= lo <= hi <= C.MAX_SEATS):
            raise ConfigError(f"{self.ruleset_id}: invalid player_count {self.player_count}")
        if self.safety_horizon_rounds <= 0:
            raise ConfigError(f"{self.ruleset_id}: safety_horizon_rounds must be positive")
        if self.game_end == "short_game" and self.max_rounds <= 0:
            raise ConfigError(f"{self.ruleset_id}: short_game requires max_rounds > 0")
        if self.starting_cash < 0 or self.salary < 0 or self.jail_fine < 0:
            raise ConfigError(f"{self.ruleset_id}: monetary constants must be non-negative")

    @property
    def official_windows(self) -> bool:
        """True if out-of-turn windows exist (P-01)."""
        return self.decision_protocol == "official_windows"

    @property
    def sealed(self) -> bool:
        """True for sealed one-round auctions (D-02, D-05)."""
        return self.auction_protocol == "sealed_7_levels"

    @property
    def short_game(self) -> bool:
        """True for the short-game variant (D-06)."""
        return self.game_end == "short_game"

    def with_overrides(self, **kwargs: Any) -> Ruleset:
        """Return a copy with replaced fields (e.g. ``safety_horizon_rounds``)."""
        return replace(self, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Ruleset:
        """Build a ruleset from a parsed config dict."""
        try:
            pc = data["player_count"]
            if isinstance(pc, int):
                player_count = (pc, pc)
            else:
                player_count = (int(pc[0]), int(pc[1]))
            return cls(
                ruleset_id=str(data["ruleset_id"]),
                source=str(data["source"]),
                edition=str(data["edition"]),
                version=str(data["version"]),
                player_count=player_count,
                rule_ids=tuple(data.get("rule_ids", ())),
                protocol_ids=tuple(data.get("protocol_ids", ())),
                deviation_ids=tuple(data.get("deviation_ids", ())),
                known_deviations=tuple(data.get("known_deviations", ())),
                house_rules=tuple(data.get("house_rules", ())),
                decision_protocol=str(data["decision_protocol"]),
                auction_protocol=str(data["auction_protocol"]),
                trade_protocol=str(data["trade_protocol"]),
                scarcity_auction=bool(data["scarcity_auction"]),
                game_end=str(data["game_end"]),
                safety_horizon_rounds=int(data["safety_horizon_rounds"]),
                max_rounds=int(data.get("max_rounds", 0)),
                verification_points=dict(data.get("verification_points", {})),
                starting_cash=int(data.get("starting_cash", 1500)),
                salary=int(data.get("salary", 200)),
                jail_fine=int(data.get("jail_fine", 50)),
                mortgage_interest_percent=int(data.get("mortgage_interest_percent", 10)),
                bank_houses=int(data.get("bank_houses", 32)),
                bank_hotels=int(data.get("bank_hotels", 12)),
                movement_only=bool(data.get("movement_only", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"invalid ruleset data: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "ruleset_id": self.ruleset_id,
            "source": self.source,
            "edition": self.edition,
            "version": self.version,
            "player_count": list(self.player_count),
            "rule_ids": list(self.rule_ids),
            "protocol_ids": list(self.protocol_ids),
            "deviation_ids": list(self.deviation_ids),
            "known_deviations": list(self.known_deviations),
            "house_rules": list(self.house_rules),
            "decision_protocol": self.decision_protocol,
            "auction_protocol": self.auction_protocol,
            "trade_protocol": self.trade_protocol,
            "scarcity_auction": self.scarcity_auction,
            "game_end": self.game_end,
            "safety_horizon_rounds": self.safety_horizon_rounds,
            "max_rounds": self.max_rounds,
            "verification_points": dict(self.verification_points),
            "starting_cash": self.starting_cash,
            "salary": self.salary,
            "jail_fine": self.jail_fine,
            "mortgage_interest_percent": self.mortgage_interest_percent,
            "bank_houses": self.bank_houses,
            "bank_hotels": self.bank_hotels,
            "movement_only": self.movement_only,
        }
