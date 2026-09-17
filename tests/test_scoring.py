"""Lineup validation, backups, and the full residual -> score path."""
from __future__ import annotations

import pytest

from slate.models import Lineup, Pick
from slate.project import BaselineProjector, GameContext, Projection
from slate.rules import BACKUP_FACTOR, BUDGET, MAX_PICKS
from slate.score import NightScorer, validate
from tests.conftest import box


class FlatProjector:
    """Projects the same thing for everyone, so tests control the residuals."""

    def __init__(self, mean=10.0, dispersion=2.0):
        self.mean, self.dispersion = mean, dispersion

    def project(self, player_id, category_id, ctx) -> Projection:
        return Projection(mean=self.mean, dispersion=self.dispersion)


def scorer(boxes, projector=None):
    return NightScorer(boxes, projector or FlatProjector(), "2025-11-14")


def pick(category_id="PTS", player_id=1, allocated=100.0, backup=None):
    return Pick(category_id, player_id, allocated, backup)


def lineup(*picks, entrant="a"):
    return Lineup(entrant=entrant, picks=tuple(picks))


# -- validation ---------------------------------------------------------

def test_over_budget_voids_the_whole_lineup_with_no_partial_credit():
    lu = lineup(
        pick("PTS", 1, BUDGET * 0.7),
        pick("REB", 2, BUDGET * 0.7),
    )
    result = scorer([box(player_id=1, pts=30), box(player_id=2, drb=10)]).score_lineup(lu)
    assert result.void
    assert result.total == 0.0
    assert "over budget" in result.void_reason


def test_exactly_on_budget_is_legal():
    assert validate(lineup(pick("PTS", 1, BUDGET))) == ""


def test_a_player_cannot_fill_two_categories():
    problem = validate(lineup(pick("PTS", 7, 100.0), pick("REB", 7, 100.0)))
    assert "more than one category" in problem


def test_a_category_cannot_be_picked_twice():
    problem = validate(lineup(pick("PTS", 1, 100.0), pick("PTS", 2, 100.0)))
    assert "picked twice" in problem


def test_disabled_location_categories_are_rejected():
    """CORNER3 is declared but needs play-by-play, so it must not be draftable
    until the data source can serve it."""
    assert "not enabled" in validate(lineup(pick("CORNER3", 1, 100.0)))


def test_allocation_below_the_minimum_is_rejected():
    assert "below minimum" in validate(lineup(pick("PTS", 1, 1.0)))


def test_too_many_picks_is_rejected():
    picks = [pick("PTS", 1, 50.0)] * (MAX_PICKS + 1)
    assert "more than" in validate(lineup(*picks))


def test_backup_cannot_be_the_starter():
    assert "backup is the starter" in validate(lineup(pick("PTS", 1, 100.0, backup=1)))


def test_empty_lineup_is_void():
    assert validate(lineup()) == "no picks"


# -- backups ------------------------------------------------------------

def test_backup_scores_at_a_discount_when_the_starter_sits():
    boxes = [
        box(player_id=1, minutes=0.0),            # scratched
        box(player_id=2, pts=30),                 # backup, played
        box(player_id=3, pts=10),
    ]
    result = scorer(boxes).score_lineup(lineup(pick("PTS", 1, 100.0, backup=2)))
    scored = result.picks[0]
    assert scored.scored_player_id == 2
    assert scored.factor == BACKUP_FACTOR
    assert scored.note == "backup used"
    # Top of a two-man pool. A player is counted in his own pool, so midrank
    # caps at (n - 0.5)/n = 0.75 here, never a flat 1.0.
    assert scored.multiplier == pytest.approx(0.75)
    assert scored.score == pytest.approx(100.0 * 0.75 * 1.0 * BACKUP_FACTOR)


def test_the_discount_is_real_so_hedging_is_not_free():
    boxes = [box(player_id=1, pts=30), box(player_id=2, pts=30), box(player_id=3, pts=10)]
    starter_played = scorer(boxes).score_lineup(lineup(pick("PTS", 1, 100.0, backup=2)))

    boxes_scratched = [box(player_id=1, minutes=0.0)] + boxes[1:]
    fell_through = scorer(boxes_scratched).score_lineup(lineup(pick("PTS", 1, 100.0, backup=2)))

    assert fell_through.picks[0].score < starter_played.picks[0].score


