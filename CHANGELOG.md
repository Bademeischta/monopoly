# Changelog

Alle nennenswerten Änderungen an PropertyRL. Format angelehnt an „Keep a Changelog“, Versionierung nach
SemVer.

## Unreleased

### Hinzugefügt
- `propertyrl doctor [--clean-temp]`: Zustand nach Abbruch, Absturz oder Stromausfall prüfen und den
  nächsten Runbook-Schritt nennen (A-142).
- `propertyrl train --new` erzwingt einen neuen Lauf. Ohne die Option übernimmt `train` fertige Läufe
  gleicher Konfiguration und setzt abgebrochene fort.
- `propertyrl evaluate --again`: Ohne die Option wird eine gespeicherte gleiche Auswertung übernommen.

### Geändert
- Alle Ergebnisdateien werden atomar und dauerhaft geschrieben (A-139).
- TEST-Auswertung: Die Spiele werden vor der Datenbank gespeichert. Auswertungs- und Ledger-Zeile bilden
  eine Transaktion.
- Fortsetzen nach Abbruch: Der Fortsetzungspunkt ist der neueste intakte Checkpoint; jede Fortsetzung
  wird protokolliert, und das Budget gilt über alle Abschnitte. Fortsetzen wirkt auch für `selfplay` und
  die Piloten von `sweep-gamma` (A-140).
- Der Round-Robin spielt unabhängig von `horizon.json` mit dem Platzhalter-Horizont. Training und
  TEST-Auswertung verlangen die eingefrorenen Artefakte der früheren Schritte (A-141).
- Logs der Anleitung werden angehängt statt überschrieben.
- Wiederholte 4P-Pipelines übernehmen das vorhandene Kingmaking-Ergebnis.

### Behoben
- Ein durch eine Ausnahme abgebrochener Lauf galt als „completed“ und hätte wiederverwendet und auf TEST
  ausgewertet werden können. Er heißt jetzt `failed` und wird fortgesetzt (A-140).
- Unlesbare Seed-Dateien, `run.json` und `training_state.json` führten zu unverständlichen Abbrüchen. Jetzt
  folgen Selbstreparatur, Rückgriff auf die Datenbank oder eine Meldung mit Datei und Reparaturbefehl.
- `--force-retest` wird wie in §8.2 verlangt im Bericht markiert (nur echte Wiederholungen).
- Self-Play: Beim Ausdünnen des Snapshot-Pools wurde die Champion-Datei gelöscht, weil `sb3:`-Spec und Pfad
  verglichen wurden. Das hätte den Lauf gegen Ende abbrechen lassen. Jetzt bleibt der Champion erhalten.
- Ein mit Ausnahme beendeter Lauf wird am letzten periodischen Checkpoint fortgesetzt, nicht mit den
  womöglich defekten Gewichten zum Fehlerzeitpunkt (`failed.zip`).
- Zwei Läufe, die im selben Prozess in derselben Sekunde starten, erhalten verschiedene Run-IDs.
- Der Bericht zeigt je Experiment das neueste Kingmaking-Ergebnis, statt Wiederholungen andere verdrängen zu
  lassen.

## 0.1.0 – 2026-10-07

Erste vollständige Version nach Masterplan v1.4.

### Hinzugefügt
- Engine (`propertyrl.engine`, nur Standardbibliothek): State-Machine mit Continuation-Stack, vier Rulesets
  (OFFICIAL_US_CLASSIC_2008, RESEARCH_2P_BOUNDED_V1, RESEARCH_2P_SHORTGAME_V1, TEST_MOVEMENT_ONLY),
  Knappheitsauktion (P-19), Handel mit vollständigen Trade-Objekten, Schuldenphase und Bankrott-Kaskaden,
  zählerbasierter RNG, Event-Log (Schema e1.0), Ledger, Invarianten, Watchdogs, Log/Replay mit Hashes,
  Clone mit Reseed, exakte und approximative Markov-Ketten, Textdarstellung.
- Agenten: Bewertungsprimitive, `delegation_v1`, `random_legal`, `greedy_v1`, `roi_markov_v1`,
  `strong_a_v1`, `strong_b_v1`, Anti-Oszillation, Komposition, ε-Beimischung, SB3-Agent, Registry,
  `ExternalAgentAdapter`-Schnittstelle.
- Environments: Decision Core, Observation (517 Merkmale, o1.0), Aktionsraum Discrete(106) mit
  `MaskedDiscrete`, Rewards A0–A3, Gymnasium-Env, Mehrsitz-Env, PettingZoo-AEC-Env, Gegner-Sampler mit
  Curriculum, Self-Play/PFSP, 4P und Fallback, picklebare Factories.
- Training: SMDP-MaskablePPO mit Duration-Buffer, Mehrsitz-Variante mit SeatChain-Buffer, Callbacks
  (Metriken, Checkpoints, SELECT-Auswahl, Curriculum, PFSP, Snapshots, Champion-Gate, latest-Sync,
  explained-variance-Warnung, Budget), Resume, γ-Sweep, alle Experimente und Ablationen als Konfiguration,
  Smoke-Modus, optionales W&B (offline).
- Evaluation: Seed-Pools mit Prüfsummen, TEST-Ledger, Harness und Duplicate, Wilson, Seed-Cluster-Bootstrap,
  gepaarte Vergleiche, Holm, Power, Elo, OpenSkill, Metriken, Zielkriterien Z3–Z5, Kingmaking,
  Round-Robin, Horizont-Kalibrierung, Markdown-Report mit Grafiken.
- Infrastruktur und CLI: pydantic-Konfiguration, Run-Metadaten, SQLite/JSON/Parquet-Speicher, Logging mit
  Fehler-Logs, Benchmark, Gates G0–G8, Diagnose, Lizenzprüfung, Planung, Pipelines (`--smoke-all`,
  `repro`), Befehl `propertyrl`.
- Tests (Unit, Golden Games, Hypothesis, Fuzzing mit seltenen Ereignissen, Markov, Mutanten, Determinismus,
  archivierte Replays, Environments, Agenten, Training, Evaluation, Architektur, Smoke-Pipeline), CI für
  Linux und Windows, vollständige deutschsprachige Dokumentation.
