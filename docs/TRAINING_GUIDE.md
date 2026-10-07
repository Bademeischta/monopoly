# TRAINING_GUIDE – Schritt für Schritt entlang der Gates

Diese Anleitung führt von der Installation bis zum Abschlussbericht. Laufzeiten beziehen sich auf die
Referenzmessung dieses Builds (4 CPU-Kerne, siehe `docs/BUILD_REPORT.md`); `propertyrl plan --experiments
all` rechnet sie für die eigene Maschine aus dem gemessenen Durchsatz um. Alle Befehle schreiben unter
`$PROPERTYRL_HOME` (Standard: Repository-Wurzel) in `artifacts/`, `runs/` und `reports/`.

## 0. Vorbereitung

```bash
python -m venv .venv && source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e .[dev]
propertyrl play --seed 1                                     # Funktionsprobe
propertyrl pipeline --smoke-all                              # komplette Kette im Kleinformat (~25-35 min)
propertyrl gates
```

Der Smoke-Lauf prüft alle Stufen technisch; seine Ergebnisse sind als „SMOKE – keine Aussagekraft“
markiert und belasten weder SELECT-Entscheidungen noch den TEST-Ledger. Wer den Smoke-Lauf getrennt von
echten Ergebnissen halten will, setzt `PROPERTYRL_HOME` auf ein eigenes Verzeichnis.

## G0 – Artefaktsatz (Woche 1)

1. `docs/RULESPEC.md` lesen, insbesondere die V-Punkte V1–V6 (Betrag der Fonds-Karte B12, Steuer-2,
   Steuer-1, Zufall-Karte A13, Karten je Deck, Spielerzahl), und mit dem eigenen Regelheft abgleichen. Abweichungen nur in den YAML-Dateien unter
   `configs/` korrigieren (die Engine liest ausschließlich diese Werte).
2. Bestätigen: `propertyrl gates --confirm-v-points` (schreibt `artifacts/frozen/v_points_confirmed.json`).
   Fallback: ohne Bestätigung gelten die Standardwerte als eingefroren.

## G1 – Engine verifiziert (bis Woche 5)

```bash
pytest -n auto --cov=propertyrl --cov-branch --cov-report=xml:artifacts/test-reports/coverage.xml \
       --junitxml=artifacts/test-reports/junit.xml
propertyrl fuzz --total-decisions 10000000 --rare-events --rare-decisions 1000000   # Gate-Größe, ~10-15 h auf 1 Kern
propertyrl markov-check --moves 10000000 --tolerance-pp 0.05                        # Gate-Größe, ~1-2 h
propertyrl gates --gate G1
```

Die CI-Größen (100.000 Fuzz-Entscheidungen je Konfiguration, 1 Mio. Markov-Ruheereignisse) laufen in der
Testsuite bzw. mit `propertyrl fuzz --decisions 100000 --rare-events` und
`propertyrl markov-check --moves 1000000 --tolerance-pp 0.15`. `propertyrl gates` kennzeichnet, ob die
Gate-Größe erreicht ist. Fallback laut ROADMAP: Mehrfach-Asset-Angebote begrenzen bzw.
`scarcity_auction: false` (K-05).

## G2 – Environments (bis Woche 7)

```bash
PROPERTYRL_MASK_STEPS=1000000 pytest tests/env/test_masks_leak.py --junitxml=artifacts/test-reports/junit_env.xml   # 1 Mio. Schritte
propertyrl benchmark                                    # JSON in artifacts/benchmarks/, Empfehlung für n_envs
propertyrl gates --gate G2
```

Die Benchmark-Empfehlung (`vec_env`, `n_envs`) in `configs/training/ppo_default.yaml` übernehmen
(`vec_env: subproc`, wenn SubprocVecEnv schneller ist). Fallback: Logging im Training ist ohnehin aus.

## G3 – Baselines und Horizont (bis Woche 9)

```bash
propertyrl round-robin            # 10 Paare × 2 Blöcke × 1.000 Seeds × 2 Sitze = 40.000 Spiele, ~15-60 min
propertyrl calibrate-horizon      # 2.000 (2P) + 1.000 (4P) Spiele ohne Horizont, ~5-30 min
propertyrl power --freeze 2p=1200,4p=250
propertyrl gates --gate G3
```

Ergebnisse: `artifacts/frozen/strongest_baseline.json`, `horizon.json`, `test_size.json`. Fallback bei
Zyklen oder instabiler Spitze: `strong_b_v1` aus der Auswertung nehmen und `strong_a_v1` als einzige
Referenz verwenden (Gegnerlisten in `configs/experiments/*.yaml`).

