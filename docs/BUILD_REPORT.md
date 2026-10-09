# BUILD_REPORT – PropertyRL 0.1.0

Erstellt am 2026-10-07 im Dateimodus nach Masterplan v1.4. Dieser Bericht dokumentiert jeden ausgeführten
Befehl der Definition of Done (§16) mit Ergebnis und Laufzeit, die aufgelösten Paketversionen, offene
Punkte und die Befehle für die vollen Gate-Läufe des Nutzers.

## 1. Was gebaut wurde

| Bereich | Inhalt |
|---|---|
| Engine (`src/propertyrl/engine`, nur Standardbibliothek, 35 Module) | State-Machine mit Continuation-Stack, vier Rulesets, Knappheitsauktion (P-19), Handel, Schulden/Bankrott, zählerbasierter RNG, Events (e1.0), Ledger, Invarianten, Watchdogs, Log/Replay mit Hashes, Clone, Markov-Ketten, Textdarstellung |
| Agenten (`agents`) | Bewertungsprimitive, `delegation_v1`, `random_legal`, `greedy_v1`, `roi_markov_v1`, `strong_a_v1`, `strong_b_v1`, Anti-Oszillation, Komposition, ε-Beimischung, SB3-Agent, Registry, ExternalAgentAdapter-Schnittstelle |
| Environments (`env`) | Decision Core, Observation 517 (o1.0), Discrete(106) mit MaskedDiscrete (a1.0), Rewards A0–A3, Gymnasium-, Mehrsitz- und PettingZoo-AEC-Env, Gegner-Sampler (Curriculum, Self-Play/PFSP, 4P, Fallback), Factories |
| Training (`training`) | SMDP-MaskablePPO, Mehrsitz-PPO mit SeatChain-Buffer, Callbacks, Resume, γ-Sweep, Self-Play mit Champion-Gate, alle 14 Experimente, Smoke-Modus, Budget, optionales W&B |
| Evaluation (`evaluation`) | Seeds, TEST-Ledger, Harness/Duplicate, Wilson, Seed-Cluster-Bootstrap, Holm, Power, Elo, OpenSkill, Metriken, Zielkriterien Z3/Z4/Z5, Kingmaking, Round-Robin, Horizont, Report |
| Infrastruktur und CLI (`infra`, `cli.py`) | pydantic-Konfiguration, Run-Metadaten, SQLite/JSON/Parquet, Logging, Benchmark (inkl. PPO-Durchsatz), Gates G0–G8, Diagnose, Lizenzprüfung, Planung, Pipelines (`--smoke-all`, `repro`), 20 Befehle |
| Tests (`tests`, 425 Testfälle) | Unit, 19 Golden Games (+ Runner), Hypothesis, Fuzz + seltene Ereignisse, Markov, 17 Mutanten, Determinismus, archivierte Replays, Env, Agenten, Training, Evaluation, Infrastruktur/CLI, Architektur/Doku, Smoke-Pipeline |
| Doku (`docs`, Deutsch) | alle Dokumente aus §11, README, CHANGELOG, CI-Workflow (Linux/Windows × Python 3.11/3.12) |

## 2. Umgebung der Verifikation

| Merkmal | Wert |
|---|---|
| Betriebssystem | Ubuntu 24.04.5 LTS, Kernel 6.18 (Container) |
| CPU | Intel Xeon @ 2,10 GHz, 4 Kerne |
| RAM | 16 GB (Speicher-cgroup) |
| Python | 3.12.3 |
| Virtuelle Umgebung | frisch angelegt mit `python3.12 -m venv`, pip 26.2.1 |
| torch | 2.14.1 aus PyPI (CPU-Betrieb; der CPU-Index `download.pytorch.org/whl/cpu` war aus dieser Umgebung nicht erreichbar, Proxy 403) |

## 3. DoD-Status (§16)

