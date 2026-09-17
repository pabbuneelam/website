"""Turning a night of basketball into attribute ratings.

    difficulty-adjusted value
      -> percentile among everyone who qualified tonight
      -> rating 0-99

Percentiles are bounded by construction, so ratings are comparable across
nights and across attributes without any tuning. That matters more here than in
a pure prediction game: these ratings go onto a card that joins a roster and
eventually a simulator, so a 97 has to mean the performance was genuinely
elite -- not merely surprising.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from . import attributes
from .models import BoxScore

MAX_RATING = 99


def percentile_rank(value: float, pool: Sequence[float]) -> float:
    """Midrank percentile in 0..1. Ties split the difference, so two identical
    nights rate identically instead of one arbitrarily beating the other.

    An empty pool scores 0.0; a single-element pool scores 0.5.
    """
    if not pool:
        return 0.0
    below = sum(1 for p in pool if p < value)
    equal = sum(1 for p in pool if p == value)
    return (below + 0.5 * equal) / len(pool)


@dataclass
class AttributePool:
    """Everyone who posted a qualifying value in one attribute tonight."""

    slot: str
    value: dict[int, float]

    @property
    def values(self) -> list[float]:
        return list(self.value.values())


class NightRater:
    """Rates any player in any attribute, against everyone who played tonight."""

    def __init__(self, boxscores: Iterable[BoxScore]) -> None:
        self._boxes = {b.player_id: b for b in boxscores}
        self._pools: dict[str, AttributePool] = {}

    @property
    def boxes(self) -> dict[int, BoxScore]:
        return self._boxes

    def pool(self, slot: str) -> AttributePool:
        if slot not in self._pools:
            metric = attributes.get(slot).metric
            value: dict[int, float] = {}
            for pid, box in self._boxes.items():
                if not box.played:
                    continue
                v = metric(box)
                if v is not None:
                    value[pid] = v
            self._pools[slot] = AttributePool(slot, value)
        return self._pools[slot]

    def rate(self, slot: str, player_id: int) -> tuple[int, float | None, float, str]:
        """Return (rating, value, percentile, note)."""
        pool = self.pool(slot)
        box = self._boxes.get(player_id)

        if box is None:
            return 0, None, 0.0, "not on tonight's slate"
        if not box.played:
            return 0, None, 0.0, "did not play"
        if player_id not in pool.value:
            return 0, None, 0.0, f"did not qualify ({attributes.get(slot).guardrail})"

        value = pool.value[player_id]
        percentile = percentile_rank(value, pool.values)
        return round(percentile * MAX_RATING), value, percentile, ""
