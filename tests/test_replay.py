"""End-to-end over the committed fixture, plus the golden total."""
from __future__ import annotations

import pytest

from slate import catalog
from slate.__main__ import demo_lineup
from slate.project import BaselineProjector
from slate.score import NightScorer


@pytest.fixture
def scorer(night):
    return NightScorer(
        night.boxscores, BaselineProjector(night.logs), night.date, night.games
    )


def test_fixture_loads(night):
    assert night.date == "2025-11-14"
    assert len(night.games) == 3
    assert len(night.boxscores) == 30


def test_fixture_contains_the_edge_cases_it_is_supposed_to(night):
    by_id = {b.player_id: b for b in night.boxscores}
    assert any(not b.played for b in night.boxscores), "need a DNP"
    assert any(0 < b.fga < 8 for b in night.boxscores), "need a sub-guardrail shooter"
    assert any(0 < b.minutes < 15 for b in night.boxscores), "need a short stint"
    assert any(b.player_id not in night.logs for b in night.boxscores), "need a rookie"
    rebs = [b.reb for b in night.boxscores]
    assert len(rebs) != len(set(rebs)), "need a tie to exercise midrank"


def test_every_enabled_category_produces_a_pool(scorer):
    for cat in catalog.enabled():
        pool = scorer.pool(cat.id)
        assert pool.actual, f"{cat.id} pool is empty"
        assert set(pool.z) == set(pool.actual)


def test_disabled_location_categories_have_empty_pools_on_boxscore_data(night):
    """The fixture does carry play-by-play, so these resolve -- proving the
    categories work before anyone pays for the GOAT tier."""
    scorer = NightScorer(night.boxscores, BaselineProjector(night.logs), night.date)
    assert scorer.pool("CORNER3").actual


def test_multipliers_are_bounded_across_the_whole_slate(scorer):
    for cat in catalog.enabled():
        pool = scorer.pool(cat.id)
        from slate.score import percentile_rank
        for z in pool.zs:
            assert 0.0 <= percentile_rank(z, pool.zs) <= 1.0


def test_golden_total_does_not_drift(night, scorer):
    """Pins the fixture to a known score so a refactor cannot quietly move the
    numbers. If this changes, it should be because you meant it to."""
    result = scorer.score_lineup(demo_lineup(night))
    assert not result.void
    assert result.total == pytest.approx(652.5861, abs=1e-3)
