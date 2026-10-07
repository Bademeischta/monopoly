"""Money ledger (§4.7). Bank = -1.

Per-seat inflow/outflow totals are part of the game state (cheap to copy) and
back the invariant ``cash = start + inflow - outflow``. The full transaction
list is only recorded when event logging is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Transaction:
    """A single money transfer."""

    sender: int
    receiver: int
    amount: int
    reason: str
    decision_index: int

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return {
            "from": self.sender,
            "to": self.receiver,
            "amount": self.amount,
            "reason": self.reason,
            "decision_index": self.decision_index,
        }


class Ledger:
    """Append-only list of transactions with consistency helpers."""

    __slots__ = ("transactions",)

    def __init__(self) -> None:
        self.transactions: list[Transaction] = []

    def record(self, sender: int, receiver: int, amount: int, reason: str, decision_index: int) -> None:
        """Append a transaction."""
        self.transactions.append(Transaction(sender, receiver, amount, reason, decision_index))

    def totals(self, n_players: int) -> tuple[list[int], list[int]]:
        """Return per-seat (inflow, outflow) totals."""
        inflow = [0] * n_players
        outflow = [0] * n_players
        for t in self.transactions:
            if t.sender >= 0:
                outflow[t.sender] += t.amount
            if t.receiver >= 0:
                inflow[t.receiver] += t.amount
        return inflow, outflow

    def balance(self, seat: int, starting_cash: int) -> int:
        """Cash implied by the ledger for ``seat``."""
        balance = starting_cash
        for t in self.transactions:
            if t.sender == seat:
                balance -= t.amount
            if t.receiver == seat:
                balance += t.amount
        return balance

    def copy(self) -> Ledger:
        """Shallow copy (transactions are immutable)."""
        out = Ledger()
        out.transactions = list(self.transactions)
        return out

    def to_list(self) -> list[dict[str, Any]]:
        """JSON-serialisable list."""
        return [t.to_dict() for t in self.transactions]