def test_no_backup_and_a_scratch_scores_zero():
    result = scorer([box(player_id=1, minutes=0.0), box(player_id=2, pts=20)]).score_lineup(
        lineup(pick("PTS", 1, 100.0))
    )
    assert result.picks[0].score == 0.0
    assert result.picks[0].note == "starter did not play, no backup"


def test_neither_starter_nor_backup_played_scores_zero():
    boxes = [box(player_id=1, minutes=0.0), box(player_id=2, minutes=0.0), box(player_id=3, pts=9)]
    result = scorer(boxes).score_lineup(lineup(pick("PTS", 1, 100.0, backup=2)))
    assert result.picks[0].score == 0.0
    assert result.picks[0].note == "neither starter nor backup played"


# -- the residual path --------------------------------------------------

def test_a_guardrail_failure_scores_zero_and_leaves_the_pool():
    """The 1-for-1 shooter is not merely last in the shooting category, he is
    absent from it -- otherwise he would drag everyone else's percentile up."""
    boxes = [
        box(player_id=1, pts=3, fgm=1, fga=1, fg3m=1, fg3a=1),  # under 8 FGA
        box(player_id=2, pts=25, fga=18, fta=4),
        box(player_id=3, pts=18, fga=16, fta=2),
    ]
    s = scorer(boxes, FlatProjector(mean=0.5, dispersion=0.1))
    assert 1 not in s.pool("TS_PCT").actual
    result = s.score_lineup(lineup(pick("TS_PCT", 1, 100.0)))
    assert result.picks[0].score == 0.0
    assert result.picks[0].note == "no valid value"


def test_beating_your_own_projection_beats_the_bigger_raw_number():
    """The whole design: a star hitting his number loses to a role player who
    blows past his."""
    boxes = [box(player_id=1, pts=30), box(player_id=2, pts=12)]

    class PerPlayer:
        def project(self, player_id, category_id, ctx):
            return Projection(mean=30.0 if player_id == 1 else 4.0, dispersion=3.0)

    s = scorer(boxes, PerPlayer())
    star = s.score_lineup(lineup(pick("PTS", 1, 100.0))).picks[0]
    role = s.score_lineup(lineup(pick("PTS", 2, 100.0))).picks[0]
    assert role.score > star.score
    assert star.residual == pytest.approx(0.0)


def test_no_history_falls_back_to_the_field():
    """A player the projector knows nothing about is measured against the pool
    rather than crashing or scoring zero."""

    class Blind:
        def project(self, player_id, category_id, ctx):
            return None

    boxes = [box(player_id=1, pts=30), box(player_id=2, pts=10), box(player_id=3, pts=20)]
    result = scorer(boxes, Blind()).score_lineup(lineup(pick("PTS", 1, 100.0)))
    # Highest scorer in a three-man pool -> (2 + 0.5)/3
    assert result.picks[0].multiplier == pytest.approx(5 / 6)
    assert result.picks[0].projected == pytest.approx(20.0)  # the pool mean
    assert result.picks[0].score > 0


def test_boost_multiplies_the_score():
    boxes = [box(player_id=1, pts=30), box(player_id=2, pts=10)]
    s = scorer(boxes)
    plain = s.score_lineup(lineup(pick("PTS", 1, 100.0))).picks[0]
    boosted = s.score_lineup(lineup(pick("PTS", 1, 100.0)), boosts={"PTS": 2.0}).picks[0]
    assert boosted.score == pytest.approx(plain.score * 2.0)


def test_multiplier_never_exceeds_one_however_wild_the_night():
    boxes = [box(player_id=1, pts=81), box(player_id=2, pts=2)]
    s = scorer(boxes, FlatProjector(mean=1.0, dispersion=0.01))
    scored = s.score_lineup(lineup(pick("PTS", 1, 100.0))).picks[0]
    assert scored.multiplier <= 1.0
    assert scored.score <= 100.0 * 1.0 * 1.0


def test_a_player_is_counted_in_his_own_pool():
    """Self-inclusion is deliberate: it keeps the multiplier honest on thin
    slates, at the cost of a perfect night capping just under 1.0."""
    boxes = [box(player_id=i, pts=i) for i in range(1, 11)]
    best = scorer(boxes).score_lineup(lineup(pick("PTS", 10, 100.0))).picks[0]
    assert best.multiplier == pytest.approx(0.95)
