"""The scoring engine.

    residual -> z -> percentile -> boost -> score

A pick's multiplier is the percentile of how far that player beat *his own
projection*, among everyone who played tonight in that category. Percentiles are
bounded 0..1 by construction, so a bad projector makes the game noisy but can
never blow up the scale, and no category can run away with the night.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from . import catalog
from .metrics import METRICS
from .models import BoxScore, Lineup, Pick, Result, ScoredPick, SlateGame
from .project import GameContext, Projection, Projector
from .rules import BACKUP_FACTOR, BUDGET, MAX_PICKS, MIN_ALLOCATION

DISPERSION_FLOOR = 1e-6


def percentile_rank(value: float, pool: Sequence[float]) -> float:
    """Midrank percentile in 0..1. Ties split the difference, so two identical
    nights score identically instead of one arbitrarily beating the other.

    An empty pool scores 0.0; a single-element pool scores 0.5.
    """
    if not pool:
        return 0.0
    below = sum(1 for p in pool if p < value)
    equal = sum(1 for p in pool if p == value)
    return (below + 0.5 * equal) / len(pool)


@dataclass
class CategoryPool:
    """Everyone who posted a valid value in one category tonight."""

    category_id: str
    actual: dict[int, float]
    projected: dict[int, float]
    z: dict[int, float]

    @property
    def zs(self) -> list[float]:
        return list(self.z.values())


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _stdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


class NightScorer:
    """Scores every lineup for one night against one set of box scores."""

    def __init__(
        self,
        boxscores: Iterable[BoxScore],
        projector: Projector,
        date: str,
        games: Sequence[SlateGame] = (),
    ) -> None:
        self._boxes = {b.player_id: b for b in boxscores}
        self._projector = projector
        self._date = date
        self._home_teams = {g.home for g in games}
        self._pools: dict[str, CategoryPool] = {}

    # -- pools ---------------------------------------------------------

    def _context(self, box: BoxScore) -> GameContext:
        return GameContext(
            date=self._date,
            team=box.team,
            opponent=box.opponent,
            home=box.team in self._home_teams,
        )

    def pool(self, category_id: str) -> CategoryPool:
        if category_id in self._pools:
            return self._pools[category_id]

        metric = METRICS[catalog.get(category_id).metric]

        # Pass one: actuals. A None here is a guardrail failure or missing
        # play-by-play, and it removes the player from the pool entirely.
        actual: dict[int, float] = {}
        for pid, box in self._boxes.items():
            if not box.played:
                continue
            value = metric(box)
            if value is not None:
                actual[pid] = value

        pool_mean = _mean(list(actual.values())) if actual else 0.0
        pool_std = _stdev(list(actual.values()))

        # Pass two: residuals, normalised. The pool supplies mean and scale
        # whenever the projector cannot -- a player with no history is measured
        # against the field instead, which is the honest fallback.
        projected: dict[int, float] = {}
        z: dict[int, float] = {}
        for pid, value in actual.items():
            proj: Projection | None = self._projector.project(
                pid, category_id, self._context(self._boxes[pid])
            )
            mean = proj.mean if proj is not None else pool_mean
            dispersion = proj.dispersion if proj is not None else None
            if dispersion is None or dispersion <= 0:
                dispersion = pool_std
            if dispersion <= 0:
                dispersion = DISPERSION_FLOOR
            projected[pid] = mean
            z[pid] = (value - mean) / dispersion

        self._pools[category_id] = CategoryPool(category_id, actual, projected, z)
        return self._pools[category_id]

    # -- lineups -------------------------------------------------------

    def score_lineup(
        self, lineup: Lineup, boosts: Mapping[str, float] | None = None
    ) -> Result:
        problem = validate(lineup)
        if problem:
            return Result(entrant=lineup.entrant, total=0.0, void=True, void_reason=problem)

        scored = tuple(self._score_pick(p, boosts or {}) for p in lineup.picks)
        return Result(
            entrant=lineup.entrant,
            total=round(sum(s.score for s in scored), 4),
            picks=scored,
        )

    def _score_pick(self, pick: Pick, boosts: Mapping[str, float]) -> ScoredPick:
        cat = catalog.get(pick.category_id)
        boost = boosts.get(cat.id, cat.seed_boost)
        pool = self.pool(cat.id)

        scored_id, factor, note = self._resolve_player(pick)

        if scored_id is None or scored_id not in pool.z:
            # Nobody available played, or the one who did failed the guardrail.
            return ScoredPick(
                category_id=cat.id,
                player_id=pick.player_id,
                scored_player_id=scored_id if scored_id is not None else pick.player_id,
                allocated=pick.allocated,
                actual=None,
                projected=None,
                residual=None,
                z=None,
                multiplier=0.0,
                boost=boost,
                factor=factor,
                score=0.0,
                note=note or "no valid value",
            )

        actual = pool.actual[scored_id]
        projected = pool.projected[scored_id]
        z = pool.z[scored_id]
        multiplier = percentile_rank(z, pool.zs)

        return ScoredPick(
            category_id=cat.id,
            player_id=pick.player_id,
            scored_player_id=scored_id,
            allocated=pick.allocated,
            actual=actual,
            projected=projected,
            residual=actual - projected,
            z=z,
            multiplier=multiplier,
            boost=boost,
            factor=factor,
            score=round(pick.allocated * multiplier * boost * factor, 4),
            note=note,
        )

    def _resolve_player(self, pick: Pick) -> tuple[int | None, float, str]:
        """Starter if he played, else the backup at a discount.

        The discount is the point: checking the injury report stays a skill
        rather than becoming a free hedge.
        """
        starter = self._boxes.get(pick.player_id)
        if starter is not None and starter.played:
            return pick.player_id, 1.0, ""
        if pick.backup_player_id is None:
            return None, 1.0, "starter did not play, no backup"
        backup = self._boxes.get(pick.backup_player_id)
        if backup is not None and backup.played:
            return pick.backup_player_id, BACKUP_FACTOR, "backup used"
        return None, 1.0, "neither starter nor backup played"


def validate(lineup: Lineup) -> str:
    """Return an empty string when the lineup is legal, else the reason it is
    void. Over the cap is void outright -- no partial credit."""
    picks = lineup.picks
    if not picks:
        return "no picks"
    if len(picks) > MAX_PICKS:
        return f"more than {MAX_PICKS} picks"

    seen_categories: set[str] = set()
    starters: set[int] = set()
    for p in picks:
        try:
            cat = catalog.get(p.category_id)
        except KeyError as exc:
            return str(exc)
        if not cat.enabled:
            return f"category {cat.id} is not enabled"
        if cat.id in seen_categories:
            return f"category {cat.id} picked twice"
        seen_categories.add(cat.id)

        if p.allocated < MIN_ALLOCATION:
            return f"{cat.id} allocation below minimum of {MIN_ALLOCATION:g}"
        if p.player_id in starters:
            return f"player {p.player_id} fills more than one category"
        starters.add(p.player_id)
        if p.backup_player_id == p.player_id:
            return f"{cat.id} backup is the starter"

    total = sum(p.allocated for p in picks)
    if total > BUDGET:
        return f"over budget: {total:g} > {BUDGET:g}"
    return ""
