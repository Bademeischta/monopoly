# TRAINING_GUIDE – Schritt für Schritt bis zum Abschlussbericht

Diese Anleitung führt von der Installation bis G8. Die Befehle sind gegen den Code geprüft. Laufzeiten
gelten für 4 CPU-Kerne (gemessen: ~1.030 PPO-Schritte/s, ~10 Heuristik-Spiele/s je Kern). Nach Schritt 4
rechnet `propertyrl plan --experiments all` sie für die eigene Maschine um.

| Schritt | Inhalt | Dauer (4 Kerne) |
|---|---|---|
| 1 | Installation | 10–15 min |
| 2 | Funktionsprobe inkl. Smoke-Kette | ~35 min |
| 3 | G0: V-Punkte prüfen | Handarbeit |
| 4 | G1/G2 auf dem eigenen Rechner (Pflicht) | ~50 min |
| 5 | G3: Round-Robin, Horizont, TEST-Größe | ~1–1,5 h |
| 6 | G4: γ-Sweep und erster MCR-Agent | ~5–6 h |
| 7 | G5: MCR mit 3 Seeds, TEST | ~7 h |
| 8 | P1: sieben Ablationen | ~70 h |
| 9 | G6: Self-Play | ~15 h |
| 10 | G7: 4 Spieler (Stretch) | ~10 h (+10 h Fallback, +10 h A3) |
| 11 | G8: Repro, Bericht, Abschluss | ~1 h |
| optional | Seeds 4/5 für A0, A1, A2 | ~20 h |

Gesamt etwa 140 h reine Rechenzeit, also rund 6 Tage ohne Pause, Schritte strikt nacheinander.

## Grundregeln für die Langläufe

1. **Lange Befehle nie im normalen Terminal.** Linux/macOS/WSL2: `tmux new -s prl` (abkoppeln mit
   `Strg-b d`, zurück mit `tmux attach -t prl`) oder `nohup <befehl> > logs/<name>.log 2>&1 &`. Ruhezustand
   abschalten: macOS `caffeinate -is <befehl>`, Linux-Desktop `systemd-inhibit --what=idle:sleep <befehl>`,
   Windows Energieoptionen „Nie“ und Updates pausieren. Natives Windows (ohne WSL) ist in der CI geprüft;
   alle Befehle in PowerShell-Form stehen im Anhang „Windows (PowerShell, ohne WSL)“ am Ende.
2. **Jede neue Shell:** `cd ~/propertyrl && source .venv/bin/activate` (Windows:
   `cd propertyrl; .venv\Scripts\Activate.ps1`). `echo $PROPERTYRL_HOME` muss leer sein, denn alle echten
   Ergebnisse gehören ins Repository (`artifacts/`, `runs/`, `reports/`).
3. **Smoke nur getrennt:** `--smoke` und `--smoke-all` ausschließlich mit `PROPERTYRL_HOME=$HOME/prl_smoke`.
4. **Abbrechen nur mit Strg-C** (nie Fenster schließen oder `kill -9`). Nach einem Abbruch denselben
   `propertyrl pipeline …`-Befehl erneut starten: Fertige Läufe mit gleicher Konfiguration werden
   wiederverwendet, unterbrochene fortgesetzt und vorhandene Auswertungen nicht wiederholt (A-136). Ein
   einzelner `propertyrl train`-Lauf wird mit `propertyrl train --resume runs/<run_id>` fortgesetzt.
