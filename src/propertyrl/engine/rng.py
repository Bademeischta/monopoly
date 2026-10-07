"""Counter-based, platform independent RNG service (§4.3), pure Python.

All randomness of the project derives from :func:`u64` keyed by explicit
stream constants, so that decisions of one seat never shift the dice of
another seat (basis of the duplicate evaluation).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from propertyrl.engine import constants as C

MASK64 = (1 << 64) - 1
_FOLD_INIT = 0x6A09E667F3BCC908
_TWO_POW_53 = float(1 << 53)

T = TypeVar("T")


def _splitmix(z: int) -> int:
    z = (z + 0x9E3779B97F4A7C15) & MASK64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return z ^ (z >> 31)


def u64(*values: int) -> int:
    """Deterministic 64-bit hash of a sequence of integers (splitmix64 fold)."""
    h = _FOLD_INIT
    for v in values:
        h = _splitmix(h ^ (v & MASK64))
    return h


def dice_value(game_seed: int, epoch: int, seat: int, seat_turn: int, throw: int, die: int) -> int:
    """Pip value 1-6 of one die (§4.3)."""
    return 1 + u64(game_seed, C.STREAM_DICE, epoch, seat, seat_turn, throw, die) % 6


def shuffle_deck(game_seed: int, epoch: int, deck_id: int, n: int = C.DECK_SIZE) -> list[int]:
    """Fisher-Yates shuffle of card indices ``0..n-1`` keyed by game seed, epoch and deck."""
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        j = u64(game_seed, C.STREAM_CARDS, epoch, deck_id, i) % (i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def reshuffle_positions(deck: list[int], drawn_mask: int, game_seed: int, epoch: int, deck_id: int) -> list[int]:
    """Shuffle the cards not drawn in the current cycle among their positions (clone reseed)."""
    positions = [i for i, card in enumerate(deck) if not (drawn_mask >> card) & 1]
    cards = [deck[i] for i in positions]
    for i in range(len(cards) - 1, 0, -1):
        j = u64(game_seed, C.STREAM_CARDS, epoch, deck_id, 1000 + i) % (i + 1)
        cards[i], cards[j] = cards[j], cards[i]
    out = list(deck)
    for pos, card in zip(positions, cards, strict=True):
        out[pos] = card
    return out


class AgentRng:
    """Per-seat agent randomness with its own counter (§4.3). Seats share no state."""

    __slots__ = ("counter", "game_seed", "seat", "stream")

    def __init__(self, game_seed: int, seat: int, stream: int = C.STREAM_AGENT) -> None:
        self.game_seed = game_seed
        self.seat = seat
        self.stream = stream
        self.counter = 0

    def _next(self) -> int:
        self.counter += 1
        return u64(self.game_seed, self.stream, self.seat, self.counter)

    def random(self) -> float:
        """Uniform float in [0, 1)."""
        return (self._next() >> 11) / _TWO_POW_53

    def randint(self, a: int, b: int) -> int:
        """Uniform integer in [a, b] (inclusive)."""
        if b < a:
            raise ValueError(f"randint: empty range [{a}, {b}]")
        return a + self._next() % (b - a + 1)

    def choice(self, seq: Sequence[T]) -> T:
        """Uniform choice from a non-empty sequence."""
        if not seq:
            raise ValueError("choice from empty sequence")
        return seq[self._next() % len(seq)]


class SeededStream:
    """Generic counter-based stream for non-game randomness (e.g. bootstrap, Elo order)."""

    __slots__ = ("counter", "keys")

    def __init__(self, *keys: int) -> None:
        self.keys = keys
        self.counter = 0

    def next_u64(self) -> int:
        """Next raw 64-bit value."""
        self.counter += 1
        return u64(*self.keys, self.counter)

    def random(self) -> float:
        """Uniform float in [0, 1)."""
        return (self.next_u64() >> 11) / _TWO_POW_53

    def randint(self, a: int, b: int) -> int:
        """Uniform integer in [a, b]."""
        return a + self.next_u64() % (b - a + 1)
