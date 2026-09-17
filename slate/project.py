"""Projections — the seam the ML eventually replaces.

Everything downstream depends only on the ``Projector`` protocol. Opponent
adjustment, similar-team clustering, injury context and market odds all arrive
later as new ``Projector`` implementations; ``score.py`` never learns they exist.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .metrics import METRICS
from .models import BoxScore

# Recency decay inside a season, and the extra discount per season back. Both
# are guesses and both are meant to be tuned against real slates.
GAME_DECAY = 0.90
SEASON_WEIGHT = 0.55
MIN_SAMPLES_FOR_DISPERSION = 3


@dataclass(frozen=True)
class GameContext:
    """What a projector is allowed to know before tipoff. The baseline ignores
    all of it; the ML will not."""

    date: str
    team: str
    opponent: str
    home: bool


@dataclass(frozen=True)
class Projection:
    mean: float
    dispersion: float | None  # None => score.py falls back to the category pool


class Projector(Protocol):
    def project(
        self, player_id: int, category_id: str, ctx: GameContext
    ) -> Projection | None:
        """Return ``None`` when there is no basis for a projection at all.
        ``score.py`` then measures the player against the field instead."""
        ...


class BaselineProjector:
    """Exponentially-decayed mean of the player's prior games in that category,
    blended across seasons.

    Deliberately dumb and honest. It exists so the engine is testable and the
    game is playable before any model is trained, and so that the day a real
    model lands the diff is one constructor argument.
    """

    def __init__(self, logs: dict[int, Sequence[tuple[int, BoxScore]]]) -> None:
        # logs: player_id -> [(season_offset, box)], most recent first.
        # season_offset 0 is the current season, 1 the one before it.
        self._logs = logs

    def project(
        self, player_id: int, category_id: str, ctx: GameContext
    ) -> Projection | None:
        metric = METRICS[category_id_to_metric(category_id)]
        samples: list[tuple[float, float]] = []  # (weight, value)
        for i, (season_offset, box) in enumerate(self._logs.get(player_id, ())):
            value = metric(box)
            if value is None:
                continue  # guardrail failed that night; it teaches us nothing
            weight = (GAME_DECAY**i) * (SEASON_WEIGHT**season_offset)
            samples.append((weight, value))

        if not samples:
            return None

        total = sum(w for w, _ in samples)
        mean = sum(w * v for w, v in samples) / total

        if len(samples) < MIN_SAMPLES_FOR_DISPERSION:
            # One or two games is not a spread. Let the pool supply the scale.
            return Projection(mean=mean, dispersion=None)

        var = sum(w * (v - mean) ** 2 for w, v in samples) / total
        dispersion = math.sqrt(var)
        return Projection(mean=mean, dispersion=dispersion if dispersion > 0 else None)


def category_id_to_metric(category_id: str) -> str:
    from .catalog import get

    return get(category_id).metric
