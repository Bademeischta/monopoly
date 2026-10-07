"""Ratings (§8.6): Elo for 2P, OpenSkill Plackett-Luce for 4P (and additionally 2P)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from propertyrl.engine import constants as C
from propertyrl.engine.rng import SeededStream


def elo(records: Sequence[dict[str, Any]], start: float = 1500.0, k: float = 32.0, seed: int = 0) -> dict[str, float]:
    """Elo over 2P games in a fixed, seed-shuffled order (draws/truncations count 0.5)."""
    games = [r for r in records if r["n_players"] == 2]
    order = list(range(len(games)))
    rng = SeededStream(seed, C.STREAM_EVAL, 77)
    for i in range(len(order) - 1, 0, -1):
        j = rng.randint(0, i)
        order[i], order[j] = order[j], order[i]
    ratings: dict[str, float] = {}
    for idx in order:
        g = games[idx]
        a, b = g["seats"]
        ra, rb = ratings.setdefault(a, start), ratings.setdefault(b, start)
        if g["truncated"] or g["winner"] is None:
            sa = 0.5
        else:
            sa = 1.0 if g["winner"] == 0 else 0.0
        ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        ratings[a] = ra + k * (sa - ea)
        ratings[b] = rb + k * ((1.0 - sa) - (1.0 - ea))
    return ratings


def openskill(records: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """OpenSkill Plackett-Luce ratings from game placements (mu, sigma, ordinal)."""
    from openskill.models import PlackettLuce

    model = PlackettLuce()
    players: dict[str, Any] = {}
    for g in records:
        names = g["seats"]
        teams = [[players.setdefault(name, model.rating(name=name))] for name in names]
        ranks = [float(p) for p in g["placements"]]
        if len(set(names)) < len(names):
            continue  # identical policies in several seats cannot be rated as separate teams
        new = model.rate(teams, ranks=ranks)
        for name, team in zip(names, new, strict=True):
            players[name] = team[0]
    return {
        name: {"mu": float(r.mu), "sigma": float(r.sigma), "ordinal": float(r.ordinal())}
        for name, r in sorted(players.items())
    }
