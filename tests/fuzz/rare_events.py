"""Rare-event generators used as fuzz start states (implementation in propertyrl.infra.fuzz).

The generators live in the package so that ``propertyrl fuzz --rare-events`` can use them.
"""

from __future__ import annotations

from propertyrl.infra.fuzz import (
    RARE_EVENT_GENERATORS,
    RARE_EVENT_SCHEDULE,
    RARE_EVENT_TYPES,
    rare_event_fuzz,
)

__all__ = ["RARE_EVENT_GENERATORS", "RARE_EVENT_SCHEDULE", "RARE_EVENT_TYPES", "rare_event_fuzz"]
