"""Self-play support (§7.8): snapshot pool with even thinning and the two-block champion gate."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from propertyrl.evaluation.duplicate import duplicate_specs, summarize
from propertyrl.evaluation.harness import run_games

log = logging.getLogger(__name__)


@dataclass
class SnapshotPool:
    """Chronological snapshot paths; when larger than ``max_size`` the oldest part is thinned evenly."""

    max_size: int = 50
    paths: list[str] = field(default_factory=list)

    def add(self, path: str) -> list[str]:
        """Add a snapshot and return the paths that were removed by thinning."""
        self.paths.append(path)
        removed: list[str] = []
        while len(self.paths) > self.max_size:
            victim = self._thin_candidate()
            self.paths.remove(victim)
            removed.append(victim)
        return removed

    @staticmethod
    def _step(path: str) -> int:
        nums = re.findall(r"(\d+)", path.rsplit("/", 1)[-1])
        return int(nums[-1]) if nums else 0

    def _thin_candidate(self) -> str:
        """Element of the older half whose neighbours are closest together (even thinning)."""
        half = max(2, len(self.paths) // 2)
        steps = [self._step(p) for p in self.paths]
        best, best_gap = 1, None
        for i in range(1, min(half, len(self.paths) - 1)):
            gap = steps[i + 1] - steps[i - 1]
            if best_gap is None or gap < best_gap:
                best, best_gap = i, gap
        return self.paths[best]

    def state(self) -> dict[str, Any]:
        """Serialisable state."""
        return {"max_size": self.max_size, "paths": list(self.paths)}


def pfsp_weights(stats: dict[str, list[int]]) -> dict[str, float]:
    """PFSP weight (1 - p)^2 with p = (wins + 1) / (games + 2) per opponent id."""
    out = {}
    for oid, (wins, games) in stats.items():
        p = (wins + 1) / (games + 2)
        out[oid] = (1.0 - p) ** 2
    return out


def evaluate_pair(
    agent: str, opponent: str, ruleset: str, seeds: list[int], workers: int | None = None
) -> dict[str, Any]:
    """Duplicate evaluation of ``agent`` against one opponent on the given seeds."""
    records = run_games(duplicate_specs(agent, [opponent], seeds, ruleset, 2), workers=workers)
    return summarize(records, agent, bootstrap_reps=1000)


def champion_gate(
    candidate: str,
    champion: str,
    ruleset: str,
    blocks: list[list[int]],
    margin_pp: float,
    champion_vs_a: dict[int, float] | None = None,
    workers: int | None = None,
) -> dict[str, Any]:
    """Candidate vs champion on SELECT block 1, then block 2 (§7.8).

    A block passes if the Wilson lower 95 % bound of the candidate's win rate is > 50 % and its win
    rate against strong_a_v1 is at least the champion's minus ``margin_pp`` percentage points.
    """
    result: dict[str, Any] = {"candidate": candidate, "champion": champion, "blocks": [], "passed": False}
    cache = dict(champion_vs_a or {})
    for i, seeds in enumerate(blocks):
        head = evaluate_pair(candidate, champion, ruleset, seeds, workers)
        cand_a = evaluate_pair(candidate, "strong_a_v1", ruleset, seeds, workers)["win_rate"]
        if i not in cache:
            cache[i] = evaluate_pair(champion, "strong_a_v1", ruleset, seeds, workers)["win_rate"]
        ok = head["wilson_lower"] > 0.5 and cand_a >= cache[i] - margin_pp / 100.0
        result["blocks"].append(
            {
                "block": i + 1,
                "head_to_head": head["win_rate"],
                "wilson_lower": head["wilson_lower"],
                "candidate_vs_strong_a": cand_a,
                "champion_vs_strong_a": cache[i],
                "passed": ok,
            }
        )
        if not ok:
            result["champion_vs_a"] = cache
            return result
    result["passed"] = True
    result["champion_vs_a"] = cache
    return result
