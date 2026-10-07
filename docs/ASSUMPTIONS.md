# ASSUMPTIONS – verbindliche Annahmen (§15) und eigene Annahmen (A-1xx)

## 1. Annahmen aus dem Auftrag (A-01 bis A-36)

| ID | Annahme | Umsetzung |
|---|---|---|
| A-01 | Ausgabe US Classic 2008 mit den Werten aus §3; V1–V6 prüft der Nutzer. | Werte in `configs/`; V-Tabelle in RULESPEC; `propertyrl gates --confirm-v-points` |
| A-02 | Das Zeitlimit ist ein Sicherheitsnetz (truncated); Kurzspiel nur als eigene Research-Variante. | Safety-Horizon in allen Rulesets; `RESEARCH_2P_SHORTGAME_V1` |
| A-03 | Primäres Ruleset für MCR, Self-Play und 4P ist OFFICIAL; RESEARCH dient als Fallback und Vergleich. | Experiment-Konfigurationen |
| A-04 | Ein 2P-Ergebnis (MCR) ist ein vollständiger Projekterfolg; 4P ist Stretch. | G5 vs. G7 (Stretch) |
| A-05 | Handel ist im MCR aktiv und delegiert; „ohne Handel“ ist Ablation. | `delegated_kinds`, `ablation_no_trade` |
| A-06 | Hardware: CPU, höchstens 12 h pro Run; GPU optional. | `device: cpu`, `budget_hours: 12` |
| A-07 | Privat bis G5; danach Release-Entscheidung nach Marken- und Lizenzprüfung. | `docs/LEGAL.md` |
| A-08 | Keine Tests mit Menschen. | keine Human-Eval-Komponenten |
| A-09 | Kein vorhandener Code wird übernommen. | eigene Implementierung; nur die markierte Kopie von `collect_rollouts` aus sb3-contrib (MIT) |
| A-10 | Hauptstudie Reward, Nebenstudie Aktionsabstraktion. | Ablationen A0–A3, N4, ohne Handel, gemeinsame Delegation |
| A-11 | Markov-Abgleich in reduzierter Konfiguration. | `TEST_MOVEMENT_ONLY` |
| A-12 | Kingmaking wird gemessen; der Malus ist nur Ablation A3. | `evaluation/kingmaking.py`, `ablation_a3_kingmaking_4p` |
| A-13 | DummyVecEnv als Standard, SubprocVecEnv nach Benchmark. | `vec_env: dummy`, Benchmark-Empfehlung |
| A-14 | GNOME-p3 nur als Adapter-Schnittstelle. | `agents/external.py`, `docs/EXTERNAL_ANCHOR.md` |
| A-15 | 4P als Shared-Policy-MARL mit Mehrsitz-Datensammlung (Default aus v1.4: echtes MARL nach dem MCR); Fallback ein Lernsitz. | `fourp_official`, `fourp_single_seat_fallback` |
| A-16 | Auktion OFFICIAL aufsteigend, RESEARCH verdeckt. | Rulesets (`auction`) |
| A-17 | Heuristik-Parameter als YAML je Policy. | `configs/policies/*.yaml` |
| A-18 | Evaluation lokal mit multiprocessing. | `evaluation/harness.py` |
| A-19 | Code englisch, Doku deutsch. | gesamtes Repository |
| A-20 | Abgeschnittene Spiele zählen in der Evaluation als Remis; Sensitivität nach Equity. | `duplicate.score` |
| A-21 | RL-Agenten werden deterministisch evaluiert, Trainingsgegner handeln stochastisch. | `sb3:` vs. `snapshot:`/`latest:` |
| A-22 | Checkpoints alle 100.000 Schritte (statt 10.000 aus v1.0), letzte 10 behalten. | `ppo_default.yaml` |
| A-23 | Coverage-Schwellen: Engine 95 % Zeilen und 90 % Zweige, gesamt 80 %. | Gate G1, BUILD_REPORT |
| A-24 | A2 ist eine Purdue-artige Näherung, nicht die exakte Formel der Arbeit. | `env/rewards.py` |
| A-25 | Paketversionen werden bei der Implementierung aufgelöst und gepinnt. | `requirements-lock.txt` |
| A-26 | Die Bank hat unbegrenzt Geld, die Würfel sind fair, Startspieler ist Sitz 0. | Engine |
| A-27 | Knappheitsauktion nach P-19 mit berechneter Nachfrage (K-03), Prämie zusätzlich zum Hauspreis. | `engine/scarcity.py` |
| A-28 | Neutrale Decknamen „Zufall“ und „Fonds“ (keine Begriffe einer Originalausgabe). | `configs/cards/` |
| A-29 | Primärer Endpunkt gegen die stärkste Baseline laut G3; `strong_a_v1` wird immer zusätzlich berichtet. | `evaluate.strongest_baseline`, Gegnerlisten |
| A-30 | 4P-TEST-Größe 250 Seeds × 4 Rotationen. | `DEFAULT_TEST`, `test_size.json` |
| A-31 | `max_rounds` des Kurzspiels = kalibrierter Horizont. | `load_ruleset` liest `horizon.json` |
| A-32 | `greedy_v1` ist die ungesehene Evaluations-Policy. | Gegner-Sampler lehnt `greedy_v1` ab |
| A-33 | Referenz-Linux ist Ubuntu 22.04; die CI nutzt ubuntu-latest. | `.github/workflows/ci.yml` |
| A-34 | Der Smoke-Modus nutzt SMOKE-Seeds und verkleinerte Größen, nie TEST. | `training/smoke.py`, `evaluate_agent` |
| A-35 | Watchdogs pro Fenster und Spiel statt Spiellängenlimit (P-16). | `EngineWatchdogError` |
| A-36 | Anti-Oszillationsregel für alle deterministischen Heuristiken. | `agents/base.py` |

