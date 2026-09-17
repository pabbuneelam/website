"""Self-tuning niche boosts.

A category's boost is the spread of its normalised residuals. If the projector
were perfectly calibrated the z-values would have a standard deviation of 1, so
std > 1 means the category is harder to call than the model thinks, and it pays
more. That makes the boost self-correcting: as the model improves, the boost on
a category it has learned falls back toward 1.

The known failure mode is that noise and difficulty look identical from here --
a pure coin-flip category would otherwise claim the top multiplier. Three
guards, none of which fully solve it:

* z is dispersion-normalised, so raw scale differences do not leak in
* the result is clamped to [BOOST_MIN, BOOST_MAX]
* seeds stand until MIN_NIGHTS_TO_TUNE nights exist, so cold start is hand-set

The real fix is to change what this measures. Once there is user data, swap the
target from "hardest to predict" to "widest spread among entrants", which is a
much closer proxy for skill. That is a change to `_target` alone.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from . import catalog
from .rules import BOOST_MAX, BOOST_MIN, MIN_NIGHTS_TO_TUNE

# category_id -> one list of z-values per night
History = Mapping[str, Sequence[Sequence[float]]]


def _stdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def _target(nights: Sequence[Sequence[float]]) -> float:
    pooled = [z for night in nights for z in night]
    return _stdev(pooled)


def clamp(value: float) -> float:
    return max(BOOST_MIN, min(BOOST_MAX, value))


class BoostTuner:
    def __init__(self, min_nights: int = MIN_NIGHTS_TO_TUNE) -> None:
        self.min_nights = min_nights

    def boosts(self, history: History) -> dict[str, float]:
        out: dict[str, float] = {}
        for cat in catalog.CATALOG:
            nights = history.get(cat.id, ())
            if len(nights) < self.min_nights:
                out[cat.id] = cat.seed_boost
                continue
            out[cat.id] = clamp(_target(nights))
        return out


def night_residuals(scorer, category_ids: Sequence[str]) -> dict[str, list[float]]:
    """Pull one night's z-values out of a NightScorer, ready to append to history."""
    return {cid: scorer.pool(cid).zs for cid in category_ids}
