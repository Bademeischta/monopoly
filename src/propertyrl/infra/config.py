"""Configuration models (pydantic v2), YAML loading and config hashing (§9.1).

The engine never reads YAML; this module parses the files, validates them and
builds the immutable engine objects.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from propertyrl.engine import constants as C
from propertyrl.engine.board import Board
from propertyrl.engine.cards import EFFECT_TYPES, Decks
from propertyrl.engine.errors import ConfigError
from propertyrl.engine.hashing import sha256_hex
from propertyrl.engine.ruleset import Ruleset

#: Repository root (src/propertyrl/infra/config.py -> repo).
REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "configs"
#: Label of every smoke result (A-34).
SMOKE_LABEL = "SMOKE – keine Aussagekraft"

RULESET_FILES = {
    "OFFICIAL_US_CLASSIC_2008": "official_us_classic_2008.yaml",
    "RESEARCH_2P_BOUNDED_V1": "research_2p_bounded_v1.yaml",
    "RESEARCH_2P_SHORTGAME_V1": "research_2p_shortgame_v1.yaml",
    "TEST_MOVEMENT_ONLY": "test_movement_only.yaml",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- engine data models
class SquareModel(_Strict):
    index: int = Field(ge=0, lt=C.N_SQUARES)
    kind: Literal["START", "STREET", "RAIL", "UTIL", "CARD_A", "CARD_B", "TAX", "JAIL", "REST", "ARREST"]
    name: str
    group: str | None = None
    price: int = Field(default=0, ge=0)
    rents: list[int] = Field(default_factory=list)
    house_price: int = Field(default=0, ge=0)
    mortgage_value: int = Field(default=0, ge=0)
    tax: int = Field(default=0, ge=0)


class BoardModel(_Strict):
    board_id: str
    squares: list[SquareModel]


class CardModel(_Strict):
    id: str
    effect: str
    params: list[int] = Field(default_factory=list)
    text: str

    @field_validator("effect")
    @classmethod
    def _effect_known(cls, v: str) -> str:
        if v not in EFFECT_TYPES:
            raise ValueError(f"unknown effect {v}")
        return v


class DeckModel(_Strict):
    deck: Literal["A", "B"]
    name: str
    cards: list[CardModel]


class RulesetModel(_Strict):
    ruleset_id: str
    source: str
    edition: str
    version: str
    player_count: list[int]
    rule_ids: list[str]
    protocol_ids: list[str]
    deviation_ids: list[str]
    known_deviations: list[str]
    house_rules: list[str]
    decision_protocol: Literal["official_windows", "own_turn_only"]
    auction_protocol: Literal["ascending_open", "sealed_7_levels"]
    trade_protocol: Literal["window_offers", "active_player_only", "none"]
    scarcity_auction: bool
    game_end: Literal["natural", "short_game"]
    safety_horizon_rounds: int = Field(gt=0)
    max_rounds: int = Field(ge=0)
    verification_points: dict[str, Any] = Field(default_factory=dict)
    starting_cash: int = Field(default=1500, ge=0)
    salary: int = Field(default=200, ge=0)
    jail_fine: int = Field(default=50, ge=0)
    mortgage_interest_percent: int = Field(default=10, ge=0)
    bank_houses: int = Field(default=32, ge=0)
    bank_hotels: int = Field(default=12, ge=0)
    movement_only: bool = False


# --------------------------------------------------------------------------- policy, training, seeds
class PolicyConfig(_Strict):
    name: str
    heuristic_version: str
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class PPOConfig(_Strict):
    n_envs: int = Field(default=16, gt=0)
    n_steps: int = Field(default=256, gt=0)
    batch_size: int = Field(default=512, gt=1)
    n_epochs: int = Field(default=10, gt=0)
    learning_rate: float = Field(default=3e-4, gt=0)
    gamma: float = Field(default=0.995, gt=0, le=1)
    gae_lambda: float = Field(default=0.95, ge=0, le=1)
    clip_range: float = Field(default=0.2, gt=0)
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    net_arch_pi: list[int] = Field(default_factory=lambda: [256, 256])
    net_arch_vf: list[int] = Field(default_factory=lambda: [256, 256])
    activation: Literal["relu", "tanh"] = "relu"
    ortho_init: bool = True
    layer_norm: bool = False
    device: Literal["cpu", "auto", "cuda"] = "cpu"
    total_timesteps: int = Field(default=10_000_000, gt=0)
    checkpoint_interval: int = Field(default=100_000, gt=0)
    keep_checkpoints: int = Field(default=10, gt=0)
    select_eval_interval: int = Field(default=500_000, gt=0)
    select_eval_seeds: int = Field(default=200, gt=0)
    vec_env: Literal["dummy", "subproc"] = "dummy"
    budget_hours: float = Field(default=12.0, gt=0)
    eval_budget_fraction: float = Field(default=0.2, gt=0, le=1)
    ev_warning_fraction: float = 0.2
    ev_warning_threshold: float = 0.3


class SeedPoolConfig(_Strict):
    pool_id: int
    size: int = Field(gt=0)


class SeedsConfig(_Strict):
    master_seed: int
    pools: dict[str, SeedPoolConfig]
    subsets: dict[str, list[int]]


# --------------------------------------------------------------------------- experiments
class EnvSettings(_Strict):
    ruleset: str = "OFFICIAL_US_CLASSIC_2008"
    n_players: int = Field(default=2, ge=2, le=4)
    reward_variant: Literal["A0", "A1", "A2", "A3"] = "A1"
    gamma: float | Literal["frozen"] = "frozen"
    beta: float = 1.0
    beta2: float = 0.01
    kingmaking_malus: float = 0.1
    terminal_rewards_4p: list[float] = Field(default_factory=lambda: [1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0])
    auto_skip: bool = True
    smdp: bool = True
    delegation: str = "delegation_v1"
    delegated_kinds: list[str] = Field(default_factory=lambda: ["TRADE_OFFER", "TRADE_RESPONSE", "AUCTION_BID", "DEBT"])
    trade_enabled: bool = True
    safety_horizon_rounds: int | Literal["frozen"] = "frozen"
    max_rounds: int | Literal["frozen"] | None = None


class OpponentSettings(_Strict):
    mode: Literal["curriculum", "selfplay", "fourp", "fourp_fallback", "fixed"] = "curriculum"
    fixed: list[str] = Field(default_factory=lambda: ["strong_a_v1"])
    curriculum_stages: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {"opponents": ["random_legal"], "threshold": 0.80, "max_steps": 1_000_000},
            {"opponents": ["roi_markov_v1"], "threshold": 0.55, "max_steps": 3_000_000},
            {"opponents": ["strong_a_v1", "strong_b_v1"], "threshold": None, "max_steps": None},
        ]
    )
    epsilon_train: float = Field(default=0.05, ge=0, le=1)
    shared_delegation: bool = False
    baselines: list[str] = Field(default_factory=lambda: ["strong_a_v1", "strong_b_v1"])
    recent_snapshots: int = 5
    p_recent: float = 0.5
    p_old: float = 0.3
    p_baseline: float = 0.2
    extra_learning_seat_prob: float = 0.4
    snapshot_interval: int = 200_000
    pool_max: int = 50
    select_mini_seeds: int = 100


class TrainingSettings(_Strict):
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3])
    #: Additional seeds for the final report (A0, A1, A2 with 5 seeds, §0.1).
    extended_seeds: list[int] = Field(default_factory=list)
    ppo_overrides: dict[str, Any] = Field(default_factory=dict)
    init_from: str | None = None
    algorithm: Literal["smdp_ppo", "multiseat_ppo"] = "smdp_ppo"


class EvaluationSettings(_Strict):
    opponents: list[str] = Field(
        default_factory=lambda: ["strongest_baseline", "strong_a_v1", "strong_b_v1", "greedy_v1",
                                 "roi_markov_v1", "random_legal"]
    )  # fmt: skip
    n_test_seeds: int | Literal["frozen"] = "frozen"
    n_select_seeds: int = 200


class SweepSettings(_Strict):
    gammas: list[float] = Field(default_factory=lambda: [0.99, 0.995, 0.999])
    timesteps: int = 2_000_000
    seed: int = 1


class SelfPlaySettings(_Strict):
    gate_block1: list[int] = Field(default_factory=lambda: [0, 400])
    gate_block2: list[int] = Field(default_factory=lambda: [1000, 1400])
    gate_margin_pp: float = 2.0


class ExperimentConfig(_Strict):
    name: str
    description: str
    label: Literal["official", "research"] = "official"
    mode: Literal["single", "multiseat", "selfplay", "sweep"] = "single"
    env: EnvSettings = Field(default_factory=EnvSettings)
    opponents: OpponentSettings = Field(default_factory=OpponentSettings)
    training: TrainingSettings = Field(default_factory=TrainingSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    sweep: SweepSettings | None = None
    selfplay: SelfPlaySettings | None = None
    requires_gate_failure: str | None = None
    report_label: str = ""


class SmokeOverrides(_Strict):
    training_seeds: int = 1
    mcr_timesteps: int = 20_000
    other_timesteps: int = 4096
    n_envs: int = 2
    n_steps: int = 256
    batch_size: int = 256
    checkpoint_interval: int = 2048
    select_eval_interval: int = 4096
    select_eval_seeds: int = 10
    smoke_eval_seeds: int = 20
    roundrobin_seeds_per_block: int = 10
    horizon_games: int = 50
    sweep_timesteps: int = 4096
    selfplay_snapshots: int = 2
    selfplay_snapshot_interval: int = 2048
    champion_gate_seeds: int = 10
    kingmaking_games: int = 3
    kingmaking_points: int = 1
    kingmaking_actions: int = 2
    kingmaking_rollouts: int = 2
    curriculum_thresholds: list[int] = Field(default_factory=lambda: [2048, 4096])
    select_mini_seeds: int = 10
    budget_hours: float = 1.0


# --------------------------------------------------------------------------- loading
def load_yaml(path: Path) -> Any:
    """Load a YAML file with a clear ConfigError on failure."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc


