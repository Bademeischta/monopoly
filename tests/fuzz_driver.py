"""Random legal responder for all decision kinds (shared by fuzz, property and replay tests)."""

from __future__ import annotations

from propertyrl.infra.fuzz import random_offers, random_response

__all__ = ["random_offers", "random_response"]
