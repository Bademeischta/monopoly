"""`propertyrl doctor`: state check after an interruption, a crash or a power-off (A-142).

Checks the frozen artifacts, seed pools, database (integrity, TEST ledger), training runs, stored evaluations,
other JSON artifacts and leftover temporary files, and names the next runbook step (respecting the G4 and G5
stop rules). Nothing is changed, except that SQLite rolls back an incomplete transaction when the database is
opened (its normal recovery) and ``clean_temp`` deletes leftovers of finished processes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import psutil

from propertyrl.engine.errors import ArtifactError
from propertyrl.engine.hashing import sha256_hex
from propertyrl.infra.config import FROZEN_SOURCES, list_experiments, load_experiment
from propertyrl.infra.storage import TMP_MARKER, connect, home_dir, read_json

log = logging.getLogger(__name__)
ERROR = "FEHLER"
WARN = "WARNUNG"
INFO = "INFO"
OK = "OK"
P1_EXPERIMENTS = (
    "ablation_a0_terminal",
    "ablation_a2_purdue",
    "ablation_n4_buy_delegated",
    "ablation_no_trade",
    "ablation_shared_delegation",
    "ablation_no_smdp",
    "research_shortgame_2p",
)
#: Temporary files younger than this may belong to a write that is still running.
TEMP_MIN_AGE_S = 600


def _finding(level: str, item: str, detail: str, action: str = "") -> dict[str, str]:
    return {"level": level, "item": item, "detail": detail, "action": action}


def _json_state(path: Path) -> str:
    if not path.exists():
        return "fehlt"
    try:
        read_json(path)
    except ArtifactError:
        return "beschädigt"
    return "ok"


def _rel(home: Path, path: Path) -> str:
    return path.relative_to(home).as_posix()


def check_frozen(home: Path) -> list[dict[str, str]]:
    """Frozen artifacts of the runbook steps (and the round-robin table the report reads)."""
    out = []
    files = {name: home / "artifacts" / "frozen" / f"{name}.json" for name in FROZEN_SOURCES}
    files["roundrobin_latest"] = home / "artifacts" / "roundrobin" / "latest.json"
    for name, path in files.items():
        state = _json_state(path)
        source = FROZEN_SOURCES.get(name, FROZEN_SOURCES["strongest_baseline"])
        if state == "beschädigt":
            out.append(_finding(ERROR, _rel(home, path), "beschädigt (unvollständig geschrieben)",
                                f"Datei löschen, dann '{source}' erneut ausführen"))  # fmt: skip
        elif state == "ok":
            out.append(_finding(OK, _rel(home, path), "lesbar"))
    if _json_state(files["strongest_baseline"]) == "ok" and _json_state(files["roundrobin_latest"]) == "fehlt":
        action = f"'{FROZEN_SOURCES['strongest_baseline']}' erneut ausführen (Ergebnis identisch)"
        detail = "fehlt (der Bericht liest die Tabelle daraus)"
        out.append(_finding(WARN, "artifacts/roundrobin/latest.json", detail, action))
    return out


def check_seeds(home: Path) -> list[dict[str, str]]:
    """Seed pool files: readable and equal to the pools of the master seed."""
    from propertyrl.evaluation.seeds import POOL_ORDER, generate_pools

    d = home / "artifacts" / "seeds"
    if not (d / "checksums.json").exists():
        return [_finding(INFO, "artifacts/seeds", "noch nicht erzeugt (entsteht beim ersten Befehl)")]
    expected = generate_pools()
    try:
        checks = read_json(d / "checksums.json")
        pools = {n: [int(x) for x in read_json(d / f"{n.lower()}.json")] for n in POOL_ORDER}
    except (ArtifactError, FileNotFoundError, TypeError, ValueError) as err:
        action = "nichts zu tun: wird beim nächsten Befehl aus dem Master-Seed identisch neu erzeugt"
        return [_finding(WARN, "artifacts/seeds", f"unlesbar ({err})", action)]
    if pools != expected or any(checks.get(n) != sha256_hex(pools[n]) for n in POOL_ORDER):
        return [_finding(ERROR, "artifacts/seeds", "weicht vom Master-Seed ab",
                         "configs/training/seeds.yaml prüfen; nicht weiterarbeiten")]  # fmt: skip
    return [_finding(OK, "artifacts/seeds", "Pools vollständig und prüfsummengleich")]


def check_database(home: Path) -> tuple[list[dict[str, str]], bool]:
    """Integrity of artifacts/propertyrl.db; returns the findings and whether the database can be queried."""
    db = home / "artifacts" / "propertyrl.db"
    has_results = any((home / "runs").glob("*/run.json")) or any((home / "artifacts" / "eval").glob("*"))
    restore = "Sicherung zurückspielen (die Datenbank enthält das TEST-Ledger); bis dahin keine Befehle ausführen"
    if not db.exists() or db.stat().st_size == 0:
        if has_results:
            return [_finding(ERROR, "artifacts/propertyrl.db", "fehlt, obwohl Läufe oder Auswertungen existieren",
                             restore)], False  # fmt: skip
        return [_finding(INFO, "artifacts/propertyrl.db", "noch nicht angelegt")], False
    out = []
    if db.with_name(db.name + "-journal").exists():
        detail = "unvollständige Transaktion eines Abbruchs; SQLite rollt sie beim Öffnen automatisch zurück"
        out.append(_finding(INFO, "artifacts/propertyrl.db-journal", detail))
    try:
        conn = sqlite3.connect(str(db), timeout=60)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = ("runs", "eval_summaries", "test_ledger")
            counts = (
                {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables} if result == "ok" else {}
            )
        finally:
            conn.close()
    except sqlite3.DatabaseError as err:  # not a database, malformed, or tables missing
        out.append(_finding(ERROR, "artifacts/propertyrl.db", f"nicht lesbar ({err})", restore))
        return out, False
    if result != "ok":
        out.append(_finding(ERROR, "artifacts/propertyrl.db", f"integrity_check: {result}", restore))
        return out, False
    out.append(_finding(OK, "artifacts/propertyrl.db",
                        f"intakt ({counts['runs']} Läufe, {counts['eval_summaries']} Auswertungen, "
                        f"{counts['test_ledger']} TEST-Ledger-Einträge)"))  # fmt: skip
    return out, True


def _rerun_hint(meta: dict[str, Any]) -> str:
    from propertyrl.training.train import is_sweep_pilot

    experiment, seed = meta["experiment"], meta.get("training_seed")
    if is_sweep_pilot(meta["run_id"], experiment):
        return "'propertyrl sweep-gamma' erneut starten (fertige Piloten werden übernommen)"
    seeds = load_experiment(experiment).training.seeds if experiment in list_experiments() else []
    if (experiment == "mcr_official_2p" and seed == 1) or seed not in seeds:
        # Step 6 (before G4) and the optional extra seeds train without the pipeline's TEST evaluation.
        return f"'propertyrl train --experiment {experiment} --seed {seed}' erneut starten"
    return f"'propertyrl pipeline --experiment {experiment}' erneut starten"


def check_runs(home: Path) -> list[dict[str, str]]:
    """Training runs: finished, resumable, superseded by a newer attempt, or without an intact checkpoint."""
    from propertyrl.training.callbacks import checkpoint_ok, latest_valid_checkpoint
    from propertyrl.training.train import is_finished

    with connect() as conn:
        rows = conn.execute("SELECT run_id, run_json FROM runs WHERE smoke = 0 ORDER BY started").fetchall()
    metas = [json.loads(raw) for _, raw in rows]
    newest: dict[tuple[Any, ...], str] = {}  # train_or_reuse lets the newest attempt of a configuration decide
    for m in metas:
        newest[(m["experiment"], m.get("training_seed"), m.get("config_hash"))] = m["run_id"]
    out = []
    n_ok = 0
    for meta in metas:
        rdir = home / "runs" / meta["run_id"]
        name = f"runs/{meta['run_id']}"
        key = (meta["experiment"], meta.get("training_seed"), meta.get("config_hash"))
        if _json_state(rdir / "training_state.json") == "beschädigt":
            action = "Sicherung von runs/ zurückspielen; sonst den Lauf mit --new neu beginnen"
            out.append(_finding(ERROR, f"{name}/training_state.json", "beschädigt", action))
            continue
        if is_finished(meta):
            if checkpoint_ok(rdir / "final.zip"):
                n_ok += 1
            else:
                out.append(_finding(ERROR, name, "fertig, aber final.zip fehlt oder ist beschädigt",
                                    "Sicherung von runs/ zurückspielen"))  # fmt: skip
            continue
        steps = f"{meta.get('timesteps_done') or '?'} / {meta.get('total_timesteps')} Schritte"
        if newest[key] != meta["run_id"]:
            out.append(_finding(INFO, name, f"abgebrochen ({meta.get('status')}, {steps}), durch einen neueren "
                                            "Lauf gleicher Konfiguration ersetzt"))  # fmt: skip
            continue
        last = latest_valid_checkpoint(rdir) if rdir.exists() else None
        if last is None:
            out.append(_finding(WARN, name, f"abgebrochen ({meta.get('status')}, {steps}), kein intakter Checkpoint",
                                f"{_rerun_hint(meta)}: der Lauf beginnt dann neu"))  # fmt: skip
        else:
            out.append(_finding(WARN, name, f"abgebrochen ({meta.get('status')}, {steps}), fortsetzbar ab "
                                            f"{last.name}",
                                f"{_rerun_hint(meta)}: er wird fortgesetzt, solange die Konfiguration in configs/ "
                                "unverändert ist"))  # fmt: skip
    known = {m["run_id"] for m in metas}
    for run_json in sorted((home / "runs").glob("*/run.json")):
        rdir = run_json.parent
        trained = (rdir / "final.zip").exists() or any((rdir / "checkpoints").glob("ckpt_*.zip"))
        if rdir.name not in known and not rdir.name.endswith("_smoke") and trained:
            out.append(_finding(ERROR, f"runs/{rdir.name}", "trainierter Lauf ohne Datenbankeintrag "
                                "(Datenbank ersetzt oder verloren?)",
                                "Sicherung von artifacts/propertyrl.db zurückspielen"))  # fmt: skip
    if n_ok:
        out.append(_finding(OK, "runs/", f"{n_ok} fertige Läufe mit intaktem final.zip"))
    return out


def check_evaluations(home: Path) -> list[dict[str, str]]:
    """Stored evaluations: games readable, TEST evaluations in the ledger, directories without a database row."""
    import pyarrow.parquet as pq

    with connect() as conn:
        rows = conn.execute("SELECT eval_id, agent_hash, split, n_games, path, smoke FROM eval_summaries").fetchall()
        ledger = {(a, r) for a, r in conn.execute("SELECT agent_hash, result_id FROM test_ledger").fetchall()}
    out = []
    known = set()
    n_ok = 0
    for eval_id, agent_hash, split, n_games, path, smoke in rows:
        known.add(Path(path).name)
        if smoke:
            continue
        try:
            readable = pq.read_metadata(Path(path) / "games.parquet").num_rows == n_games
        except (OSError, ValueError):
            readable = False
        damaged = "games.parquet fehlt oder ist beschädigt"
        if not readable and split == "test":
            action = "nicht neu auswerten (TEST-Ledger): Sicherung von artifacts/eval zurückspielen"
            out.append(_finding(ERROR, f"artifacts/eval/{eval_id}", damaged, action))
        elif not readable:
            action = "nur für 'propertyrl repro' nötig; Gates und Bericht nutzen die Zusammenfassung"
            out.append(_finding(WARN, f"artifacts/eval/{eval_id}", damaged, action))
        elif split == "test" and (agent_hash, eval_id) not in ledger:
            out.append(_finding(ERROR, f"artifacts/eval/{eval_id}", "TEST-Auswertung ohne TEST-Ledger-Eintrag",
                                "Sicherung von artifacts/propertyrl.db zurückspielen; nicht erneut auf TEST "
                                "auswerten"))  # fmt: skip
        else:
            n_ok += 1
    eval_root = home / "artifacts" / "eval"
    for d in sorted(eval_root.iterdir()) if eval_root.exists() else []:
        if not d.is_dir() or d.name in known or d.name.startswith("smoke_"):
            continue
        if d.name.startswith("test_") and (d / "games.parquet").exists():
            out.append(_finding(WARN, f"artifacts/eval/{d.name}", "vollständige TEST-Spiele ohne Datenbankeintrag",
                                "Wurde die Auswertung kurz vor dem Datenbankeintrag abgebrochen, wiederholt der "
                                "Befehl sie identisch. Fehlen dagegen auch andere Einträge (Datenbank ersetzt), "
                                "die Sicherung von artifacts/propertyrl.db zurückspielen"))  # fmt: skip
        else:
            out.append(_finding(INFO, f"artifacts/eval/{d.name}", "abgebrochene Auswertung ohne Datenbankeintrag; "
                                "wird ignoriert und vom Befehl wiederholt"))  # fmt: skip
    if n_ok:
        out.append(_finding(OK, "artifacts/eval", f"{n_ok} Auswertungen vollständig"))
    return out


def check_other_json(home: Path) -> list[dict[str, str]]:
    """Every other JSON artifact (run metadata, fuzz/markov/benchmark/repro/kingmaking results, summaries)."""
    out = []
    skip = {"frozen", "seeds"}
    root = home / "artifacts"
    candidates = [p for p in root.rglob("*.json") if not set(p.relative_to(root).parts) & skip] if root.exists() else []
    candidates += list((home / "runs").glob("*/run.json"))
    for path in sorted(candidates):
        if TMP_MARKER in path.name or _json_state(path) != "beschädigt":
            continue
        if path.name == "run.json":
            out.append(_finding(WARN, _rel(home, path), "beschädigt; die Kopie in der Datenbank wird verwendet"))
        else:
            out.append(_finding(WARN, _rel(home, path), "beschädigt",
                                "Datei löschen; der Befehl, der sie geschrieben hat, erzeugt sie neu"))  # fmt: skip
    return out


def _writer_alive(path: Path) -> bool:
    """True if the process that wrote this temporary file may still be writing it."""
    pid = path.name.split(TMP_MARKER, 1)[1].split(".", 1)[0]
    if pid.isdigit() and psutil.pid_exists(int(pid)):
        return True
    return time.time() - path.stat().st_mtime < TEMP_MIN_AGE_S


def temp_files(home: Path) -> list[Path]:
    """Temporary files left by writes that a crash or power-off interrupted (not those still being written)."""
    found: list[Path] = []
    for sub in ("artifacts", "runs", "reports"):
        root = home / sub
        if root.exists():
            found += [p for p in root.rglob(f"*{TMP_MARKER}*") if p.is_file() and not _writer_alive(p)]
    return sorted(found)


def _gate_failed(gate: str) -> bool:
    from propertyrl.infra import gates

    crits = {"G4": gates.gate_g4, "G5": gates.gate_g5, "G7": gates.gate_g7}[gate]()
    return any(c["status"].startswith(gates.FAIL) for c in crits)


def _test_agents(experiment: str) -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(DISTINCT agent_hash) FROM eval_summaries WHERE experiment = ? AND "
                           "split = 'test' AND smoke = 0", (experiment,)).fetchone()  # fmt: skip
    return int(row[0])


def _done(experiment: str) -> bool:
    if experiment not in set(list_experiments()):
        return True
    return _test_agents(experiment) >= len(load_experiment(experiment).training.seeds)


def next_step(home: Path, db_ok: bool) -> str:
    """The next runbook step (docs/TRAINING_GUIDE.md) judged from the stored artifacts and the stop rules."""
    from propertyrl.training.train import find_checkpoint

    db = home / "artifacts" / "propertyrl.db"
    has_results = any((home / "runs").glob("*/run.json")) or any((home / "artifacts" / "eval").glob("*"))
    if not db_ok and (has_results or (db.exists() and db.stat().st_size > 0)):
        return "zuerst die Datenbank aus der Sicherung zurückspielen (siehe FEHLER oben), dann doctor erneut"
    if not (home / "artifacts" / "test-reports" / "junit.xml").exists():
        return "Schritt 4: G1/G2 (Testsuite mit Berichten, fuzz, markov-check, Maskentest, benchmark)"
    frozen = home / "artifacts" / "frozen"
    if _json_state(home / "artifacts" / "roundrobin" / "latest.json") != "ok":
        return f"Schritt 5: {FROZEN_SOURCES['strongest_baseline']}"
    for name, step in (("strongest_baseline", 5), ("horizon", 5), ("test_size", 5), ("gamma", 6)):
        if _json_state(frozen / f"{name}.json") != "ok":
            return f"Schritt {step}: {FROZEN_SOURCES[name]}"
    if not db_ok or find_checkpoint("mcr_official_2p", 1, False) is None:
        return "Schritt 6: propertyrl train --experiment mcr_official_2p --seed 1"
    with connect() as conn:
        select = conn.execute("SELECT COUNT(*) FROM eval_summaries WHERE experiment = 'mcr_official_2p' AND "
                              "split = 'select' AND smoke = 0").fetchone()[0]  # fmt: skip
    mcr_tested = _test_agents("mcr_official_2p") > 0
    if not select and not mcr_tested:
        return ("Schritt 6: propertyrl evaluate --agent experiment:mcr_official_2p:1 --split select --experiment "
                "mcr_official_2p, danach propertyrl gates --gate G4")  # fmt: skip
    if not mcr_tested and _gate_failed("G4"):
        return (
            "Schritt 6: G4 nicht bestanden – Stopp-Regel, keine TEST-Auswertung: propertyrl diagnose --run "
            "runs/<Seed-1-Lauf>, Ursache beheben, Schritt 6 wiederholen (ohne Änderung in configs/ mit --new)"
        )
    if not _done("mcr_official_2p"):
        return "Schritt 7: propertyrl pipeline --experiment mcr_official_2p"
    if _gate_failed("G5") and not _done("fallback_research_2p"):
        return ("Schritt 7: G5 nicht bestanden – Fallback: propertyrl pipeline --experiment "
                "ablation_n4_buy_delegated, danach propertyrl pipeline --experiment fallback_research_2p")  # fmt: skip
    for experiment in P1_EXPERIMENTS:
        if not _done(experiment):
            return f"Schritt 8: propertyrl pipeline --experiment {experiment}"
    if not _done("selfplay_official_2p"):
        return "Schritt 9: propertyrl pipeline --experiment selfplay_official_2p"
    if not _done("fourp_official"):
        return "Schritt 10: propertyrl pipeline --experiment fourp_official"
    if _gate_failed("G7") and not _done("fourp_single_seat_fallback"):
        return "Schritt 10: G7 nicht bestanden – propertyrl pipeline --experiment fourp_single_seat_fallback"
    if not _done("ablation_a3_kingmaking_4p"):
        return "Schritt 10: propertyrl pipeline --experiment ablation_a3_kingmaking_4p"
    if not any((home / "artifacts" / "repro").glob("repro_mcr_official_2p_*.json")):
        return ("Schritt 11: propertyrl repro --run <Seed-1-Lauf von mcr_official_2p>, danach propertyrl report "
                "--experiment mcr_official_2p")  # fmt: skip
    return "alle Runbook-Schritte haben Ergebnisse; Gate-Status mit 'propertyrl gates' prüfen"


def doctor(clean_temp: bool = False) -> dict[str, Any]:
    """Run all checks; ``clean_temp`` deletes leftover temporary files of finished processes."""
    home = home_dir()
    findings = check_frozen(home) + check_seeds(home)
    db_findings, db_ok = check_database(home)
    findings += db_findings
    if db_ok:
        findings += check_runs(home) + check_evaluations(home)
    findings += check_other_json(home)
    temps = temp_files(home)
    if temps and clean_temp:
        removed = 0
        for p in temps:
            try:
                p.unlink(missing_ok=True)
                removed += 1
            except PermissionError:  # Windows: still open after all
                log.warning("temporary file %s is in use; skipped", p)
        findings.append(_finding(OK, "Temporärdateien", f"{removed} Reste eines Abbruchs gelöscht"))
    elif temps:
        findings.append(_finding(INFO, "Temporärdateien", f"{len(temps)} Reste eines Abbruchs (harmlos)",
                                 "propertyrl doctor --clean-temp (nur wenn kein propertyrl-Befehl läuft)"))  # fmt: skip
    errors = sum(1 for f in findings if f["level"] == ERROR)
    return {"home": str(home), "findings": findings, "errors": errors, "next_step": next_step(home, db_ok)}