def _validate(model: type[BaseModel], data: Any, path: Path) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


@functools.cache
def load_board(path: str | None = None) -> Board:
    """Load and validate the board."""
    p = Path(path) if path else CONFIG_DIR / "board" / "board_us_neutral.yaml"
    model = _validate(BoardModel, load_yaml(p), p)
    return Board.from_dict(model.model_dump())


@functools.cache
def load_decks(path_a: str | None = None, path_b: str | None = None) -> Decks:
    """Load and validate both card decks."""
    pa = Path(path_a) if path_a else CONFIG_DIR / "cards" / "deck_a.yaml"
    pb = Path(path_b) if path_b else CONFIG_DIR / "cards" / "deck_b.yaml"
    ma = _validate(DeckModel, load_yaml(pa), pa)
    mb = _validate(DeckModel, load_yaml(pb), pb)
    return Decks.from_dicts(ma.model_dump(), mb.model_dump())


@functools.cache
def _load_ruleset_file(ruleset_id: str) -> Ruleset:
    if ruleset_id not in RULESET_FILES:
        raise ConfigError(f"unknown ruleset {ruleset_id!r}; known: {sorted(RULESET_FILES)}")
    p = CONFIG_DIR / "rulesets" / RULESET_FILES[ruleset_id]
    model = _validate(RulesetModel, load_yaml(p), p)
    return Ruleset.from_dict(model.model_dump())


