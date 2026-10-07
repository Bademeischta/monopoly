"""Engine fuzzing: random legal play per ruleset and rare-event start states (§10, G1)."""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from propertyrl.engine import (
    Bid,
    BidLevel,
    Engine,
    EngineOptions,
    PropertyRLError,
    ScenarioBuilder,
    TradeOffer,
)
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine.events import EVENT_TYPES
from propertyrl.engine.rng import AgentRng, u64
from propertyrl.engine.trade import validate_offer
from propertyrl.infra.config import load_setup

log = logging.getLogger(__name__)

#: Configurations of the CI fuzz (§10).
FUZZ_CONFIGS: tuple[tuple[str, int], ...] = (
    ("OFFICIAL_US_CLASSIC_2008", 2),
    ("OFFICIAL_US_CLASSIC_2008", 4),
    ("OFFICIAL_US_CLASSIC_2008", 8),
    ("RESEARCH_2P_BOUNDED_V1", 2),
    ("RESEARCH_2P_SHORTGAME_V1", 2),
    ("TEST_MOVEMENT_ONLY", 2),
)
#: Event types that are rare in plain random play and must occur >= 100 times in the rare-event fuzz.
RARE_EVENT_TYPES: tuple[str, ...] = (
    "BUILDING_AUCTION_STARTED",
    "BUILDING_AUCTION_WON",
    "GROUP_SOLD_DOWN",
    "HOTEL_BUILT",
    "JAIL_CARD_USED",
    "BANKRUPTCY",
    "ASSETS_TRANSFERRED",
    "INTEREST_PAID",
    "DEBT_SETTLED",
    "TRADE_EXECUTED",
)
FUZZ_MAX_ROUNDS = 1000