| Nr. | Kriterium | Status | Beleg |
|---|---|---|---|
| 1 | `pip install -e .[dev]` in frischer venv; requirements-lock.txt | ✅ erfüllt | 579 s; `requirements-lock.txt` (83 Pins) aus dieser venv per `pip freeze` |
| 2 | ruff check, ruff format --check, mypy engine+env | ✅ erfüllt | „All checks passed!“, „169 files already formatted“, mypy „no issues found in 45 source files“ |
| 3 | `pytest -n auto --cov=propertyrl --cov-branch` grün, Coverage-Schwellen | ✅ erfüllt | Abschlusslauf 425 passed (§12); Engine 98,4 % Zeilen / 95,7 % Zweige, gesamt 89,2 % Zeilen |
| 4 | Regel-ID-, Event-Coverage-Test, archivierte Replays, alle Mutanten | ✅ erfüllt | Teil des Testlaufs; `propertyrl gates` G1 |
| 5 | Fuzz (alle Rulesets + seltene Ereignisse), Markov 1 Mio./0,15 pp; Gate-Varianten | ✅ erfüllt | CI: 700.000 Entscheidungen fehlerfrei, Markov max 0,048 pp; Gate: 10.999.996 Entscheidungen fehlerfrei, Markov 10 Mio. max 0,0134 pp |
| 6 | check_env (Gymnasium, SB3), api_test, MaskedDiscrete, Maskentest, Leak, SubprocVecEnv spawn, Mehrsitz-Äquivalenz | ✅ erfüllt | Testlauf; Maskentest zusätzlich in Gate-Größe (1.000.000 Schritte) |
| 7 | `propertyrl benchmark`, JSON, Empfehlung | ✅ erfüllt | `artifacts/benchmarks/benchmark_20261007-155644.json`, Empfehlung siehe §7 |
| 8 | `propertyrl pipeline --smoke-all` vollständig, Artefakte, Ledger leer | ✅ erfüllt | 1.686,6 s (28,1 min) auf 4 Kernen, `test_ledger_empty: true`, `repro_match: true` |
| 9 | `play --seed 1`, `replay --log …`, Hash identisch | ✅ erfüllt | Hash `5a8b4863…84d4`, „Replay identisch: True“ |
| 10 | `propertyrl gates`: G0–G2 PASS, G3–G8 „bereit, nicht ausgeführt“ mit Smoke-Nachweis | ✅ erfüllt | G1 und G2 sogar in Gate-Größe (siehe §9) |
| 11 | Alle Dokumente aus §11, README-Befehle getestet | ✅ erfüllt | `tests/architecture/test_docs.py` (Existenz, Vollständigkeit R01–R36/A-01–A-36, Python-Beispiele aus API.md und README.md werden ausgeführt); CLI-Befehle der README im DoD-Lauf ausgeführt |
| 12 | Keine Platzhalter | ✅ erfüllt | `grep` findet nur die 7 erlaubten `raise NotImplementedError` der abstrakten ExternalAgentAdapter-Schnittstelle (§5.8) |
| 13 | BUILD_REPORT | ✅ erfüllt | dieses Dokument |

## 4. Ausgeführte Befehle, Ergebnisse, Laufzeiten

Alle Befehle liefen in der frischen venv aus §2 im Repository-Wurzelverzeichnis (`PROPERTYRL_HOME` =
Repository), die Testsuite mit privatem temporären `PROPERTYRL_HOME` (conftest).