5. **Fortschritt:** `tensorboard --logdir runs` (zweites Terminal, dann http://localhost:6006);
   `ls runs/<run_id>/checkpoints` zeigt den Stand bis 10.000.000 Schritte. Ausgaben mitschreiben:
   `… 2>&1 | tee -a logs/<schritt>.log` (PowerShell: `| Tee-Object -FilePath logs\<schritt>.log -Append`).
6. **Konfiguration einfrieren:** Änderungen in `configs/` (Schritt 3/4) sofort committen
   (`git switch -c meine-konfiguration && git commit -am "…"`) und ab Schritt 5 nichts mehr ändern.
7. **Sicherung nach jedem Gate:** `tar czf ~/prl_backup_$(date +%F).tgz artifacts runs reports` (der
   TEST-Ledger in `artifacts/propertyrl.db` ist unwiederbringlich). Nie `git clean -x` ausführen.
8. **Speicher:** Faustregel RAM ≥ 4 GB + 0,3 GB × CPU-Threads; sonst `export PROPERTYRL_EVAL_WORKERS=<n>`
   dauerhaft setzen.

## Schritt 1 – Installation

Linux/macOS/WSL2:

```bash
git clone https://github.com/Bademeischta/monopoly propertyrl && cd propertyrl
git checkout claude/propertyrl-implementation
python3.12 -m venv .venv && source .venv/bin/activate && python --version   # 3.11.x oder 3.12.x
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu          # macOS: pip install torch
pip install -e ".[dev]"
mkdir -p logs
```

Windows (PowerShell, ohne WSL): siehe Anhang am Ende dieses Dokuments.

## Schritt 2 – Funktionsprobe

```bash
propertyrl play --seed 1
pytest -n auto -m "not slow"
PROPERTYRL_HOME=$HOME/prl_smoke propertyrl pipeline --smoke-all 2>&1 | tee logs/smoke.log
PROPERTYRL_HOME=$HOME/prl_smoke propertyrl gates
```

Woran du erkennst, dass alles funktioniert:

- `play` endet mit `Sieger: 0 (strong_a_v1), Runden: 44, Entscheidungen: 2136` und
  `state_hash: 5a8b4863fa57102ec2427441b4ef923565ab02dfbd8213e38d238f5e13be84d4`.
- `pytest` meldet nur grüne Tests (1 deselektiert = die Smoke-Pipeline).
- `--smoke-all` läuft ohne Traceback durch; im JSON am Ende stehen `"test_ledger_unchanged": true` und
  `"repro_match": true` (auch in `$HOME/prl_smoke/artifacts/pipeline/smoke_all.json`).
- `gates` im Smoke-Verzeichnis: G0 PASS, G1/G2 „bereit, nicht ausgeführt“ (normal, dort liegen keine
  Testberichte), G3–G8 „bereit, nicht ausgeführt“ und **jede** Kriterienzeile nennt einen
  „Smoke-Nachweis: …“. Steht irgendwo „kein Smoke-Nachweis“, hat der Smoke-Lauf nicht funktioniert.

PowerShell: `$env:PROPERTYRL_HOME="$HOME\prl_smoke"; propertyrl pipeline --smoke-all; propertyrl gates;
Remove-Item Env:PROPERTYRL_HOME`.

## Schritt 3 – G0: V-Punkte

Tabelle V1–V6 in `docs/RULESPEC.md` mit dem eigenen Regelheft vergleichen (Betrag der Fonds-Karte B12,
Steuer-2, Steuer-1, Zufall-Karte A13, Karten je Deck, Spielerzahl).

- Alles stimmt: `propertyrl gates --confirm-v-points`.
- Ein Wert weicht ab: Wert in `configs/` ändern (Karten in `configs/cards/*.yaml`, Steuern in
  `configs/board/board_us_neutral.yaml`), `verification_points` im Ruleset-YAML und die Tabelle in
  RULESPEC anpassen, die erwarteten Werte in `tests/unit/test_data.py` und `tests/unit/test_cards_debt.py`
  nachziehen, committen, dann `propertyrl gates --confirm-v-points`. Danach Schritt 4 komplett.

## Schritt 4 – G1/G2 auf dem eigenen Rechner (Pflicht)

`artifacts/` ist nicht versioniert; ohne diesen Schritt zeigt `propertyrl gates` G1/G2 als „bereit, nicht
ausgeführt“. Im Repository-Wurzelverzeichnis, `PROPERTYRL_HOME` leer, in dieser Reihenfolge:

```bash
pytest -n auto -m "not slow" --cov=propertyrl --cov-branch \
       --cov-report=xml:artifacts/test-reports/coverage.xml --junitxml=artifacts/test-reports/junit.xml
propertyrl fuzz --total-decisions 10000000 --rare-events --rare-decisions 1000000     # ~7 min
propertyrl markov-check --moves 10000000 --tolerance-pp 0.05                          # ~4 min
PROPERTYRL_MASK_STEPS=1000000 pytest tests/env/test_masks_leak.py \
       --junitxml=artifacts/test-reports/junit_env.xml                                # ~4 min
propertyrl benchmark
propertyrl plan --experiments all
propertyrl gates
```

Erwartung: `G1: PASS` und `G2: PASS`, Fuzz/Markov/Maskentest jeweils „(Gate-Größe)“. Aus dem Benchmark nur
`recommendation.vec_env` übernehmen: Steht dort `subproc`, in `configs/training/ppo_default.yaml`
`vec_env: subproc` setzen und committen; `n_envs: 16` bleibt (wird automatisch auf die Kernzahl begrenzt).
Liegt `hours_per_run` + `eval_hours_per_run` aus `plan` nahe 12 h, `budget_hours` erhöhen.

## Schritt 5 – G3: Baselines und Horizont

```bash
propertyrl round-robin --workers 4          # --workers = Kernzahl, wenn sonst nichts läuft
propertyrl calibrate-horizon --workers 4
propertyrl power --freeze 2p=1200,4p=250
propertyrl gates --gate G3
```

- Round-Robin FAIL (Zyklus oder instabile Spitze): Fallback ohne `strong_b_v1`:
  `propertyrl round-robin --policies random_legal,greedy_v1,roi_markov_v1,strong_a_v1`. Bleibt die Spitze
  instabil, in `artifacts/frozen/strongest_baseline.json` `"policy": "strong_a_v1"` setzen (ROADMAP:
  `strong_a_v1` als einzige Referenz) und als Abweichung notieren. `strong_b_v1` bleibt Gegner in den
  Auswertungen (Z4 braucht ihn).
- `calibrate-horizon` endet mit Exit-Code 1, wenn die 2P-Truncation ≥ 5 % ist (kein Absturz). G3 wird an
  2P gemessen (A-135); eine hohe 4P-Truncation ist ein erwarteter Befund (Patt-Spiele ohne Monopole) und
  betrifft erst G7.
- Nach diesem Schritt `round-robin` und `calibrate-horizon` nicht mehr wiederholen: Training und
  Auswertung lesen die eingefrorenen Dateien.

## Schritt 6 – G4: γ-Sweep und erster Agent

```bash
propertyrl sweep-gamma 2>&1 | tee logs/sweep.log                        # 3 Piloten à 2 Mio. Schritte
propertyrl train --experiment mcr_official_2p --seed 1 2>&1 | tee logs/mcr_s1.log
propertyrl evaluate --agent experiment:mcr_official_2p:1 --split select --experiment mcr_official_2p
propertyrl gates --gate G4
```

Erwartung: γ eingefroren, gegen `random_legal` ≥ 90 %, gegen `roi_markov_v1` > 50 % (SELECT). Die Ausgabe
von `evaluate` nennt unter `agent` den verwendeten Checkpoint (`runs/mcr_official_2p_s1_…`, kein
`_g…`-Pilot).

**Stopp-Regel:** Nur bei G4 PASS weiter. Bei FAIL: `propertyrl diagnose --run runs/<run_id>` (Reward-Skala,
Masken, Entropie, explained_variance, Dauerverteilung, Gegnermix), Ursache beheben, Schritt 6 wiederholen.
Bis dahin keine TEST-Auswertung.

## Schritt 7 – G5: MCR auf TEST

```bash
propertyrl pipeline --experiment mcr_official_2p 2>&1 | tee logs/mcr_pipeline.log
propertyrl gates --gate G5
```

Die Pipeline übernimmt den Seed-1-Lauf aus Schritt 6 (gleiche Konfiguration), trainiert Seeds 2 und 3 und
wertet alle drei einmalig auf TEST aus. Bei Abbruch denselben Befehl erneut starten.

Bei G5 FAIL: `propertyrl diagnose --run runs/<run_id>`; dann die Ablation N4 vorziehen
(`propertyrl pipeline --experiment ablation_n4_buy_delegated`, Z3 im Bericht
`reports/ablation_n4_buy_delegated.md` prüfen) und danach
`propertyrl pipeline --experiment fallback_research_2p` (als Research beschriftet). G5 bleibt im
Gate-Status FAIL; das Negativergebnis im Bericht dokumentieren. Bei G5 PASS `fallback_research_2p` nicht
ausführen.

## Schritt 8 – P1: Ablationen

```bash
for e in ablation_a0_terminal ablation_a2_purdue ablation_n4_buy_delegated ablation_no_trade \
         ablation_shared_delegation ablation_no_smdp research_shortgame_2p; do
  propertyrl pipeline --experiment $e 2>&1 | tee -a logs/p1_$e.log
done
```

PowerShell: `foreach ($e in 'ablation_a0_terminal','ablation_a2_purdue','ablation_n4_buy_delegated',
'ablation_no_trade','ablation_shared_delegation','ablation_no_smdp','research_shortgame_2p')
{ propertyrl pipeline --experiment $e }`. Die Schleife darf nach einem Abbruch einfach neu gestartet werden.

## Schritt 9 – G6: Self-Play

```bash
propertyrl pipeline --experiment selfplay_official_2p 2>&1 | tee logs/selfplay.log
propertyrl gates --gate G6
```

Voraussetzung sind die drei MCR-Läufe aus Schritt 7 (Self-Play-Seed s startet vom MCR-Seed s). Die
TEST-Auswertung des Champions enthält automatisch den MCR-Agenten und ältere Snapshots (Z4). Bei FAIL bleibt
der MCR-Agent Champion; Zyklen in `runs/<selfplay_run>/training_state.json` (`champion_history`)
analysieren. G8 hängt nicht von G6 ab.

## Schritt 10 – G7: 4 Spieler (Stretch)

```bash
propertyrl pipeline --experiment fourp_official 2>&1 | tee logs/fourp.log
propertyrl gates --gate G7
# nur bei FAIL:
propertyrl pipeline --experiment fourp_single_seat_fallback && propertyrl gates --gate G7
# Ablation A3 (nicht gate-relevant):
propertyrl pipeline --experiment ablation_a3_kingmaking_4p
```

Reicht auch der Fallback nicht, 4P im Bericht als Ausblick dokumentieren.

## Schritt 11 – G8: Abschluss

```bash
MCR_RUN=$(ls -d runs/mcr_official_2p_s1_* | sort | tail -1)    # der TEST-ausgewertete Seed-1-Lauf
propertyrl repro --run "$MCR_RUN"
propertyrl report --experiment mcr_official_2p
propertyrl license-check
propertyrl gates
```

Reihenfolge beachten: `repro` erzeugt den Bericht ebenfalls neu, deshalb `report` danach, damit dessen
Gate-Tabelle G8 bereits enthält. Für alle anderen Experimente liegen die Berichte unter
`reports/<experiment>.md`.

## Optional – Seeds 4 und 5 für A0, A1 und A2

Nur wenn Zeit übrig ist (ROADMAP: Pufferwochen); G5 bleibt davon unberührt (A-137).

```bash
for e in ablation_a0_terminal mcr_official_2p ablation_a2_purdue; do
  propertyrl train --experiment $e --extended
  for s in 4 5; do
    propertyrl evaluate --agent experiment:$e:$s --split select --experiment $e
    propertyrl evaluate --agent experiment:$e:$s --split test --experiment $e
  done
  propertyrl report --experiment $e
done
```

## Wenn etwas schiefgeht

| Symptom | Maßnahme |
|---|---|
| Terminal geschlossen, Strom weg, Abbruch | denselben `pipeline`-Befehl neu starten bzw. `propertyrl train --resume runs/<id>` |
| `SeedLedgerError` | Agent wurde schon auf TEST ausgewertet – nicht erzwingen; `--force-retest` nur bewusst, wird im Bericht markiert |
| `EngineWatchdogError` | Log in `artifacts/errors/` sichern, Fehler melden; betroffenen Lauf mit `--resume` fortsetzen |
| Gate FAIL | Fallbacks in `docs/ROADMAP.md`, Diagnose mit `propertyrl diagnose --run runs/<id>` |
| Lauf stoppt nach 12 h | Budget-Wächter: `budget_hours` in `configs/training/ppo_default.yaml` prüfen |
| Speicher voll (OOM) | `PROPERTYRL_EVAL_WORKERS` kleiner setzen |
| Windows: `UnicodeEncodeError` | `$env:PYTHONUTF8 = "1"` |

## Anhang: Windows (PowerShell, ohne WSL) – alle Schritte

Gilt für Windows 10/11 mit der vorinstallierten Windows PowerShell 5.1 und für PowerShell 7. Die
Inhalte der Schritte (Erwartungen, Stopp-Regeln, Fallbacks) sind dieselben wie oben; hier stehen nur die
Befehle in Windows-Form. Unterschiede zu Linux: Umgebungsvariablen mit `$env:NAME = "wert"`, kein `tmux`
(stattdessen bleibt das PowerShell-Fenster offen und lange Läufe schreiben in eine Logdatei, die ein zweites
Fenster live anzeigt), kein `&&`.

### Einmalige Vorbereitung

Voraussetzungen: Python 3.12 von python.org (mit „py launcher“) und Git für Windows, z. B. per
`winget install Python.Python.3.12` und `winget install Git.Git`.

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

Danach ein neues PowerShell-Fenster öffnen. Windows-Updates für die Laufzeit pausieren (Einstellungen →
Windows Update → Updates aussetzen) und den Rechner am Netzteil lassen.

### Jedes neue Fenster

```powershell
cd $HOME\propertyrl
.\.venv\Scripts\Activate.ps1
Remove-Item Env:PROPERTYRL_HOME -ErrorAction SilentlyContinue
```

### Lange Läufe und Logs

Lange Befehle über `cmd /c` mit Umleitung in eine Logdatei starten (funktioniert in PowerShell 5.1 und 7
gleich) und in einem zweiten Fenster mitlesen. Das erste Fenster nicht schließen; abbrechen nur mit Strg-C.

```powershell
cmd /c "propertyrl pipeline --experiment mcr_official_2p > logs\mcr_pipeline.log 2>&1"
"Exit-Code: $LASTEXITCODE"
```

Zweites Fenster (mitlesen):

```powershell
Get-Content $HOME\propertyrl\logs\mcr_pipeline.log -Wait -Tail 30 -Encoding UTF8
```

### Schritt 1 – Installation

```powershell
cd $HOME
git clone https://github.com/Bademeischta/monopoly propertyrl
cd propertyrl
git checkout claude/propertyrl-implementation
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
New-Item -ItemType Directory -Force logs | Out-Null
```

### Schritt 2 – Funktionsprobe

```powershell
propertyrl play --seed 1
pytest -n auto -m "not slow"
$env:PROPERTYRL_HOME = "$HOME\prl_smoke"
cmd /c "propertyrl pipeline --smoke-all > logs\smoke.log 2>&1"
"Exit-Code: $LASTEXITCODE"
Get-Content "$HOME\prl_smoke\artifacts\pipeline\smoke_all.json" -Encoding UTF8 | ConvertFrom-Json | Select-Object test_ledger_unchanged, repro_match
propertyrl gates
Remove-Item Env:PROPERTYRL_HOME
```

Erwartung: Exit-Code 0, `test_ledger_unchanged` und `repro_match` sind `True`, und bei `gates` nennt jede
Zeile von G3–G8 einen „Smoke-Nachweis“.

### Schritt 3 – G0

```powershell
propertyrl gates --confirm-v-points
```

### Schritt 4 – G1/G2 (Pflicht)

```powershell
pytest -n auto -m "not slow" --cov=propertyrl --cov-branch --cov-report=xml:artifacts/test-reports/coverage.xml --junitxml=artifacts/test-reports/junit.xml
cmd /c "propertyrl fuzz --total-decisions 10000000 --rare-events --rare-decisions 1000000 > logs\fuzz.log 2>&1"
propertyrl markov-check --moves 10000000 --tolerance-pp 0.05
$env:PROPERTYRL_MASK_STEPS = "1000000"
pytest tests/env/test_masks_leak.py --junitxml=artifacts/test-reports/junit_env.xml
Remove-Item Env:PROPERTYRL_MASK_STEPS
propertyrl benchmark
propertyrl plan --experiments all
propertyrl gates
```

### Schritt 5 – G3

```powershell
propertyrl round-robin --workers $env:NUMBER_OF_PROCESSORS
propertyrl calibrate-horizon --workers $env:NUMBER_OF_PROCESSORS
propertyrl power --freeze 2p=1200,4p=250
propertyrl gates --gate G3
```

### Schritt 6 – G4

```powershell
cmd /c "propertyrl sweep-gamma > logs\sweep.log 2>&1"
cmd /c "propertyrl train --experiment mcr_official_2p --seed 1 > logs\mcr_s1.log 2>&1"
propertyrl evaluate --agent experiment:mcr_official_2p:1 --split select --experiment mcr_official_2p
propertyrl gates --gate G4
```

### Schritt 7 – G5

```powershell
cmd /c "propertyrl pipeline --experiment mcr_official_2p > logs\mcr_pipeline.log 2>&1"
propertyrl gates --gate G5
```

### Schritt 8 – Ablationen

```powershell
$ablations = "ablation_a0_terminal", "ablation_a2_purdue", "ablation_n4_buy_delegated", "ablation_no_trade", "ablation_shared_delegation", "ablation_no_smdp", "research_shortgame_2p"
foreach ($e in $ablations) {
    cmd /c "propertyrl pipeline --experiment $e > logs\p1_$e.log 2>&1"
    if ($LASTEXITCODE -ne 0) { Write-Host "Fehler in $e (Exit-Code $LASTEXITCODE), siehe logs\p1_$e.log"; break }
}
```

### Schritt 9 – G6

```powershell
cmd /c "propertyrl pipeline --experiment selfplay_official_2p > logs\selfplay.log 2>&1"
propertyrl gates --gate G6
```

### Schritt 10 – G7

```powershell
cmd /c "propertyrl pipeline --experiment fourp_official > logs\fourp.log 2>&1"
propertyrl gates --gate G7
```

Nur bei FAIL: `cmd /c "propertyrl pipeline --experiment fourp_single_seat_fallback > logs\fourp_fallback.log 2>&1"`,
danach `propertyrl gates --gate G7`. Ablation A3: `cmd /c "propertyrl pipeline --experiment
ablation_a3_kingmaking_4p > logs\a3.log 2>&1"`.

### Schritt 11 – G8

```powershell
$mcr = Get-ChildItem runs -Directory -Filter "mcr_official_2p_s1_*" | Sort-Object Name | Select-Object -Last 1
propertyrl repro --run $mcr.FullName
propertyrl report --experiment mcr_official_2p
propertyrl license-check
propertyrl gates
```

### Sicherung nach jedem Gate

```powershell
tar -czf "$HOME\prl_backup_$(Get-Date -Format yyyy-MM-dd).tgz" artifacts runs reports
```

Fortschritt eines Trainings: `tensorboard --logdir runs` und im Browser http://localhost:6006 öffnen.