def random_offers(eng: Engine, seat: int, rng: AgentRng) -> list[TradeOffer]:
    """Up to two random offers that satisfy P-14."""
    st = eng.state
    others = [s for s in range(st.n_players) if s != seat and not st.bankrupt[s]]
    out: list[TradeOffer] = []
    for _ in range(C.MAX_OFFERS_PER_WINDOW):
        if not others or rng.random() < 0.6:
            break
        r = rng.choice(others)
        give = tuple(p for p in range(C.N_PROPS) if st.owner[p] == seat and rng.random() < 0.25)
        get = tuple(p for p in range(C.N_PROPS) if st.owner[p] == r and rng.random() < 0.25)
        offer = TradeOffer(
            seat,
            r,
            rng.randint(0, max(0, st.cash[seat] // 3)),
            rng.randint(0, max(0, st.cash[r] // 3)),
            give,
            get,
            st.jail_cards[seat] if rng.random() < 0.5 else 0,
            st.jail_cards[r] if rng.random() < 0.5 else 0,
        )
        if validate_offer(st, eng.board, eng.ruleset, offer, seat) is None:
            out.append(offer)
    return out


def random_response(eng: Engine, rng: AgentRng) -> Any:
    """A random legal response for any decision kind."""
    d = eng.pending()
    assert d is not None
    if d.kind in (D.MAIN, D.DEBT):
        return rng.choice(d.legal_actions())
    if d.kind == D.TRADE_OFFER:
        return random_offers(eng, d.seat, rng)
    if d.kind == D.TRADE_RESPONSE:
        return rng.random() < 0.5
    ctx = d.context
    if ctx["format"] == D.FORMAT_SEALED:
        legal: list[int | None] = [i for i, ok in enumerate(ctx["legal_levels"]) if ok]
        return BidLevel(rng.choice([*legal, None]))
    lo, hi = ctx["min_bid"], ctx["max_bid"]
    if hi < lo or rng.random() < 0.4:
        return Bid(None)
    return Bid(rng.randint(lo, min(hi, lo + max(1, ctx["ref_price"]))))


@dataclass
class FuzzReport:
    """Result of a fuzz run."""

    name: str
    decisions: int = 0
    games: int = 0
    completed_games: int = 0
    truncated_games: int = 0
    seconds: float = 0.0
    event_counts: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)

    def merge(self, other: FuzzReport) -> None:
        """Add another report into this one."""
        self.decisions += other.decisions
        self.games += other.games
        self.completed_games += other.completed_games
        self.truncated_games += other.truncated_games
        self.seconds += other.seconds
        self.event_counts.update(other.event_counts)
        self.errors.extend(other.errors)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary."""
        return {
            "name": self.name,
            "decisions": self.decisions,
            "games": self.games,
            "completed_games": self.completed_games,
            "truncated_games": self.truncated_games,
            "seconds": round(self.seconds, 2),
            "event_counts": {t: self.event_counts.get(t, 0) for t in EVENT_TYPES},
            "errors": list(self.errors),
            "invariant_violations": sum(1 for e in self.errors if "InvariantError" in e),
        }


def _play(eng: Engine, rng: AgentRng, budget: int, max_rounds: int, report: FuzzReport) -> None:
    used = 0
    while used < budget and not eng.is_over() and eng.state.round_index < max_rounds:
        eng.apply(random_response(eng, rng))
        used += 1
    report.decisions += used
    report.games += 1
    if eng.is_over():
        report.completed_games += 1
    else:
        report.truncated_games += 1
    report.event_counts.update(e.type for e in eng.events)


def _guarded(fn: Callable[[], None], report: FuzzReport) -> None:
    try:
        fn()
    except PropertyRLError as err:
        from propertyrl.infra.logging_setup import dump_error_log

        path = dump_error_log(err, prefix="fuzz")
        report.errors.append(f"{type(err).__name__}: {err} (log: {path})")
        raise


def fuzz(
    ruleset_id: str,
    n_players: int,
    decisions: int,
    seed: int = 0,
    max_rounds: int = FUZZ_MAX_ROUNDS,
    check_invariants: bool = True,
) -> FuzzReport:
    """Random legal play for ``decisions`` decisions; games are truncated after ``max_rounds`` rounds."""
    rules, board, decks = load_setup(ruleset_id, n_players)
    report = FuzzReport(f"{ruleset_id}/{n_players}p")
    start = time.perf_counter()
    game = 0
    while report.decisions < decisions:
        game_seed = u64(seed, C.STREAM_GAME, n_players, game) & ((1 << 63) - 1)
        game += 1

        def one(gs: int = game_seed) -> None:
            opts = EngineOptions(log_events=True, check_invariants=check_invariants)
            eng = Engine.new(rules, board, decks, n_players, gs, opts)
            _play(eng, AgentRng(gs, 77), decisions - report.decisions, max_rounds, report)

        _guarded(one, report)
    report.seconds = time.perf_counter() - start
    return report


# --------------------------------------------------------------------------- rare-event start states
def _distribute_groups(b: ScenarioBuilder, rng: AgentRng, n: int, max_houses: int, hotels_ok: bool) -> None:
    """Give colour groups to random seats with even random levels within bank limits."""
    houses = 0
    hotels = 0
    for g in range(C.N_COLOR_GROUPS):
        if rng.random() < 0.15:
            continue
        seat = rng.randint(0, n - 1)
        b.own_group(seat, C.GROUP_NAMES[g])
        members = C.GROUP_BUILDS[g]
        top = 5 if hotels_ok else 4
        lvl = rng.randint(0, top)
        if lvl == 5:
            if hotels + len(members) > 12:
                lvl = 4
            else:
                hotels += len(members)
        if lvl < 5:
            if houses + lvl * len(members) > max_houses:
                lvl = max(0, (max_houses - houses) // len(members))
            houses += lvl * len(members)
        for m in members:
            b.level(m, lvl)


def _gen_near_empty_bank(rules_id: str, n: int, seed: int, rng: AgentRng) -> ScenarioBuilder:
    rules, board, decks = load_setup(rules_id, n)
    b = ScenarioBuilder(rules, board, decks, n, seed)
    _distribute_groups(b, rng, n, max_houses=32, hotels_ok=True)
    for s in range(n):
        b.cash(s, rng.randint(150, 2500))
        b.position(s, rng.randint(0, 39) if rng.random() < 0.5 else 0)
    return b


def _gen_debt_cascade(rules_id: str, n: int, seed: int, rng: AgentRng) -> ScenarioBuilder:
    """A rich landlord with hotels; poor players with mortgaged holdings (bankruptcies, cascades)."""
    rules, board, decks = load_setup(rules_id, n)
    b = ScenarioBuilder(rules, board, decks, n, seed)
    landlord = rng.randint(0, n - 1)
    b.own_group(landlord, "GRUEN", 5).own_group(landlord, "GELB", 5).own_group(landlord, "ROT", rng.randint(2, 4))
    b.cash(landlord, rng.randint(0, 60))
    others = [s for s in range(n) if s != landlord]
    for p in range(C.N_PROPS):
        if C.P_GROUP[p] in (C.GROUP_ID["GRUEN"], C.GROUP_ID["GELB"], C.GROUP_ID["ROT"]):
            continue
        if rng.random() < 0.8:
            b.own(rng.choice(others), p, mortgaged=rng.random() < 0.75)
    for s in others:
        b.cash(s, rng.randint(0, 120))
        b.position(s, rng.randint(14, 30))
    b.active(rng.choice(others))
    return b


def _gen_hotel_selldown(rules_id: str, n: int, seed: int, rng: AgentRng) -> ScenarioBuilder:
    """Hotels with (almost) no houses in the bank and a cash-strapped owner (P-08 sell-downs)."""
    rules, board, decks = load_setup(rules_id, n)
    b = ScenarioBuilder(rules, board, decks, n, seed)
    seller = rng.randint(0, n - 1)
    other = (seller + 1) % n
    b.own_group(seller, "BRAUN", 5).own_group(seller, "HELLBLAU", 5).own_group(seller, "PINK", 5)
    b.own_group(other, "GRUEN", 4).own_group(other, "GELB", 4).own_group(other, "ROT", 2)
    b.own_group(other, "ORANGE", 0)
    extra = rng.randint(0, 2)
    for k, bi in enumerate(C.GROUP_BUILDS[C.GROUP_ID["ORANGE"]]):
        b.level(bi, 1 if k < extra else 0)
    b.own(other, 2, 10, 17, 25, 7, 20)
    b.cash(seller, rng.randint(0, 40))
    b.cash(other, rng.randint(200, 1500))
    b.position(seller, rng.randint(0, 39))
    b.active(seller)
    return b


def _gen_jail_cards(rules_id: str, n: int, seed: int, rng: AgentRng) -> ScenarioBuilder:
    rules, board, decks = load_setup(rules_id, n)
    b = ScenarioBuilder(rules, board, decks, n, seed)
    holder = rng.randint(0, n - 1)
    second = (holder + 1) % n if rng.random() < 0.5 else holder
    b.jail_card(holder, C.DECK_A).jail_card(second, C.DECK_B)
    for s in range(n):
        if s in (holder, second) or rng.random() < 0.5:
            b.jail(s, rng.randint(0, 2))
        b.cash(s, rng.randint(20, 1500))
    b.active(holder)
    return b


def _gen_movement_cards(rules_id: str, n: int, seed: int, rng: AgentRng) -> ScenarioBuilder:
    rules, board, decks = load_setup(rules_id, n)
    b = ScenarioBuilder(rules, board, decks, n, seed)
    movers_a = ["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A10", "A11", "A14", "A09", "A12", "A15"]
    order_a = list(movers_a)
    for i in range(len(order_a) - 1, 0, -1):
        j = rng.randint(0, i)
        order_a[i], order_a[j] = order_a[j], order_a[i]
    b.cards(C.DECK_A, order_a)
    b.cards(C.DECK_B, ["B01", "B06", "B05", "B09", "B14", "B03"])
    for p in range(C.N_PROPS):
        if rng.random() < 0.5:
            b.own(rng.randint(0, n - 1), p)
    for s in range(n):
        b.position(s, rng.choice([3, 5, 14, 15, 17, 20, 30, 31, 34]))
    return b


def _gen_scarcity(rules_id: str, n: int, seed: int, rng: AgentRng) -> ScenarioBuilder:
    rules, board, decks = load_setup(rules_id, n)
    b = ScenarioBuilder(rules, board, decks, n, seed)
    # Two expensive groups nearly full, several cheap groups unbuilt -> bank shortage with many builders.
    full = ["GRUEN", "GELB", "ROT"]
    open_groups = ["BRAUN", "HELLBLAU", "PINK", "ORANGE", "DUNKELBLAU"]
    for i, g in enumerate(full):
        b.own_group(i % n, g, 4 if i < 2 else rng.randint(1, 2))
    for i, g in enumerate(open_groups):
        b.own_group((i + 1) % n, g, 0)
    for s in range(n):
        b.cash(s, rng.randint(400, 3000))
    return b


_BOTH = ("OFFICIAL_US_CLASSIC_2008", "RESEARCH_2P_BOUNDED_V1")
_Gen = Callable[[str, int, int, AgentRng], ScenarioBuilder]
#: name -> (generator, rulesets, decisions per episode)
RARE_EVENT_GENERATORS: dict[str, tuple[_Gen, tuple[str, ...], int]] = {
    "near_empty_bank": (_gen_near_empty_bank, _BOTH, 400),
    "debt_cascade": (_gen_debt_cascade, _BOTH, 150),
    "hotel_selldown": (_gen_hotel_selldown, _BOTH, 120),
    "jail_cards": (_gen_jail_cards, _BOTH, 20),
    "movement_cards": (_gen_movement_cards, _BOTH, 200),
    "scarcity": (_gen_scarcity, _BOTH, 300),
}
#: Episode schedule (weights): rarer targets appear more often.
RARE_EVENT_SCHEDULE: tuple[str, ...] = (
    "near_empty_bank",
    "debt_cascade",
    "jail_cards",
    "hotel_selldown",
    "debt_cascade",
    "jail_cards",
    "movement_cards",
    "jail_cards",
    "scarcity",
    "jail_cards",
)


def rare_event_fuzz(decisions: int, seed: int = 0) -> FuzzReport:
    """Fuzz from rare-event start states (fast-moving through bank shortage, debt cascades, cards)."""
    report = FuzzReport("rare_events")
    start = time.perf_counter()
    names = RARE_EVENT_SCHEDULE
    episode = 0
    while report.decisions < decisions:
        name = names[episode % len(names)]
        gen, rulesets, episode_decisions = RARE_EVENT_GENERATORS[name]
        rng = AgentRng(u64(seed, C.STREAM_GAME, episode), 3)
        ruleset_id = rulesets[(episode // len(names)) % len(rulesets)]
        n = 2 if ruleset_id != "OFFICIAL_US_CLASSIC_2008" else rng.randint(2, 4)
        if name == "debt_cascade" and ruleset_id == "OFFICIAL_US_CLASSIC_2008":
            n = rng.randint(3, 4)
        game_seed = u64(seed, C.STREAM_GAME, 10_000 + episode) & ((1 << 63) - 1)
        episode += 1

        def one(
            gen_: Any = gen,
            rid: str = ruleset_id,
            n_: int = n,
            gs: int = game_seed,
            r: AgentRng = rng,
            per_episode: int = episode_decisions,
        ) -> None:
            eng = gen_(rid, n_, gs, r).options(log_events=True, check_invariants=True).build()
            budget = min(per_episode, decisions - report.decisions)
            _play(eng, AgentRng(gs, 78), budget, FUZZ_MAX_ROUNDS, report)

        _guarded(one, report)
    report.seconds = time.perf_counter() - start
    return report


def run_suite(decisions_per_config: int, rare_decisions: int, seed: int = 0) -> dict[str, Any]:
    """Run the full fuzz suite (all configurations plus rare events) and return the report dict."""
    reports = [fuzz(r, n, decisions_per_config, seed) for r, n in FUZZ_CONFIGS]
    rare = rare_event_fuzz(rare_decisions, seed) if rare_decisions > 0 else None
    total = FuzzReport("total")
    for rep in reports:
        total.merge(rep)
    if rare is not None:
        total.merge(rare)
    out: dict[str, Any] = {
        "configs": [r.to_dict() for r in reports],
        "rare_events": rare.to_dict() if rare is not None else None,
        "total": total.to_dict(),
        "decisions_per_config": decisions_per_config,
        "rare_decisions": rare_decisions,
    }
    if rare is not None:
        out["rare_event_min_counts"] = {t: rare.event_counts.get(t, 0) for t in RARE_EVENT_TYPES}
    out["unseen_event_types"] = [t for t in EVENT_TYPES if total.event_counts.get(t, 0) == 0]
    return out
