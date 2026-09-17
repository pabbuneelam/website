"""Formulas, checked against numbers worked out by hand."""
from __future__ import annotations

import pytest

from slate.metrics import METRICS
from tests.conftest import box


def test_true_shooting_matches_hand_calculation():
    # 28 pts on 18 FGA and 6 FTA -> 28 / (2 * (18 + 2.64)) = 0.6783...
    b = box(pts=28, fga=18, fta=6)
    assert METRICS["ts_pct"](b) == pytest.approx(28 / (2 * (18 + 0.44 * 6)))


def test_true_shooting_guardrail_rejects_a_one_for_one_night():
    """The whole point of the guardrail: perfect efficiency on one shot is not
    a shooting performance."""
    assert METRICS["ts_pct"](box(pts=3, fgm=1, fga=1, fg3m=1, fg3a=1)) is None


def test_true_shooting_accepts_exactly_the_minimum():
    assert METRICS["ts_pct"](box(pts=10, fga=8)) is not None


def test_plus_minus_guardrail_rejects_a_short_stint():
    assert METRICS["plus_minus"](box(minutes=11.0, plus_minus=21)) is None
    assert METRICS["plus_minus"](box(minutes=15.0, plus_minus=21)) == 21.0


def test_game_score_matches_hand_calculation():
    b = box(pts=30, fgm=10, fga=20, ftm=6, fta=8, orb=2, drb=6,
            ast=5, stl=2, blk=1, tov=3, pf=2)
    expected = (
        30 + 0.4 * 10 - 0.7 * 20 - 0.4 * (8 - 6)
        + 0.7 * 2 + 0.3 * 6 + 2 + 0.7 * 5 + 0.7 * 1 - 0.4 * 2 - 3
    )
    assert METRICS["game_score"](b) == pytest.approx(expected)


def test_turnovers_are_negated_so_higher_is_always_better():
    assert METRICS["tov_neg"](box(tov=5)) < METRICS["tov_neg"](box(tov=1))


def test_combo_metrics():
    assert METRICS["stocks"](box(stl=3, blk=2)) == 5.0
    assert METRICS["ast_to"](box(ast=9, tov=4)) == 5.0


def test_location_metrics_are_none_without_play_by_play():
    """Below the GOAT tier these fields are absent, and absence must behave
    exactly like a guardrail failure rather than scoring zero silently."""
    assert METRICS["corner3m"](box()) is None
    assert METRICS["corner3m"](box(corner3m=3)) == 3.0
