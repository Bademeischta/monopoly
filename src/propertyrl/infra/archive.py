"""Archived replays (§4.10): deterministic reference games with expected state hashes.

``propertyrl replay --regenerate`` rewrites them after a deliberate rule change (engine_version bump).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from propertyrl.engine import Engine, EngineOptions, read_log, replay_log, write_log
from propertyrl.engine.rng import AgentRng
from propertyrl.infra.config import REPO_ROOT, load_setup
from propertyrl.infra.fuzz import RARE_EVENT_GENERATORS, random_response
from propertyrl.infra.storage import read_json, write_json

ARCHIVE_DIR = REPO_ROOT / "tests" / "data" / "replays"


@dataclass(frozen=True)
class ArchiveSpec:
    """One archived reference game."""

    name: str
    ruleset: str
    players: int
    seed: int
    max_decisions: int
    scenario: str | None = None


ARCHIVE_SPECS: tuple[ArchiveSpec, ...] = (
    ArchiveSpec("official_2p", "OFFICIAL_US_CLASSIC_2008", 2, 101, 4000),
    ArchiveSpec("official_4p", "OFFICIAL_US_CLASSIC_2008", 4, 102, 3000),
    ArchiveSpec("official_8p", "OFFICIAL_US_CLASSIC_2008", 8, 103, 3000),
    ArchiveSpec("research_2p", "RESEARCH_2P_BOUNDED_V1", 2, 104, 4000),
    ArchiveSpec("shortgame_2p", "RESEARCH_2P_SHORTGAME_V1", 2, 105, 4000),
    ArchiveSpec("scarcity_official_3p", "OFFICIAL_US_CLASSIC_2008", 3, 106, 1500, scenario="scarcity"),
)


def play_spec(spec: ArchiveSpec) -> Engine:
    """Play an archived reference game with the deterministic random responder."""
    opts = EngineOptions(log_events=False, check_invariants=True, hash_interval=25)
    if spec.scenario is not None:
        gen, _, _ = RARE_EVENT_GENERATORS[spec.scenario]
        builder = gen(spec.ruleset, spec.players, spec.seed, AgentRng(spec.seed, 5))
        eng = builder.options(log_events=False, check_invariants=True, hash_interval=25).build()
    else:
        rules, board, decks = load_setup(spec.ruleset, spec.players, safety_horizon_rounds=1000, **(
            {"max_rounds": 30} if spec.ruleset == "RESEARCH_2P_SHORTGAME_V1" else {}))  # fmt: skip
        eng = Engine.new(rules, board, decks, spec.players, spec.seed, opts)
    eng.meta = {"archive": spec.name, "policies": ["fuzz_random"] * spec.players}
    rng = AgentRng(spec.seed, 41)
    while not eng.is_over() and eng.state.decision_index < spec.max_decisions:
        eng.apply(random_response(eng, rng))
    return eng


def regenerate(directory: Path = ARCHIVE_DIR) -> dict[str, str]:
    """Rewrite all archived logs and the expected hashes; return name -> hash."""
    directory.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for spec in ARCHIVE_SPECS:
        eng = play_spec(spec)
        write_log(eng.to_log(), directory / f"{spec.name}.jsonl")
        hashes[spec.name] = eng.state_hash()
    write_json(directory / "expected_hashes.json", hashes)
    return hashes


def verify(directory: Path = ARCHIVE_DIR) -> dict[str, Any]:
    """Replay every archived log and compare with the expected hash."""
    expected = read_json(directory / "expected_hashes.json")
    results: dict[str, Any] = {}
    for name, want in sorted(expected.items()):
        log = read_log(directory / f"{name}.jsonl")
        got = replay_log(log).state_hash()
        results[name] = {"expected": want, "got": got, "ok": got == want == log["header"]["final_state_hash"]}
    return results
