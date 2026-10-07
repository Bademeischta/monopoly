"""Decision Core (§6.1-§6.3): shared basis of the Gymnasium, multi-seat and AEC environments.

For every learning seat the core keeps one open transition (start potential, tick counter k,
accumulated extra reward). Opponent decisions and delegated decision kinds are answered inside
the core; forced decisions of learning seats are auto-skipped and counted as ticks (SMDP clock).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from propertyrl.agents.base import Policy, decision_kind_key, respond_decision
from propertyrl.agents.registry import make_policy
from propertyrl.engine import Engine, EngineOptions, IllegalActionError
from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.equity import canonical_equity, equity_shares
from propertyrl.engine.events import COUNTER_INDEX
from propertyrl.engine.rng import AgentRng, SeededStream
from propertyrl.env.observation import encode
from propertyrl.env.opponents import OpponentConfig, OpponentSampler, SeatPlan
from propertyrl.env.rewards import RewardSpec, is_hopeless, potential, terminal_reward, weighted_level
from propertyrl.evaluation.seeds import train_seed
from propertyrl.infra.config import load_setup

ALWAYS_DELEGATED = frozenset({"TRADE_OFFER", "TRADE_RESPONSE", "AUCTION_BID"})
DEFAULT_DELEGATED = ("TRADE_OFFER", "TRADE_RESPONSE", "AUCTION_BID", "DEBT")


@dataclass
class EnvConfig:
    """Environment configuration (plain data, picklable for SubprocVecEnv workers)."""

    ruleset: str = "OFFICIAL_US_CLASSIC_2008"
    n_players: int = 2
    reward_variant: str = "A1"
    gamma: float = 0.995
    beta: float = 1.0
    beta2: float = 0.01
    kingmaking_malus: float = 0.1
    terminal_rewards_4p: tuple[float, ...] = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
    auto_skip: bool = True
    smdp: bool = True
    delegation: str = "delegation_v1"
    delegated_kinds: tuple[str, ...] = DEFAULT_DELEGATED
    trade_enabled: bool = True
    safety_horizon_rounds: int = 300
    max_rounds: int | None = None
    opponents: OpponentConfig = field(default_factory=OpponentConfig)
    log_events: bool = False
    check_invariants: bool = False

    def __post_init__(self) -> None:
        if not 2 <= self.n_players <= 4:
            raise ValueError("RL environments support 2-4 players")
        if isinstance(self.opponents, dict):
            self.opponents = OpponentConfig.from_dict(self.opponents)
        self.delegated_kinds = tuple(sorted(set(self.delegated_kinds) | ALWAYS_DELEGATED))
        self.terminal_rewards_4p = tuple(self.terminal_rewards_4p)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation."""
        d = asdict(self)
        d["opponents"] = self.opponents.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EnvConfig:
        """Inverse of :meth:`to_dict`."""
        data = dict(d)
        data["opponents"] = OpponentConfig.from_dict(data.get("opponents", {}))
        for key in ("delegated_kinds", "terminal_rewards_4p"):
            if key in data:
                data[key] = tuple(data[key])
        return cls(**data)


@dataclass
class Closed:
    """A closed transition of one learning seat."""

    seat: int
    reward: float
    duration: int
    terminated: bool
    truncated: bool
    terminal_observation: np.ndarray | None = None

    def to_dict(self) -> dict[str, Any]:
        """Dict form used in ``info["closed"]``."""
        return {
            "seat": self.seat,
            "reward": self.reward,
            "duration": self.duration,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "terminal_observation": self.terminal_observation,
        }


