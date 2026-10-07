# Implementierungsplan PropertyRL

Dieser Plan setzt den Programmierauftrag (Masterplan v1.4) in einem Durchlauf um. Er beschreibt Module,
Abhängigkeiten, Build-Reihenfolge, Testplan je Modul, Umsetzungsrisiken und alle zusätzlichen Annahmen
(Details der Annahmen in `docs/ASSUMPTIONS.md`, IDs A-1xx).

## 1. Schichten und Abhängigkeiten

```
versions ─┐
          ├─> engine (nur Standardbibliothek)
infra.config (pydantic, YAML) ──> engine-Objekte (Ruleset, Board, Decks)
agents (primitives, Heuristiken, Delegation, SB3Agent) ──> engine, infra.config
env (core, observation, spaces, rewards, single_agent, multi_seat, aec, opponents, factory) ──> engine, agents
training (smdp_ppo, multiseat_ppo, buffers, callbacks, curriculum, selfplay, sweep, budget, smoke, train) ──> env, agents
evaluation (seeds, harness, duplicate, stats, ratings, metrics, kingmaking, roundrobin, horizon, ledger, report) ──> engine, agents
infra (runmeta, storage, logging_setup, benchmark, gates, diagnose, licenses, plan, pipeline) ──> alle
cli ──> infra, training, evaluation
```

Die Engine importiert ausschließlich die Standardbibliothek und `propertyrl.versions`. Ein Architekturtest
prüft dies in einem frischen Subprozess über `sys.modules`.

## 2. Modulliste

| Paket | Module | Inhalt |
|---|---|---|
| `engine` | errors, constants, board, cards, ruleset, rng, state, actions, decisions, legality, movement, property_rules, rent, building, scarcity, mortgage, jail, card_effects, auction, trade, debt, game, events, ledger, invariants, equity, replay, scenario, markov, render_text, hashing; Hilfsmodule frames (Opcode-Tabelle), turns (Zug-/Fenstersteuerung), view (PublicState) | deterministische Zustandsmaschine mit Fortsetzungsstapel |
| `agents` | base, public_view, primitives, random_legal, greedy, roi_markov, strong_a, strong_b, delegation, composite, sb3_agent, external, registry | Policies, Bewertungsprimitive, Delegation |
| `env` | core, observation, spaces, rewards, single_agent, multi_seat, aec, opponents, factory | Decision Core, Gymnasium-, Mehrsitz- und AEC-Env |
| `training` | smdp_ppo, multiseat_ppo, buffers, callbacks, curriculum, selfplay, sweep, budget, smoke, train | SMDP-MaskablePPO, Mehrsitz-Kollektor, Trainingssteuerung |
| `evaluation` | seeds, harness, duplicate, stats, ratings, metrics, kingmaking, roundrobin, horizon, ledger, report | Evaluationspipeline |
| `infra` | config, runmeta, storage, logging_setup, benchmark, gates, diagnose, licenses, plan, pipeline | Infrastruktur |
| `cli` | cli.py | argparse-CLI `propertyrl` |

## 3. Kernentscheidung Engine: Fortsetzungsstapel

Die Engine ist eine explizite Zustandsmaschine. Der gesamte Kontrollfluss eines Zuges liegt als Stapel
kleiner Int-Tupel (`frames.py`) im `GameState`: automatische Frames (Wurf, Bewegung, Landung, Zahlung,
Bankrott, Auktionsstart, Fenster) werden in `Engine._run` ausgeführt, Entscheidungs-Frames bleiben oben
liegen, bis `apply` sie beantwortet. Dadurch sind Zustand, Klon (`copy()` kopiert nur Listen) und Hash
vollständig und billig, verschachtelte Abläufe (Knappheitsauktion im Fenster, Schuldenkaskade nach
Bankrott, Bankauktionen) sind natürlich abbildbar, und Frames bankrotter Sitze verfallen automatisch.

## 4. Build-Reihenfolge (wie ausgeführt)

1. a) Projektgerüst, `pyproject.toml`, Konfigurationsmodelle (`infra/config.py`), Storage-Pfade, Seeds-Modul.
2. b) Engine-Daten (Brett, Karten, Rulesets als YAML + Validierung), RNG, Zustand.
3. c) Engine-Regeln inkl. Knappheitsauktion, Entscheidungsmaschine, Events, Ledger, Invarianten,
   Replay, Clone, Markov-Modul, Textdarstellung.
4. d) Engine-Tests: Unit je Regel-ID, Golden Games (YAML), Hypothesis, Fuzz-Smoke mit
   Seltene-Ereignis-Generatoren, Markov, Mutanten-Harness, archivierte Replays, Architekturtests.
   **Kein RL-Code vor grünen Engine-Tests (Auflage „kein RL-Code vor G1“).**
5. e) Agenten: Primitive, Delegation, Baselines, Registry.
6. f) Decision Core, Observation, Spaces, Rewards, Gymnasium-, Mehrsitz-, AEC-Env, Gegner-Sampler; Env-Tests.
7. g) Training: SMDP-MaskablePPO, Mehrsitz-Kollektor, Buffer, Callbacks, Curriculum, Self-Play, γ-Sweep,
   Budget, Smoke-Modus; SB3Agent.
