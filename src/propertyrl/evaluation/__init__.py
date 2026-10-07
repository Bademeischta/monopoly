"""Evaluation: seeds, harness, duplicate, statistics, ratings, metrics, kingmaking, round robin, horizon,
TEST ledger and reports (§8)."""

from propertyrl.evaluation.duplicate import duplicate_specs, score, summarize
from propertyrl.evaluation.evaluate import evaluate_agent, strongest_baseline
from propertyrl.evaluation.harness import GameSpec, play_game, run_games
from propertyrl.evaluation.horizon import calibrate_horizon
from propertyrl.evaluation.kingmaking import KingmakingParams, run_kingmaking
from propertyrl.evaluation.ledger import agent_hash
from propertyrl.evaluation.metrics import agent_metrics, seat_win_rates
from propertyrl.evaluation.ratings import elo, openskill
from propertyrl.evaluation.report import generate_report
from propertyrl.evaluation.roundrobin import run_round_robin
from propertyrl.evaluation.seeds import load_pools, subset, train_seed
from propertyrl.evaluation.stats import cluster_bootstrap, holm, paired_bootstrap, power_n, wilson

__all__ = [
    "GameSpec",
    "KingmakingParams",
    "agent_hash",
    "agent_metrics",
    "calibrate_horizon",
    "cluster_bootstrap",
    "duplicate_specs",
    "elo",
    "evaluate_agent",
    "generate_report",
    "holm",
    "load_pools",
    "openskill",
    "paired_bootstrap",
    "play_game",
    "power_n",
    "run_games",
    "run_kingmaking",
    "run_round_robin",
    "score",
    "seat_win_rates",
    "strongest_baseline",
    "subset",
    "summarize",
    "train_seed",
    "wilson",
]
