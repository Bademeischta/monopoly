"""Deterministic state machine and public engine API (§4.5).

All internal steps without a decision (dice, movement, rent, automatic payments)
run inside :meth:`Engine.apply` until the next decision is pending.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from propertyrl.engine import actions as A
from propertyrl.engine import constants as C
from propertyrl.engine import decisions as D
from propertyrl.engine import frames as F
from propertyrl.engine.auction import apply_bid, bid_context, start_property_auction
from propertyrl.engine.board import Board
from propertyrl.engine.building import do_build, do_sell
from propertyrl.engine.card_effects import draw_frame
from propertyrl.engine.cards import Decks
from propertyrl.engine.debt import after_debt_action, bankrupt_frame, pay_frame
from propertyrl.engine.equity import all_equities
from propertyrl.engine.errors import (
    EngineWatchdogError,
    IllegalActionError,
    InvariantError,
    PropertyRLError,
    RuleViolationError,
)
from propertyrl.engine.events import (
    CNT_DECISIONS,
    CNT_JAIL_EXPENSE,
    CNT_JAIL_INCOME,
    CNT_JAIL_LEAVE,
    CNT_JAIL_STAY,
    COUNTER_NAMES,
    Event,
)
from propertyrl.engine.jail import jail_roll_frame, leave_jail_frame, pay_fine, send_jail_frame, use_card
from propertyrl.engine.ledger import Ledger
from propertyrl.engine.legality import frame_mask
from propertyrl.engine.mortgage import do_mortgage, do_unmortgage
from propertyrl.engine.movement import after_roll_frame, move_by_frame, move_to_frame, roll_frame
from propertyrl.engine.property_rules import buy, decline, land_frame
from propertyrl.engine.rng import dice_value, reshuffle_positions, shuffle_deck
from propertyrl.engine.ruleset import Ruleset
from propertyrl.engine.scarcity import try_build
from propertyrl.engine.state import GameState
from propertyrl.engine.trade import handle_offers, handle_response, present_next
from propertyrl.engine.turns import close_window, next_turn_frame, oot_frame, turn_start_frame, window_frame
from propertyrl.engine.view import PublicState

_WINDOW_PHASE = (D.PRE_ROLL, D.POST_MOVE, D.OUT_OF_TURN)


@dataclass(slots=True)
class EngineOptions:
    """Engine options (§4.5). Test hooks require ``allow_test_hooks=True``."""

    log_events: bool = True
    check_invariants: bool = False
    dice_script: tuple[tuple[int, int], ...] | None = None
    card_order: dict[str, tuple[str, ...]] | None = None
    allow_test_hooks: bool = False
    #: Record a state hash every ``hash_interval`` decisions in the log (0 = off).
    hash_interval: int = 0

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable representation (used in log headers)."""
        return {
            "log_events": self.log_events,
            "check_invariants": self.check_invariants,
            "dice_script": [list(x) for x in self.dice_script] if self.dice_script is not None else None,
            "card_order": {k: list(v) for k, v in self.card_order.items()} if self.card_order else None,
            "allow_test_hooks": self.allow_test_hooks,
            "hash_interval": self.hash_interval,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EngineOptions:
        """Inverse of :meth:`to_dict`."""
        script = d.get("dice_script")
        order = d.get("card_order")
        return cls(
            log_events=bool(d.get("log_events", True)),
            check_invariants=bool(d.get("check_invariants", False)),
            dice_script=tuple((int(a), int(b)) for a, b in script) if script is not None else None,
            card_order={k: tuple(v) for k, v in order.items()} if order else None,
            allow_test_hooks=bool(d.get("allow_test_hooks", False)),
            hash_interval=int(d.get("hash_interval", 0)),
        )


@dataclass(slots=True)
class GameResult:
    """Final result of a game (truncation is decided by the environment, never by the engine)."""

    winner: int | None
    placements: list[int]
    rounds: int
    decisions: int
    truncated: bool
    final_equities: list[int]
    counters: dict[str, list[int]] = field(default_factory=dict)
    rest_counts: list[int] = field(default_factory=list)
    ended_by_rounds: bool = False


_Handler = Callable[["Engine", tuple[int, ...]], None]
_HANDLERS: dict[int, _Handler] = {
    F.OP_TURN_START: turn_start_frame,
    F.OP_WINDOW: window_frame,
    F.OP_TRADE_PRESENT: present_next,
    F.OP_ROLL: roll_frame,
    F.OP_JAIL_ROLL: jail_roll_frame,
    F.OP_AFTER_ROLL: after_roll_frame,
    F.OP_MOVE_BY: move_by_frame,
    F.OP_MOVE_TO: move_to_frame,
    F.OP_LAND: land_frame,
    F.OP_AUCTION_START: start_property_auction,
    F.OP_PAY: pay_frame,
    F.OP_BANKRUPT: bankrupt_frame,
    F.OP_DRAW: draw_frame,
    F.OP_SEND_JAIL: send_jail_frame,
    F.OP_LEAVE_JAIL: leave_jail_frame,
    F.OP_OOT: oot_frame,
    F.OP_NEXT_TURN: next_turn_frame,
}


class Engine:
    """Rule engine for one game. Use :meth:`Engine.new` to create."""

    __slots__ = (
        "_apply_events",
        "_dice_script",
        "_pending",
        "board",
        "decision_log",
        "decks",
        "event_seq",
        "events",
        "initial_state",
        "ledger",
        "log",
        "meta",
        "options",
        "ruleset",
        "state",
    )

    def __init__(self, ruleset: Ruleset, board: Board, decks: Decks, state: GameState, options: EngineOptions) -> None:
        self.ruleset = ruleset
        self.board = board
        self.decks = decks
        self.state = state
        self.options = options
        self.log = options.log_events
        self.events: list[Event] = []
        self._apply_events: list[Event] = []
        self.ledger = Ledger()
        self.decision_log: list[dict[str, Any]] = []
        self._pending: D.Decision | None = None
        self._dice_script = options.dice_script
        self.event_seq = 0
        #: Free-form metadata for the log header (e.g. policy names per seat).
        self.meta: dict[str, Any] = {}
        #: Canonical start state for scenario-based games (None for regular games).
        self.initial_state: dict[str, Any] | None = None

    # ------------------------------------------------------------------ creation
    @classmethod
    def new(
        cls,
        ruleset: Ruleset,
        board: Board,
        decks: Decks,
        n_players: int,
        game_seed: int,
        options: EngineOptions | None = None,
    ) -> Engine:
        """Create a new game and advance to the first decision."""
        opts = options or EngineOptions()
        lo, hi = ruleset.player_count
        if not lo <= n_players <= hi:
            raise RuleViolationError(
                f"ruleset {ruleset.ruleset_id} allows {lo}-{hi} players, got {n_players}", game_seed=game_seed
            )
        if (opts.dice_script is not None or opts.card_order) and not opts.allow_test_hooks:
            raise RuleViolationError("dice_script/card_order require allow_test_hooks", game_seed=game_seed)
        state = GameState(n_players, game_seed, ruleset.starting_cash, ruleset.bank_houses, ruleset.bank_hotels)
        for deck_idx, name in ((C.DECK_A, "A"), (C.DECK_B, "B")):
            order = shuffle_deck(game_seed, 0, deck_idx)
            if opts.card_order and name in opts.card_order:
                front = [decks.index_of(deck_idx, cid) for cid in opts.card_order[name]]
                order = front + [c for c in range(C.DECK_SIZE) if c not in front]
            if deck_idx == C.DECK_A:
                state.deck_a = order
            else:
                state.deck_b = order
        eng = cls(ruleset, board, decks, state, opts)
        eng.start(0)
        return eng

    @classmethod
    def from_state(
        cls,
        ruleset: Ruleset,
        board: Board,
        decks: Decks,
        state: GameState,
        options: EngineOptions,
        first_seat: int,
    ) -> Engine:
        """Start a game from a prepared state (scenarios, replays of scenario logs)."""
        eng = cls(ruleset, board, decks, state, options)
        eng.initial_state = state.to_canonical_dict()
        eng.initial_state["_first_seat"] = first_seat
        if eng.log:
            for seat in range(state.n_players):
                if state.ledger_in[seat]:
                    eng.ledger.record(C.BANK, seat, state.ledger_in[seat], "SCENARIO", 0)
                if state.ledger_out[seat]:
                    eng.ledger.record(seat, C.BANK, state.ledger_out[seat], "SCENARIO", 0)
        eng.start(first_seat, scenario=True)
        return eng

    def start(self, first_seat: int, scenario: bool = False) -> None:
        """Emit GAME_STARTED, schedule the first turn and advance to the first decision."""
        st = self.state
        data: dict[str, Any] = {"n_players": st.n_players, "ruleset": self.ruleset.ruleset_id}
        if scenario:
            data["scenario"] = True
        self.emit("GAME_STARTED", -1, data)
        st.stack.append((F.OP_TURN_START, first_seat))
        self._run()
        self.pending()

    # ------------------------------------------------------------------ helpers used by rule modules
    def emit(self, etype: str, seat: int, data: dict[str, Any]) -> None:
        """Emit an event (always counted for the P-16 watchdog, stored only when logging)."""
        st = self.state
        st.turn_events += 1
        if st.turn_events > C.WATCHDOG_TURN_EVENTS:
            raise self._error(EngineWatchdogError, f"more than {C.WATCHDOG_TURN_EVENTS} events in one turn")
        if self.log:
            ev = Event(self.event_seq, st.decision_index, etype, seat, data)
            self.event_seq += 1
            self.events.append(ev)
            self._apply_events.append(ev)

    def transfer(self, sender: int, receiver: int, amount: int, reason: str) -> None:
        """Move money; every cash change goes through here (ledger, §4.7)."""
        st = self.state
        if amount < 0:
            raise self._error(RuleViolationError, f"negative transfer {amount}")
        if amount == 0:
            return
        n = st.n_players
        if sender >= 0:
            if st.cash[sender] < amount:
                raise self._error(RuleViolationError, f"seat {sender} cannot pay {amount} ({reason})")
            st.cash[sender] -= amount
            st.ledger_out[sender] += amount
            if st.in_jail[sender]:
                st.counters[CNT_JAIL_EXPENSE * n + sender] += amount
        if receiver >= 0:
            st.cash[receiver] += amount
            st.ledger_in[receiver] += amount
            if st.in_jail[receiver]:
                st.counters[CNT_JAIL_INCOME * n + receiver] += amount
        if self.log:
            self.ledger.record(sender, receiver, amount, reason, st.decision_index)

    def push(self, frame: tuple[int, ...]) -> None:
        """Push a continuation frame."""
        self.state.stack.append(frame)

    def pop(self) -> tuple[int, ...]:
        """Pop the top continuation frame."""
        return self.state.stack.pop()

    def cnt(self, counter: int, seat: int, delta: int = 1) -> None:
        """Increase a per-seat counter."""
        if seat >= 0:
            st = self.state
            st.counters[counter * st.n_players + seat] += delta

    def roll_dice(self, seat: int, throw: int) -> tuple[int, int]:
        """Roll two dice (§4.3) or take them from the test DiceScript."""
        st = self.state
        if self._dice_script is not None:
            if st.script_pos >= len(self._dice_script):
                raise self._error(RuleViolationError, "DiceScript exhausted", seat)
            d1, d2 = self._dice_script[st.script_pos]
            st.script_pos += 1
        else:
            turn = st.seat_turn_counter[seat]
            d1 = dice_value(st.game_seed, st.rng_epoch, seat, turn, throw, 0)
            d2 = dice_value(st.game_seed, st.rng_epoch, seat, turn, throw, 1)
        if throw < 100:
            st.last_dice = (d1, d2)
        return d1, d2

    def illegal(self, message: str, seat: int | None = None) -> IllegalActionError:
        """Build an IllegalActionError with game context."""
        err = self._error(IllegalActionError, message, seat)
        assert isinstance(err, IllegalActionError)
        return err

    def _error(self, cls: type[PropertyRLError], message: str, seat: int | None = None) -> PropertyRLError:
        st = self.state
        err = cls(message, game_seed=st.game_seed, decision_index=st.decision_index, seat=seat)
        return err

    def check_game_end(self) -> bool:
        """R-901: finish the game if at most one player is active."""
        if self.state.n_active() <= 1:
            self.finish_game()
            return True
        return False

    def finish_game(self, by_rounds: bool = False) -> None:
        """Finish the game: winner, placements (R-902) and final equities."""
        st = self.state
        n = st.n_players
        eq = all_equities(st, self.board)
        placements = [0] * n
        active = [s for s in range(n) if not st.bankrupt[s]]
        if by_rounds:
            # D-06: rank active seats by canonical equity, ties share the better place.
            for s in active:
                placements[s] = 1 + sum(1 for o in active if eq[o] > eq[s])
            best = [s for s in active if placements[s] == 1]
            winner = best[0] if len(best) == 1 else -1
        else:
            winner = active[0] if active else -1
            for s in active:
                placements[s] = 1
        # R-902: bankrupt players by reverse bankruptcy order.
        for k, s in enumerate(st.bankruptcy_order):
            placements[s] = n - k
        st.placements = placements
        st.final_equities = eq
        st.winner = winner
        st.game_over = True
        st.ended_by_rounds = by_rounds
        st.stack.clear()
        st.auction = None
        st.offers = []
        st.current_offer = None
        st.phase = ""
        self.emit(
            "GAME_ENDED",
            winner,
            {"winner": winner, "placements": placements, "by_rounds": by_rounds, "equities": eq},
        )

    # ------------------------------------------------------------------ loop
    def _run(self) -> None:
        """Execute automatic frames until a decision is pending or the game is over."""
        st = self.state
        stack = st.stack
        handlers = _HANDLERS
        while not st.game_over:
            if not stack:
                raise self._error(RuleViolationError, "empty continuation stack")
            top = stack[-1]
            op = top[0]
            if op in F.DECISION_OPS:
                if self._decision_alive(top):
                    return
                stack.pop()
                continue
            stack.pop()
            handlers[op](self, top)
        stack.clear()

    def _decision_alive(self, frame: tuple[int, ...]) -> bool:
        st = self.state
        op = frame[0]
        if op == F.OP_D_AUCTION:
            return st.auction is not None
        if op == F.OP_D_TRADE_RESPONSE:
            offer = st.current_offer
            return offer is not None and not st.bankrupt[offer.recipient] and not st.bankrupt[offer.proposer]
        return not st.bankrupt[frame[1]]

    # ------------------------------------------------------------------ public API
    def pending(self) -> D.Decision | None:
        """Current decision or ``None`` at game end."""
        if self._pending is not None:
            return self._pending
        st = self.state
        if st.game_over:
            return None
        frame = st.stack[-1]
        op = frame[0]
        if op == F.OP_D_WINDOW:
            seat, wkind = frame[1], frame[2]
            phase = D.JAIL_PRE_ROLL if wkind == F.W_PRE_ROLL and st.in_jail[seat] else _WINDOW_PHASE[wkind]
            d = D.Decision(seat, D.MAIN, phase, frame_mask(self, frame), {"window_id": st.window_counter})
        elif op == F.OP_D_BUY:
            p = frame[2]
            d = D.Decision(frame[1], D.MAIN, D.BUY_PHASE, frame_mask(self, frame), {
                "p": p, "price": self.board.p_price[p]})  # fmt: skip
        elif op == F.OP_D_DEBT:
            ctx = {"creditor": frame[2], "amount": frame[3], "reason": F.REASONS[frame[4]]}
            d = D.Decision(frame[1], D.DEBT, D.DEBT_PHASE, frame_mask(self, frame), ctx)
        elif op == F.OP_D_PLACE:
            item = D.ITEMS[frame[2]]
            d = D.Decision(frame[1], D.MAIN, D.PLACE_BUILDING, frame_mask(self, frame), {"item": item})
        elif op == F.OP_D_TRADE_OFFER:
            seat, wkind = frame[1], frame[2]
            phase = D.JAIL_PRE_ROLL if wkind == F.W_PRE_ROLL and st.in_jail[seat] else _WINDOW_PHASE[wkind]
            d = D.Decision(seat, D.TRADE_OFFER, phase, None, {"max_offers": C.MAX_OFFERS_PER_WINDOW})
        elif op == F.OP_D_TRADE_RESPONSE:
            offer = st.current_offer
            assert offer is not None
            d = D.Decision(offer.recipient, D.TRADE_RESPONSE, st.offer_phase, None, {"offer": offer})
        elif op == F.OP_D_AUCTION:
            auction = st.auction
            assert auction is not None
            d = D.Decision(auction.bidder, D.AUCTION_BID, auction.phase, None, bid_context(self))
        else:
            raise self._error(RuleViolationError, f"no decision frame on top (op={op})")
        if d.legal is not None and not any(d.legal):
            raise self._error(InvariantError, f"decision without legal action ({d.phase})", d.seat)
        st.phase = d.phase
        self._pending = d
        return d

    def legal_mask(self) -> list[bool]:
        """Legal mask of the pending MAIN/DEBT decision (all False otherwise)."""
        d = self.pending()
        if d is None or d.legal is None:
            return [False] * A.N_ACTIONS
        return list(d.legal)

    def apply(self, response: Any) -> list[Event]:
        """Apply the response to the pending decision and advance to the next decision."""
        d = self.pending()
        st = self.state
        if d is None:
            raise self._error(IllegalActionError, "game is over")
        self._apply_events = []
        try:
            if st.decision_index >= C.WATCHDOG_GAME_DECISIONS:
                raise self._error(EngineWatchdogError, "more than 2,000,000 decisions in one game")
            frame = st.stack[-1]
            serialized = self._dispatch(d, frame, response)
            st.counters[CNT_DECISIONS * st.n_players + d.seat] += 1
            entry: dict[str, Any] = {"i": st.decision_index, "seat": d.seat, "kind": d.kind, "r": serialized}
            self.emit("DECISION", d.seat, {"kind": d.kind, "phase": d.phase, "response": serialized})
            st.decision_index += 1
            self._pending = None
            self._run()
            self.pending()  # derive the next decision (and phase) before hashing
            hi = self.options.hash_interval
            if hi and st.decision_index % hi == 0:
                entry["h"] = st.state_hash()
            self.decision_log.append(entry)
            if self.options.check_invariants:
                from propertyrl.engine.invariants import check_invariants

                check_invariants(self)
        except PropertyRLError as err:
            if err.game_log is None and not isinstance(err, IllegalActionError):
                err.game_log = self.to_log()
            raise
        return self._apply_events

    def _check_action(self, d: D.Decision, response: Any) -> int:
        if not isinstance(response, int) or isinstance(response, bool):
            raise self.illegal(f"{d.kind} expects an action id, got {response!r}", d.seat)
        assert d.legal is not None
        if not 0 <= response < A.N_ACTIONS or not d.legal[response]:
            name = A.action_name(response) if 0 <= response < A.N_ACTIONS else str(response)
            raise self.illegal(f"illegal action {name} in phase {d.phase}", d.seat)
        return response

    def _dispatch(self, d: D.Decision, frame: tuple[int, ...], response: Any) -> Any:
        st = self.state
        op = frame[0]
        if op == F.OP_D_TRADE_OFFER:
            self.pop()
            try:
                return handle_offers(self, d.seat, response, d.phase)
            except IllegalActionError:
                self.push(frame)
                raise
        if op == F.OP_D_TRADE_RESPONSE:
            if not isinstance(response, bool):
                raise self.illegal("TRADE_RESPONSE expects bool", d.seat)
            self.pop()
            handle_response(self, response)
            return response
        if op == F.OP_D_AUCTION:
            self.pop()
            try:
                out = apply_bid(self, response)
            except IllegalActionError:
                self.push(frame)
                raise
            if st.auction is not None:
                self.push(frame)
            return out
        action = self._check_action(d, response)
        st.ctx_decisions += 1
        if st.ctx_decisions > C.WATCHDOG_WINDOW_DECISIONS:
            raise self._error(EngineWatchdogError, "more than 1000 decisions in one window/phase", d.seat)
        seat = d.seat
        st.window_actions.append((seat, action))
        if op == F.OP_D_WINDOW:
            self._apply_window(frame, seat, action)
        elif op == F.OP_D_BUY:
            if action == A.BUY:
                self.pop()
                buy(self, seat, frame[2])
            elif action == A.DECLINE:
                self.pop()
                decline(self, seat, frame[2])
            else:
                self._management(seat, action, in_window=False)
        elif op == F.OP_D_DEBT:
            self._management(seat, action, in_window=False)
            after_debt_action(self, frame)
        elif op == F.OP_D_PLACE:
            self.pop()
            do_build(self, seat, action - A.BUILD_BASE)
        return action

    def _apply_window(self, frame: tuple[int, ...], seat: int, action: int) -> None:
        st = self.state
        if action == A.ROLL:
            jailed = st.in_jail[seat]
            if jailed:
                self.cnt(CNT_JAIL_STAY, seat)
            close_window(self, seat)
            self.pop()
            self.push((F.OP_JAIL_ROLL, seat) if jailed else (F.OP_ROLL, seat))
        elif action == A.END_PHASE:
            close_window(self, seat)
            self.pop()
        elif action == A.PAY_JAIL_FINE:
            self.cnt(CNT_JAIL_LEAVE, seat)
            pay_fine(self, seat)
        elif action == A.USE_JAIL_CARD:
            self.cnt(CNT_JAIL_LEAVE, seat)
            use_card(self, seat)
        else:
            self._management(seat, action, in_window=True)

    def _management(self, seat: int, action: int, in_window: bool) -> None:
        if action < A.SELL_BASE:
            b = action - A.BUILD_BASE
            if in_window:
                try_build(self, seat, b)
            else:
                do_build(self, seat, b)
        elif action < A.MORTGAGE_BASE:
            do_sell(self, seat, action - A.SELL_BASE)
        elif action < A.UNMORTGAGE_BASE:
            do_mortgage(self, seat, action - A.MORTGAGE_BASE)
        else:
            do_unmortgage(self, seat, action - A.UNMORTGAGE_BASE)

    def is_over(self) -> bool:
        """True once the game has ended."""
        return self.state.game_over

    def result(self) -> GameResult:
        """Result of a finished game (or the current standings if still running)."""
        st = self.state
        n = st.n_players
        counters = {name: st.counters[i * n : (i + 1) * n] for i, name in enumerate(COUNTER_NAMES)}
        return GameResult(
            winner=st.winner if st.game_over and st.winner >= 0 else None,
            placements=list(st.placements),
            rounds=st.round_index + 1,
            decisions=st.decision_index,
            truncated=False,
            final_equities=list(st.final_equities) if st.game_over else all_equities(st, self.board),
            counters=counters,
            rest_counts=list(st.rest_counts),
            ended_by_rounds=st.ended_by_rounds,
        )

    def clone(self, reseed: int | None = None, log_events: bool | None = None) -> Engine:
        """Cheap copy; with ``reseed`` future dice and undrawn cards are resampled (§4.3)."""
        opts = EngineOptions(
            log_events=self.options.log_events if log_events is None else log_events,
            check_invariants=self.options.check_invariants,
            dice_script=self.options.dice_script if reseed is None else None,
            card_order=self.options.card_order,
            allow_test_hooks=self.options.allow_test_hooks,
            hash_interval=self.options.hash_interval,
        )
        new = Engine(self.ruleset, self.board, self.decks, self.state.copy(), opts)
        new.decision_log = list(self.decision_log)
        new.meta = dict(self.meta)
        new.initial_state = self.initial_state
        new.event_seq = self.event_seq
        if self.log and new.log:
            new.ledger = self.ledger.copy()
        if reseed is not None:
            st = new.state
            st.rng_epoch = reseed
            st.deck_a = reshuffle_positions(st.deck_a, st.deck_cycle_drawn_a, st.game_seed, reseed, C.DECK_A)
            st.deck_b = reshuffle_positions(st.deck_b, st.deck_cycle_drawn_b, st.game_seed, reseed, C.DECK_B)
        return new

    def state_hash(self) -> str:
        """SHA-256 of the canonical state."""
        return self.state.state_hash()

    def public_view(self, seat: int) -> PublicState:
        """Read-only public information for ``seat`` (no deck order, no RNG state)."""
        st = self.state
        d = self.pending()
        return PublicState(
            seat=seat,
            n_players=st.n_players,
            cash=tuple(st.cash),
            position=tuple(st.position),
            in_jail=tuple(st.in_jail),
            jail_attempts=tuple(st.jail_attempts),
            jail_cards=tuple(st.jail_cards),
            bankrupt=tuple(st.bankrupt),
            bankruptcy_order=tuple(st.bankruptcy_order),
            owner=tuple(st.owner),
            mortgaged=tuple(st.mortgaged),
            interest_prepaid=tuple(st.interest_prepaid),
            level=tuple(st.level),
            bank_houses=st.bank_houses,
            bank_hotels=st.bank_hotels,
            deck_cycle_drawn_a=st.deck_cycle_drawn_a,
            deck_cycle_drawn_b=st.deck_cycle_drawn_b,
            active_seat=st.active_seat,
            doubles_count=st.doubles_count,
            turn_index=st.turn_index,
            round_index=st.round_index,
            window_counter=st.window_counter,
            window_actions=tuple(st.window_actions),
            phase=d.phase if d is not None else "",
            decision_kind=d.kind if d is not None else "",
            last_dice=st.last_dice,
            board=self.board,
            ruleset=self.ruleset,
            game_over=st.game_over,
            context=dict(d.context) if d is not None and d.seat == seat else {},
        )

    def to_log(self) -> dict[str, Any]:
        """Self-contained game log (header, decisions, optional events, see replay.py)."""
        from propertyrl.engine.replay import build_log

        return build_log(self)

    @classmethod
    def replay(cls, log: dict[str, Any]) -> Engine:
        """Replay a log; raises ReplayMismatchError on any divergence."""
        from propertyrl.engine.replay import replay_log

        return replay_log(log)
