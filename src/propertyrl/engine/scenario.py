"""ScenarioBuilder: hand-crafted start states with DiceScript and card order (tests only, §4.3).

Cash deviations from the starting cash are booked as bank transfers so that the
ledger invariant holds; building levels draw from the bank stock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import constants as C
from propertyrl.engine.errors import RuleViolationError
from propertyrl.engine.state import GameState

if TYPE_CHECKING:
    from propertyrl.engine.board import Board
    from propertyrl.engine.cards import Decks
    from propertyrl.engine.game import Engine
    from propertyrl.engine.ruleset import Ruleset


class ScenarioBuilder:
    """Fluent builder for test scenarios."""

    def __init__(self, ruleset: Ruleset, board: Board, decks: Decks, n_players: int = 2, game_seed: int = 0) -> None:
        self.ruleset = ruleset
        self.board = board
        self.decks = decks
        self.n = n_players
        self.seed = game_seed
        self._cash: dict[int, int] = {}
        self._owner: dict[int, int] = {}
        self._mortgaged: set[int] = set()
        self._levels: dict[int, int] = {}
        self._position: dict[int, int] = {}
        self._jail: dict[int, int] = {}
        self._jail_cards: dict[int, int] = {}
        self._bankrupt: list[int] = []
        self._dice: list[tuple[int, int]] | None = None
        self._cards: dict[int, list[str]] = {}
        self._active = 0
        self._round = 0
        self._log_events = True
        self._check = True
        self._hash_interval = 0

    def cash(self, seat: int, amount: int) -> ScenarioBuilder:
        """Set the cash of a seat."""
        self._cash[seat] = amount
        return self

    def own(self, seat: int, *props: int, mortgaged: bool = False) -> ScenarioBuilder:
        """Give properties (by p index) to a seat."""
        for p in props:
            self._owner[p] = seat
            if mortgaged:
                self._mortgaged.add(p)
            else:
                self._mortgaged.discard(p)
        return self

    def own_group(self, seat: int, group: str, level: int = 0) -> ScenarioBuilder:
        """Give a whole group to a seat, optionally built to a uniform level."""
        g = C.GROUP_ID[group]
        self.own(seat, *C.GROUP_PROPS[g])
        for b in C.GROUP_BUILDS[g]:
            self._levels[b] = level
        return self

    def level(self, b: int, lvl: int) -> ScenarioBuilder:
        """Set the building level of buildable index b."""
        self._levels[b] = lvl
        return self

    def position(self, seat: int, square: int) -> ScenarioBuilder:
        """Place a seat on a square."""
        self._position[seat] = square
        return self

    def jail(self, seat: int, attempts: int = 0) -> ScenarioBuilder:
        """Put a seat in jail with the given number of failed attempts."""
        self._jail[seat] = attempts
        return self

    def jail_card(self, seat: int, deck: int) -> ScenarioBuilder:
        """Give a jail-free card of deck 0 (A) or 1 (B)."""
        self._jail_cards[seat] = self._jail_cards.get(seat, 0) | C.DECK_BITS[deck]
        return self

    def bankrupt(self, seat: int) -> ScenarioBuilder:
        """Mark a seat as already bankrupt (owns nothing, cash 0)."""
        self._bankrupt.append(seat)
        return self

    def dice(self, *pairs: tuple[int, int]) -> ScenarioBuilder:
        """Install a DiceScript (consumed by every throw in order)."""
        self._dice = list(pairs)
        return self

    def cards(self, deck: int, card_ids: list[str]) -> ScenarioBuilder:
        """Put the given cards on top of a deck in order."""
        self._cards[deck] = list(card_ids)
        return self

    def active(self, seat: int) -> ScenarioBuilder:
        """Seat whose turn starts first."""
        self._active = seat
        return self

    def round(self, round_index: int) -> ScenarioBuilder:
        """Initial round counter (short-game tests)."""
        self._round = round_index
        return self

    def options(
        self, log_events: bool = True, check_invariants: bool = True, hash_interval: int = 0
    ) -> ScenarioBuilder:
        """Engine options for the scenario."""
        self._log_events = log_events
        self._check = check_invariants
        self._hash_interval = hash_interval
        return self

    def build(self) -> Engine:
        """Create the engine and advance to the first decision."""
        from propertyrl.engine.game import Engine, EngineOptions

        rules = self.ruleset
        st = GameState(self.n, self.seed, rules.starting_cash, rules.bank_houses, rules.bank_hotels)
        for p, seat in self._owner.items():
            st.owner[p] = seat
        for p in self._mortgaged:
            st.mortgaged[p] = True
        for b, lvl in self._levels.items():
            st.level[b] = lvl
            if lvl == C.HOTEL_LEVEL:
                st.bank_hotels -= 1
            else:
                st.bank_houses -= lvl
        if st.bank_houses < 0 or st.bank_hotels < 0:
            raise RuleViolationError("scenario uses more buildings than the bank holds")
        for seat, sq in self._position.items():
            st.position[seat] = sq
        for seat, attempts in self._jail.items():
            st.in_jail[seat] = True
            st.position[seat] = C.JAIL_SQUARE
            st.jail_attempts[seat] = attempts
        for seat, amount in self._cash.items():
            delta = amount - rules.starting_cash
            st.cash[seat] = amount
            if delta > 0:
                st.ledger_in[seat] += delta
            else:
                st.ledger_out[seat] += -delta
        for seat in self._bankrupt:
            st.bankrupt[seat] = True
            st.bankruptcy_order.append(seat)
            st.ledger_out[seat] += st.cash[seat]
            st.cash[seat] = 0
        decks = {C.DECK_A: list(range(C.DECK_SIZE)), C.DECK_B: list(range(C.DECK_SIZE))}
        for deck_idx, ids in self._cards.items():
            front = [self.decks.index_of(deck_idx, cid) for cid in ids]
            decks[deck_idx] = front + [c for c in range(C.DECK_SIZE) if c not in front]
        for seat, mask in self._jail_cards.items():
            st.jail_cards[seat] = mask
            for deck_idx in (C.DECK_A, C.DECK_B):
                if mask & C.DECK_BITS[deck_idx]:
                    decks[deck_idx].remove(self.decks.jail_free_index[deck_idx])
        st.deck_a = decks[C.DECK_A]
        st.deck_b = decks[C.DECK_B]
        st.round_index = self._round
        opts = EngineOptions(
            log_events=self._log_events,
            check_invariants=self._check,
            dice_script=tuple(self._dice) if self._dice is not None else None,
            allow_test_hooks=True,
            hash_interval=self._hash_interval,
        )
        eng = Engine.from_state(rules, self.board, self.decks, st, opts, self._active)
        if self._check:
            from propertyrl.engine.invariants import check_invariants

            check_invariants(eng)
        return eng
