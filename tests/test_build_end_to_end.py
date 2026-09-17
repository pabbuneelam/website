"""The whole path over the committed fixture."""
from __future__ import annotations

import pytest

from slate import attributes
from slate.__main__ import best_available
from slate.card import build_card
from slate.score import NightRater


@pytest.fixture
def rater(night):
    return NightRater(night.boxscores)


def test_fixture_loads(night):
    assert night.date == "2025-11-14"
    assert len(night.games) == 3
    assert len(night.boxscores) == 30


def test_every_player_has_a_real_salary(night):
    """Contract is half the game; a slate with missing salaries is unplayable."""
    assert all(b.salary and b.salary > 0 for b in night.boxscores)


def test_the_fixture_carries_the_advanced_fields_every_attribute_needs(night):
    played = [b for b in night.boxscores if b.played]
    assert all(b.rebound_chances_total is not None for b in played)
    assert all(b.defended_at_rim_fga is not None for b in played)
    assert all(b.contested_share is not None for b in played)


def test_the_fixture_still_contains_its_deliberate_edge_cases(night):
    assert any(not b.played for b in night.boxscores), "need a DNP"
    assert any(0 < b.fg3a < 4 for b in night.boxscores), "need a sub-guardrail shooter"
    assert any(0 < b.minutes < 15 for b in night.boxscores), "need a short stint"


def test_every_attribute_produces_a_non_empty_pool(rater):
    for slot in attributes.SLOTS:
        assert rater.pool(slot).value, f"{slot} pool is empty"


def test_a_full_build_produces_a_valid_card(night, rater):
    card = build_card(best_available(rater), rater, night.date)
    assert not card.void
    assert len(card.ratings) == 6
    assert 0 <= card.ovr <= 99
    assert card.contract > 0


def test_a_minimum_salary_player_can_win_an_attribute(night, rater):
    """The value premise: cheap players must be able to post elite nights, or
    there is no point hunting for them."""
    cheapest = min(b.salary for b in night.boxscores)
    winners = []
    for slot in attributes.SLOTS:
        pool = rater.pool(slot)
        top = max(pool.value, key=pool.value.get)
        winners.append(rater.boxes[top].salary)
    assert cheapest in winners


def test_golden_card_does_not_drift(night, rater):
    """Pins the fixture to a known card so a refactor cannot quietly move the
    numbers. If this changes, it should be because you meant it to."""
    card = build_card(best_available(rater), rater, night.date)
    assert card.ovr == 96
    assert card.contract == 27_833_333
    assert [r.rating for r in card.ratings] == [95, 97, 97, 97, 97, 93]
