"""Opponent and learning-seat sampling (§6.9): curriculum, self-play with PFSP, 4P shared policy, fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from propertyrl.agents.base import Policy
from propertyrl.agents.registry import make_policy
from propertyrl.engine.errors import ConfigError
from propertyrl.engine.rng import SeededStream

MODES = ("curriculum", "selfplay", "fourp", "fourp_fallback", "fixed")
DEFAULT_STAGES: tuple[tuple[str, ...], ...] = (
    ("random_legal",),
    ("roi_markov_v1",),
    ("strong_a_v1", "strong_b_v1"),
)


@dataclass
class OpponentConfig:
    """Sampler configuration (plain data, picklable)."""

    mode: str = "fixed"
    fixed: tuple[str, ...] = ("strong_a_v1",)
    stages: tuple[tuple[str, ...], ...] = DEFAULT_STAGES
    stage: int = 0
    epsilon: float = 0.05
    shared_delegation: bool = False
    baselines: tuple[str, ...] = ("strong_a_v1", "strong_b_v1")
    recent: int = 5
    p_recent: float = 0.5
    p_old: float = 0.3
    p_baseline: float = 0.2
    extra_learning_prob: float = 0.4
    snapshots: tuple[str, ...] = ()
    latest_path: str | None = None
    weights: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ConfigError(f"unknown opponent mode {self.mode!r}")
        if "greedy_v1" in self.fixed or any("greedy_v1" in s for st in self.stages for s in st):
            raise ConfigError("greedy_v1 is the unseen evaluation policy and never a training opponent (A-32)")
        self.fixed = tuple(self.fixed)
        self.stages = tuple(tuple(s) for s in self.stages)
        self.baselines = tuple(self.baselines)
        self.snapshots = tuple(self.snapshots)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OpponentConfig:
        """Inverse of :meth:`to_dict` (lists become tuples)."""
        data = dict(d)
        if "stages" in data:
            data["stages"] = tuple(tuple(s) for s in data["stages"])
        for key in ("fixed", "baselines", "snapshots"):
            if key in data:
                data[key] = tuple(data[key])
        return cls(**data)


@dataclass
class SeatPlan:
    """Roles of one game: learning seats and opponent specs per seat."""

    learning_seats: list[int]
    opponents: dict[int, str]
    opponent_ids: dict[int, str]
    category: dict[int, str]


class OpponentSampler:
    """Samples seat roles per game; opponents are cached policy objects."""

    def __init__(self, cfg: OpponentConfig, n_players: int) -> None:
        self.cfg = cfg
        self.n = n_players
        self._cache: dict[str, Policy] = {}

    # ------------------------------------------------------------------ updates from callbacks
    def set_weights(self, weights: dict[str, float]) -> None:
        """PFSP weights per snapshot id (path)."""
        self.cfg.weights = dict(weights)

    def reload(self, manifest: dict[str, Any]) -> None:
        """New snapshot list and/or latest policy file; cached SB3 opponents are dropped."""
        if "snapshots" in manifest:
            self.cfg.snapshots = tuple(manifest["snapshots"])
        if "latest_path" in manifest:
            self.cfg.latest_path = manifest["latest_path"]
        self._cache = {k: v for k, v in self._cache.items() if "snapshot:" not in k and "latest:" not in k}

    def set_stage(self, stage: int) -> None:
        """Curriculum stage (0-based)."""
        self.cfg.stage = max(0, min(int(stage), len(self.cfg.stages) - 1))

    # ------------------------------------------------------------------ sampling
    def _wrap(self, base: str) -> str:
        spec = base
        if self.cfg.shared_delegation and ":" not in base:
            spec = f"with_delegation:{spec}"
        if self.cfg.epsilon > 0:
            spec = f"epsilon:{self.cfg.epsilon}:{spec}"
        return spec

    def _category_opponent(self, rng: SeededStream) -> tuple[str, str, str]:
        """(spec, id, category) from the 50 % recent / 30 % old (PFSP) / 20 % baseline mix."""
        cfg = self.cfg
        snaps = list(cfg.snapshots)
        recent = snaps[-cfg.recent :] if snaps else []
        old = snaps[: -cfg.recent] if len(snaps) > cfg.recent else []
        p_recent = cfg.p_recent + (cfg.p_old if not old else 0.0)
        p_old = cfg.p_old if old else 0.0
        if not recent:
            p_recent = 0.0
            p_old = 0.0
        r = rng.random()
        if r < p_recent:
            path = recent[rng.randint(0, len(recent) - 1)]
            return f"snapshot:{path}", path, "recent"
        if r < p_recent + p_old:
            weights = [max(1e-9, cfg.weights.get(path, 0.25)) for path in old]
            total = sum(weights)
            x = rng.random() * total
            acc = 0.0
            for path, w in zip(old, weights, strict=True):
                acc += w
                if x < acc:
                    return f"snapshot:{path}", path, "old"
            return f"snapshot:{old[-1]}", old[-1], "old"
        name = cfg.baselines[rng.randint(0, len(cfg.baselines) - 1)]
        return name, name, "baseline"

    def plan(self, rng: SeededStream) -> SeatPlan:
        """Draw the roles of one game."""
        cfg = self.cfg
        n = self.n
        learner = rng.randint(0, n - 1)
        learning = [learner]
        opponents: dict[int, str] = {}
        ids: dict[int, str] = {}
        cats: dict[int, str] = {}
        for seat in range(n):
            if seat == learner:
                continue
            if cfg.mode in ("curriculum", "fixed"):
                pool = cfg.stages[cfg.stage] if cfg.mode == "curriculum" else cfg.fixed
                name = pool[rng.randint(0, len(pool) - 1)]
                spec, oid, cat = name, name, "baseline"
            elif cfg.mode == "selfplay":
                spec, oid, cat = self._category_opponent(rng)
            elif cfg.mode == "fourp":
                if rng.random() < cfg.extra_learning_prob:
                    learning.append(seat)
                    continue
                spec, oid, cat = self._category_opponent(rng)
            else:  # fourp_fallback: 40 % latest copy of the current policy (no training data)
                if rng.random() < cfg.extra_learning_prob and cfg.latest_path:
                    spec, oid, cat = f"latest:{cfg.latest_path}", "latest", "latest"
                else:
                    spec, oid, cat = self._category_opponent(rng)
            opponents[seat] = spec
            ids[seat] = oid
            cats[seat] = cat
        return SeatPlan(sorted(learning), opponents, ids, cats)

    def policy(self, spec: str) -> Policy:
        """Cached policy object for an opponent spec (with epsilon and delegation wrappers)."""
        full = self._wrap(spec)
        pol = self._cache.get(full)
        if pol is None:
            pol = make_policy(full)
            self._cache[full] = pol
        return pol
