# API – öffentliche Schnittstellen

Alle hier gezeigten Python-Beispiele werden von `tests/architecture/test_docs.py` ausgeführt (Blöcke mit
der Sprache `python`), sie sind also lauffähig. Bezeichner und Docstrings im Code sind englisch.

## 1. Engine (`propertyrl.engine`)

| Objekt | Zweck |
|---|---|
| `Engine.new(ruleset, board, decks, n_players, seed, options)` | neues Spiel (Sitz 0 beginnt, A-26) |
| `engine.pending() -> Decision \| None` | offene Entscheidung (Sitz, Art, Phase, legale Aktionen, Kontext) |
| `engine.legal_mask() -> list[bool]` | Maske der 106 Aktions-IDs für MAIN/DEBT-Entscheidungen |
| `engine.apply(response) -> list[Event]` | Antwort anwenden (Aktions-ID, Liste von `TradeOffer`, `bool`, `Bid`/`BidLevel`) |
| `engine.is_over()`, `engine.result() -> GameResult` | Spielende, Sieger, Platzierungen, Zähler |
| `engine.clone(reseed=None, log_events=None)` | billige Kopie; `reseed` mischt nicht gezogene Karten neu |
| `engine.state_hash()` | SHA-256 des kanonischen Zustands |
| `engine.public_view(seat) -> PublicState` | Sicht für Policies (ohne Deck-Inhalt und RNG) |
| `engine.to_log()`, `write_log`, `read_log`, `replay_log` | Log und Replay mit Hash-Prüfung |
| `EngineOptions(log_events, check_invariants, dice_script, card_order, allow_test_hooks, hash_interval)` | Optionen |
| `ScenarioBuilder` | Testszenarien (Besitz, Gebäude, Bargeld, Position, Decks) |
| `render_text(state, board)` | Textdarstellung |
| `canonical_equity`, `weighted_equity`, `liquidation_value` | Equity-Funktionen (eine Implementierung) |

Konfigurationen werden über `propertyrl.infra.load_setup(ruleset_id, n_players)` geladen
(Rulesets `OFFICIAL_US_CLASSIC_2008`, `RESEARCH_2P_BOUNDED_V1`, `RESEARCH_2P_SHORTGAME_V1`,
`TEST_MOVEMENT_ONLY`).

```python
from propertyrl.agents import make_policy, respond
from propertyrl.engine import AgentRng, Engine, EngineOptions, replay_log
from propertyrl.infra import load_setup

rules, board, decks = load_setup("OFFICIAL_US_CLASSIC_2008", 2)
eng = Engine.new(rules, board, decks, 2, 42, EngineOptions(log_events=True, check_invariants=True))
policies = [make_policy("strong_a_v1"), make_policy("roi_markov_v1")]
rngs = [AgentRng(42, seat) for seat in range(2)]
while not eng.is_over() and eng.state.round_index < 400:
    decision = eng.pending()
    eng.apply(respond(policies[decision.seat], eng, rngs[decision.seat]))
log = eng.to_log()
assert replay_log(log).state_hash() == eng.state_hash()
print(eng.result().winner, eng.result().rounds)
```

Entscheidungen können auch direkt beantwortet werden:

```python
from propertyrl.engine import Engine, EngineOptions, actions, decisions
from propertyrl.infra import load_setup

rules, board, decks = load_setup("OFFICIAL_US_CLASSIC_2008", 2)
eng = Engine.new(rules, board, decks, 2, 7, EngineOptions())
d = eng.pending()
print(d.seat, d.kind, d.phase)
if d.kind == decisions.TRADE_OFFER:  # every window opens with the (optional) trade offers of the seat
    eng.apply([])
    d = eng.pending()
assert d.kind == decisions.MAIN
legal = [a for a, ok in enumerate(eng.legal_mask()) if ok]
assert actions.ROLL in legal
eng.apply(actions.ROLL)
twin = eng.clone(reseed=123)
assert twin.state.round_index == eng.state.round_index
```