class DecisionCore:
    """Runs games, answers non-learning decisions and keeps the per-seat transition bookkeeping."""

    def __init__(self, cfg: EnvConfig, worker: int = 0) -> None:
        self.cfg = cfg
        self.worker = worker
        overrides: dict[str, Any] = {"safety_horizon_rounds": cfg.safety_horizon_rounds}
        if cfg.max_rounds:
            overrides["max_rounds"] = cfg.max_rounds
        self.ruleset, self.board, self.decks = load_setup(cfg.ruleset, cfg.n_players, **overrides)
        self.reward = RewardSpec(
            cfg.reward_variant,
            cfg.gamma,
            cfg.beta,
            cfg.beta2,
            cfg.kingmaking_malus,
            cfg.smdp,
            cfg.terminal_rewards_4p,
        )
        self.delegation: Policy = make_policy(cfg.delegation)
        self.delegated = frozenset(cfg.delegated_kinds)
        self.sampler = OpponentSampler(cfg.opponents, cfg.n_players)
        self.eng: Engine | None = None
        self.plan: SeatPlan | None = None
        self.learning: list[int] = []
        self.rngs: dict[int, AgentRng] = {}
        self.open: dict[int, bool] = {}
        self.ticks: dict[int, int] = {}
        self.phi_start: dict[int, float] = {}
        self.phi_now: dict[int, float] = {}
        self.extra: dict[int, float] = {}
        self.done: dict[int, bool] = {}
        self.current: int | None = None
        self.truncated = False
        self.episode_over = False
        self.seed_base = 0
        self.episode = 0
        self.game_seed = 0
        self.restarts = 0
        self.illegal_actions = 0
        #: All seats are learning seats (PettingZoo AEC environment).
        self.all_learning = False
        #: Optional per-seat delegation policies (AEC: configurable per agent).
        self.seat_delegation: dict[int, Policy] = {}

    # ------------------------------------------------------------------ game start
    def start(self, seed: int | None = None) -> list[Closed]:
        """Start a new game and advance to the first genuine decision of a learning seat."""
        if seed is not None:
            self.seed_base = int(seed)
            self.episode = 0
        self.restarts = 0
        while True:
            game_seed, used = train_seed(self.seed_base, self.worker, self.episode)
            if self.all_learning:
                plan = SeatPlan(list(range(self.cfg.n_players)), {}, {}, {})
            else:
                plan = self.sampler.plan(SeededStream(self.seed_base, C.STREAM_TRAIN, self.worker, used))
            self.episode = used + 1
            self._new_game(game_seed, plan)
            closed = self._advance()
            if self.current is not None:
                return closed
            self.restarts += 1

    def _new_game(self, game_seed: int, plan: SeatPlan) -> None:
        cfg = self.cfg
        opts = EngineOptions(log_events=cfg.log_events, check_invariants=cfg.check_invariants)
        self.eng = Engine.new(self.ruleset, self.board, self.decks, cfg.n_players, game_seed, opts)
        self.eng.meta = {"learning_seats": plan.learning_seats, "opponents": plan.opponents}
        self.game_seed = game_seed
        self.plan = plan
        self.learning = list(plan.learning_seats)
        self.rngs = {s: AgentRng(game_seed, s) for s in range(cfg.n_players)}
        self.open = {s: False for s in self.learning}
        self.ticks = {s: 0 for s in self.learning}
        self.phi_start = {s: 0.0 for s in self.learning}
        self.phi_now = {s: 0.0 for s in self.learning}
        self.extra = {s: 0.0 for s in self.learning}
        self.done = {s: False for s in self.learning}
        self.current = None
        self.truncated = False
        self.episode_over = False
        self.illegal_actions = 0

    # ------------------------------------------------------------------ observation and masks
    @property
    def engine(self) -> Engine:
        """The running engine."""
        assert self.eng is not None
        return self.eng

    def phase(self) -> str:
        """Phase of the pending engine decision ('' at game end)."""
        d = self.engine.pending()
        return d.phase if d is not None else ""

    def observe(self, seat: int) -> np.ndarray:
        """Ego-centric observation of ``seat`` at the current state."""
        eng = self.engine
        return encode(eng.state, self.board, self.ruleset, seat, self.phase())

    def legal_mask(self) -> np.ndarray:
        """Legal-action mask of the current learning seat (all False if none)."""
        if self.current is None or self.eng is None:
            return np.zeros(A.N_ACTIONS, dtype=bool)
        return np.asarray(self.engine.legal_mask(), dtype=bool)

    # ------------------------------------------------------------------ stepping
    def act(self, action: int) -> list[Closed]:
        """Apply the current learning seat's action and advance to the next genuine decision."""
        seat = self.current
        if seat is None:
            raise IllegalActionError("no learning seat is deciding", game_seed=self.game_seed)
        eng = self.engine
        mask = eng.legal_mask()
        a = int(action)
        if not 0 <= a < A.N_ACTIONS or not mask[a]:
            self.illegal_actions += 1
            raise IllegalActionError(
                f"illegal action {a} for learning seat", game_seed=self.game_seed,
                decision_index=eng.state.decision_index, seat=seat,
            )  # fmt: skip
        hopeless = self.reward.variant == "A3" and is_hopeless(eng.state, self.board, seat)
        eq_before = canonical_equity(eng.state, self.board, seat) if hopeless else 0
        self.phi_start[seat] = self.phi_now[seat]
        self.open[seat] = True
        self.ticks[seat] = 1
        self.extra[seat] = 0.0
        self.current = None
        eng.apply(a)
        closed: list[Closed] = []
        if hopeless and a not in (A.ROLL, A.END_PHASE):
            # A3 proxy: an own genuine action that immediately lowers the own canonical equity.
            if canonical_equity(eng.state, self.board, seat) < eq_before:
                self.extra[seat] -= self.reward.kingmaking_malus
        closed += self._check_bankruptcies()
        closed += self._advance()
        return closed

    def _respond(self, policy: Policy, d: D.Decision) -> Any:
        if d.kind == D.TRADE_OFFER and not self.cfg.trade_enabled:
            return []
        return respond_decision(policy, d, self.engine.public_view(d.seat), self.rngs[d.seat])

    def _advance(self) -> list[Closed]:
        eng = self.engine
        closed: list[Closed] = []
        learning = set(self.learning)
        while True:
            if eng.is_over() or all(self.done[s] for s in self.learning):
                for s in self.learning:
                    if self.open[s]:
                        closed.append(self._close(s, terminated=True))
                    self.done[s] = True
                self.current = None
                self.episode_over = True
                return closed
            d = eng.pending()
            assert d is not None
            seat = d.seat
            if seat in learning and not self.done[seat]:
                if decision_kind_key(d) in self.delegated or d.kind in ALWAYS_DELEGATED:
                    eng.apply(self._respond(self.seat_delegation.get(seat, self.delegation), d))
                    closed += self._check_bankruptcies()
                    continue
                assert d.legal is not None
                legal = d.legal_actions()
                if self.cfg.auto_skip and len(legal) == 1:
                    eng.apply(legal[0])
                    if self.open[seat]:
                        self.ticks[seat] += 1
                    closed += self._check_bankruptcies()
                    continue
                # Genuine decision of a learning seat.
                phi = potential(eng.state, self.board, seat, self.cfg.beta)
                self.phi_now[seat] = phi
                if not self.ruleset.short_game and eng.state.round_index >= self.ruleset.safety_horizon_rounds:
                    # Safety horizon: the episode is truncated (bootstrap), the game is not ended.
                    for s in self.learning:
                        if self.open[s]:
                            closed.append(self._close(s, truncated=True))
                    self.truncated = True
                    self.episode_over = True
                    self.current = None
                    return closed
                if self.open[seat]:
                    closed.append(self._close(seat, phi_end=phi))
                self.current = seat
                return closed
            policy = self.sampler.policy(self.plan.opponents[seat]) if self.plan else self.delegation
            eng.apply(self._respond(policy, d))
            closed += self._check_bankruptcies()

    def _check_bankruptcies(self) -> list[Closed]:
        out = []
        st = self.engine.state
        for s in self.learning:
            if not self.done[s] and st.bankrupt[s]:
                self.done[s] = True
                if self.open[s]:
                    out.append(self._close(s, terminated=True))
        return out

    def placement(self, seat: int) -> int:
        """Placement of a seat (final at game end, fixed at its bankruptcy, else rank by equity)."""
        st = self.engine.state
        if st.game_over:
            return st.placements[seat]
        if st.bankrupt[seat]:
            return st.n_players - st.bankruptcy_order.index(seat)
        eq = [canonical_equity(st, self.board, s) for s in range(st.n_players)]
        return 1 + sum(1 for s in range(st.n_players) if not st.bankrupt[s] and eq[s] > eq[seat])

    def _close(
        self, seat: int, terminated: bool = False, truncated: bool = False, phi_end: float | None = None
    ) -> Closed:
        eng = self.engine
        st = eng.state
        duration = self.ticks[seat] if self.cfg.smdp else 1
        terminal = 0.0
        if terminated:
            winner = eng.result().winner if st.game_over else None
            terminal = terminal_reward(st.n_players, self.placement(seat), winner, seat, self.cfg.terminal_rewards_4p)
        if phi_end is None:
            phi_end = 0.0 if terminated else potential(st, self.board, seat, self.cfg.beta)
        level = weighted_level(st, self.board, seat) if self.reward.variant == "A2" and not terminated else 0.0
        reward = self.reward.transition_reward(
            terminal, terminated, self.phi_start[seat], phi_end, duration, level, self.extra[seat]
        )
        self.open[seat] = False
        obs = self.observe(seat) if truncated else None
        return Closed(seat, float(reward), int(duration), terminated, truncated, obs)

    # ------------------------------------------------------------------ episode statistics
    def episode_info(self, seat: int) -> dict[str, Any]:
        """Statistics of the finished episode for ``seat`` (§6.7)."""
        eng = self.engine
        st = eng.state
        res = eng.result()
        n = st.n_players

        def cnt(name: str) -> int:
            return st.counters[COUNTER_INDEX[name] * n + seat]

        shares = equity_shares(st, self.board)
        return {
            "winner": res.winner if st.game_over else None,
            "placement": self.placement(seat),
            "won": bool(st.game_over and res.winner == seat),
            "rounds": res.rounds,
            "decisions": res.decisions,
            "truncated": self.truncated,
            "final_equity_share": shares[seat],
            "opponent_ids": dict(self.plan.opponent_ids) if self.plan else {},
            "opponent_categories": dict(self.plan.category) if self.plan else {},
            "learning_seats": list(self.learning),
            "counters": {
                "purchases": cnt("purchases"),
                "builds": cnt("houses_built") + cnt("hotels_built"),
                "mortgages": cnt("mortgages"),
                "unmortgages": cnt("unmortgages"),
                "trades": cnt("trades_executed"),
                "auctions_won": cnt("auctions_won"),
                "scarcity_auctions": cnt("scarcity_auctions_triggered") + cnt("scarcity_auctions_won"),
                "jail_stay": cnt("jail_stay"),
                "jail_leave": cnt("jail_leave"),
                "jail_balance": cnt("jail_income") - cnt("jail_expense"),
            },
        }
