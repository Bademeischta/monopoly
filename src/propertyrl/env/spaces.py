"""MaskedDiscrete action space (§6.5): sample() without mask draws only legal actions."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

import numpy as np
from gymnasium import spaces


class MaskedDiscrete(spaces.Discrete):
    """Discrete(n) whose unmasked ``sample()`` respects the current legal-action mask of its env.

    The back-reference to the mask function is dropped on pickling so that SubprocVecEnv does
    not ship the whole environment along with the space.
    """

    def __init__(self, n: int, mask_fn: Callable[[], np.ndarray | None] | None = None, seed: int | None = None) -> None:
        super().__init__(n, seed=seed)
        self._mask_fn = mask_fn

    def set_mask_fn(self, mask_fn: Callable[[], np.ndarray | None] | None) -> None:
        """Attach (or detach) the mask provider."""
        self._mask_fn = mask_fn

    def sample(self, mask: Any = None, probability: Any = None) -> np.int64:
        """Sample a legal action; an explicit ``mask`` behaves exactly like ``Discrete.sample``."""
        if mask is None and probability is None and self._mask_fn is not None:
            current = self._mask_fn()
            if current is not None and current.any():
                return super().sample(mask=current.astype(np.int8))
        if probability is not None:
            return super().sample(probability=probability)
        return super().sample(mask=mask)

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state["_mask_fn"] = None
        return state

    def __setstate__(self, state: Iterable[tuple[str, Any]] | Mapping[str, Any]) -> None:
        super().__setstate__(state)
        if "_mask_fn" not in self.__dict__:
            self._mask_fn = None

    def __repr__(self) -> str:
        return f"MaskedDiscrete({self.n})"
