"""Logging configuration and error log dumps (§9.4)."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from propertyrl.engine.errors import PropertyRLError
from propertyrl.engine.replay import write_log
from propertyrl.infra.storage import sub_artifacts

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    """Configure console (stderr) logging and an optional per-run log file."""
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) and getattr(h, "_prl", False) for h in root.handlers):
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(_FORMAT))
        console._prl = True  # type: ignore[attr-defined]
        root.addHandler(console)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(fh)


def dump_error_log(err: PropertyRLError, prefix: str = "error") -> Path | None:
    """Write the game log attached to ``err`` to artifacts/errors/ for reproduction."""
    if err.game_log is None:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"{prefix}_{type(err).__name__}_{err.game_seed}_{err.decision_index}_{stamp}.jsonl"
    path = sub_artifacts("errors") / name
    write_log(err.game_log, path)
    logging.getLogger(__name__).error("%s; game log written to %s", err, path)
    return path
