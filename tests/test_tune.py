from __future__ import annotations

import pytest

from slate import catalog
from slate.rules import BOOST_MAX, BOOST_MIN
from slate.tune import BoostTuner


def nights(value: float, count: int, spread: float = 1.0):
    """`count` nights whose z-values have roughly the given spread."""
    return [[value - spread, value, value + spread] for _ in range(count)]


def test_seeds_hold_until_there_is_enough_history():
    """Cold start is the normal case at launch, and a boost tuned on three
    nights is noise dressed up as a number."""
    tuner = BoostTuner(min_nights=20)
    boosts = tuner.boosts({"PTS": nights(0.0, 3, spread=5.0)})
    assert boosts["PTS"] == catalog.get("PTS").seed_boost


def test_every_category_gets_a_boost_even_with_no_history_at_all():
    boosts = BoostTuner().boosts({})
    assert set(boosts) == {c.id for c in catalog.CATALOG}
    assert all(b == catalog.get(k).seed_boost for k, b in boosts.items())


def test_a_hard_to_predict_category_pays_more_than_a_calibrated_one():
    tuner = BoostTuner(min_nights=2)
    boosts = tuner.boosts({
        "PTS": nights(0.0, 5, spread=0.2),   # model nails it
        "STL": nights(0.0, 5, spread=3.0),   # model is lost
    })
    assert boosts["STL"] > boosts["PTS"]


def test_a_perfectly_calibrated_category_falls_to_the_floor():
    """z spread of 1 means the projector's own dispersion was right, so there
    is nothing extra to pay for."""
    tuner = BoostTuner(min_nights=2)
    boosts = tuner.boosts({"PTS": nights(0.0, 5, spread=0.0)})
    assert boosts["PTS"] == BOOST_MIN


def test_a_coin_flip_category_is_clamped_rather_than_running_away():
    """The known weakness of tuning on predictability: noise and difficulty look
    identical. The clamp stops a lottery category from owning the night."""
    tuner = BoostTuner(min_nights=2)
    boosts = tuner.boosts({"BLK": nights(0.0, 5, spread=500.0)})
    assert boosts["BLK"] == BOOST_MAX


def test_boosts_always_sit_inside_the_clamp():
    tuner = BoostTuner(min_nights=1)
    for spread in (0.0, 0.5, 1.0, 2.0, 50.0):
        boosts = tuner.boosts({"REB": nights(0.0, 3, spread=spread)})
        assert BOOST_MIN <= boosts["REB"] <= BOOST_MAX