| Befehl | Ergebnis | Laufzeit |
|---|---|---|
| `python3.12 -m venv … && pip install --upgrade pip && pip install -e ".[dev]"` | Exit 0 | 579 s |
| `pip freeze --exclude-editable` → `requirements-lock.txt` | 83 Pins, CUDA-Wheels mit Marker `sys_platform == "linux"` | < 1 s |
| `ruff check .` | All checks passed! | < 1 s |
| `ruff format --check .` | 169 files already formatted | < 1 s |
| `mypy --no-incremental src/propertyrl/engine src/propertyrl/env` | Success: no issues found in 45 source files | 18 s |
| `pytest -n auto --cov=propertyrl --cov-branch --cov-report=xml:… --junitxml=…` (1. Lauf) | 423 passed, 1 failed (BUILD_REPORT.md fehlte zu diesem Zeitpunkt noch) | 1.868 s |
| `propertyrl fuzz --decisions 100000 --rare-events` | 700.000 Entscheidungen, 0 Fehler | 27 s |
| `propertyrl markov-check --moves 1000000 --tolerance-pp 0.15` | passed, max 0,0477 pp (Feld 15) | 22 s |
| `propertyrl benchmark` (1. Versuch) | Exit 137: OOM-Kill bei 64 SubprocVecEnv-Workern (je ≈ 230 MB) → behoben (A-134) | 135 s |
| `propertyrl pipeline --smoke-all` | Exit 0, alle Stufen, Ledger leer, Repro identisch | 1.748 s (intern 1.686,6 s) |
| `propertyrl play --seed 1` | Sieger Sitz 0 (`strong_a_v1`), 44 Runden, 2.136 Entscheidungen | < 1 s |
| `propertyrl replay --log artifacts/logs/play_OFFICIAL_US_CLASSIC_2008_2p_seed1.jsonl` | Replay identisch: True | < 1 s |
| `propertyrl license-check` | 53 Laufzeitpakete, 0 Verstöße, 0 unbekannt ohne Allowlist | 3 s |
| `propertyrl plan --experiments all` (1. Versuch) | maß fälschlich Smoke-Läufe (199 Schritte/s) → behoben, Smoke-Läufe ausgeschlossen | 3 s |
| `PROPERTYRL_MASK_STEPS=1000000 pytest -q tests/env/test_masks_leak.py --junitxml=…/junit_env.xml` | 3 passed (1.000.000 maskierte Schritte, 0 illegal) | 214 s |
| `propertyrl markov-check --moves 10000000 --tolerance-pp 0.05` (1. Versuch) | EngineWatchdogError (2 Mio. Entscheidungen je Spiel) → behoben: Stichprobe läuft über mehrere Spiele | 26 s |
| `propertyrl fuzz --total-decisions 10000000 --rare-events --rare-decisions 1000000` | 10.999.996 Entscheidungen, 0 Fehler, seltene Ereignisse ≥ 1.297 | 420 s |
| `propertyrl markov-check --moves 10000000 --tolerance-pp 0.05` | passed, max 0,0134 pp (Feld 22) | 216 s |
| `propertyrl benchmark` | Exit 0, JSON geschrieben | 89 s |
| `propertyrl plan --experiments all` | 106,4 h Training + 23,7 h Evaluation (18,2 %), keine Warnung | 4 s |
| `propertyrl gates` | G0–G2 PASS (Gate-Größe), G3–G8 bereit, nicht ausgeführt | 1 s |
| `grep -rn "TODO\|NotImplementedError\|FIXME" src/` | nur 7 Treffer in `agents/external.py` (abstrakte Schnittstelle) | < 1 s |
| `pytest -n auto --cov=…` (Abschlusslauf) | 425 passed, 0 failed | 1.836 s |

## 5. Testsuite und Coverage

Erster vollständiger Lauf (1.868 s, 4 xdist-Worker): 424 Testfälle, 423 grün, 1 rot
(`test_document_exists[BUILD_REPORT.md]`, weil dieses Dokument erst am Ende entsteht).

| Bereich | Tests | Summe Laufzeit |
|---|---|---|
| unit | 195 | 4,3 s |
| golden | 20 | 0,2 s |
| property (Hypothesis) | 1 | 3,7 s |
| fuzz | 8 | 144,5 s |
| markov | 5 | 132,1 s |
| mutation | 19 | 13,1 s |
| determinism | 9 | 2,3 s |
| env | 41 | 188,8 s |
| agents | 22 | 40,7 s |
| training | 13 | 15,1 s |
| evaluation | 37 | 18,4 s |
| infra | 17 | 14,3 s |
| architecture | 36 | 6,2 s |
| smoke (`pipeline --smoke-all` im Subprozess) | 1 | 1.671,5 s |

Coverage (Cobertura, `artifacts/test-reports/coverage.xml`): Engine 98,40 % Zeilen und 95,69 % Zweige
(Schwelle 95 % / 90 %), gesamt 89,14 % Zeilen und 82,21 % Zweige (Schwelle 80 %).

Abschlusslauf nach Fertigstellung dieses Berichts: siehe §12.

## 6. Fuzzing und Markov

CI-Größe (`--decisions 100000 --rare-events`):

| Konfiguration | Entscheidungen | Spiele | Fehler | Invariantenverletzungen |
|---|---|---|---|---|
| OFFICIAL 2P | 100.000 | 79 | 0 | 0 |
| OFFICIAL 4P | 100.000 | 36 | 0 | 0 |
| OFFICIAL 8P | 100.000 | 18 | 0 | 0 |
| RESEARCH_2P_BOUNDED_V1 | 100.000 | 61 | 0 | 0 |
| RESEARCH_2P_SHORTGAME_V1 | 100.000 | 61 | 0 | 0 |
| TEST_MOVEMENT_ONLY | 100.000 | 25 | 0 | 0 |
| Seltene-Ereignis-Generatoren | 100.000 | 777 | 0 | 0 |

Seltene Ereignisse (Minimum je Typ, CI): Knappheitsauktion gestartet 3.858, gewonnen 3.841, Gruppenabbau
339, Hotel gebaut 2.034, Freikarte genutzt 179, Bankrott 174, Vermögensübertrag 174, Zins gezahlt 1.187,
Schuld beglichen 146, Handel ausgeführt 1.044; 43 Event-Typen insgesamt beobachtet.

