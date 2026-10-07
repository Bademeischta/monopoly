"""Hypothesis RuleBasedStateMachine: random legal answers of all decision kinds, invariants after every step."""

from __future__ import annotations

from typing import Any

from helpers import MOVEMENT, OFFICIAL, RESEARCH, SHORTGAME, new_game
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from propertyrl.engine import Engine
from propertyrl.engine import actions as A
from propertyrl.engine import decisions as D
from propertyrl.engine.invariants import check_invariants
from propertyrl.engine.rng import AgentRng
from propertyrl.infra.fuzz import RARE_EVENT_GENERATORS, random_response

WINDOW_PHASES = (D.PRE_ROLL, D.JAIL_PRE_ROLL, D.POST_MOVE, D.OUT_OF_TURN)


class EngineMachine(RuleBasedStateMachine):
    """Drives one game per example with Hypothesis-chosen random answers."""

    eng: Engine | None = None

    @initialize(
        ruleset=st.sampled_from([OFFICIAL, OFFICIAL, RESEARCH, SHORTGAME, MOVEMENT]),
        n=st.integers(min_value=2, max_value=6),
        seed=st.integers(min_value=0, max_value=2**40),
        rare=st.sampled_from([None, *sorted(RARE_EVENT_GENERATORS)]),
    )
    def start(self, ruleset: str, n: int, seed: int, rare: str | None) -> None:
        if ruleset != OFFICIAL:
            n = 2
        if rare is not None and ruleset in (OFFICIAL, RESEARCH):
            gen, _, _ = RARE_EVENT_GENERATORS[rare]
            self.eng = gen(ruleset, min(n, 4), seed, AgentRng(seed, 5)).options(check_invariants=True).build()
        else:
            self.eng = new_game(ruleset, n, seed=seed)

    @rule(choice=st.integers(min_value=0, max_value=2**32))
    def answer(self, choice: int) -> None:
        eng = self.eng
        assert eng is not None
        if eng.is_over():
            return
        before = eng.pending()
        assert before is not None
        response: Any = random_response(eng, AgentRng(choice, 1))
        eng.apply(response)
        after = eng.pending()
        # A-111: inside a window only ROLL can lead to a payment obligation (debt phase).
        if before.kind == D.MAIN and before.phase in WINDOW_PHASES and response != A.ROLL and after is not None:
            assert after.kind != D.DEBT

    @invariant()
    def consistent(self) -> None:
        if self.eng is not None:
            check_invariants(self.eng)


TestEngineMachine = EngineMachine.TestCase
TestEngineMachine.settings = settings(
    max_examples=40, stateful_step_count=150, deadline=None, suppress_health_check=list(HealthCheck)
)