def frozen_dir() -> Path:
    """Directory of frozen artifacts (gamma, horizon, strongest baseline, test size)."""
    from propertyrl.infra.storage import artifacts_dir

    return artifacts_dir() / "frozen"


#: Command that (re)creates each frozen artifact (runbook order, docs/TRAINING_GUIDE.md).
FROZEN_SOURCES = {
    "v_points_confirmed": "propertyrl gates --confirm-v-points",
    "strongest_baseline": "propertyrl round-robin",
    "horizon": "propertyrl calibrate-horizon",
    "test_size": "propertyrl power --freeze 2p=1200,4p=250",
    "gamma": "propertyrl sweep-gamma",
}


def require_frozen(names: list[str], purpose: str) -> None:
    """Refuse to start ``purpose`` while an earlier runbook step has not frozen its artifact."""
    missing = [n for n in names if read_frozen(n) is None]
    if missing:
        steps = "; ".join(f"artifacts/frozen/{n}.json <- {FROZEN_SOURCES[n]}" for n in missing)
        raise ConfigError(f"{purpose} needs the frozen artifacts of the earlier runbook steps first: {steps}")


def read_frozen(name: str) -> dict[str, Any] | None:
    """Read artifacts/frozen/<name>.json if present; a damaged file raises ArtifactError with the repair command."""
    from propertyrl.engine.errors import ArtifactError
    from propertyrl.infra.storage import read_json

    path = frozen_dir() / f"{name}.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = read_json(path)
    except ArtifactError as err:
        source = FROZEN_SOURCES.get(name.removesuffix("_smoke"), "the command that wrote it")
        raise ArtifactError(f"{err.raw_message}; delete the file and run '{source}' again",
                            details=err.details) from err  # fmt: skip
    return data


