"""Statistics (§8.5): Wilson intervals, seed-cluster bootstrap, paired differences, Holm correction, power."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from propertyrl.engine import constants as C
from propertyrl.engine.rng import u64

Z95 = 1.959963984540054


def wilson(successes: float, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion (fractional successes allowed for draws)."""
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def power_n(p: float, half_width: float, z: float = Z95) -> int:
    """Number of games for a CI half width: n = z^2 p (1 - p) / hw^2, rounded up."""
    return math.ceil(z * z * p * (1 - p) / (half_width * half_width) - 1e-9)


def _rng(seed_key: Sequence[int]) -> np.random.Generator:
    return np.random.default_rng(u64(*seed_key, C.STREAM_EVAL) % (2**63))


@dataclass(frozen=True)
class BootstrapResult:
    """Point estimate with a percentile bootstrap interval."""

    estimate: float
    lower: float
    upper: float
    p_value: float
    n_clusters: int

    def to_dict(self) -> dict[str, float]:
        """Dict form."""
        return {
            "estimate": self.estimate,
            "lower": self.lower,
            "upper": self.upper,
            "p_value": self.p_value,
            "n_clusters": self.n_clusters,
        }


def cluster_bootstrap(
    values: Sequence[float],
    clusters: Sequence[int],
    reps: int = 5000,
    seed_key: Sequence[int] = (0,),
    null: float = 0.5,
    alpha: float = 0.05,
) -> BootstrapResult:
    """Seed-cluster bootstrap of the mean (clusters = TEST seeds); two-sided p-value against ``null``."""
    groups: dict[int, list[float]] = defaultdict(list)
    for v, c in zip(values, clusters, strict=True):
        groups[c].append(float(v))
    keys = sorted(groups)
    sums = np.array([sum(groups[k]) for k in keys])
    counts = np.array([len(groups[k]) for k in keys])
    estimate = float(sums.sum() / counts.sum()) if counts.sum() else float("nan")
    if len(keys) == 0:
        return BootstrapResult(estimate, float("nan"), float("nan"), 1.0, 0)
    rng = _rng(seed_key)
    idx = rng.integers(0, len(keys), size=(reps, len(keys)))
    means = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    lower = float(np.quantile(means, alpha / 2))
    upper = float(np.quantile(means, 1 - alpha / 2))
    centred = means - estimate + null
    p = float(min(1.0, 2 * min((centred >= estimate).mean(), (centred <= estimate).mean())))
    return BootstrapResult(estimate, lower, upper, max(p, 1.0 / reps), len(keys))


def paired_bootstrap(
    a: dict[int, float], b: dict[int, float], reps: int = 5000, seed_key: Sequence[int] = (1,), alpha: float = 0.05
) -> BootstrapResult:
    """Paired difference A - B over common seeds (seed-cluster bootstrap), p-value against 0."""
    keys = sorted(set(a) & set(b))
    diffs = np.array([a[k] - b[k] for k in keys], dtype=float)
    if len(keys) == 0:
        return BootstrapResult(float("nan"), float("nan"), float("nan"), 1.0, 0)
    estimate = float(diffs.mean())
    rng = _rng(seed_key)
    idx = rng.integers(0, len(keys), size=(reps, len(keys)))
    means = diffs[idx].mean(axis=1)
    lower = float(np.quantile(means, alpha / 2))
    upper = float(np.quantile(means, 1 - alpha / 2))
    centred = means - estimate
    p = float(min(1.0, 2 * min((centred >= abs(estimate)).mean(), (centred <= -abs(estimate)).mean())))
    return BootstrapResult(estimate, lower, upper, max(p, 1.0 / reps), len(keys))


def holm(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (same order as the input)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        value = min(1.0, (m - rank) * p_values[i])
        running = max(running, value)
        adjusted[i] = running
    return adjusted
