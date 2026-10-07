"""Statistics (§8.5) against published reference values and analytic properties."""

from __future__ import annotations

import math

import numpy as np
import pytest

from propertyrl.evaluation.stats import cluster_bootstrap, holm, paired_bootstrap, power_n, wilson


@pytest.mark.parametrize(
    ("successes", "n", "lower", "upper"),
    [
        # Newcombe (1998), Statistics in Medicine 17, Table I, method 3 (score interval without correction).
        (81, 263, 0.2553, 0.3662),
        (15, 148, 0.0624, 0.1605),
        (0, 20, 0.0000, 0.1611),
        (1, 29, 0.0061, 0.1718),
    ],
)
def test_wilson_reference_values(successes: int, n: int, lower: float, upper: float) -> None:
    lo, hi = wilson(successes, n)
    assert lo == pytest.approx(lower, abs=5e-5)
    assert hi == pytest.approx(upper, abs=5e-5)


def test_wilson_symmetry_and_bounds() -> None:
    lo, hi = wilson(50, 100)
    assert lo + hi == pytest.approx(1.0)
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    lo2, hi2 = wilson(100, 100)
    assert hi2 == pytest.approx(1.0)
    assert lo2 > 0.95
    assert wilson(0, 0) == (0.0, 1.0)
    # Fractional successes (truncated games count 0.5) are allowed.
    lo3, hi3 = wilson(50.5, 100)
    assert lo < lo3 < hi3 and hi < hi3


def test_power_n() -> None:
    # Spec §8.5: p = 0.5, half width 2 pp -> n = 1.96^2 * 0.25 / 0.0004 ~ 2401.
    assert power_n(0.5, 0.02) == 2401
    assert power_n(0.5, 0.05) == 385
    assert power_n(0.6, 0.03) == math.ceil(1.959963984540054**2 * 0.24 / 0.0009)


def test_holm_hand_computed() -> None:
    p = [0.01, 0.04, 0.03, 0.005]
    # sorted: 0.005*4=0.02, 0.01*3=0.03, 0.03*2=0.06, 0.04*1=0.04 -> monotone 0.06
    assert holm(p) == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert holm([0.5]) == [0.5]
    assert holm([0.6, 0.7]) == [1.0, 1.0]
    assert holm([]) == []


def test_cluster_bootstrap_iid_matches_wilson_width() -> None:
    rng = np.random.default_rng(12345)
    values = rng.integers(0, 2, size=2000).astype(float)
    res = cluster_bootstrap(values, list(range(2000)), reps=4000, seed_key=(7,))
    lo, hi = wilson(values.sum(), 2000)
    assert res.estimate == pytest.approx(values.mean())
    assert res.lower < res.estimate < res.upper
    assert (res.upper - res.lower) == pytest.approx(hi - lo, rel=0.15)
    assert res.n_clusters == 2000


def test_cluster_bootstrap_respects_clusters() -> None:
    """Perfectly correlated games within a seed widen the interval by about sqrt(2)."""
    rng = np.random.default_rng(99)
    per_seed = rng.integers(0, 2, size=800).astype(float)
    values = np.repeat(per_seed, 2)
    clusters = np.repeat(np.arange(800), 2)
    clustered = cluster_bootstrap(values, clusters.tolist(), reps=4000, seed_key=(3,))
    naive = cluster_bootstrap(values, list(range(1600)), reps=4000, seed_key=(3,))
    ratio = (clustered.upper - clustered.lower) / (naive.upper - naive.lower)
    assert ratio == pytest.approx(math.sqrt(2), rel=0.15)
    assert clustered.n_clusters == 800


def test_cluster_bootstrap_p_value_and_determinism() -> None:
    values = [1.0] * 300 + [0.0] * 100
    clusters = list(range(400))
    a = cluster_bootstrap(values, clusters, reps=2000, seed_key=(5,))
    b = cluster_bootstrap(values, clusters, reps=2000, seed_key=(5,))
    assert a == b
    assert a.p_value <= 1.0 / 2000 + 1e-12
    balanced = cluster_bootstrap([1.0, 0.0] * 200, clusters, reps=2000, seed_key=(5,))
    assert balanced.p_value > 0.5
    empty = cluster_bootstrap([], [], reps=10)
    assert empty.n_clusters == 0 and empty.p_value == 1.0


def test_paired_bootstrap() -> None:
    a = {i: 0.6 for i in range(100)}
    b = {i: 0.5 for i in range(100)}
    res = paired_bootstrap(a, b, reps=1000)
    assert res.estimate == pytest.approx(0.1)
    assert res.lower == pytest.approx(0.1) and res.upper == pytest.approx(0.1)
    assert res.p_value == pytest.approx(1.0 / 1000)
    same = paired_bootstrap(a, a, reps=1000)
    assert same.estimate == 0.0 and same.p_value == 1.0
    rng = np.random.default_rng(1)
    noise_a = {i: float(rng.integers(0, 2)) for i in range(400)}
    noise_b = {i: float(rng.integers(0, 2)) for i in range(400)}
    res2 = paired_bootstrap(noise_a, noise_b, reps=2000)
    diffs = [noise_a[i] - noise_b[i] for i in range(400)]
    assert res2.estimate == pytest.approx(float(np.mean(diffs)))
    assert res2.lower <= res2.estimate <= res2.upper
    # only common keys are paired
    partial = paired_bootstrap({0: 1.0, 1: 1.0}, {1: 0.0, 2: 0.0}, reps=100)
    assert partial.n_clusters == 1