Gate-Größe (`--total-decisions 10000000 --rare-events --rare-decisions 1000000`): je Konfiguration
1.666.666 Entscheidungen, zusammen mit den seltenen Ereignissen 10.999.996, keine Fehler; Minimum der
seltenen Ereignisse 1.297 (Schuld beglichen).

Markov (TEST_MOVEMENT_ONLY, exakte Kette gegen Engine): 1 Mio. Ruheereignisse max. Abweichung 0,0477 pp
(Toleranz 0,15); 10 Mio. Ruheereignisse max. Abweichung 0,0134 pp (Toleranz 0,05).

## 7. Benchmark und Empfehlung (`benchmark_20261007-155644.json`)

| Messung | Ohne Event-Logging | Mit Event-Logging |
|---|---|---|
| Engine allein (strong_a gegen strong_b) | 10,6 Spiele/s, 23.285 Entscheidungen/s, p50 0,079 s, p95 0,181 s | 9,5 Spiele/s, 20.817 Entscheidungen/s, p50 0,082 s, p95 0,215 s |
| Gym-Env (1 Lernsitz, Zufallsaktionen) | 4.032 Schritte/s | 3.678 Schritte/s |

| n_envs | DummyVecEnv Schritte/s | SubprocVecEnv Schritte/s |
|---|---|---|
| 1 | 3.868 | 1.575 |
| 4 | 4.467 | 2.275 |
| 8 | 4.758 | 2.878 |
| 16 | 3.577 | 3.289 |
| 32, 64 | – | übersprungen (Speicher, A-134) |

PPO-Trainingsdurchsatz inklusive Updates (SMDP-MaskablePPO, ppo_default.yaml, 4 Envs): **1.034
Schritte/s**. **Empfehlung:** `vec_env: dummy`, `n_envs` = Kernzahl (hier 4; `ppo_default.yaml` kappt die
16 auf die Kernzahl). SubprocVecEnv lohnt erst bei mehr Kernen. Daraus folgt für einen MCR-Lauf mit 10 Mio.
Schritten ≈ 2,7 h Training plus ≈ 0,7 h Evaluation; `propertyrl plan --experiments all` ergibt 106,4 h
Training und 23,7 h Evaluation (Anteil 18,2 % < 20 %), kein Run über 12 h.

## 8. Smoke-Pipeline (`propertyrl pipeline --smoke-all`)

Gesamt 1.686,6 s (28,1 min) auf 4 Kernen, Ziel < 30 min erreicht. Ergebnis
(`artifacts/pipeline/smoke_all.json`): stärkste Baseline (Smoke, 10 Seeds je Block) `roi_markov_v1`,
Horizont 2P 114 Runden (Smoke), γ = 0,995, 0 Champion-Wechsel, Kingmaking-Rate 0,0, `repro_match: true`,
`test_ledger_empty: true`. Alle Ergebnisse tragen „SMOKE – keine Aussagekraft“.

| Stufe | s | Stufe | s |
|---|---|---|---|
| round_robin | 12,5 | calibrate_horizon | 71,6 |
| sweep_gamma (3 Piloten) | 142,2 | train_mcr | 102,9 |
| evaluate_select | 18,4 | evaluate_smoke | 67,0 |
| train/evaluate A0 | 41,2 / 59,2 | train/evaluate A2 | 32,3 / 52,4 |
| train/evaluate N4 | 37,7 / 54,2 | train/evaluate ohne Handel | 49,6 / 69,3 |
| train/evaluate gemeinsame Delegation | 53,4 / 74,5 | train/evaluate ohne SMDP | 40,6 / 55,5 |
| train/evaluate fallback_research_2p | 44,8 / 66,9 | train/evaluate research_shortgame_2p | 30,9 / 60,1 |
| selfplay (Champion-Gate) | 122,4 | evaluate_selfplay | 115,0 |
| train/evaluate fourp_official | 20,6 / 13,9 | train/evaluate fourp_single_seat_fallback | 29,0 / 13,5 |
| train/evaluate A3 (4P) | 41,2 / 33,3 | kingmaking | 4,4 |
| reports (4) | 1,1 | repro | 55,1 |

## 9. Gate-Status (`propertyrl gates`)