## 2. Agenten (`propertyrl.agents`)

| Objekt | Zweck |
|---|---|
| `Policy` | Protokoll: `act_main`, `propose_trades`, `respond_trade`, `bid`, `liquidate` |
| `make_policy(spec)`, `cached_policy(spec)` | Registry (Namen und Präfixe siehe HEURISTICS_SPEC) |
| `respond(policy, engine, rng)` | beantwortet die offene Entscheidung mit der passenden Methode |
| `Valuer` | Bewertungsprimitive |
| `CompositePolicy`, `WithDelegation`, `EpsilonPolicy` | Komposition |
| `ExternalAgentAdapter`, `register_external` | Schnittstelle für externe Agenten (EXTERNAL_ANCHOR.md) |

```python
from propertyrl.agents import BENCHMARK_POLICIES, Valuer, make_policy
from propertyrl.engine import Engine, EngineOptions
from propertyrl.infra import load_setup

rules, board, decks = load_setup("OFFICIAL_US_CLASSIC_2008", 2)
eng = Engine.new(rules, board, decks, 2, 3, EngineOptions())
valuer = Valuer(eng.public_view(0), horizon=10)
print(BENCHMARK_POLICIES, valuer.reserve(0, 150))
pol = make_policy("epsilon:0.05:with_delegation:strong_b_v1")
print(pol.name)
```

## 3. Environments (`propertyrl.env`)

| Objekt | Zweck |
|---|---|
| `EnvConfig` | Konfiguration (Ruleset, Spielerzahl, Reward-Variante, γ, β, β2, Auto-Skip, SMDP, Delegation, Handel, Horizont, Gegner) |
| `PropertySingleAgentEnv(config)` | Gymnasium-Env mit einem Lernsitz, `action_masks()` |
| `PropertyMultiSeatEnv(config)` | mehrere Lernsitze, Transitionen in `info["closed"]` |
| `PropertyAECEnv(config)` | PettingZoo AEC |
| `OpponentConfig`, `OpponentSampler` | Gegnerwahl (fixed, curriculum, selfplay, fourp, fourp_fallback) |
| `make_env`, `env_fns`, `make_vec_env` | picklebare Factories, Dummy- oder SubprocVecEnv |
| `encode`, `obs_schema`, `OBS_DIM` | Observation-Encoder (517 Merkmale) |

```python
import numpy as np

from propertyrl.env import EnvConfig, OpponentConfig, PropertySingleAgentEnv

cfg = EnvConfig(opponents=OpponentConfig(mode="fixed", fixed=("roi_markov_v1",)), safety_horizon_rounds=200)
env = PropertySingleAgentEnv(cfg)
obs, info = env.reset(seed=1)
rng = np.random.default_rng(0)
done = False
while not done:
    mask = env.action_masks()
    action = int(rng.choice(np.flatnonzero(mask)))
    obs, reward, terminated, truncated, info = env.step(action)
    done = terminated or truncated
print(info["placement"], info["rounds"], info["truncated"])
```

```python
from propertyrl.env import EnvConfig, PropertyAECEnv

aec = PropertyAECEnv(EnvConfig(n_players=2, safety_horizon_rounds=50))
aec.reset(seed=3)
for agent in aec.agent_iter(max_iter=200):
    obs, reward, termination, truncation, info = aec.last()
    action = None if termination or truncation else int(obs["action_mask"].nonzero()[0][0])
    aec.step(action)
```

## 4. Training (`propertyrl.training`)

| Objekt | Zweck |
|---|---|
| `train(experiment, seed, smoke=False, resume=None, gamma=None, timesteps=None)` | ein Trainingslauf, Rückgabe-Dict mit `run_id`, `run_dir`, Checkpoints |
| `SMDPMaskablePPO`, `MultiSeatSMDPMaskablePPO` | Algorithmen (γ^k-Diskontierung) |
| `DurationMaskableRolloutBuffer`, `SeatChainRolloutBuffer` | Rollout-Puffer |
| `run_gamma_sweep(smoke)` | γ-Sweep, schreibt `artifacts/frozen/gamma.json` |
| `CurriculumController`, `SnapshotPool`, `pfsp_weights`, `champion_gate` | Steuerung |
| `find_checkpoint(experiment, seed, smoke, kind)` | Checkpoint eines Experiments finden |

