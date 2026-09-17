"""Rating scale and pool construction."""
from __future__ import annotations

import pytest

from slate import attributes
from slate.score import MAX_RATING, NightRater
from tests.conftest import box


def shooters(lines):
    return [box(player_id=i + 1, fg3m=m, fg3a=a) for i, (m, a) in enumerate(lines)]


def test_the_best_night_rates_highest_and_the_worst_lowest():
    rater = NightRater(shooters([(8, 12), (4, 10), (1, 9)]))
    ratings = [rater.rate("OUTSIDE", pid)[0] for pid in (1, 2, 3)]
    assert ratings == sorted(ratings, reverse=True)


def test_ratings_sit_on_a_player_card_scale():
    rater = NightRater(shooters([(8, 12), (4, 10), (1, 9), (6, 11)]))
    for pid in (1, 2, 3, 4):
        assert 0 <= rater.rate("OUTSIDE", pid)[0] <= MAX_RATING


def test_a_player_is_counted_in_his_own_pool():
    """Self-inclusion is deliberate -- it keeps ratings honest on a two-game
    slate, at the cost of a perfect night capping just under 99."""
    rater = NightRater(shooters([(m, 12) for m in range(1, 11)]))
    best = rater.rate("OUTSIDE", 10)[0]
    assert best == round(0.95 * MAX_RATING)


def test_players_who_fail_the_guardrail_leave_the_pool_entirely():
    """A one-shot night must not drag everyone else's percentile around."""
    rater = NightRater(shooters([(8, 12), (1, 1), (4, 10)]))
    assert set(rater.pool("OUTSIDE").value) == {1, 3}


def test_a_player_not_on_tonights_slate_rates_zero_with_a_reason():
    rater = NightRater(shooters([(5, 10)]))
    rating, value, percentile, note = rater.rate("OUTSIDE", 999)
    assert (rating, value, percentile) == (0, None, 0.0)
    assert note == "not on tonight's slate"


def test_a_scratch_rates_zero():
    rater = NightRater([box(player_id=1, minutes=0.0, fg3m=9, fg3a=10)])
    assert rater.rate("OUTSIDE", 1)[0] == 0
    assert rater.rate("OUTSIDE", 1)[3] == "did not play"


def test_a_guardrail_failure_names_the_guardrail():
    rater = NightRater(shooters([(8, 12), (1, 2)]))
    assert attributes.get("OUTSIDE").guardrail in rater.rate("OUTSIDE", 2)[3]


def test_pools_are_computed_once_and_reused():
    rater = NightRater(shooters([(5, 10)]))
    assert rater.pool("OUTSIDE") is rater.pool("OUTSIDE")


def test_an_empty_slate_does_not_crash():
    rater = NightRater([])
    assert rater.rate("OUTSIDE", 1)[0] == 0
    assert rater.pool("REBOUNDING").values == []