```text
G0: PASS
    - Artefaktsatz (RULESPEC, Action Schema, Heuristik-Spezifikation, Testmatrix, Benchmark-Protokoll): PASS (vollständig)
    - V1–V6 geprüft: PASS (Fallback: Standardwerte als Konfiguration eingefroren (Bestätigung durch den Nutzer offen))
G1: PASS
    - jede Regel-ID getestet: PASS (3 Tests grün)
    - Golden Games: PASS (20 Tests grün)
    - Hypothesis-Zustandsmaschine: PASS (1 Tests grün)
    - alle Mutanten fallen: PASS (19 Tests grün)
    - archivierte Replays identisch: PASS (7 Tests grün)
    - Event-Coverage: PASS (1 Tests grün)
    - Fuzz ohne Invariantenverletzung: PASS (Gate-Größe) (10,999,996 Entscheidungen, Fehler: False)
    - Seltene Ereignisse je >= 100: PASS (Minimum 1297)
    - Markov-Abgleich: PASS (Gate-Größe) (10,000,000 Ruheereignisse, max 0.0134 pp)
    - Coverage-Schwellen: PASS (Engine 98.4% Zeilen / 95.7% Zweige, gesamt 89.1%)
G2: PASS
    - check_env Gymnasium: PASS (1 Tests grün)
    - check_env SB3: PASS (1 Tests grün)
    - PettingZoo api_test: PASS (2 Tests grün)
    - SubprocVecEnv (spawn): PASS (1 Tests grün)
    - Mehrsitz-Äquivalenz: PASS (1 Tests grün)
    - 0 illegale Aktionen (Maskentest): PASS (Gate-Größe) (1,000,000 maskierte Schritte)
    - Durchsatz mit und ohne Logging gemessen: PASS (benchmark_20261007-155644.json)
G3: bereit, nicht ausgeführt
    - Round-Robin transitiv, stabile Spitze, eingefroren: bereit, nicht ausgeführt (Smoke-Nachweis: strongest_baseline_smoke.json)
    - Horizont kalibriert, Truncation < 5 %: bereit, nicht ausgeführt (Smoke-Nachweis: horizon_smoke.json)
G4: bereit, nicht ausgeführt
    - gegen random_legal >= 90 % (SELECT): bereit, nicht ausgeführt (Smoke-Nachweis: gamma_smoke.json)
    - gegen roi_markov_v1 > 50 % (SELECT): bereit, nicht ausgeführt (Smoke-Nachweis: gamma_smoke.json)
    - γ eingefroren: bereit, nicht ausgeführt (Smoke-Nachweis: gamma_smoke.json)
G5: bereit, nicht ausgeführt
    - Z3 auf TEST (MCR): bereit, nicht ausgeführt (Smoke-Nachweis: 1 SMOKE-Auswertungen)
G6: bereit, nicht ausgeführt
    - Z4 auf TEST (Self-Play): bereit, nicht ausgeführt (Smoke-Nachweis: 1 SMOKE-Auswertungen)
G7: bereit, nicht ausgeführt
    - Z5 (4P, Stretch): bereit, nicht ausgeführt (Smoke-Nachweis: 2 SMOKE-Auswertungen)
G8: bereit, nicht ausgeführt
    - TEST-Bericht, Ablationen, Repro-Paket: bereit, nicht ausgeführt (Smoke-Nachweis: repro_smoke_mcr_official_2p_s1_20261007-151600_12746_smoke.json)
```

G1 und G2 wurden damit nicht nur in CI-Größe, sondern in Gate-Größe nachgewiesen. G0 steht auf dem
dokumentierten Fallback, bis der Nutzer V1–V6 bestätigt (`propertyrl gates --confirm-v-points`).

## 10. Aufgelöste Paketversionen (`requirements-lock.txt`)

Kern: torch 2.14.1, stable-baselines3 2.9.0, sb3-contrib 2.9.0, gymnasium 1.4.0, pettingzoo 1.27.0,
numpy 2.5.3, scipy 1.18.1, pandas 3.0.6, pyarrow 25.0.1, pydantic 2.13.5, PyYAML 6.0.3, openskill 6.2.0,
tensorboard 2.21.0, matplotlib 3.11.2, psutil 7.2.2. Entwicklung: pytest 9.1.1, pytest-cov 7.1.0,
pytest-xdist 3.8.0, hypothesis 6.168.5, ruff 0.16.10, mypy 2.4.0, pip-licenses 5.5.5, types-PyYAML
6.0.12.20260906.

Vollständige Liste:

