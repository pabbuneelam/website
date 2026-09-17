"""The six attribute metrics.

Each one answers the same question -- how much did he produce over what an
average player produces on the same opportunities, and how hard was it -- so
the tests check that shape as much as the arithmetic.
"""
from __future__ import annotations

import pytest

from slate import attributes as A
from tests.conftest import box


# -- outside shooting ---------------------------------------------------

def test_outside_shooting_is_points_added_over_a_league_average_shooter():
    b = box(fg3m=5, fg3a=10)
    assert A.outside_shooting(b) == pytest.approx(3 * 5 - 3 * A.LEAGUE_3P * 10)


def test_a_league_average_night_lands_near_zero():
    b = box(fg3m=4, fg3a=11)  # 36.4%, essentially league average
    assert abs(A.outside_shooting(b)) < 0.5


def test_efficiency_matters_not_just_makes():
    """8-for-12 and 8-for-20 are the same number of makes and must not rate
    the same."""
    assert A.outside_shooting(box(fg3m=8, fg3a=12)) > A.outside_shooting(box(fg3m=8, fg3a=20))


def test_volume_matters_not_just_efficiency():
    """Both shot 50%. The one who did it eight times was harder."""
    assert A.outside_shooting(box(fg3m=4, fg3a=8)) > A.outside_shooting(box(fg3m=2, fg3a=4))


def test_contested_threes_beat_open_ones_on_an_identical_line():
    """The headline example from the design doc, as a test."""
    hard = box(fg3m=8, fg3a=14, contested_fga=12, uncontested_fga=4)
    easy = box(fg3m=8, fg3a=14, contested_fga=2, uncontested_fga=14)
    assert A.outside_shooting(hard) > A.outside_shooting(easy)


def test_outside_shooting_guardrail_rejects_a_three_for_three_night():
    """Small samples cannot buy an elite shooting rating."""
    assert A.outside_shooting(box(fg3m=3, fg3a=3)) is None
    assert A.outside_shooting(box(fg3m=1, fg3a=4)) is not None


def test_difficulty_is_neutral_rather_than_zero_without_tracking_data():
    """Below GOAT tier the contested split is absent. The attribute must
    degrade to plain efficiency, not collapse."""
    b = box(fg3m=5, fg3a=10)
    assert b.contested_share is None
    assert A._difficulty(b) == 1.0
    assert A.outside_shooting(b) is not None


# -- finishing ----------------------------------------------------------

def test_finishing_needs_rim_data_which_only_exists_above_the_free_tier():
    assert A.finishing(box(fgm=8, fga=12)) is None
    assert A.finishing(box(rim_fgm=6, rim_fga=8)) is not None


def test_finishing_guardrail():
    assert A.finishing(box(rim_fgm=2, rim_fga=2)) is None


# -- playmaking ---------------------------------------------------------

def test_playmaking_counts_the_passes_that_are_not_assists():
    plain = A.playmaking(box(ast=8, tov=2))
    with_extras = A.playmaking(box(ast=8, tov=2, secondary_assists=4, free_throw_assists=2))
    assert with_extras > plain
    assert with_extras == pytest.approx(8 + 0.5 * 4 + 0.5 * 2 - 2)


def test_playmaking_is_punished_by_turnovers():
    assert A.playmaking(box(ast=10, tov=6)) < A.playmaking(box(ast=10, tov=1))


def test_playmaking_guardrail_is_minutes():
    assert A.playmaking(box(ast=4, tov=0, minutes=9.0)) is None


# -- rebounding ---------------------------------------------------------

def test_rebounding_measures_conversion_not_volume():
    """Twelve boards from thirty chances is worse than eight from twelve.
    This is the clearest case for the whole design."""
    volume = box(orb=4, drb=8, rebound_chances_total=30)
    efficient = box(orb=2, drb=6, rebound_chances_total=12)
    assert efficient.reb < volume.reb
    assert A.rebounding(efficient) > A.rebounding(volume)


def test_rebounding_needs_chance_data():
    assert A.rebounding(box(orb=5, drb=10)) is None


def test_rebounding_guardrail():
    assert A.rebounding(box(orb=1, drb=1, rebound_chances_total=3)) is None


# -- defense ------------------------------------------------------------

def test_perimeter_defense_rewards_holding_your_man_below_league_average():
    locked = box(matchup_minutes=20.0, matchup_fga=12, matchup_fgm=3)
    cooked = box(matchup_minutes=20.0, matchup_fga=12, matchup_fgm=9)
    assert A.perimeter_defense(locked) > 0 > A.perimeter_defense(cooked)


def test_deflections_add_to_perimeter_defense():
    quiet = box(matchup_minutes=20.0, matchup_fga=10, matchup_fgm=4)
    active = box(matchup_minutes=20.0, matchup_fga=10, matchup_fgm=4, deflections=5)
    assert A.perimeter_defense(active) > A.perimeter_defense(quiet)


def test_perimeter_defense_guardrail_is_matchup_minutes():
    assert A.perimeter_defense(box(matchup_minutes=4.0, matchup_fga=3, matchup_fgm=0)) is None


def test_interior_defense_is_rim_protection():
    wall = box(defended_at_rim_fga=10, defended_at_rim_fgm=3, blk=4)
    turnstile = box(defended_at_rim_fga=10, defended_at_rim_fgm=9, blk=0)
    assert A.interior_defense(wall) > 0 > A.interior_defense(turnstile)


def test_interior_defense_guardrail():
    assert A.interior_defense(box(defended_at_rim_fga=2, defended_at_rim_fgm=0)) is None


# -- catalog ------------------------------------------------------------

def test_there_are_exactly_six_slots_and_they_are_unique():
    assert len(A.SLOTS) == 6
    assert len(set(A.SLOTS)) == 6


def test_every_attribute_has_a_guardrail_and_a_stated_data_requirement():
    for a in A.ATTRIBUTES:
        assert a.guardrail
        assert a.requires in {"boxscore", "pbp", "advanced"}


def test_unknown_slot_raises():
    with pytest.raises(KeyError):
        A.get("DUNKING")