def load_ruleset(ruleset_id: str, use_frozen_horizon: bool = True, **overrides: Any) -> Ruleset:
    """Load a ruleset; the calibrated horizon (artifacts/frozen/horizon.json) is applied when present."""
    rules = _load_ruleset_file(ruleset_id)
    explicit = "safety_horizon_rounds" in overrides and (not rules.short_game or "max_rounds" in overrides)
    if use_frozen_horizon and not rules.movement_only and not explicit:
        frozen = read_frozen("horizon")
        if frozen:
            key = "horizon_4p" if overrides.get("_n_players", 2) > 2 else "horizon_2p"
            value = frozen.get(key) or frozen.get("horizon_2p")
            if value:
                upd: dict[str, Any] = {"safety_horizon_rounds": int(value)}
                if rules.short_game:
                    upd["max_rounds"] = int(frozen.get("horizon_2p", value))
                rules = rules.with_overrides(**upd)
    overrides.pop("_n_players", None)
    if overrides:
        rules = rules.with_overrides(**overrides)
    return rules


def load_setup(ruleset_id: str, n_players: int = 2, **overrides: Any) -> tuple[Ruleset, Board, Decks]:
    """Convenience: (ruleset, board, decks) for a ruleset id."""
    return load_ruleset(ruleset_id, _n_players=n_players, **overrides), load_board(), load_decks()


@functools.cache
def load_policy_config(name: str) -> PolicyConfig:
    """Load configs/policies/<name>.yaml."""
    p = CONFIG_DIR / "policies" / f"{name}.yaml"
    cfg: PolicyConfig = _validate(PolicyConfig, load_yaml(p), p)
    return cfg


def load_ppo_config(path: Path | None = None) -> PPOConfig:
    """Load configs/training/ppo_default.yaml."""
    p = path or CONFIG_DIR / "training" / "ppo_default.yaml"
    cfg: PPOConfig = _validate(PPOConfig, load_yaml(p), p)
    return cfg


@functools.cache
def load_seeds_config() -> SeedsConfig:
    """Load configs/training/seeds.yaml."""
    p = CONFIG_DIR / "training" / "seeds.yaml"
    cfg: SeedsConfig = _validate(SeedsConfig, load_yaml(p), p)
    return cfg


def load_experiment(name: str) -> ExperimentConfig:
    """Load configs/experiments/<name>.yaml."""
    p = CONFIG_DIR / "experiments" / f"{name}.yaml"
    cfg: ExperimentConfig = _validate(ExperimentConfig, load_yaml(p), p)
    if cfg.name != name:
        raise ConfigError(f"{p}: name {cfg.name!r} does not match file name")
    return cfg


def list_experiments() -> list[str]:
    """Names of all experiment configs (excluding smoke overrides)."""
    return sorted(p.stem for p in (CONFIG_DIR / "experiments").glob("*.yaml") if p.stem != "smoke_overrides")


def load_smoke_overrides() -> SmokeOverrides:
    """Load configs/experiments/smoke_overrides.yaml."""
    p = CONFIG_DIR / "experiments" / "smoke_overrides.yaml"
    cfg: SmokeOverrides = _validate(SmokeOverrides, load_yaml(p), p)
    return cfg


def config_hash(obj: Any) -> str:
    """SHA-256 over the canonical JSON of a fully resolved configuration."""
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return sha256_hex(obj)