```text
Farama-Notifications==0.0.6
Jinja2==3.1.6
Markdown==3.11
MarkupSafe==3.0.4
PyYAML==6.0.3
Pygments==2.21.0
Werkzeug==3.1.9
absl-py==2.5.0
annotated-types==0.8.0
ast_serialize==0.12.1
cloudpickle==3.1.2
contourpy==1.4.0
coverage==7.16.2
cuda-bindings==13.4.3 ; sys_platform == "linux"
cuda-pathfinder==1.8.3 ; sys_platform == "linux"
cuda-toolkit==13.0.3.0 ; sys_platform == "linux"
cycler==0.12.1
execnet==2.1.2
filelock==4.0.12
fonttools==4.66.1
fsspec==2026.9.0
grpcio==1.84.0
gymnasium==1.4.0
hypothesis==6.168.5
iniconfig==2.3.1
kiwisolver==1.5.1
librt==0.16.0
matplotlib==3.11.2
mpmath==1.3.0
mypy==2.4.0
mypy_extensions==1.1.0
networkx==3.7
numpy==2.5.3
nvidia-cublas==13.1.1.3 ; sys_platform == "linux"
nvidia-cuda-cupti==13.0.85 ; sys_platform == "linux"
nvidia-cuda-nvrtc==13.0.88 ; sys_platform == "linux"
nvidia-cuda-runtime==13.0.96 ; sys_platform == "linux"
nvidia-cudnn-cu13==9.24.0.43 ; sys_platform == "linux"
nvidia-cufft==12.0.0.61 ; sys_platform == "linux"
nvidia-cufile==1.15.1.6 ; sys_platform == "linux"
nvidia-curand==10.4.0.35 ; sys_platform == "linux"
nvidia-cusolver==12.0.4.66 ; sys_platform == "linux"
nvidia-cusparse==12.6.3.3 ; sys_platform == "linux"
nvidia-cusparselt-cu13==0.8.1 ; sys_platform == "linux"
nvidia-nccl-cu13==2.30.7 ; sys_platform == "linux"
nvidia-nvjitlink==13.4.92 ; sys_platform == "linux"
nvidia-nvshmem-cu13==3.4.5 ; sys_platform == "linux"
nvidia-nvtx==13.0.85 ; sys_platform == "linux"
openskill==6.2.0
packaging==26.3
pandas==3.0.6
pathspec==1.1.1
pettingzoo==1.27.0
pillow==12.3.0
pip-licenses==5.5.5
pluggy==1.6.0
prettytable==3.18.0
protobuf==7.36.2
psutil==7.2.2
pyarrow==25.0.1
pydantic==2.13.5
pydantic_core==2.46.5
pyparsing==3.3.3
pytest-cov==7.1.0
pytest-xdist==3.8.0
pytest==9.1.1
python-dateutil==2.9.0.post0
ruff==0.16.10
sb3_contrib==2.9.0
scipy==1.18.1
setuptools==84.0.0
six==1.17.0
sortedcontainers==2.4.0
stable_baselines3==2.9.0
sympy==1.14.0
tensorboard-data-server==0.7.2
tensorboard==2.21.0
torch==2.14.1
triton==3.8.0 ; sys_platform == "linux"
types-PyYAML==6.0.12.20260906
typing-inspection==0.4.4
typing_extensions==4.16.0
wcwidth==0.9.2
```

## 11. Offene Punkte und Abweichungen

1. **G3–G8 (volle Läufe)** sind wie beauftragt als lauffähige Pipeline mit Smoke-Nachweis geliefert; die
   vollen Läufe (Round-Robin, Horizont, γ-Sweep, MCR, Ablationen, Self-Play, 4P, Abschlussbericht) startet
   der Nutzer (Befehle in §13, Laufzeiten in §7 und `docs/TRAINING_GUIDE.md`).
2. **V1–V6** sind noch nicht vom Nutzer bestätigt; G0 steht auf dem dokumentierten Fallback
   „Standardwerte eingefroren“.
3. **CPU-torch:** Der PyTorch-CPU-Index war aus der Build-Umgebung nicht erreichbar (Proxy 403). torch
   2.14.1 kam deshalb aus PyPI (CUDA-Build, läuft auf der CPU; die CUDA-Laufzeitpakete stehen im Lockfile
   mit Linux-Marker). README und CI verwenden weiterhin den CPU-Index.
4. **Windows/macOS** wurden in dieser Umgebung nicht ausgeführt; die CI-Matrix (`.github/workflows/ci.yml`)
   enthält windows-latest, und der spawn-Test für SubprocVecEnv läuft bereits unter Linux mit `spawn`.
5. **Während der Verifikation behobene Befunde:** (a) Benchmark mit 64 SubprocVecEnv-Workern überschritt
   16 GB → Workerzahl wird nach verfügbarem Speicher begrenzt (A-134); (b) `plan` nutzte Smoke-Läufe als
   Durchsatzmessung → ausgeschlossen, zusätzlich echter PPO-Durchsatz im Benchmark; (c) Markov-Gate-Lauf mit
   10 Mio. Ereignissen löste den Spiel-Watchdog aus → Stichprobe läuft über mehrere Spiele (Test ergänzt);
   (d) Smoke-SELECT-Auswertung wurde als echte Auswertung gespeichert → als Smoke markiert (A-127).
