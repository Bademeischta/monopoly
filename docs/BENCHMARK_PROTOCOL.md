# BENCHMARK_PROTOCOL – Seeds, Duplicate-Evaluation, Endpunkte, Statistik, Ledger, Budget, Smoke-Modus

Dieses Protokoll ist vor jeder TEST-Auswertung verbindlich festgelegt (Präregistrierung). Implementierung:
`src/propertyrl/evaluation/`, Konfiguration: `configs/training/seeds.yaml`, `configs/experiments/*.yaml`.

## 1. Seeds (§8.1, §7.4)

| Pool | pool_id | Größe | Verwendung |
|---|---|---|---|
| SELECT | 1 | 2.000 | Checkpoint-Auswahl, Round-Robin, Horizont, Champion-Gate, Sanity (G4) |
| TEST | 2 | 10.000 | ausschließlich finale, einmalige Auswertungen (Ledger) |
| SMOKE | 3 | 50 | Smoke-Modus, nie für Aussagen |
| TRAIN | – | unbegrenzt | `u64(master, TRAIN, run_seed, worker, episode)` |

- Master-Seed `20261007`. Evaluationsseeds: `u64(master, EVAL, pool_id, i)`, auf 63 Bit beschränkt (A-112).
- Kollisionen: ein bereits vergebener Seed wird übersprungen, der Pool mit dem nächsten Index aufgefüllt; die
  Disjunktheit aller Pools wird beim Erzeugen geprüft (`check_disjoint`).
- TRAIN-Seeds kollidieren nie mit SELECT/TEST/SMOKE: bei Kollision wird der nächste Episodenzähler verwendet.
- Die Pools liegen in `artifacts/seeds/{select,test,smoke}.json` mit `checksums.json` (SHA-256); bei jedem
  Laden werden Prüfsummen und Übereinstimmung mit dem Master-Seed verglichen (`SeedLedgerError` bei
  Abweichung).
- Feste Teilmengen (Indizes in SELECT): SELECT-Mini 0–99 (Curriculum), Checkpoint-Evaluation 0–199,
  Champion-Gate Block 1 0–399 und Block 2 1000–1399, Round-Robin Block 1 0–999 und Block 2 1000–1999,
  Horizont-Kalibrierung ganze Blöcke.

## 2. TEST-Ledger (§8.2)

- SQLite-Tabelle `test_ledger(agent_hash, experiment, ruleset_id, n_seeds, time, result_id, forced)` in
  `artifacts/propertyrl.db`.
- `agent_hash` = SHA-256 der Checkpoint-Datei (RL-Agenten) bzw. Hash aus Name und Heuristik-Version.
- Je `agent_hash` genau eine TEST-Auswertung; ein zweiter Versuch löst `SeedLedgerError` aus, außer mit
  `--force-retest` (Eintrag `forced = 1`, Warnung im Log, Markierung im Report).
- Alle Gegner einer TEST-Auswertung werden in **einem** Aufruf ausgewertet (für Self-Play inklusive
  MCR-Agent und älterer Snapshots), damit der Ledger nicht mehrfach belastet wird.
- Checkpoint-Auswahl (`best_select`) erfolgt ausschließlich auf SELECT.
- Smoke-Läufe schreiben nie in den Ledger; `evaluate --smoke --split test` ist verboten (`ConfigError`), und
  `propertyrl pipeline --smoke-all` bricht ab, falls der Ledger danach nicht leer ist.
- `propertyrl repro` wiederholt gespeicherte Spiele direkt über den Harness und schreibt nicht in den Ledger
  (A-116).

## 3. Harness und Duplicate (§8.3)

- Spiele laufen direkt über die Engine mit Policy-Objekten je Sitz (ohne Gym), parallel per
  `multiprocessing` (Worker bauen Policies aus picklebaren Spezifikationsstrings; `torch.set_num_threads(1)`).
- 2P: jeder Seed in beiden Sitzbelegungen. 4P: jeder Seed in allen 4 zyklischen Rotationen. Alle
  verglichenen Agenten spielen dieselben Seeds.
- Evaluation immer mit ε = 0; RL-Agenten deterministisch (`sb3:`), mit derselben Anti-Oszillationsmaske wie
  im Training (A-115).
- Safety-Horizon: eingefrorener Wert aus `artifacts/frozen/horizon.json`; danach gilt das Spiel als
  abgeschnitten.
