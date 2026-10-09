"""Error hierarchy of PropertyRL.

Every message carries ``game_seed``, ``decision_index`` and ``seat`` where available.
``IllegalActionError`` means a policy/agent answered illegally, whereas
``RuleViolationError`` signals an internal programming or test error.
"""

from __future__ import annotations

from typing import Any


class PropertyRLError(Exception):
    """Base class of all PropertyRL errors with optional game context."""

    def __init__(
        self,
        message: str,
        *,
        game_seed: int | None = None,
        decision_index: int | None = None,
        seat: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.raw_message = message
        self.game_seed = game_seed
        self.decision_index = decision_index
        self.seat = seat
        self.details = details or {}
        #: Full game log (JSON-serialisable dict) attached by the engine when
        #: available; written to artifacts/errors/ by the infrastructure layer.
        self.game_log: dict[str, Any] | None = None
        super().__init__(self._format())

    def _format(self) -> str:
        parts = [self.raw_message]
        ctx = []
        if self.game_seed is not None:
            ctx.append(f"game_seed={self.game_seed}")
        if self.decision_index is not None:
            ctx.append(f"decision_index={self.decision_index}")
        if self.seat is not None:
            ctx.append(f"seat={self.seat}")
        if ctx:
            parts.append("[" + ", ".join(ctx) + "]")
        return " ".join(parts)


class IllegalActionError(PropertyRLError):
    """A policy or agent returned an illegal response."""


class RuleViolationError(PropertyRLError):
    """Internal programming or test error (e.g. exhausted DiceScript)."""


class InvariantError(PropertyRLError):
    """A game state invariant is violated."""


class EngineWatchdogError(PropertyRLError):
    """A watchdog limit (P-16) was exceeded: bug in code or policy."""


class ReplayMismatchError(PropertyRLError):
    """Replaying a game log produced a different state."""


class SchemaVersionError(PropertyRLError):
    """A log, checkpoint or artifact has an incompatible schema version."""


class ConfigError(PropertyRLError):
    """Configuration is invalid or inconsistent."""


class SeedLedgerError(PropertyRLError):
    """Seed pools or the TEST ledger were used in a forbidden way."""


class ArtifactError(PropertyRLError):
    """A stored artifact (JSON, Parquet, checkpoint) is unreadable, e.g. torn by a power-off."""


__all__ = [
    "ArtifactError",
    "ConfigError",
    "EngineWatchdogError",
    "IllegalActionError",
    "InvariantError",
    "PropertyRLError",
    "ReplayMismatchError",
    "RuleViolationError",
    "SchemaVersionError",
    "SeedLedgerError",
]