6. **Zusätzliche Annahmen** A-101 bis A-134 stehen in `docs/ASSUMPTIONS.md`.

## 12. Abschlusslauf der Testsuite

Wird nach dem Schreiben dieses Berichts mit identischem Befehl wiederholt
(`pytest -n auto --cov=propertyrl --cov-branch --cov-report=xml:artifacts/test-reports/coverage.xml
--junitxml=artifacts/test-reports/junit.xml`); das Ergebnis steht unten.

**Ergebnis: 425 passed, 0 failed, 4 Warnungen (PettingZoo-Hinweis „Observation is not a NumPy array“ für
die Dict-Observation des AEC-Envs) in 1.836 s (30,6 min).** Coverage: Engine 98,41 % Zeilen und 95,70 %
Zweige, gesamt 89,17 % Zeilen und 82,23 % Zweige. Der anschließende `propertyrl gates`-Lauf liest diese
Berichte und meldet unverändert G0–G2 PASS (G1/G2 in Gate-Größe) und G3–G8 „bereit, nicht ausgeführt“.

## 13. Befehle für die vollen Gate-Läufe (Nutzer)

Die vollständige, gegen den Code geprüfte Schritt-für-Schritt-Anleitung (inklusive Windows-Varianten,
Stopp-Regeln, Fallbacks, Wiederaufnahme nach Abbrüchen und Laufzeiten) steht in `docs/TRAINING_GUIDE.md`.
Kurzfassung für Linux/macOS/WSL2, strikt in dieser Reihenfolge, lange Schritte in `tmux`:

```bash
propertyrl gates --confirm-v-points                                       # G0 nach Prüfung von V1–V6
pytest -n auto -m "not slow" --cov=propertyrl --cov-branch \
       --cov-report=xml:artifacts/test-reports/coverage.xml --junitxml=artifacts/test-reports/junit.xml
propertyrl fuzz --total-decisions 10000000 --rare-events --rare-decisions 1000000
propertyrl markov-check --moves 10000000 --tolerance-pp 0.05
PROPERTYRL_MASK_STEPS=1000000 pytest tests/env/test_masks_leak.py --junitxml=artifacts/test-reports/junit_env.xml
propertyrl benchmark && propertyrl plan --experiments all && propertyrl gates   # G1/G2
propertyrl round-robin && propertyrl calibrate-horizon && propertyrl power --freeze 2p=1200,4p=250   # G3
propertyrl sweep-gamma
propertyrl train --experiment mcr_official_2p --seed 1
propertyrl evaluate --agent experiment:mcr_official_2p:1 --split select --experiment mcr_official_2p
propertyrl gates --gate G4                                                 # nur bei PASS weiter
propertyrl pipeline --experiment mcr_official_2p && propertyrl gates --gate G5
for e in ablation_a0_terminal ablation_a2_purdue ablation_n4_buy_delegated ablation_no_trade \
         ablation_shared_delegation ablation_no_smdp research_shortgame_2p; do
  propertyrl pipeline --experiment $e
done
propertyrl pipeline --experiment selfplay_official_2p && propertyrl gates --gate G6
propertyrl pipeline --experiment fourp_official && propertyrl gates --gate G7
propertyrl pipeline --experiment ablation_a3_kingmaking_4p
propertyrl repro --run "$(ls -d runs/mcr_official_2p_s1_* | sort | tail -1)"
propertyrl report --experiment mcr_official_2p
propertyrl license-check && propertyrl gates                               # G8
```

## 14. Nachträge nach der Übergabe

Eine Prüfung der Nutzer-Anleitung gegen den Code (fünf unabhängige Reviews) ergab folgende Korrekturen,
die nach dem Abschlusslauf eingearbeitet wurden:

1. **Windows-CI:** Beide Windows-Jobs scheiterten an `ruff format --check`, weil Git unter Windows mit CRLF
   auscheckt. Neu: `.gitattributes` (`* text=auto eol=lf`). Linux-Jobs waren grün.
2. **G3** misst die Truncation-Bedingung an der 2P-Kalibrierung (§8.10); 4P wird separat berichtet (A-135).
   Im Smoke-Lauf endeten 8 von 24 4P-Spielen nicht innerhalb von 5.000 Runden – ein Befund für G7.