## 2. Eigene Annahmen dieses Builds (A-101 ff.)

| ID | Annahme | Begründung / Ort |
|---|---|---|
| A-101 | „Ganzzahlig gerundet“ bedeutet kaufmännische Rundung (halb auf). | `engine/constants.round_half_up` |
| A-102 | „Zug endet“ (R-104/R-105) beendet nur die Bewegung; Post-Move- und Out-of-Turn-Fenster finden statt. | Movement/Jail-Tests |
| A-103 | Bankauktionen nach einem Bankrott an die Bank (R-703) beginnen beim nächsten aktiven Sitz nach dem Bankrotteur. | `engine/debt.py` |
| A-104 | Hält ein Spieler beide Freikarten, wird zuerst die Karte aus Deck A verwendet. | `engine/jail.py` |
| A-105 | Die Kapital-Option nach P-13 endet beim Schließen des nächsten eigenen Managementfensters des Empfängers (`interest_prepaid` wird dann gelöscht). | `engine/game.py` |
| A-106 | Der Watchdog „1.000 Entscheidungen pro Fenster“ zählt MAIN- und DEBT-Entscheidungen; Auktionen sind durch P-03 begrenzt. | `engine/game.py` |
| A-107 | Ein zweites Angebot, das durch ein vorher angenommenes ungültig wurde, wird vor der Vorlage erneut geprüft und verworfen. | `engine/trade.py` |
| A-108 | `TEST_MOVEMENT_ONLY` verwendet das Handelsprotokoll „none“. | Ruleset-YAML |
| A-109 | Würfelindex des Haftwurfs ist 0, der Werk-Sonderwurf (NEAREST_UTIL) verwendet 100 + k. | `engine/rng.py`-Verwendung |
| A-110 | Zahlungen an einen inzwischen bankrotten Gläubiger verfallen. | `engine/debt.py` |
| A-111 | Unter dem Fensterprotokoll entstehen in Fenstern keine Zahlungspflichten; der Randfall „Bankrott während eines Out-of-Turn-Fensters“ wird als „Bankrott, während Out-of-Turn-Fenster ausstehen“ getestet. | `tests/unit/test_trade_flow.py` |
| A-112 | Seeds werden auf 63 Bit beschränkt (`& (2^63 − 1)`), damit sie in SQLite, Parquet und numpy verlustfrei als vorzeichenbehaftete 64-Bit-Zahl gespeichert werden. | `evaluation/seeds.py` |
| A-113 | `propertyrl fuzz --decisions N` zählt N Entscheidungen je Konfiguration (OFFICIAL 2/4/8, RESEARCH 2P, Kurzspiel 2P, Bewegung); `--total-decisions` verteilt eine Gesamtzahl gleichmäßig. Fuzz-Spiele werden nach 1.000 Runden abgeschnitten und neu begonnen. | `infra/fuzz.py`, `cli.py` |
| A-114 | Im Smoke-Modus eingefrorene Werte liegen in `artifacts/frozen/*_smoke.json`; echte Läufe lesen nur die Dateien ohne Suffix. Smoke-Training liest `gamma_smoke.json` (Kette Sweep → Training); Smoke-Spiele verwenden den Horizont aus `horizon.json` bzw. den Ruleset-Standard, `horizon_smoke.json` und `strongest_baseline_smoke.json` dienen nur dem Smoke-Report und dem Gate-Nachweis. | `horizon.py`, `roundrobin.py`, `sweep.py`, `train.frozen_gamma`, `report.py` |
| A-115 | Die Anti-Oszillationsregel wird auch als Zusatzmaske für RL-Lernsitze angewendet (Training und Evaluation identisch); forced Entscheidungen werden nach dem Filter bestimmt. Ohne sie kann ein deterministischer, untrainierter Agent den Fenster-Watchdog auslösen. | `env/core.py`, `agents/sb3_agent.py` |
| A-116 | `propertyrl repro` spielt die gespeicherten Spiele direkt über den Harness nach (gleiche Seeds, Sitzbelegungen, Policies), vergleicht Sieger, Platzierungen und Runden je Spiel und schreibt nicht in den TEST-Ledger. | `infra/pipeline.repro` |
| A-117 | `train --resume` lädt den jüngsten Zustand (`final.zip`, das bei jedem Abbruch geschrieben wird, oder den letzten periodischen Checkpoint) und trainiert nur die verbleibenden Schritte bis `total_timesteps`. | `training/train.py` |
| A-118 | OpenSkill bewertet keine Spiele, in denen dieselbe Policy-Spezifikation mehrere Sitze belegt (keine Selbstbewertung). | `evaluation/ratings.py` |
| A-119 | Kingmaking-Rollouts, die das Entscheidungslimit oder den Horizont erreichen, werden dem nach kanonischer Equity Führenden zugeschlagen. | `evaluation/kingmaking.py` |
| A-120 | Platzierungen abgeschnittener Spiele (Sensitivitätsanalyse, Z5) folgen der kanonischen Equity; bankrotte Sitze stehen hinten. | `evaluation/harness.py` |
| A-121 | Z4 (a) verwendet als MCR-Agenten den Start-Checkpoint des Self-Play-Laufs (`init_from`); Z4 (c) wertet bis zu 5 gleichmäßig gewählte Snapshots aus, die älter als der aktuelle Champion sind. Alle Gegner werden in der einen TEST-Auswertung des Champions gespielt. | `infra/pipeline.selfplay_opponents`, `evaluation/criteria.z4` |
| A-122 | Z5 „mittlere Platzierung besser als jede Baseline“: Das 95-%-Bootstrap-CI der mittleren Differenz (Platz Agent − Platz Baseline, Cluster = Seed) liegt vollständig unter 0. | `evaluation/criteria.z5` |
| A-123 | Holm-Familien im Report: je Auswertung alle Nicht-Primärgegner (Bootstrap-p gegen 50 %); Ablationen gepaart gegen A1. | `evaluation/report.py` |
| A-124 | W&B läuft nur mit `--wandb`, standardmäßig im Offline-Modus (`WANDB_MODE` steuert es) und nur mit technischen Skalaren. | `training/wandb_logging.py` |
| A-125 | `PROPERTYRL_HOME` verlegt `artifacts/`, `runs/` und `reports/`; die Testsuite nutzt ein temporäres Verzeichnis. | `infra/storage.py`, `tests/conftest.py` |
| A-126 | Die Bestätigung der V-Punkte erfolgt mit `propertyrl gates --confirm-v-points` (Datei `artifacts/frozen/v_points_confirmed.json`); ohne sie gilt der G0-Fallback „Standardwerte eingefroren“. | `infra/gates.py` |
| A-127 | Die SELECT-Auswertung innerhalb von `--smoke-all` wird als Smoke-Ergebnis gespeichert und zählt nicht für G4. | `infra/pipeline.smoke_all` |
| A-128 | Horizont-Kalibrierung 4P: halbe Spielzahl der 2P-Kalibrierung mit zwei festen Aufstellungen aus `strong_a_v1`, `strong_b_v1`, `roi_markov_v1`. | `evaluation/horizon.py` |
| A-129 | Pakete ohne erkennbare Lizenzangabe stehen mit Begründung in `configs/license_allowlist.yaml`; Lizenzbezeichner werden exakt (nicht per Teilstring) verglichen. | `infra/licenses.py` |
| A-130 | Ohne eingefrorene TEST-Größe gelten 1.200 (2P) bzw. 250 (4P) Seeds. | `evaluation/evaluate.test_size` |
| A-131 | Kingmaking eines Agenten verwendet die TEST-Seeds der Ledger-Auswertung (erste Rotation je Seed) und spielt diese deterministisch nach; es entsteht kein neuer Ledger-Eintrag. | `infra/pipeline.kingmaking_for` |
| A-132 | Die Zahl der maskierten Zufallsschritte steht in der Test-ID (`steps<N>`), damit `propertyrl gates` CI- und Gate-Größe unterscheiden kann (`PROPERTYRL_MASK_STEPS`). | `tests/env/test_masks_leak.py`, `infra/gates.py` |
| A-133 | Der γ-Sweep wählt die höchste SELECT-Siegquote gegen `roi_markov_v1`; liegen weitere Piloten innerhalb des Wilson-Intervalls des Besten, entscheidet die höhere mittlere explained_variance. | `training/sweep.py` |
| A-134 | Der Benchmark misst SubprocVecEnv nur für n_envs, deren Worker (≈ 300 MB je Prozess) in die Hälfte des verfügbaren Speichers passen; übersprungene Größen stehen mit Begründung im Benchmark-JSON (`skipped_n_envs`). Ohne diese Grenze beendet der OOM-Killer den Lauf bei 64 Workern auf 16 GB. | `infra/benchmark.memory_cap` |
| A-135 | Die G3-Bedingung „Truncation < 5 %“ wird wie in §8.10 beschrieben an der 2P-Kalibrierung gemessen; die 4P-Kalibrierung wird eingefroren und separat berichtet (`passed_4p`, Gate-Detail). Hintergrund: Im Smoke-Lauf endeten 8 von 24 4P-Heuristikspielen nicht innerhalb von 5.000 Runden (Patt ohne Monopole), was ein Forschungsbefund für G7 ist und nicht die 2P-Baselines betrifft. | `evaluation/horizon.py`, `infra/gates.gate_g3` |
| A-136 | `propertyrl pipeline` ist wiederholbar: Für jeden Seed wird ein abgeschlossener Lauf mit identischem `config_hash` wiederverwendet, ein unterbrochener Lauf mit `--resume`-Logik fortgesetzt und eine vorhandene SELECT/TEST-Auswertung desselben Agenten im selben Experiment nicht erneut ausgeführt. Smoke-Pipelines trainieren immer neu. Zwei Pipelines desselben Experiments dürfen nicht gleichzeitig laufen. | `training/train.train_or_reuse`, `infra/pipeline._evaluate_once` |
| A-137 | Z3/G5 poolt nur die im Experiment konfigurierten Trainingsseeds (mcr_official_2p: 1, 2, 3) mit der jeweils neuesten TEST-Auswertung je Seed; Zusatz-Seeds (`--extended`) erscheinen im Bericht, verändern G5 aber nicht. Checkpoint-Suche (`experiment:<name>:<seed>`, `init_from`) ignoriert γ-Sweep-Piloten und nicht abgeschlossene Läufe. | `evaluation/criteria.z3`, `training/train.find_checkpoint` |
| A-138 | `propertyrl evaluate --experiment <name>` übernimmt ohne explizite Angaben Gegnerliste, Ruleset, Spielerzahl und Label des Experiments (wie die Pipeline); doppelte Gegner werden entfernt. Smoke-Round-Robins schreiben nicht mehr `roundrobin/latest.json`, G8 liest die neueste Repro-Datei, und `--smoke-all` prüft, dass es selbst keine Ledger-Einträge erzeugt (frühere echte Einträge sind erlaubt). | `cli.py`, `evaluation/roundrobin.py`, `infra/gates.py`, `infra/pipeline.py` |
