"""TEST ledger (§8.2): one TEST evaluation per agent hash; smoke runs never write to it."""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from propertyrl.engine.errors import SeedLedgerError
from propertyrl.engine.hashing import sha256_bytes, sha256_hex
from propertyrl.infra.storage import connect, query
from propertyrl.versions import HEURISTIC_VERSIONS

log = logging.getLogger(__name__)


def agent_hash(spec: str) -> str:
    """SHA-256 of the checkpoint file for RL agents; hash of name and version for heuristics."""
    head, _, rest = spec.partition(":")
    if head in ("sb3", "sb3s", "snapshot", "latest") and rest:
        return sha256_bytes(Path(rest).read_bytes())
    return sha256_hex({"policy": spec, "version": HEURISTIC_VERSIONS.get(spec, "unknown")})


def entries(agent: str | None = None, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Ledger rows (optionally for one agent hash; read on the caller's connection when ``conn`` is given)."""
    sql = "SELECT agent_hash, experiment, ruleset_id, n_seeds, time, result_id, forced FROM test_ledger"
    sql += " WHERE agent_hash = ?" if agent else ""
    params: tuple[Any, ...] = (agent,) if agent else ()
    rows = list(conn.execute(sql, params).fetchall()) if conn is not None else query(sql, params)
    keys = ("agent_hash", "experiment", "ruleset_id", "n_seeds", "time", "result_id", "forced")
    return [dict(zip(keys, r, strict=True)) for r in rows]


def is_empty() -> bool:
    """True if no TEST evaluation was ever recorded."""
    return not entries()


def check(agent: str, conn: sqlite3.Connection | None = None) -> None:
    """Raise SeedLedgerError if ``agent`` (hash) already used the TEST split."""
    if entries(agent, conn):
        raise SeedLedgerError(f"agent {agent[:12]} was already evaluated on TEST (use --force-retest to override)")


def record(
    agent: str,
    experiment: str,
    ruleset_id: str,
    n_seeds: int,
    result_id: str,
    force: bool = False,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Record a TEST evaluation; a repeated evaluation requires ``force`` and is marked.

    With ``conn`` the row joins the caller's transaction (evaluation summary and ledger row commit together).
    """
    if conn is None:
        with connect() as own:
            record(agent, experiment, ruleset_id, n_seeds, result_id, force, own)
        return
    if not force:
        check(agent, conn)
    elif entries(agent, conn):
        log.warning("forced TEST re-evaluation of %s", agent[:12])
    conn.execute(
        "INSERT INTO test_ledger VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agent, experiment, ruleset_id, n_seeds, time.time(), result_id, int(force)),
    )