3. **`propertyrl pipeline` ist wiederholbar** (A-136): gleiche Konfiguration → Lauf wiederverwenden,
   unterbrochener Lauf → fortsetzen, vorhandene Auswertung → nicht wiederholen. Dadurch übernimmt die
   G5-Pipeline den Seed-1-Lauf aus G4 (spart ~3,4 h).
4. **Z3** zählt nur die konfigurierten Trainingsseeds (A-137); Checkpoint-Suche ignoriert γ-Piloten und
   unfertige Läufe.
5. **`evaluate --experiment`** übernimmt Gegner, Ruleset und Spielerzahl des Experiments; doppelte Gegner
   werden entfernt; die Ausgabe nennt den verwendeten Checkpoint (A-138).
6. **Kleinere Korrekturen:** Smoke-Round-Robin überschreibt nicht mehr `roundrobin/latest.json`; G8 liest
   die neueste Repro-Datei; `--smoke-all` prüft „Ledger unverändert“ statt „Ledger leer“; `round-robin
   --policies` für den G3-Fallback; UTF-8-Ausgabe der CLI unter Windows; README-Installation (Anführungszeichen
   bei `".[dev]"`, `python -m pip`, Python-3.12-Auswahl, PowerShell-Varianten).

### Nachtrag 2: Robustheit gegen Abbruch, Absturz und Stromausfall

Beim ersten Volllauf auf einem Windows-Rechner wurde der PC während Schritt 5 ausgeschaltet. Eine Prüfung
aller Schreib- und Fortsetzungspfade (fünf Teilsysteme, unabhängig verifiziert) ergab Lücken, die vor
Schritt 6 geschlossen wurden:

1. **Atomare, dauerhafte Dateien** (A-139): JSON, Parquet, Checkpoints, Kopien, Berichte und Grafiken werden
   über Temporärdatei, `fsync` und `os.replace` geschrieben. Checkpoint-Metadaten tragen den Zip-Hash.
   Unlesbare Dateien melden `ArtifactError` mit Reparaturbefehl, Seed-Dateien reparieren sich selbst.
2. **Kein „completed“ nach Absturz** (A-140): Eine Ausnahme setzt den Status `failed`. Fertig ist nur ein Lauf
   mit allen Schritten oder Budget-Stopp. Vorher hätte ein abgebrochener Lauf als fertig gegolten und die
   einmalige TEST-Auswertung verbraucht.
3. **Fortsetzen überall** (A-140): `train`, `selfplay`, `sweep-gamma` und `pipeline` übernehmen fertige
   Läufe und setzen unfertige am neuesten intakten Checkpoint fort. Beschädigte Checkpoints werden
   übersprungen. Fortsetzungen werden protokolliert, das Budget gilt über alle Abschnitte.
4. **TEST-Auswertung in einer Transaktion** (A-139): Die Spiele werden vor der Datenbank gespeichert;
   Auswertungs- und Ledger-Zeile werden gemeinsam übernommen oder gar nicht.
5. **Reihenfolge-unabhängiges G3 und Vorbedingungen** (A-141): Der Round-Robin ignoriert `horizon.json`.
   Training und TEST verlangen die eingefrorenen Artefakte, erzwungene TEST-Wiederholungen stehen im
   Bericht.
6. **`propertyrl doctor`** (A-142) und Anleitung „Nach Abbruch, Absturz oder Stromausfall“
   (`docs/TRAINING_GUIDE.md`). Logs werden angehängt statt überschrieben.
7. **Review der Korrekturen** (vier Teilsysteme, adversarial verifiziert). Ergebnis: Der neueste Lauf einer
   Konfiguration entscheidet (eine unterbrochene `--new`-Wiederholung wird fortgesetzt). `failed.zip` statt
   `final.zip` nach Ausnahmen. Neue Seeds je Fortsetzungsabschnitt nach dem Laden. `doctor` beachtet die
   Stopp-Regeln G4/G5/G7 und übersteht eine beschädigte Datenbank. `evaluate` übernimmt gleiche Auswertungen.
   Kingmaking-Wiederverwendung nur bei gleichem Agenten, gleichen Seeds, Parametern und Horizont. Ein
   bestehender Self-Play-Fehler ist behoben: Die Champion-Datei wurde beim Ausdünnen gelöscht.
8. **G3-Horizont des ersten Volllaufs** (A-143): Truncation 5,1 % bei H = 140 (Grenze < 5 %), auf Linux
   bitgleich nachgespielt. H bleibt nach Formel eingefroren, G3 FAIL wird als Negativergebnis berichtet.
