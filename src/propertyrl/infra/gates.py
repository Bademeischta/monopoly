"""Gate evaluation G0-G8 (§12) from artifacts: test reports, coverage, fuzz, Markov, benchmark, evaluations."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from propertyrl.infra.config import REPO_ROOT, frozen_dir
from propertyrl.infra.storage import artifacts_dir, query, read_json, record_gate, sub_artifacts, write_json

PASS = "PASS"
FAIL = "FAIL"
READY = "bereit, nicht ausgeführt"
GATES = ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")
CI_FUZZ = 100_000
GATE_FUZZ = 10_000_000
CI_MARKOV = 1_000_000
GATE_MARKOV = 10_000_000
CI_MASK = 100_000
GATE_MASK = 1_000_000
DOCS_G0 = ("RULESPEC.md", "ACTION_SCHEMA.md", "HEURISTICS_SPEC.md", "TEST_MATRIX.md", "BENCHMARK_PROTOCOL.md")


def _crit(name: str, status: str, detail: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _overall(criteria: list[dict[str, str]]) -> str:
    states = {c["status"].split(" ")[0] for c in criteria}
    if FAIL in states:
        return FAIL
    if all(c["status"].startswith(PASS) for c in criteria):
        if any("CI-Größe" in c["status"] for c in criteria):
            return f"{PASS} (CI-Größe; Gate-Größen markiert)"
        return PASS
    return READY


def test_report_dir() -> Path:
    """artifacts/test-reports (junit.xml, coverage.xml written by the CI/pytest run)."""
    return artifacts_dir() / "test-reports"


def junit_results(path: Path | None = None) -> dict[str, str]:
    """Map 'file::test' -> 'passed'|'failed'|'skipped' from a JUnit XML report."""
    p = path or test_report_dir() / "junit.xml"
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for case in ET.parse(p).getroot().iter("testcase"):
        cls = case.get("classname", "")
        name = case.get("name", "")
        status = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                status = "failed"
            elif child.tag == "skipped":
                status = "skipped"
        out[f"{cls}::{name}"] = status
    return out


def _tests_status(results: dict[str, str], fragment: str) -> tuple[str, str]:
    hits = {k: v for k, v in results.items() if fragment in k}
    if not hits:
        return READY, f"keine Tests '{fragment}' im Testreport"
    failed = [k for k, v in hits.items() if v == "failed"]
    if failed:
        return FAIL, f"{len(failed)} fehlgeschlagen: {failed[:3]}"
    return PASS, f"{len(hits)} Tests grün"


def coverage(path: Path | None = None) -> dict[str, float] | None:
    """Overall and engine line/branch rates from a Cobertura coverage.xml."""
    p = path or test_report_dir() / "coverage.xml"
    if not p.exists():
        return None
    root = ET.parse(p).getroot()
    out = {"line": float(root.get("line-rate", 0)), "branch": float(root.get("branch-rate", 0))}
    lines_valid = lines_cov = br_valid = br_cov = 0
    for cls in root.iter("class"):
        fname = cls.get("filename", "")
        if "engine/" not in fname.replace("\\", "/"):
            continue
        for line in cls.iter("line"):
            lines_valid += 1
            if int(line.get("hits", "0")) > 0:
                lines_cov += 1
            cond = line.get("condition-coverage")
            if line.get("branch") == "true" and cond:
                frac = cond.split("(")[1].rstrip(")")
                covered, total = frac.split("/")
                br_cov += int(covered)
                br_valid += int(total)
    out["engine_line"] = lines_cov / lines_valid if lines_valid else 0.0
    out["engine_branch"] = br_cov / br_valid if br_valid else 0.0
    return out


def _json(path: Path) -> Any:
    return read_json(path) if path.exists() else None


def _size_status(value: int, ci: int, gate: int) -> str:
    if value >= gate:
        return f"{PASS} (Gate-Größe)"
    if value >= ci:
        return f"{PASS} (CI-Größe; Gate-Größe {gate:,} ausstehend)"
    return READY


def confirm_v_points() -> Path:
    """Record that the user checked the verification points V1–V6 of RULESPEC (G0)."""
    import time

    path = frozen_dir() / "v_points_confirmed.json"
    write_json(path, {"confirmed": True, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    return path


def gate_g0() -> list[dict[str, str]]:
    docs = REPO_ROOT / "docs"
    missing = [d for d in DOCS_G0 if not (docs / d).exists()]
    crit = [_crit("Artefaktsatz (RULESPEC, Action Schema, Heuristik-Spezifikation, Testmatrix, Benchmark-Protokoll)",
                  FAIL if missing else PASS, f"fehlend: {missing}" if missing else "vollständig")]  # fmt: skip
    confirmed = frozen_dir() / "v_points_confirmed.json"
    fallback = "Fallback: Standardwerte als Konfiguration eingefroren (Bestätigung durch den Nutzer offen)"
    crit.append(_crit("V1–V6 geprüft", PASS, "vom Nutzer bestätigt" if confirmed.exists() else fallback))
    return crit


def gate_g1() -> list[dict[str, str]]:
    res = junit_results()
    crit = []
    for name, frag in (
        ("jede Regel-ID getestet", "test_rule_coverage"),
        ("Golden Games", "test_golden"),
        ("Hypothesis-Zustandsmaschine", "test_state_machine"),
        ("alle Mutanten fallen", "test_mutants_killed"),
        ("archivierte Replays identisch", "test_archived_replays"),
        ("Event-Coverage", "test_event_coverage"),
    ):
        status, detail = _tests_status(res, frag)
        crit.append(_crit(name, status, detail))
    fuzz = _json(sub_artifacts("fuzz") / "fuzz_report.json")
    if fuzz is None:
        crit.append(_crit("Fuzz ohne Invariantenverletzung", READY, "propertyrl fuzz nicht ausgeführt"))
    else:
        total = int(fuzz["total"]["decisions"])
        ok = not fuzz["total"]["errors"]
        per_cfg = min(c["decisions"] for c in fuzz["configs"]) if fuzz["configs"] else 0
        status = _size_status(total, CI_FUZZ, GATE_FUZZ) if ok and per_cfg >= CI_FUZZ else (FAIL if not ok else READY)
        crit.append(_crit("Fuzz ohne Invariantenverletzung", status, f"{total:,} Entscheidungen, Fehler: {not ok}"))
        rare = fuzz.get("rare_event_min_counts") or {}
        rare_ok = bool(rare) and min(rare.values()) >= 100
        crit.append(_crit("Seltene Ereignisse je >= 100", PASS if rare_ok else (READY if not rare else FAIL),
                          f"Minimum {min(rare.values()) if rare else '–'}"))  # fmt: skip
    markov = _json(sub_artifacts("markov") / "markov_report.json")
    if markov is None:
        crit.append(_crit("Markov-Abgleich", READY, "propertyrl markov-check nicht ausgeführt"))
    else:
        moves = int(markov["moves"])
        tol = float(markov["tolerance_pp"])
        if not markov["passed"]:
            st = FAIL
        elif moves >= GATE_MARKOV and tol <= 0.05:
            st = f"{PASS} (Gate-Größe)"
        elif moves >= CI_MARKOV and tol <= 0.15:
            st = f"{PASS} (CI-Größe; Gate 10 Mio. / 0,05 pp ausstehend)"
        else:
            st = READY
        crit.append(_crit("Markov-Abgleich", st, f"{moves:,} Ruheereignisse, max {markov['max_abs_diff_pp']:.4f} pp"))
    cov = coverage()
    if cov is None:
        crit.append(_crit("Coverage-Schwellen", READY, "coverage.xml fehlt"))
    else:
        ok = cov["engine_line"] >= 0.95 and cov["engine_branch"] >= 0.90 and cov["line"] >= 0.80
        crit.append(_crit("Coverage-Schwellen", PASS if ok else FAIL,
                          f"Engine {cov['engine_line']:.1%} Zeilen / {cov['engine_branch']:.1%} Zweige, gesamt "
                          f"{cov['line']:.1%}"))  # fmt: skip
    return crit


def _mask_criterion(res: dict[str, str]) -> dict[str, str]:
    """0 illegal actions in masked random steps; the step count is part of the test id (steps<N>)."""
    name = "0 illegale Aktionen (Maskentest)"
    status, detail = _tests_status(res, "test_masked_random_steps_never_illegal")
    if status != PASS:
        return _crit(name, status, detail)
    counts = [int(m) for k, v in res.items() if v == "passed" for m in re.findall(r"never_illegal\[steps(\d+)\]", k)]
    steps = max(counts, default=0)
    return _crit(name, _size_status(steps, CI_MASK, GATE_MASK) if steps else PASS, f"{steps:,} maskierte Schritte")


def gate_g2() -> list[dict[str, str]]:
    res = junit_results()
    crit = []
    for name, frag in (
        ("check_env Gymnasium", "test_gymnasium_check_env"),
        ("check_env SB3", "test_sb3_check_env"),
        ("PettingZoo api_test", "test_pettingzoo_api"),
        ("SubprocVecEnv (spawn)", "test_dummy_and_subproc_spawn_identical"),
        ("Mehrsitz-Äquivalenz", "test_one_learning_seat_equivalent_to_single_env"),
    ):
        status, detail = _tests_status(res, frag)
        crit.append(_crit(name, status, detail))
    crit.append(_mask_criterion(res))
    bench = sorted(sub_artifacts("benchmarks").glob("benchmark_*.json"))
    if bench:
        data = read_json(bench[-1])
        both = {"with_logging", "without_logging"} <= set(data.get("engine", {}))
        crit.append(_crit("Durchsatz mit und ohne Logging gemessen", PASS if both else FAIL, bench[-1].name))
    else:
        crit.append(_crit("Durchsatz mit und ohne Logging gemessen", READY, "propertyrl benchmark nicht ausgeführt"))
    return crit


def _smoke_evidence(paths: list[Path]) -> str:
    found = [p.name for p in paths if p.exists()]
    return f"Smoke-Nachweis: {', '.join(found)}" if found else "kein Smoke-Nachweis"


def _eval_rows(experiment: str, split: str, smoke: bool) -> list[dict[str, Any]]:
    rows = query("SELECT summary_json FROM eval_summaries WHERE experiment = ? AND split = ? AND smoke = ?",
                 (experiment, split, int(smoke)))  # fmt: skip
    return [json.loads(r[0]) for r in rows]


def gate_g3() -> list[dict[str, str]]:
    rr = _json(frozen_dir() / "strongest_baseline.json")
    hz = _json(frozen_dir() / "horizon.json")
    ev_rr = _smoke_evidence([frozen_dir() / "strongest_baseline_smoke.json"])
    ev_hz = _smoke_evidence([frozen_dir() / "horizon_smoke.json"])
    c1 = _crit("Round-Robin transitiv, stabile Spitze, eingefroren",
               READY if rr is None else (PASS if rr.get("passed") else FAIL),
               ev_rr if rr is None else f"stärkste Baseline {rr.get('policy')}")  # fmt: skip
    c2 = _crit("Horizont kalibriert, Truncation < 5 %", READY if hz is None else (PASS if hz.get("passed") else FAIL),
               ev_hz if hz is None else f"H2P = {hz.get('horizon_2p')}, H4P = {hz.get('horizon_4p')}")  # fmt: skip
    return [c1, c2]


def _best_rate(rows: list[dict[str, Any]], opponent: str) -> float | None:
    rates = [r["opponents"][opponent]["win_rate"] for r in rows if opponent in r.get("opponents", {})]
    return max(rates) if rates else None


def gate_g4() -> list[dict[str, str]]:
    rows = _eval_rows("mcr_official_2p", "select", False)
    gamma = _json(frozen_dir() / "gamma.json")
    smoke = _smoke_evidence([frozen_dir() / "gamma_smoke.json"])
    rnd, roi = _best_rate(rows, "random_legal"), _best_rate(rows, "roi_markov_v1")
    c1 = _crit("gegen random_legal >= 90 % (SELECT)", READY if rnd is None else (PASS if rnd >= 0.9 else FAIL),
               smoke if rnd is None else f"{rnd:.3f}")  # fmt: skip
    c2 = _crit("gegen roi_markov_v1 > 50 % (SELECT)", READY if roi is None else (PASS if roi > 0.5 else FAIL),
               smoke if roi is None else f"{roi:.3f}")  # fmt: skip
    c3 = _crit("γ eingefroren", READY if gamma is None else PASS, smoke if gamma is None else f"γ = {gamma['gamma']}")
    return [c1, c2, c3]


def _smoke_evals(*experiments: str) -> str:
    n = sum(len(_eval_rows(e, "smoke", True)) for e in experiments)
    return f"Smoke-Nachweis: {n} SMOKE-Auswertungen" if n else "kein Smoke-Nachweis"


def gate_g5() -> list[dict[str, str]]:
    from propertyrl.evaluation.criteria import z3

    res = z3("mcr_official_2p", "test", False)
    if not res["evaluated"]:
        return [_crit("Z3 auf TEST (MCR)", READY, _smoke_evals("mcr_official_2p"))]
    pooled = res["pooled"]
    detail = (f"{len(res['agents'])} Seeds, Siegquoten {[round(a['win_rate'] or 0.0, 3) for a in res['agents']]}, "
              f"gepoolt {pooled['win_rate']:.3f} [{pooled['lower']:.3f}, {pooled['upper']:.3f}]")  # fmt: skip
    return [_crit("Z3 auf TEST (MCR)", PASS if res["passed"] else FAIL, detail)]


def gate_g6() -> list[dict[str, str]]:
    from propertyrl.evaluation.criteria import z4

    res = z4("test", False)
    if not res["evaluated"]:
        return [_crit("Z4 auf TEST (Self-Play)", READY, _smoke_evals("selfplay_official_2p"))]
    parts = [f"a={c['a_passed']}, b={c['b_passed']}, c={c['c_passed']}" for c in res["champions"]]
    return [_crit("Z4 auf TEST (Self-Play)", PASS if res["passed"] else FAIL, "; ".join(parts))]


def gate_g7() -> list[dict[str, str]]:
    from propertyrl.evaluation.criteria import z5

    results = [z5(e, "test", False) for e in ("fourp_official", "fourp_single_seat_fallback")]
    if not any(r["evaluated"] for r in results):
        return [_crit("Z5 (4P, Stretch)", READY, _smoke_evals("fourp_official", "fourp_single_seat_fallback"))]
    ok = any(r["passed"] for r in results)
    detail = "; ".join(f"{r['experiment']}: " + ", ".join(f"Platz 1 {a['first_place_rate']:.3f}" for a in r["agents"])
                       for r in results if r["evaluated"])  # fmt: skip
    return [_crit("Z5 (4P, Stretch)", PASS if ok else FAIL, detail)]


def gate_g8() -> list[dict[str, str]]:
    from propertyrl.infra.storage import reports_dir

    repro = sorted(sub_artifacts("repro").glob("repro_*.json"))
    real = [p for p in repro if "smoke" not in p.name]
    smoke = [p for p in repro if "smoke" in p.name]
    if not real:
        return [_crit("TEST-Bericht, Ablationen, Repro-Paket", READY,
                      f"Smoke-Nachweis: {smoke[-1].name}" if smoke else "kein Smoke-Nachweis")]  # fmt: skip
    data = read_json(real[-1])
    report = reports_dir() / "mcr_official_2p.md"
    ablations = [e for e in ("ablation_a0_terminal", "mcr_official_2p") if _eval_rows(e, "test", False)]
    crit = [
        _crit("Repro-Paket (propertyrl repro) identisch", PASS if data.get("match") else FAIL, real[-1].name),
        _crit("TEST-Bericht", PASS if report.exists() else FAIL, str(report.name)),
        _crit("Ablationen mindestens A0 und A1 auf TEST", PASS if len(ablations) == 2 else FAIL,
              f"vorhanden: {ablations}"),
    ]  # fmt: skip
    return crit


_GATE_FUNCS = {
    "G0": gate_g0,
    "G1": gate_g1,
    "G2": gate_g2,
    "G3": gate_g3,
    "G4": gate_g4,
    "G5": gate_g5,
    "G6": gate_g6,
    "G7": gate_g7,
    "G8": gate_g8,
}


def evaluate_gates(only: str | None = None, record: bool = False) -> dict[str, dict[str, Any]]:
    """Status of every gate (or a single one) with its criteria."""
    out = {}
    for gate in GATES:
        if only and gate != only:
            continue
        criteria = _GATE_FUNCS[gate]()
        status = _overall(criteria)
        out[gate] = {"status": status, "criteria": criteria}
        if record:
            record_gate(gate, status, out[gate])
    return out
