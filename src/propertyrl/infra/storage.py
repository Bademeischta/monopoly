"""Local storage: directories, SQLite database and JSON helpers (§9.3)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from propertyrl.engine.errors import ArtifactError

_REPO_ROOT = Path(__file__).resolve().parents[3]
#: Attempts of os.replace when Windows reports the target as in use (reader, virus scanner).
_REPLACE_ATTEMPTS = 20
#: Marker in the names of temporary files written by :func:`atomic_path`.
TMP_MARKER = ".tmp-"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, experiment TEXT, status TEXT, smoke INTEGER,
    started REAL, ended REAL, run_json TEXT
);
CREATE TABLE IF NOT EXISTS checkpoints (
    run_id TEXT, step INTEGER, path TEXT, sha256 TEXT, kind TEXT,
    select_winrate REAL, created REAL
);
CREATE TABLE IF NOT EXISTS eval_summaries (
    eval_id TEXT PRIMARY KEY, agent_hash TEXT, experiment TEXT, split TEXT, ruleset_id TEXT,
    n_seeds INTEGER, n_games INTEGER, opponents TEXT, summary_json TEXT, path TEXT,
    smoke INTEGER, created REAL
);
CREATE TABLE IF NOT EXISTS test_ledger (
    agent_hash TEXT, experiment TEXT, ruleset_id TEXT, n_seeds INTEGER, time REAL,
    result_id TEXT, forced INTEGER
);
CREATE TABLE IF NOT EXISTS benchmarks (bench_id TEXT PRIMARY KEY, created REAL, json TEXT);
CREATE TABLE IF NOT EXISTS gates (gate TEXT, status TEXT, created REAL, json TEXT);
"""


def home_dir() -> Path:
    """Base directory for artifacts/, runs/ and reports/ (env PROPERTYRL_HOME, default repo root)."""
    env = os.environ.get("PROPERTYRL_HOME")
    return Path(env) if env else _REPO_ROOT


def artifacts_dir() -> Path:
    """artifacts/ directory (created on demand)."""
    p = home_dir() / "artifacts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runs_dir() -> Path:
    """runs/ directory (created on demand)."""
    p = home_dir() / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def reports_dir() -> Path:
    """reports/ directory (created on demand)."""
    p = home_dir() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sub_artifacts(*parts: str) -> Path:
    """A sub-directory of artifacts/ (created on demand)."""
    p = artifacts_dir().joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    """Path of the SQLite database."""
    return artifacts_dir() / "propertyrl.db"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the database (schema created on first use) and commit on exit.

    Everything written inside one ``with connect()`` block is a single transaction: after a crash or
    power-off either all of it or none of it is in the database (rollback journal, synchronous=FULL; A-139).
    """
    conn = sqlite3.connect(str(db_path()), timeout=60)
    try:
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _fsync_file(path: Path) -> None:
    with path.open("rb+") as fh:
        os.fsync(fh.fileno())


def _retry_in_use(action: Callable[[], object]) -> None:
    """Run ``action``; retry briefly while Windows reports the file as in use (reader, virus scanner)."""
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            action()
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def _fsync_dir(directory: Path) -> None:
    """Persist a rename on POSIX; Windows cannot open directories (NTFS journals the rename itself)."""
    if os.name == "nt":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def replace_durably(tmp: Path, path: Path) -> None:
    """Flush ``tmp`` to disk and atomically move it over ``path`` (A-139)."""
    # Windows: another process may hold either file open for a moment; anything else is a real error.
    _retry_in_use(lambda: _fsync_file(tmp))
    _retry_in_use(lambda: os.replace(tmp, path))
    _fsync_dir(path.parent)


@contextmanager
def atomic_path(path: Path) -> Iterator[Path]:
    """Yield a temporary sibling of ``path``; when the block succeeds it is synced and renamed onto ``path``.

    A crash, Ctrl-C or power-off therefore leaves either the previous complete file or the new complete file,
    never a truncated or NUL-filled one (A-139). The suffix is kept so writers that infer the format from the
    file name (matplotlib, SB3) behave as for ``path`` itself.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.stem}{TMP_MARKER}{os.getpid()}{path.suffix}")
    try:
        yield tmp
        replace_durably(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically and durably."""
    with atomic_path(path) as tmp:
        tmp.write_bytes(data)


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 text with LF line endings atomically and durably."""
    atomic_write_bytes(path, text.encode("utf-8"))


def write_json(path: Path, data: Any) -> None:
    """Write UTF-8 JSON with LF line endings atomically and durably (A-139)."""
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")


def read_json(path: Path) -> Any:
    """Read UTF-8 JSON; a torn or unreadable file raises :class:`ArtifactError` naming the file."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise ArtifactError(
            f"{path} is damaged or incomplete ({err}); run 'propertyrl doctor' for the repair step",
            details={"path": str(path)},
        ) from err


def record_run(run_id: str, experiment: str, status: str, smoke: bool, run_json: dict[str, Any]) -> None:
    """Insert or update a run row."""
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                experiment,
                status,
                int(smoke),
                run_json.get("start_time_unix", time.time()),
                run_json.get("end_time_unix"),
                json.dumps(run_json, sort_keys=True, default=str),
            ),
        )


def record_checkpoint(run_id: str, step: int, path: Path, sha256: str, kind: str, select_winrate: float | None) -> None:
    """Insert a checkpoint row."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO checkpoints VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, step, str(path), sha256, kind, select_winrate, time.time()),
        )


def record_eval_summary(
    eval_id: str,
    agent_hash: str,
    experiment: str,
    split: str,
    ruleset_id: str,
    n_seeds: int,
    n_games: int,
    opponents: list[str],
    summary: dict[str, Any],
    path: Path,
    smoke: bool,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Insert an evaluation summary row (inside the caller's transaction when ``conn`` is given)."""
    row = (
        eval_id,
        agent_hash,
        experiment,
        split,
        ruleset_id,
        n_seeds,
        n_games,
        json.dumps(opponents),
        json.dumps(summary, sort_keys=True, default=str),
        str(path),
        int(smoke),
        time.time(),
    )
    sql = "INSERT OR REPLACE INTO eval_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    if conn is not None:
        conn.execute(sql, row)
        return
    with connect() as own:
        own.execute(sql, row)


def record_benchmark(bench_id: str, data: dict[str, Any]) -> None:
    """Insert a benchmark row."""
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO benchmarks VALUES (?, ?, ?)",
            (bench_id, time.time(), json.dumps(data, sort_keys=True, default=str)),
        )


def record_gate(gate: str, status: str, data: dict[str, Any]) -> None:
    """Insert a gate status row."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO gates VALUES (?, ?, ?, ?)",
            (gate, status, time.time(), json.dumps(data, sort_keys=True, default=str)),
        )


def query(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Run a read query."""
    with connect() as conn:
        return list(conn.execute(sql, params).fetchall())