- Je Spiel ein Datensatz in `artifacts/eval/<eval_id>/games.parquet`: seed, seed_index, rotation,
  Sitzbelegung, Policy-Namen und -Versionen, Sieger, Platzierungen, Runden, Entscheidungen (gesamt und je
  Sitz), truncated, finale Equity je Sitz, Bankrott-Status, alle Zähler, Haft-Entscheidungen nach Phase,
  vollständige Farbgruppen, Laufzeit. Zusammenfassung in `summary.json` und in der Tabelle `eval_summaries`.

## 4. Endpunkte (§8.4)

| Kennzahl | Definition |
|---|---|
| Primärer Endpunkt | Siegquote gegen die stärkste Baseline laut G3 (`artifacts/frozen/strongest_baseline.json`, erwartet `strong_a_v1`), 2P-Duplicate, TEST, OFFICIAL_US_CLASSIC_2008 |
| Wertung | Sieg 1, Niederlage 0, abgeschnitten 0,5 (A-20) |
| Sensitivität | abgeschnittene Spiele nach kanonischer Equity entschieden |
| Immer zusätzlich | Siegquote gegen `strong_a_v1`, gegen `greedy_v1` (ungesehen, A-32) |

### Zielkriterien (implementiert in `evaluation/criteria.py`)

- **Z3 (MCR):** gepoolt über mindestens 3 Trainingsseeds (je `best_select`) untere 95-%-Grenze > 50 %
  (Seed-Cluster-Bootstrap über TEST-Seeds, B = 5.000) UND jeder Trainingsseed mit Punktschätzer > 50 %.
- **Z4 (Self-Play):** (a) Champion gegen MCR-Agent: untere Bootstrap-Grenze > 50 %; (b) Siegquote gegen
  `strong_a_v1` und `strong_b_v1` jeweils höchstens 2 Prozentpunkte unter der des MCR-Agenten (aus dessen
  TEST-Auswertung); (c) mittlere Siegquote gegen ältere Snapshots (bis zu 5, gleichmäßig gewählt) > 50 %,
  mit CI berichtet.
- **Z5 (4P, Stretch):** Gegner `strong_a_v1`, `strong_b_v1`, `roi_markov_v1` (je ein Sitz); Platz-1-Quote
  mit Wilson-Untergrenze > 25 % UND mittlere Platzierung besser als die jeder Baseline (Bootstrap-CI der
  Differenz Agent − Baseline liegt vollständig unter 0) UND Platz-1-Quote in jeder der 4 Rotationen > 25 %.
- **Sanity (G4, SELECT):** gegen `random_legal` ≥ 90 %, gegen `roi_markov_v1` > 50 %.

### TEST-Größe

Standard 2P: 1.200 Seeds × 2 Sitzbelegungen = 2.400 Spiele (≈ ±2 Prozentpunkte bei p = 0,5). Standard 4P:
250 Seeds × 4 Rotationen = 1.000 Spiele (≈ ±2,7 Prozentpunkte bei p = 0,25). `propertyrl power` berechnet n;
die gewählte Größe wird vor der ersten TEST-Auswertung mit `propertyrl power --freeze 2p=1200,4p=250` in
`artifacts/frozen/test_size.json` eingefroren.

## 5. Statistik (§8.5)

- Wilson-Score-Intervall (95 %) für Einzelquoten (Bruchteile durch Remis erlaubt).
- Seed-Cluster-Bootstrap: Resampling der Seeds (alle Spiele eines Seeds bilden einen Cluster), B = 5.000,
  RNG aus dem EVAL-Stream; Perzentil-Intervall; zweiseitiger p-Wert gegen 50 % (bzw. 0 bei Differenzen).
- Gepaarte Differenzen A − B über gemeinsame Seeds (`paired_bootstrap`), z. B. für Ablationen gegen A1.
- Holm-Korrektur für alle Sekundärvergleiche einer Berichtsfamilie (Report: je Auswertung die
  Nicht-Primärgegner, Ablationsfamilie gegen A1). Keine unkritischen t-Tests.
- Power: `n = 1,96² × p × (1 − p) / Halbbreite²` (aufgerundet): p = 0,5 → ±3 pp 1.068, ±2 pp 2.401,
  ±1 pp 9.604; p = 0,25 → ±1 pp 7.203.

## 6. Ratings (§8.6)

Elo (Start 1.500, K = 32, Spiele in fester, per Seed gemischter Reihenfolge) nur für 2P; OpenSkill
(Plackett-Luce) für 4P und zusätzlich 2P (mu, sigma, ordinal). Identische Policies in mehreren Sitzen eines
Spiels werden nicht gegeneinander bewertet.

