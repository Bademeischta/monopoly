"""Disjoint, checksummed seed pools SELECT / TEST / SMOKE and TRAIN seed derivation (§7.4, §8.1)."""

from __future__ import annotations

import functools
from pathlib import Path

from propertyrl.engine import constants as C
from propertyrl.engine.errors import SeedLedgerError
from propertyrl.engine.hashing import sha256_hex
from propertyrl.engine.rng import u64
from propertyrl.infra.config import load_seeds_config
from propertyrl.infra.storage import read_json, sub_artifacts, write_json

SEED_MASK = (1 << 63) - 1
POOL_ORDER = ("SELECT", "TEST", "SMOKE")


def eval_seed(master: int, pool_id: int, index: int) -> int:
    """u64(master, EVAL, pool_id, i) restricted to 63 bits."""
    return u64(master, C.STREAM_EVAL, pool_id, index) & SEED_MASK


def generate_pools(master: int | None = None) -> dict[str, list[int]]:
    """Generate all pools; colliding indices are skipped and the pool is refilled (§8.1)."""
    cfg = load_seeds_config()
    m = cfg.master_seed if master is None else master
    used: set[int] = set()
    pools: dict[str, list[int]] = {}
    for name in POOL_ORDER:
        pc = cfg.pools[name]
        out: list[int] = []
        i = 0
        while len(out) < pc.size:
            s = eval_seed(m, pc.pool_id, i)
            i += 1
            if s in used:
                continue
            out.append(s)
            used.add(s)
        pools[name] = out
    check_disjoint(pools)
    return pools


def check_disjoint(pools: dict[str, list[int]]) -> None:
    """Raise SeedLedgerError if any two pools share a seed or a pool has duplicates."""
    seen: dict[int, str] = {}
    for name, seeds in pools.items():
        if len(set(seeds)) != len(seeds):
            raise SeedLedgerError(f"pool {name} contains duplicates")
        for s in seeds:
            if s in seen:
                raise SeedLedgerError(f"seed {s} in both {seen[s]} and {name}")
            seen[s] = name


def seeds_dir() -> Path:
    """artifacts/seeds/."""
    return sub_artifacts("seeds")


def write_pools(pools: dict[str, list[int]]) -> dict[str, str]:
    """Write pool files with SHA-256 checksums; return the checksums."""
    d = seeds_dir()
    checksums = {}
    for name, seeds in pools.items():
        write_json(d / f"{name.lower()}.json", seeds)
        checksums[name] = sha256_hex(seeds)
    write_json(d / "checksums.json", checksums)
    return checksums


@functools.lru_cache(maxsize=4)
def _load_cached(directory: str) -> dict[str, list[int]]:
    d = Path(directory)
    checks_path = d / "checksums.json"
    if not checks_path.exists():
        pools = generate_pools()
        write_pools(pools)
        return pools
    checks = read_json(checks_path)
    pools = {}
    for name in POOL_ORDER:
        seeds = [int(x) for x in read_json(d / f"{name.lower()}.json")]
        if sha256_hex(seeds) != checks.get(name):
            raise SeedLedgerError(f"checksum mismatch for seed pool {name} in {d}")
        pools[name] = seeds
    expected = generate_pools()
    if pools != expected:
        raise SeedLedgerError("stored seed pools differ from the configured master seed")
    check_disjoint(pools)
    return pools


def load_pools() -> dict[str, list[int]]:
    """Load (or create) the seed pools and verify their checksums on every load."""
    return _load_cached(str(seeds_dir()))


def pool_checksums() -> dict[str, str]:
    """SHA-256 checksums of the current pools."""
    return {name: sha256_hex(seeds) for name, seeds in load_pools().items()}


def subset(pool: str, name: str | None = None, start: int = 0, end: int | None = None) -> list[int]:
    """Seeds of a pool, optionally restricted to a named subset or an index range."""
    seeds = load_pools()[pool]
    if name is not None:
        rng = load_seeds_config().subsets[name]
        start, end = rng[0], rng[1]
    return seeds[start:end]


@functools.lru_cache(maxsize=1)
def forbidden_seeds() -> frozenset[int]:
    """Union of all evaluation pools (TRAIN seeds must avoid them)."""
    pools = load_pools()
    return frozenset(s for seeds in pools.values() for s in seeds)


def train_seed(run_seed: int, worker: int, episode: int, master: int | None = None) -> tuple[int, int]:
    """TRAIN game seed u64(master, TRAIN, run_seed, worker, episode); on collision use the next counter.

    Returns (seed, counter actually used).
    """
    m = load_seeds_config().master_seed if master is None else master
    forbidden = forbidden_seeds()
    counter = episode
    while True:
        s = u64(m, C.STREAM_TRAIN, run_seed, worker, counter) & SEED_MASK
        if s not in forbidden:
            return s, counter
        counter += 1