```text
from propertyrl.training import train
res = train("mcr_official_2p", seed=1, smoke=True)   # ~1-2 Minuten auf 4 Kernen
print(res["run_dir"], res["best_select_win_rate"])
```

## 5. Evaluation (`propertyrl.evaluation`)

| Objekt | Zweck |
|---|---|
| `GameSpec`, `play_game`, `run_games` | Spiele direkt über die Engine, parallel |
| `duplicate_specs`, `summarize`, `score` | Duplicate und Wertung |
| `evaluate_agent(agent, opponents, split, n_seeds, ...)` | vollständige Auswertung mit Parquet, DB und Ledger |
| `wilson`, `cluster_bootstrap`, `paired_bootstrap`, `holm`, `power_n` | Statistik |
| `elo`, `openskill` | Ratings |
| `z3`, `z4`, `z5`, `load_records` | Zielkriterien aus gespeicherten Auswertungen |
| `run_round_robin`, `calibrate_horizon`, `run_kingmaking`, `generate_report` | Analysen |
| `load_pools`, `subset`, `train_seed`, `agent_hash` | Seeds und Ledger |

```python
from propertyrl.evaluation import duplicate_specs, run_games, subset, summarize, wilson

specs = duplicate_specs("strong_a_v1", ["greedy_v1"], subset("SMOKE", start=0, end=2), "OFFICIAL_US_CLASSIC_2008")
records = run_games(specs, workers=1)
summary = summarize(records, "strong_a_v1", bootstrap_reps=200)
print(summary["games"], summary["win_rate"], wilson(8, 10))
```

## 6. Infrastruktur (`propertyrl.infra`)

`load_setup`, `load_ruleset`, `load_experiment`, `list_experiments`, `config_hash`, `artifacts_dir`,
`runs_dir`, `reports_dir`, `evaluate_gates`, `run_benchmark`, `plan`, `diagnose`, `check_licenses`,
`run_experiment_pipeline`, `smoke_all`, `repro`.

```python
from propertyrl.infra import evaluate_gates, list_experiments

print(len(list_experiments()))
print({gate: info["status"] for gate, info in evaluate_gates().items()})
```

## 7. CLI (`propertyrl <befehl>`)

| Befehl | Zweck |
|---|---|
| `play --seed N [--p0 --p1 --players --ruleset --verbose]` | Textspiel, Log in `artifacts/logs/` |
| `replay --log <datei>` / `--verify-archive` / `--regenerate` | Replay mit Hash-Prüfung |
| `fuzz --decisions N [--total-decisions N] [--rare-events]` | Fuzzing aller Konfigurationen |
| `markov-check --moves N --tolerance-pp X` | Markov-Abgleich |
| `benchmark [--seconds S] [--smoke]` | Durchsatz und Empfehlung |
| `calibrate-horizon`, `round-robin`, `power`, `plan` | G3-Vorbereitung und Planung |
| `train --experiment E [--seed S] [--extended]` / `--resume runs/<id>` | Training |
| `sweep-gamma`, `selfplay` | γ-Sweep, Self-Play |
| `evaluate --agent A --split select\|test\|smoke [--opponents ...]` | Auswertung |
| `kingmaking`, `report --experiment E`, `gates`, `diagnose --run R`, `license-check`, `repro --run R` | Analyse und Abschluss |
| `pipeline --experiment E` / `--smoke-all` | Pipelines |

Jeder Trainings-, Evaluations- und Analysebefehl akzeptiert `--smoke`.

```bash
propertyrl play --seed 1
propertyrl replay --log artifacts/logs/play_OFFICIAL_US_CLASSIC_2008_2p_seed1.jsonl
propertyrl gates
```
