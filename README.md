# PropertyRL

PropertyRL ist ein Forschungsrepository für Reinforcement Learning in einem regeltreu nachgebildeten
Grundstückshandelsspiel (Regelstand US Classic 2008, neutrale Namen). Es untersucht, **welche Reward- und
Aktionsraum-Formulierung unter identischem Simulator und identischer Evaluation die stärksten und
stabilsten Agenten liefert** (Hauptstudie Reward: A0 terminal, A1 PBRS, A2 Niveau-Reward, A3 Kingmaking-Malus;
Nebenstudie Aktionsabstraktion: Kauf delegiert, ohne Handel, gemeinsame Delegation, ohne SMDP).

Enthalten sind:

- eine deterministische, vollständig getestete Spiel-Engine (nur Standardbibliothek) mit vier Rulesets,
  Knappheitsauktion, Event-Log, Ledger, Invarianten, Replay und Clone,
- Benchmark-Policies (`random_legal`, `greedy_v1`, `roi_markov_v1`, `strong_a_v1`, `strong_b_v1`) und eine
  Delegation für Handel, Auktionen und Schulden,
- Gymnasium-, Mehrsitz- und PettingZoo-Environments mit Masken und SMDP-Semantik,
- SMDP-MaskablePPO mit Curriculum, Self-Play (Champion-Gate, PFSP) und 4-Spieler-Shared-Policy-MARL,
- eine statistisch saubere Evaluation (Duplicate, disjunkte Seed-Pools, TEST-Ledger, Wilson,
  Seed-Cluster-Bootstrap, Holm, Elo, OpenSkill, Kingmaking-Analyse),
- Infrastruktur und CLI (`propertyrl …`) bis zur Gate-Auswertung G0–G8.

<!-- legal-start -->
> **Rechtlicher Hinweis:** Unabhängiges Forschungsprojekt, nicht mit Hasbro verbunden, nicht von Hasbro
> autorisiert; Spielmechaniken nachgebildet, keine geschützten Texte oder Gestaltungen. Keine
> Rechtsberatung; vor einem öffentlichen Release ist eine fachkundige Prüfung nötig. Details und Quellen:
> `docs/LEGAL.md`.
<!-- legal-end -->

## Installation

Voraussetzung: Python 3.11, 3.12 oder 3.13 (prüfen mit `python3.12 --version`). PyTorch wird als CPU-Version
installiert (MLP-Policies laufen auf der CPU; eine GPU ist nicht nötig). Linux, macOS und natives
Windows (PowerShell, ohne WSL) werden unterstützt; Linux und Windows laufen in der CI.

### Linux und macOS

```bash
git clone https://github.com/Bademeischta/monopoly propertyrl && cd propertyrl
python3.12 -m venv .venv            # Ubuntu: sudo apt install python3.12-venv; macOS: brew install python@3.12
source .venv/bin/activate
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu   # macOS: pip install torch genügt
pip install -e ".[dev]"             # Anführungszeichen nötig (zsh)
```

### Windows (PowerShell)

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned      # einmalig, erlaubt Activate.ps1
git clone https://github.com/Bademeischta/monopoly propertyrl; cd propertyrl
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
$env:PYTHONUTF8 = "1"                                    # UTF-8-Ausgabe (auch dauerhaft setzbar)
```

Umgebungsvariablen werden in PowerShell mit `$env:NAME = "wert"` gesetzt (statt `NAME=wert befehl`) und mit
`Remove-Item Env:NAME` wieder entfernt.

Exakt reproduzierbare Umgebung: `pip install -r requirements-lock.txt` (unter Linux x86_64 mit Python 3.12
aufgelöst; torch aus PyPI, dessen CUDA-Laufzeitpakete nur unter Linux installiert werden) und danach
`pip install -e . --no-deps`. Optionale Extras: `.[wandb]` (standardmäßig aus), `.[mutmut]`
(nur Linux/macOS).

## Schnellstart

```bash
propertyrl play --seed 1                          # Textspiel strong_a_v1 gegen strong_b_v1, Log in artifacts/logs/
propertyrl replay --log artifacts/logs/play_OFFICIAL_US_CLASSIC_2008_2p_seed1.jsonl   # Hash-Prüfung
PROPERTYRL_HOME=$HOME/prl_smoke propertyrl pipeline --smoke-all   # Kleinformat, getrennt von echten Ergebnissen
propertyrl gates                                  # Gate-Status G0–G8
pytest -n auto -m "not slow"                      # Testsuite ohne die 30-min-Smoke-Pipeline
```

Die vollständige, geprüfte Schritt-für-Schritt-Anleitung bis zum Abschlussbericht steht in
`docs/TRAINING_GUIDE.md` (mit einem Anhang aller Befehle für Windows-PowerShell).

Als Bibliothek:

```python
from propertyrl.agents import make_policy, respond
from propertyrl.engine import AgentRng, Engine, EngineOptions
from propertyrl.infra import load_setup

rules, board, decks = load_setup("OFFICIAL_US_CLASSIC_2008", 2)
engine = Engine.new(rules, board, decks, 2, 1, EngineOptions())
seats = [make_policy("strong_a_v1"), make_policy("strong_b_v1")]
rngs = [AgentRng(1, 0), AgentRng(1, 1)]
while not engine.is_over() and engine.state.round_index < 300:
    d = engine.pending()
    engine.apply(respond(seats[d.seat], engine, rngs[d.seat]))