## 7. Metriken (§8.7)

Siegquote, Platzierungsverteilung, mittlere Platzierung, Bankrott-Quote, Truncation-Quote, Spiellänge
(Runden, Entscheidungen), Kauf-, Bau-, Belastungs- und Ablösungshäufigkeit, Auktionspreis relativ zum
Druckpreis, Anzahl und Prämien der Knappheitsauktionen, Handels- und Annahmequote, Monopolbildungsquote,
Bau-Effizienz (Mieteinnahmen je in Gebäude investierter Geldeinheit), Haft-Entscheidungen nach Spielphase
(früh < 20 Runden, mittel < 60, spät), Haft-Bilanz, finale Equity, Sitz-Siegquoten (Positionsbias), illegale
Aktionen (muss 0 sein), Durchsatz, PPO-Diagnostik aus den Trainingslogs.

## 8. Kingmaking (§8.8, nur 4P)

Winner Sensitivity aus 100 Spielen, je bis zu 2 späte Entscheidungspunkte (letztes Drittel) von Spielern,
die nach Equity Letzter sind und einen Anteil < 0,5 / N_aktiv haben; je Punkt gewählte Aktion plus bis zu 3
Alternativen; je Aktion 12 Rollouts mit `engine.clone(reseed = u64(master, ROLLOUT, spiel, punkt, aktion,
rollout))`. WS = größte Totalvariationsdistanz der Siegerverteilungen. Berichtet: Verteilung und Mittelwert
von WS (Bootstrap-CI), Kingmaking-Rate (Anteil Spiele mit WS ≥ 0,25). Agenten: Spiele der TEST-Seeds
desselben Ledger-Eintrags (kein zusätzlicher Ledger-Verbrauch); Baselines als Referenz auf SELECT.

## 9. Baseline-Round-Robin (§8.9, G3) und Horizont (§8.10)

- Alle Paare aus `random_legal`, `greedy_v1`, `roi_markov_v1`, `strong_a_v1`, `strong_b_v1` im
  2P-Duplicate auf SELECT-Block 1 und Block 2 getrennt; Copeland-Rangfolge (Gleichstand nach mittlerer
  Siegquote); keine signifikanten Dreieckszyklen; identische Spitze in beiden Blöcken →
  `artifacts/frozen/strongest_baseline.json`.
- Horizont: 2.000 Spiele (`strong_a_v1` gegen `strong_b_v1` und gegen sich selbst) ohne Horizont bis 5.000
  Runden; `H = ceil(Median + 2 × SD)` der natürlich beendeten Spiele; Truncation-Quote bei H < 5 % →
  `artifacts/frozen/horizon.json` (2P und 4P), gelesen von allen Rulesets (auch als `max_rounds` des
  Kurzspiels, A-31).

## 10. Budget (§7.11)

Höchstens 12 Stunden pro Run (`BudgetCallback` stoppt sauber mit Checkpoint); Evaluation höchstens 20 % der
Gesamtrechenzeit. `propertyrl plan --experiments all` berechnet aus gemessenem Durchsatz (abgeschlossene
Runs, sonst Benchmark) Laufzeit je Run, Summen und Eval-Anteil und warnt bei Überschreitung.

## 11. Smoke-Modus (§7.10, A-34)

`--smoke` gilt für jeden Trainings-, Evaluations- und Analysebefehl; Größen aus
`configs/experiments/smoke_overrides.yaml` (1 Trainingsseed, MCR 20.000 Schritte, sonst 4.096, n_envs 2,
n_steps 256, batch_size 256, SELECT-Eval 10 Seeds, SMOKE-Eval 20 Seeds statt TEST, Round-Robin 10 Seeds je
Block, Horizont 50 Spiele, Sweep 3 × 4.096, Self-Play 2 Snapshots im Abstand von 2.048 Schritten,
Champion-Gate 10 Seeds je Block, Kingmaking 3 Spiele/1 Punkt/2 Aktionen/2 Rollouts, Curriculum-Schwellen
2.048/4.096). Smoke-Ergebnisse nutzen nur SMOKE-Seeds (bzw. SELECT-Indizes ohne Aussage), schreiben nie in
den Ledger, eingefrorene Smoke-Werte liegen in `*_smoke.json` (A-114) und jeder Report trägt
„SMOKE – keine Aussagekraft“.