8. h) Evaluation: Harness, Duplicate, Statistik, Ratings, Kingmaking, Round-Robin, Horizont, Ledger, Report.
9. i) Infrastruktur: Run-Metadaten, Benchmark, Gates, Diagnose, Lizenzcheck, Plan, Pipeline, CLI.
10. j) Doku, README, CI, Lockfile.

## 5. Testplan je Modul

| Modul | Tests |
|---|---|
| board/cards/ruleset/config | Datentabellen gegen §3.2/§3.4, Index-Abbildungen §3.3, Validierungsfehler (ConfigError) |
| rng | Determinismus, Wertebereich, Unabhängigkeit der Sitze, Fisher-Yates-Permutation |
| movement/jail/rent/building/mortgage/card_effects/auction/scarcity/trade/debt | je Regel-ID mindestens ein Unit-Test (`@pytest.mark.rule`), Randfälle §3.12 |
| game/turns | Fensterfolge P-01, D-01, D-03, Rundenzähler P-15, Watchdogs P-16 |
| invariants | gezielte Verletzungen erzeugen InvariantError |
| replay/hashing | Replay identisch, ReplayMismatchError, SchemaVersionError, archivierte Replays |
| scenario | Golden Games (≥ 19 YAML-Szenarien) |
| markov | exakte Kette vs. Potenziteration, Engine-Häufigkeiten vs. Kette (CI 1 Mio., 0,15 pp) |
| gesamt | Hypothesis-Zustandsmaschine, Fuzz je Ruleset, Seltene-Ereignis-Fuzz, Event-Coverage, Mutanten |
| agents | Legalität in 10.000 Zufallszuständen, Schwellen-Verschiedenheit, Anti-Oszillation |
| env | check_env (Gymnasium, SB3), api_test, MaskedDiscrete, Maskentest, Leak-Test, Schema, Determinismus, SubprocVecEnv (spawn), Mehrsitz-Äquivalenz |
| training | Duration-Buffer vs. Handrechnung, Gleichheit bei k = 1, SeatChain-Äquivalenz und Zwei-Sitz-Handrechnung, PBRS-Teleskop, γ-Konsistenz, Resume |
| evaluation | Wilson/Bootstrap/Holm gegen Referenzwerte, Ledger, Seed-Pools, Smoke-Isolation |
| infra/cli | Smoke-Pipeline, Gates, Lizenzcheck, Verbotswörter |

## 6. Risiken bei der Umsetzung

| Risiko | Gegenmaßnahme |
|---|---|
| Laufzeit der reinen Python-Engine (Training 10 Mio. Schritte) | Event-Logging abschaltbar, Masken-Berechnung je Gruppe, Caching der Primitive, Benchmark |
| Komplexität verschachtelter Abläufe (Schuldenkaskade, Knappheitsauktion) | Fortsetzungsstapel, Invarianten nach jedem Schritt in allen Tests, Seltene-Ereignis-Fuzz |
| API-Änderungen in sb3-contrib | `collect_rollouts` als markierte Kopie der gepinnten Version 2.9.0, Lockfile |
| Windows-Multiprocessing | picklebare Top-Level-Factories, `MaskedDiscrete.__getstate__`, spawn-Test |
| Rechenzeit der Smoke-Pipeline | verkleinerte Größen nach `smoke_overrides.yaml`, eine Pipeline-Ausführung je Testlauf |
| Gate-Größen (10 Mio. Fuzz/Markov) | CI-Varianten im Testlauf, Gate-Varianten als dokumentierte Befehle (Laufzeit im BUILD_REPORT) |

## 7. Zusätzliche Annahmen (Kurzfassung, Details in ASSUMPTIONS.md)

A-101 Rundung „ganzzahlig gerundet“ = kaufmännisch (halb auf). A-102 „Zug endet“ (R-104/R-105) beendet nur
die Bewegung; Post-Move- und Out-of-Turn-Fenster finden statt. A-103 Bankauktionen (R-703) beginnen beim
nächsten aktiven Sitz nach dem Bankrotteur. A-104 Freikarten-Nutzung verwendet zuerst die Karte aus Deck A.
A-105 P-13: Kapital-Option endet beim Schließen des nächsten eigenen Managementfensters. A-106 Watchdog
„1.000 Entscheidungen pro Fenster“ zählt MAIN/DEBT-Entscheidungen; Auktionen sind durch P-03 begrenzt.
A-107 Veraltete zweite Angebote werden vor der Vorlage erneut geprüft und bei Ungültigkeit verworfen.
A-108 TEST_MOVEMENT_ONLY nutzt das Handelsprotokoll „none“. A-109 Würfelindex des Haftwurfs 0, des
Werk-Sonderwurfs 100 + k. A-110 Zahlungen an inzwischen bankrotte Gläubiger verfallen. A-111 Unter dem
Fensterprotokoll entstehen in Fenstern keine Zahlungspflichten; der Randfall „Bankrott während eines
Out-of-Turn-Fensters“ wird als „Bankrott, während Out-of-Turn-Fenster ausstehen“ getestet. Weitere
Annahmen A-112 ff. siehe ASSUMPTIONS.md.