print("Sieger:", engine.result().winner)
```

## Experimente in Gate-Reihenfolge

| Gate | Befehl(e) | Ergebnis |
|---|---|---|
| G0 | `propertyrl gates --confirm-v-points` (nach Prüfung von V1–V6 in `docs/RULESPEC.md`) | Artefaktsatz und V-Punkte |
| G1 | `pytest -n auto --cov=propertyrl --cov-branch`, `propertyrl fuzz --total-decisions 10000000 --rare-events`, `propertyrl markov-check --moves 10000000 --tolerance-pp 0.05` | Engine verifiziert |
| G2 | `PROPERTYRL_MASK_STEPS=1000000 pytest tests/env/test_masks_leak.py --junitxml=artifacts/test-reports/junit_env.xml`, `propertyrl benchmark` | Environments, Durchsatz |
| G3 | `propertyrl round-robin`, `propertyrl calibrate-horizon`, `propertyrl power --freeze 2p=1200,4p=250` | stärkste Baseline, Horizont, TEST-Größe |
| G4 | `propertyrl sweep-gamma`, `propertyrl train --experiment mcr_official_2p --seed 1`, `propertyrl evaluate --agent experiment:mcr_official_2p:1 --split select --experiment mcr_official_2p` | γ eingefroren, erster Agent |
| G5 | `propertyrl pipeline --experiment mcr_official_2p` | MCR (Z3) auf TEST |
| P1 | `propertyrl pipeline --experiment <ablation>` für alle Ablationen | Reward- und Aktionsraum-Studie |
| G6 | `propertyrl pipeline --experiment selfplay_official_2p` | Self-Play (Z4) |
| G7 | `propertyrl pipeline --experiment fourp_official` (Fallback `fourp_single_seat_fallback`) | 4P (Z5, Stretch) |
| G8 | `propertyrl repro --run runs/<mcr_s1_run>`, danach `propertyrl report --experiment mcr_official_2p` | Abschlussbericht, Repro-Paket |

Eine ausführliche Anleitung mit Laufzeiten steht in `docs/TRAINING_GUIDE.md`; `propertyrl plan
--experiments all` schätzt die Rechenzeit auf der eigenen Maschine.

## Ordnerstruktur

```text
configs/        Brett, Kartendecks, Rulesets, Policy-Parameter, PPO, Seeds, Experimente, Lizenz-Allowlist
docs/           Spezifikationen und Anleitungen (RULESPEC, ACTION_SCHEMA, OBSERVATION_SCHEMA, HEURISTICS_SPEC,
                TEST_MATRIX, BENCHMARK_PROTOCOL, ARCHITECTURE, API, TRAINING_GUIDE, ROADMAP, RISKS,
                ASSUMPTIONS, LEGAL, DATENSCHUTZ, EXTERNAL_ANCHOR, GLOSSARY, IMPLEMENTATION_PLAN, BUILD_REPORT)
src/propertyrl/ engine/ (Spielregeln), agents/ (Policies), env/ (Environments), training/ (PPO),
                evaluation/ (Statistik, Ledger, Reports), infra/ (Konfiguration, Speicher, Gates), cli.py
tests/          unit, golden, property, fuzz, markov, mutation, env, agents, training, evaluation,
                determinism, architecture, infra, smoke, data/replays
tools/          Generatoren für RULESPEC, TEST_MATRIX, ACTION- und OBSERVATION-Schema
artifacts/      Seeds, eingefrorene Werte, Auswertungen, Benchmarks, Logs, SQLite-Datenbank (nicht versioniert)
runs/           Trainingsläufe mit run.json, Checkpoints, TensorBoard (nicht versioniert)
reports/        Markdown-Berichte mit Grafiken (nicht versioniert)
```

`PROPERTYRL_HOME=<verzeichnis>` verlegt `artifacts/`, `runs/` und `reports/`.

## Reproduzierbarkeit

- **Engine:** zählerbasierter RNG (splitmix64) – gleicher Seed und gleiche Entscheidungen ergeben auf jeder
  Plattform denselben Zustands-Hash; jedes Spiel ist aus seinem Log reproduzierbar
  (`propertyrl replay --log …`), archivierte Replays unter `tests/data/replays/` sichern das ab.
- **Seeds:** disjunkte Pools SELECT/TEST/SMOKE aus Master-Seed 20261007 mit SHA-256-Prüfsummen;
  TRAIN-Seeds kollidieren nie mit ihnen. TEST wird je Agent nur einmal ausgewertet (Ledger).
- **Läufe:** `runs/<run_id>/run.json` enthält Git-Commit, alle Versionen (Engine, Env, Observation,
  Aktionen, Events, Heuristiken), Konfigurations-Hash, Seeds, Pool-Prüfsummen, Paketversionen, Hash von
  `requirements-lock.txt` und Hardware.
- **Ergebnisse:** `propertyrl repro --run runs/<id>` spielt alle gespeicherten Auswertungen eines Laufs
  Spiel für Spiel nach, vergleicht sie und erzeugt den Bericht neu.

## Lizenz

MIT, siehe `LICENSE`. Laufzeitabhängigkeiten werden mit `propertyrl license-check` geprüft.
