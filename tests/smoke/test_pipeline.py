"""Smoke chain (§9.7, §10): `propertyrl pipeline --smoke-all` runs end-to-end, writes every artifact and
leaves the TEST ledger empty."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

EXPERIMENTS_TRAINED = (
    "mcr_official_2p", "ablation_a0_terminal", "ablation_a2_purdue", "ablation_n4_buy_delegated", "ablation_no_trade",
    "ablation_shared_delegation", "ablation_no_smdp", "fallback_research_2p", "research_shortgame_2p",
    "selfplay_official_2p", "fourp_official", "fourp_single_seat_fallback", "ablation_a3_kingmaking_4p",
)  # fmt: skip


@pytest.mark.slow
def test_smoke_all(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = dict(os.environ, PROPERTYRL_HOME=str(home))
    proc = subprocess.run(
        [sys.executable, "-m", "propertyrl.cli", "pipeline", "--smoke-all"],
        env=env,
        capture_output=True,
        text=True,
        timeout=3 * 3600,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    art = home / "artifacts"
    summary = json.loads((art / "pipeline" / "smoke_all.json").read_text(encoding="utf-8"))
    assert summary["test_ledger_empty"] is True
    assert summary["repro_match"] is True
    for gate in ("G3", "G4", "G5", "G6", "G7", "G8"):
        assert summary["gates"][gate] == "bereit, nicht ausgeführt", (gate, summary["gates"][gate])
    # frozen smoke decisions (never the real files)
    for name in ("strongest_baseline_smoke", "horizon_smoke", "gamma_smoke"):
        assert (art / "frozen" / f"{name}.json").exists(), name
    for name in ("strongest_baseline", "horizon", "gamma"):
        assert not (art / "frozen" / f"{name}.json").exists(), name
    # runs, evaluations, kingmaking, reports, repro
    with sqlite3.connect(art / "propertyrl.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM test_ledger").fetchone()[0] == 0
        experiments = {r[0] for r in conn.execute("SELECT experiment FROM runs WHERE smoke = 1")}
        evals = conn.execute("SELECT split, smoke, path FROM eval_summaries").fetchall()
        assert conn.execute("SELECT COUNT(*) FROM gates").fetchone()[0] >= 9
    assert set(EXPERIMENTS_TRAINED) <= experiments
    assert evals and all(split in ("smoke", "select") and smoke == 1 for split, smoke, _ in evals)
    assert all((Path(path) / "games.parquet").exists() for _, _, path in evals)
    assert list((art / "kingmaking").glob("kingmaking_smoke_*.json"))
    for report in ("mcr_official_2p", "selfplay_official_2p", "fourp_official", "gamma_sweep"):
        text = (home / "reports" / f"{report}_smoke.md").read_text(encoding="utf-8")
        assert "SMOKE – keine Aussagekraft" in text
    assert list((art / "repro").glob("repro_smoke_*.json"))
    assert list((art / "roundrobin").glob("roundrobin_smoke.json"))
