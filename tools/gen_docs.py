"""Generate docs/RULESPEC.md, docs/TEST_MATRIX.md, docs/ACTION_SCHEMA.md and docs/OBSERVATION_SCHEMA.md.

Usage: python tools/gen_docs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from rule_scan import REPO, scan_tests  # noqa: E402
from rulespec_data import (  # noqa: E402
    D_RULES,
    H_RULES,
    K_RULES,
    P_RULES,
    R_RULES,
    SRC_D,
    SRC_H,
    SRC_K,
    SRC_PROTOCOL,
    SRC_RULEBOOK,
    V_POINTS,
)

DOCS = REPO / "docs"


def _refs(refs: dict[str, list[str]], rid: str, limit: int = 3) -> str:
    items = refs.get(rid, [])
    if not items:
        return "—"
    shown = [f"`{x}`" for x in items[:limit]]
    if len(items) > limit:
        shown.append(f"(+{len(items) - limit})")
    return "<br>".join(shown)


def _table(rows: list[tuple[str, str]], source: str, refs: dict[str, list[str]]) -> list[str]:
    out = ["| ID | Regeltext | Quelle | Test |", "|---|---|---|---|"]
    for rid, text in rows:
        out.append(f"| {rid} | {text} | {source} | {_refs(refs, rid)} |")
    return out


def rulespec(refs: dict[str, list[str]]) -> str:
    lines = [
        "# RULESPEC v0 – Regelspezifikation PropertyRL",
        "",
        "Diese Spezifikation ist die verbindliche Regelgrundlage der Engine. Jede ID hat mindestens einen Test "
        "(geprüft durch `tests/architecture/test_rule_coverage.py`). Die Spalte „Test“ nennt bis zu drei "
        "Testfälle; die vollständige Zuordnung steht in `docs/TEST_MATRIX.md`. Erzeugt mit "
        "`python tools/gen_docs.py`.",
        "",
        "## Rulesets",
        "",
        "| Ruleset | Inhalt | decision_protocol | auction | trade | scarcity_auction | game_end |",
        "|---|---|---|---|---|---|---|",
        "| OFFICIAL_US_CLASSIC_2008 | R + P + K-01 bis K-04 | official_windows | ascending_open | window_offers "
        "| true | natural |",
        "| RESEARCH_2P_BOUNDED_V1 | zusätzlich D-01 bis D-05 | own_turn_only | sealed_7_levels | "
        "active_player_only | true | natural |",
        "| RESEARCH_2P_SHORTGAME_V1 | wie RESEARCH_2P_BOUNDED_V1 plus D-06 | own_turn_only | sealed_7_levels | "
        "active_player_only | true | short_game (max_rounds = kalibrierter Horizont) |",
        "| TEST_MOVEMENT_ONLY | nur Bewegung (Markov-Test): kein Kauf, keine Miete, keine Steuern, Kartenfelder "
        "ohne Wirkung, Startgeld 1.000.000.000, Kaution immer sofort | own_turn_only | – | none (A-108) | false "
        "| natural |",
        "",
        "Der Safety-Horizon (`safety_horizon_rounds`, Platzhalter 300) wird mit `propertyrl calibrate-horizon` "
        "gesetzt (`artifacts/frozen/horizon.json`); er beendet nie das Spiel, nur die Episode (truncated).",
        "",
        "## Konstanten (§3.1)",
        "",
        "Startgeld 1.500; Gehalt 200; Haft-Kaution 50; Hypothekenzins 10 % aufgerundet (P-05); Bank 32 Häuser "
        "und 12 Hotels; Steuer-1 = 200 fest, Steuer-2 = 100; Spielerzahl 2–8 (Engine), 2–4 (RL-Environments); "
        "die Bank hat unbegrenzt Geld (R-705).",
        "",
        "## Regelkatalog R (beide Modi)",
        "",
        *_table(R_RULES, SRC_RULEBOOK, refs),
        "",
        "## Protokoll-Interpretationen P (beide Modi)",
        "",
        *_table(P_RULES, SRC_PROTOCOL, refs),
        "",
        "## Bekannte Abweichungen K von OFFICIAL",
        "",
        *_table(K_RULES, SRC_K, refs),
        "",
        "## Research-Abweichungen D",
        "",
        *_table(D_RULES, SRC_D, refs),
        "",
        "## Bewusst nicht implementierte Hausregeln H",
        "",
        "Für jede Hausregel prüft ein Test, dass sie **nicht** greift.",
        "",
        *_table(H_RULES, SRC_H, refs),
        "",
        "## V-Punkte (vom Nutzer zu verifizieren, als Konfiguration änderbar)",
        "",
        "| V | Gegenstand | Wert | Hinweis |",
        "|---|---|---|---|",
        *[f"| {v} | {item} | {val} | {hint} |" for v, item, val, hint in V_POINTS],
        "",
        "## Zugablauf (§3.10) als Zustandsmaschine",
        "",
        "1. Zugbeginn; Rundenzähler nach P-15.",
        "2. Handelsangebote des aktiven Sitzes (OFFICIAL P-02, RESEARCH D-03), dann Pre-Roll-Fenster "
        "(PRE_ROLL bzw. JAIL_PRE_ROLL).",
        "3. Wurf; in Haft R-106/R-107; sonst dritter Pasch → R-104, sonst Bewegung, Gehalt, Feldauflösung.",
        "4. Zahlungen über dem Bargeld starten die Schuldenphase (DEBT).",
        "5. Pasch und nicht in Haft → automatischer erneuter Wurf ohne Fenster.",
        "6. OFFICIAL: Angebote und Post-Move-Fenster; RESEARCH: Post-Move-Fenster ohne Angebote.",
        "7. OFFICIAL: Out-of-Turn-Fenster für jeden anderen aktiven Spieler in Sitzreihenfolge.",
        "8. Übergabe an den nächsten aktiven Sitz; R-901 nach jedem Bankrott sofort geprüft.",
        "",
        "Interpretationen, die über den Text hinausgehen, stehen in `docs/ASSUMPTIONS.md` (A-1xx).",
        "",
    ]
    return "\n".join(lines)


def test_matrix(refs: dict[str, list[str]]) -> str:
    ids = [rid for rows in (R_RULES, P_RULES, K_RULES, D_RULES, H_RULES) for rid, _ in rows]
    lines = [
        "# Testmatrix",
        "",
        "Erzeugt mit `python tools/gen_docs.py` aus den Markern `@pytest.mark.rule(...)` und den Golden-Game-"
        "Szenarien.",
        "",
        "## Regel-ID → Tests",
        "",
        "| ID | Tests |",
        "|---|---|",
    ]
    for rid in ids:
        items = refs.get(rid, [])
        lines.append(f"| {rid} | {'<br>'.join(f'`{x}`' for x in items) if items else '—'} |")
    lines += [
        "",
        "## Gate → Tests und Befehle",
        "",
        "| Gate | Kriterium | Tests / Befehl |",
        "|---|---|---|",
        "| G0 | Artefaktsatz liegt vor | `tests/architecture/test_docs.py` |",
        "| G1 | jede Regel-ID getestet | `tests/architecture/test_rule_coverage.py` |",
        "| G1 | Fuzz ohne Invariantenverletzung | `tests/fuzz/test_fuzz.py` (CI 100.000 je Ruleset), "
        "`propertyrl fuzz --decisions 10000000` (Gate) |",
        "| G1 | Markov | `tests/markov/test_markov.py` (CI 1 Mio., 0,15 pp), "
        "`propertyrl markov-check --moves 10000000 --tolerance-pp 0.05` (Gate) |",
        "| G1 | alle Mutanten fallen | `tests/mutation/test_mutants_killed.py` |",
        "| G1 | archivierte Replays identisch | `tests/determinism/test_archived_replays.py` |",
        "| G1 | Coverage-Schwellen | `pytest --cov=propertyrl --cov-branch` + `propertyrl gates --gate G1` |",
        "| G1 | Event-Coverage | `tests/fuzz/test_fuzz.py::test_event_coverage` |",
        "| G1 | Golden Games | `tests/golden/test_golden.py` |",
        "| G1 | Hypothesis | `tests/property/test_state_machine.py` |",
        "| G2 | check_env (Gymnasium, SB3), api_test | `tests/env/test_env_api.py` |",
        "| G2 | 0 illegale Aktionen | `tests/env/test_masks_leak.py` (CI 100.000, Gate 1 Mio. via "
        "`PROPERTYRL_MASK_STEPS=1000000`) |",
        "| G2 | SubprocVecEnv (spawn) | `tests/env/test_vecenv.py` |",
        "| G2 | Mehrsitz-Äquivalenz | `tests/env/test_multiseat.py` |",
        "| G2 | Durchsatz gemessen | `propertyrl benchmark` |",
        "| G3 | Round-Robin, Horizont | `tests/evaluation/test_ratings_harness.py`, `propertyrl round-robin`, "
        "`propertyrl calibrate-horizon` |",
        "| G4 | Sanity auf SELECT, γ eingefroren | `tests/training/test_training_components.py`, "
        "`propertyrl sweep-gamma` |",
        "| G5–G7 | Z3, Z4, Z5 | `tests/evaluation/test_criteria.py` |",
        "| G0–G8 | Gate-Auswertung aus Artefakten | `tests/infra/test_gates_plan_licenses.py` |",
        "| Statistik, Ledger, Seeds | §8 | `tests/evaluation/test_stats.py`, `tests/evaluation/test_ledger_seeds.py` |",
        "| G3–G8 | Pipeline | `tests/smoke/test_pipeline.py` (`propertyrl pipeline --smoke-all`) |",
        "",
    ]
    return "\n".join(lines)


def action_schema() -> str:
    from propertyrl.engine import actions as A
    from propertyrl.engine import constants as C
    from propertyrl.infra.config import load_board
    from propertyrl.versions import ACTION_VERSION

    bd = load_board()
    lines = [
        "# Action Schema v0",
        "",
        f"Aktionsraum `Discrete({A.N_ACTIONS})`, `action_version` **{ACTION_VERSION}**. Erzeugt mit "
        "`python tools/gen_docs.py`.",
        "",
        "## Phasen und legale Aktionen (§3.11)",
        "",
        "| Phase | Legale Aktionen |",
        "|---|---|",
        "| PRE_ROLL | ROLL, BUILD_b, SELL_BUILDING_b, MORTGAGE_p, UNMORTGAGE_p |",
        "| JAIL_PRE_ROLL | ROLL (Pasch-Versuch), PAY_JAIL_FINE (nur jail_attempts 0 oder 1 und Bargeld ≥ 50), "
        "USE_JAIL_CARD (falls vorhanden), Managementaktionen |",
        "| BUY | BUY (Bargeld ≥ Preis), DECLINE, MORTGAGE_p, SELL_BUILDING_b (P-09) |",
        "| POST_MOVE, OUT_OF_TURN | END_PHASE und Managementaktionen |",
        "| DEBT | MORTGAGE_p, SELL_BUILDING_b (P-06) |",
        "| PLACE_BUILDING | nur BUILD_b auf legale Ziele des Auktionsgewinners |",
        "",
        "Legalität: BUILD_b nach R-401 bis R-404 und Bargeld ≥ Hauspreis; SELL_BUILDING_b nach R-405, R-406, "
        "P-08; MORTGAGE_p nach R-501; UNMORTGAGE_p, wenn belastet und Bargeld ≥ Kosten (nur Kapital bei aktivem "
        "interest_prepaid). Jeder Entscheidungspunkt hat mindestens eine legale Aktion. Illegale Aktionen "
        "werfen `IllegalActionError`; die Maske (`action_masks()`) verhindert sie im Training.",
        "",
        "## IDs",
        "",
        "| ID | Name | Feld | Bedeutung |",
        "|---|---|---|---|",
    ]
    meaning = {
        "ROLL": "Würfeln (Pre-Roll) bzw. Pasch-Versuch (Haft)",
        "BUY": "Kauf zum Druckpreis",
        "DECLINE": "Kauf ablehnen, startet die Auktion",
        "END_PHASE": "Post-Move- oder Out-of-Turn-Fenster beenden",
        "PAY_JAIL_FINE": "Kaution zahlen",
        "USE_JAIL_CARD": "Freikarte nutzen",
    }
    for a in range(A.N_ACTIONS):
        kind, idx = A.decode(a)
        if idx < 0:
            lines.append(f"| {a} | {kind} | – | {meaning[kind]} |")
            continue
        if kind in ("BUILD", "SELL_BUILDING"):
            sq = C.BUILD_SQUARES[idx]
            text = "Haus bzw. Hotel bauen" if kind == "BUILD" else "Gebäude verkaufen (halber Preis)"
        else:
            sq = C.PROP_SQUARES[idx]
            text = "belasten" if kind == "MORTGAGE" else "Belastung ablösen"
        lines.append(f"| {a} | {A.action_name(a)} | {sq} ({bd.name(sq)}) | {text} |")
    lines.append("")
    return "\n".join(lines)


def observation_schema() -> str:
    from propertyrl.env.observation import OBS_DIM, OBS_VERSION, obs_schema

    lines = [
        "# Observation Schema",
        "",
        f"Dimension **{OBS_DIM}**, `obs_version` **{OBS_VERSION}** (Basisversion plus Hash über Schema und alle "
        "Normierungskonstanten). Werte float32 in [0, 1]. Ego-zentrisch: Slot 0 = ich, Slots 1–3 = Gegner in "
        "Zugreihenfolge ab dem nächsten Sitz; leere Slots sind 0 mit active = 0. Erzeugt mit "
        "`python tools/gen_docs.py` aus `obs_schema()`; ein Test prüft die Aktualität.",
        "",
        "Keine verstrichene Spielzeit in der Observation (Safety-Horizon nicht lernbar). Leak-Test: Zustände, die "
        "sich nur in rng_epoch, game_seed oder der Reihenfolge der im Zyklus nicht gezogenen Karten "
        "unterscheiden, liefern bitgleiche Observationen.",
        "",
        "| Block | Slice | Länge | Beschreibung | Normierung |",
        "|---|---|---|---|---|",
    ]
    for block in obs_schema():
        lines.append(
            f"| {block['name']} | {block['start']}:{block['stop']} | {block['stop'] - block['start']} | "
            f"{block['description']} | {block['normalization']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    refs = scan_tests()
    DOCS.mkdir(exist_ok=True)
    (DOCS / "RULESPEC.md").write_text(rulespec(refs), encoding="utf-8", newline="\n")
    (DOCS / "TEST_MATRIX.md").write_text(test_matrix(refs), encoding="utf-8", newline="\n")
    (DOCS / "ACTION_SCHEMA.md").write_text(action_schema(), encoding="utf-8", newline="\n")
    try:
        text = observation_schema()
    except ImportError:
        text = None
    if text is not None:
        (DOCS / "OBSERVATION_SCHEMA.md").write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