## G4 – Erster Agent (bis Woche 12)

```bash
propertyrl sweep-gamma            # 3 × 2 Mio. Schritte, ~1,5-2 h je Pilot bei ~1.300 Schritten/s
propertyrl train --experiment mcr_official_2p --seed 1
propertyrl evaluate --agent experiment:mcr_official_2p:1 --split select --opponents random_legal,roi_markov_v1
propertyrl gates --gate G4
```

Der Sweep friert γ in `artifacts/frozen/gamma.json` ein. Ein MCR-Lauf mit 10 Mio. Schritten dauert bei
~1.300 Schritten/s (4 Kerne, inklusive PPO-Updates) etwa 2,2 h plus SELECT-Evaluationen; der Budget-Wächter
stoppt nach 12 h. Bei Problemen: `propertyrl diagnose --run runs/<id>` (Reward-Skala, Masken,
Observation, Entropie, explained_variance, Dauerverteilung, Gegnermix).

Abbruch und Fortsetzung: `propertyrl train --resume runs/<run_id>` lädt den jüngsten Checkpoint
(`final.zip` bei sauberem Abbruch, sonst den letzten periodischen), Optimiererzustand, Zähler,
Curriculum-Stufe, Snapshot-Pool und PFSP-Statistik; offene Mehrsitz-Transitionen werden verworfen.

## G5 – MCR auf TEST (bis Woche 14)

```bash
propertyrl pipeline --experiment mcr_official_2p     # 3 Seeds Training, SELECT + einmalige TEST-Auswertung, Bericht
propertyrl gates --gate G5
```

Die TEST-Auswertung ist je Checkpoint nur einmal möglich (Ledger). Fallbacks: Diagnose, dann Ablation N4
als neuer Hauptpfad (`ablation_n4_buy_delegated`), dann `fallback_research_2p` (als Research beschriftet);
bis Woche 16 sonst Negativergebnis im Bericht dokumentieren.

## P1 – Ablationen (Wochen 16–17)

```bash
for e in ablation_a0_terminal ablation_a2_purdue ablation_n4_buy_delegated ablation_no_trade \
         ablation_shared_delegation ablation_no_smdp research_shortgame_2p; do
  propertyrl pipeline --experiment $e
done
for e in ablation_a0_terminal mcr_official_2p ablation_a2_purdue; do   # Seeds 4 und 5 für A0, A1, A2 im Abschlussbericht
  propertyrl train --experiment $e --extended
done
```

Jede Ablation: 3 Seeds × ~2,2 h Training plus Evaluation. Die Reports vergleichen gepaart gegen A1 mit
Holm-Korrektur.

## G6 – Self-Play (bis Woche 19)

```bash
propertyrl pipeline --experiment selfplay_official_2p
propertyrl gates --gate G6
```

Start vom MCR-Checkpoint desselben Seeds; Snapshots alle 200.000 Schritte, Champion-Gate auf zwei
SELECT-Blöcken. Die TEST-Auswertung des Champions enthält in einem Aufruf die Baselines, den MCR-Agenten und
ältere Snapshots (Z4). Fallback: MCR-Agent bleibt Champion, Zyklen analysieren.

## G7 – 4 Spieler (Stretch, bis Woche 23)

```bash
propertyrl pipeline --experiment fourp_official
propertyrl pipeline --experiment ablation_a3_kingmaking_4p
propertyrl gates --gate G7
```

Fallback: `propertyrl pipeline --experiment fourp_single_seat_fallback`; reicht auch das nicht, 4P als
Ausblick dokumentieren. Kingmaking: `propertyrl kingmaking --agent experiment:fourp_official:1`.

## G8 – Abschluss (Woche 26)

```bash
propertyrl report --experiment mcr_official_2p
propertyrl repro --run runs/<mcr_run_id>
propertyrl license-check
propertyrl gates
```

`repro` spielt alle gespeicherten Auswertungen des Laufs Spiel für Spiel nach, vergleicht die Ergebnisse
und erzeugt den Bericht neu.

## Planung und Budget

- `propertyrl plan --experiments all` – Laufzeit je Run, Summen, Evaluationsanteil, Warnungen (> 12 h je
  Run, Evaluation > 20 %).
- Optional: `propertyrl train ... --wandb` protokolliert nur technische Metriken in W&B (Standard offline,
  `pip install -e .[wandb]`).
