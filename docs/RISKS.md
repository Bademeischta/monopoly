# RISKS – Risiko-Register (§13)

W/A = Wahrscheinlichkeit/Auswirkung (N niedrig, M mittel, H hoch, SH sehr hoch); Prio K kritisch, H hoch,
M mittel. Die Spalte „Umsetzung“ nennt, wo die Gegenmaßnahme in diesem Repository steckt.

| ID | Risiko | W/A | Prio | Gegenmaßnahme | Messbarer Trigger | Umsetzung |
|---|---|---|---|---|---|---|
| R01 | Regel-Engine fehlerhaft | M/SH | K | Regel-IDs, Golden Games, Fuzzing mit Seltene-Ereignis-Generatoren, Markov, Mutanten, Coverage, archivierte Replays | Invariantenverletzung, Markov außerhalb der Toleranz, überlebender Mutant oder abweichender Replay-Hash | `tests/unit`, `tests/golden`, `tests/fuzz`, `tests/markov`, `tests/mutation`, `tests/determinism`; Gate G1 |
| R02 | Protokoll-Lücken, Endlosschleifen, Deadlocks | M/H | H | P-IDs, Angebotslimit, Anti-Oszillation, Watchdogs nach P-16 | Test ohne Regel-ID oder `EngineWatchdogError` | `engine/trade.py` (Limits), `agents/base.py` (Anti-Oszillation), Watchdogs in `engine/game.py`; `test_rule_coverage.py` |
| R03 | Illegale Aktionen | H/H | K | flacher Raum, Masken in der Env-Klasse, `MaskedDiscrete`, strikter Modus | `illegal_actions > 0` | `env/spaces.py`, `action_masks()`, `IllegalActionError`; Maskentest |
| R04 | Aktionsraum beschneidet Strategie | M/H | K | Bauen auf Straßenebene | eine Baseline gewinnt nachweislich durch eine Aktion, die dem Agenten fehlt | 106 IDs mit BUILD/SELL je Straße (`docs/ACTION_SCHEMA.md`) |
| R05 | PBRS falsch implementiert | M/H | K | stückweises Φ, Teleskop-Test, Ablationen | Teleskop-Test rot oder A0 und A1 mit widersprüchlichen Optima | `env/rewards.py`; `tests/env/test_rewards_core.py`; Ablation A0 |
| R06 | SMDP-Diskontierung falsch | H/H | K | Duration-Buffer, Handrechnungstest, γ-Konsistenz | Testabweichung oder instabile Returns | `training/buffers.py`; `tests/training/test_buffers.py`; `check_gamma` |
| R07 | Mehrsitz-Kollektor falsch | M/H | H | Äquivalenztest mit einem Lernsitz, Handrechnung mit zwei Sitzen, valid-Maske | Äquivalenztest rot oder divergierende Werte | `SeatChainRolloutBuffer`; `tests/env/test_multiseat.py`, `tests/training/test_buffers.py` |
| R08 | Truncation-Hacking | H/H | K | Safety-Horizon mit Bootstrap, keine Zeit in der Observation | Truncation-Quote steigt mit dem Training | `terminal_observation`-Bootstrap; Observation ohne Spielzeit; Metrik Truncation-Quote |
| R09 | Reward-Hacking | M/H | H | terminale Utility primär, Ablationen A0 bis A2 | Equity-Anteil steigt, Siegquote nicht | Primärer Endpunkt = Siegquote; Ablationen A0/A2 |
| R10 | Kreditzuweisung über langen Horizont | H/H | H | Auto-Skip, SMDP, γ-Sweep, Shaping | explained_variance < 0,3 nach 20 % des Budgets | `ExplainedVarianceWarning`, `propertyrl sweep-gamma`, `propertyrl diagnose` |
| R11 | Training instabil, hohe Varianz zwischen Seeds | M/H | H | mindestens 3 Seeds, PPO-Diagnostik, Tuning nur auf SELECT | Spannweite der Seed-Siegquoten > 10 pp | 3 Seeds je Experiment (5 mit `--extended`); Report je Seed |
| R12 | Self-Play kollabiert oder zykliert | M/H | H | Snapshot-Pool, Baselines im Mix, Champion-Gate | Siegquote gegen `strong_a_v1` fällt > 2 pp unter die des MCR-Agenten | `training/selfplay.py`, Champion-Gate mit Marge 2 pp, Z4 (b) |
| R13 | Gegner-Overfitting | H/H | H | Gegnermix, zwei Baseline-Stile, ε-Beimischung, ungesehene Policy `greedy_v1`, verdeckter TEST | Pool- minus Baseline-Siegquote > 15 pp | `OpponentSampler`, `EpsilonPolicy`, `greedy_v1` in jeder Evaluation |
| R14 | Agent beutet Heuristiken aus | H/H | H | risikoaverse Delegation, ε-Gegner, Evaluation gegen ungesehene Policy | Siegquote gegen eine Baseline > 90 %, gegen `greedy_v1` oder `random_legal` deutlich niedriger | Report-Abschnitt „ungesehene Policy“ |
| R15 | Heuristik-Zirkularität | M/H | H | Delegation ≠ Benchmark, Kontroll-Ablation gemeinsame Delegation | Schwellen-Verschiedenheitstest rot | `test_thresholds_differ_pairwise`, `ablation_shared_delegation` |
| R16 | Heuristik divergiert zwischen Training und Evaluation | M/H | H | eine versionierte Implementierung je Policy, `heuristic_version` in allen Metadaten, Determinismustest | unterschiedliche Ergebnisse bei gleichem Seed und gleicher Version | `versions.py`, Run-/Checkpoint-/Eval-Metadaten, `test_heuristics_deterministic` |
| R17 | Baselines zu schwach oder intransitiv | M/H | H | ROI-Markov, Round-Robin-Gate, optionaler externer Anker | Zyklus oder Rangwechsel zwischen den SELECT-Blöcken | `evaluation/roundrobin.py`, G3; `docs/EXTERNAL_ANCHOR.md` |
| R18 | Selektionsbias | M/M | M | SELECT/TEST-Trennung, Ledger | zweite TEST-Auswertung oder SELECT- und TEST-Quote weichen über das CI hinaus ab | `evaluation/seeds.py`, `evaluation/ledger.py` |
| R19 | Positionsbias | M/M | M | Sitzrotation, Duplicate | Sitz-Siegquoten außerhalb des CI verschieden | `duplicate_specs`, `seat_win_rates` im Report |
| R20 | Kingmaking verzerrt 4P | H/M | H | Winner Sensitivity, A3 nur als Ablation | Kingmaking-Rate > 10 % | `evaluation/kingmaking.py`, `ablation_a3_kingmaking_4p` |
| R21 | 4P zu komplex | H/H | H | Stretch nach G6, Ein-Lernsitz-Fallback | G6 nicht bis W19 oder G7 nicht bis W23 | `fourp_single_seat_fallback` |
| R22 | Simulator zu langsam | M/M | M | Benchmark, Logging aus, Profiling und Caching; Cython oder Numba erst nach dem Projekt | geplanter Run überschreitet 12 h | `propertyrl benchmark`, `propertyrl plan`, gecachte Primitive |
| R23 | Fuzzing gibt falsche Sicherheit | H/H | H | Mutanten, Coverage, Event-Coverage, Seltene-Ereignis-Generatoren | überlebender Mutant oder ungesehener Event-Typ | `tests/mutation`, `test_event_coverage`, `infra/fuzz.py` |
| R24 | Markov-Abgleich scheitert an falscher Konfiguration | M/H | H | reduzierte Testkonfiguration, feste Ruheereignis-Definition | Toleranz überschritten | `TEST_MOVEMENT_ONLY`, `engine/markov.py` |
| R25 | Pickle- und Multiprozessfehler unter Windows | H/H | K | `action_masks` in der Klasse, `MaskedDiscrete.__getstate__`, Top-Level-Factories, spawn-Tests in CI | Exception beim Start von SubprocVecEnv | `env/factory.py`, `test_dummy_and_subproc_spawn_identical`, CI-Matrix mit Windows |
| R26 | Bibliotheks- und API-Änderungen | M/M | M | Lockfile, Versionspinning, dokumentierte Kopie von `collect_rollouts` | Build oder Import bricht | `requirements-lock.txt`, Markierungen „# SMDP change“ in `training/smdp_ppo.py` |
| R27 | RLlib-Integrationsaufwand | M/M | M | kein RLlib im Projekt | Arbeit an RLlib vor Projektende | kein RLlib in den Abhängigkeiten |
| R28 | MLOps überdimensioniert | H/M | M | lokaler Minimal-Stack | Infrastrukturarbeit übersteigt die RL-Arbeit | SQLite, JSON, Parquet, TensorBoard; W&B optional |
| R29 | Zeitverzug | H/H | H | Pufferwochen, Fallback je Gate | ein Gate mehr als 1 Woche verspätet | `docs/ROADMAP.md` |
| R30 | Scope Creep | H/M | M | Nicht-Ziele-Liste | Arbeit an Nicht-Zielen vor G5 | Nicht-Ziele in `docs/IMPLEMENTATION_PLAN.md` |
| R31 | Marken- und IP-Problem | N–M/H | H | neutrale Namen, Verbotswörter-Test, Prüfung vor Release | öffentlicher Release geplant | `tests/architecture/test_forbidden_words.py`, `docs/LEGAL.md` |
| R32 | Datenschutzverstoß bei Tests mit Menschen | N/H | M | Datenschutzkonzept vor dem ersten Test | Human-Eval oder Web-Demo geplant | `docs/DATENSCHUTZ.md` |
| R33 | Kartenwerte weichen von der Ausgabe ab | M/M | M | V-Punkte als Konfiguration | Abgleich mit dem Regelheft zeigt einen Unterschied | V1–V6 in `docs/RULESPEC.md`, Werte in `configs/` |
| R34 | Knappheitsauktion verlängert Spiele oder erzeugt Schleifen | M/M | M | Zuschlag an den Auslöser ohne Gebote, Watchdog, Golden Games | Watchdog oder um mehr als 20 % längere Spiele nach Aktivierung | `engine/scarcity.py`, Golden Games zur Knappheitsauktion |
| R35 | GPU-Speicher-Engpass (aus v1.0) | N/N | M | entfällt durch CPU-first und kleine MLPs | GPU-Training geplant | `device: cpu` in `ppo_default.yaml` |
| R36 | Motivationsverlust als Einzelperson | M/H | H | frühes MCR, sichtbare Gates | 2 Wochen ohne Kernfortschritt | `propertyrl gates`, Smoke-Pipeline |
