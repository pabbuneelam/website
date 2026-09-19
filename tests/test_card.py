"""Assembling six selections into a created player."""
from __future__ import annotations

import pytest

from slate import attributes
from slate.card import build_card, card_id, validate
from slate.models import Build, Selection
from slate.score import NightRater
from tests.conftest import box

SALARIES = [55_000_000, 45_000_000, 30_000_000, 15_000_000, 8_000_000, 3_000_000]


def full_selections(player_ids=None):
    ids = player_ids or list(range(1, 7))
    return tuple(Selection(slot, pid) for slot, pid in zip(attributes.SLOTS, ids))


def build(**kw):
    return Build(uid=kw.get("uid", "uid-v"), display_name=kw.get("display_name", "V"),
                 selections=kw.get("selections", full_selections()))


def roster():
    """Six players, one comfortably qualified in every attribute."""
    return [
        box(player_id=i + 1, player_name=f"P{i + 1}", salary=SALARIES[i],
            fg3m=5, fg3a=10, rim_fgm=5, rim_fga=8, ast=7, tov=2,
            orb=2, drb=6, rebound_chances_total=12,
            matchup_minutes=20.0, matchup_fga=10, matchup_fgm=4, deflections=2,
            defended_at_rim_fga=6, defended_at_rim_fgm=2, blk=2,
            contested_fga=6, uncontested_fga=6)
        for i in range(6)
    ]


# -- validation ---------------------------------------------------------

def test_a_legal_build_passes():
    assert validate(build()) == ""


def test_all_six_slots_must_be_filled():
    short = Build(uid="uid-v", selections=full_selections()[:5])
    assert "exactly 6 selections" in validate(short)


def test_one_player_cannot_supply_two_qualities():
    """Otherwise the single best night on the slate fills the whole card."""
    selections = full_selections([1, 1, 3, 4, 5, 6])
    assert "more than one attribute" in validate(Build(uid="uid-v", selections=selections))


def test_a_slot_cannot_be_filled_twice():
    selections = tuple(
        Selection(s, i + 1) for i, s in enumerate(
            [attributes.SLOTS[0], attributes.SLOTS[0]] + list(attributes.SLOTS[2:])
        )
    )
    assert "filled twice" in validate(Build(uid="uid-v", selections=selections))


def test_unknown_slot_is_rejected():
    selections = (Selection("DUNKING", 1),) + full_selections()[1:]
    assert "unknown attribute slot" in validate(Build(uid="uid-v", selections=selections))


def test_a_void_build_still_produces_a_card_that_says_why():
    card = build_card(Build(uid="uid-v", selections=full_selections()[:3]), NightRater([]), "2025-11-14")
    assert card.void
    assert card.ovr == 0
    assert card.void_reason


# -- the card -----------------------------------------------------------

def test_contract_is_the_average_of_the_six_real_salaries():
    """The mechanic straight out of the design doc."""
    card = build_card(build(), NightRater(roster()), "2025-11-14")
    assert card.contract == round(sum(SALARIES) / 6)
    assert card.contract == 26_000_000


def test_ovr_is_the_mean_of_the_six_attribute_ratings():
    card = build_card(build(), NightRater(roster()), "2025-11-14")
    assert card.ovr == round(sum(r.rating for r in card.ratings) / 6)


def test_ratings_are_bounded_to_a_player_card_scale():
    card = build_card(build(), NightRater(roster()), "2025-11-14")
    assert all(0 <= r.rating <= 99 for r in card.ratings)
    assert 0 <= card.ovr <= 99


def test_a_card_records_the_real_performances_behind_it():
    """A card has to be explainable -- which player, what he did, what he cost."""
    card = build_card(build(), NightRater(roster()), "2025-11-14")
    for r in card.ratings:
        assert r.player_name
        assert r.salary in SALARIES
        assert r.label


def test_value_per_million_is_the_moneyball_number():
    card = build_card(build(), NightRater(roster()), "2025-11-14")
    assert card.value_per_million == pytest.approx(card.ovr / (card.contract / 1_000_000))


def test_a_cheaper_card_with_the_same_ovr_is_better_value():
    cheap = [
        box(player_id=i + 1, player_name=f"C{i + 1}", salary=2_000_000,
            fg3m=5, fg3a=10, rim_fgm=5, rim_fga=8, ast=7, tov=2,
            orb=2, drb=6, rebound_chances_total=12,
            matchup_minutes=20.0, matchup_fga=10, matchup_fgm=4,
            defended_at_rim_fga=6, defended_at_rim_fgm=2)
        for i in range(6)
    ]
    expensive = build_card(build(), NightRater(roster()), "2025-11-14")
    bargain = build_card(build(), NightRater(cheap), "2025-11-14")
    assert bargain.value_per_million > expensive.value_per_million


def test_a_player_who_did_not_qualify_scores_zero_and_says_so():
    players = roster()
    players[0] = box(player_id=1, player_name="P1", salary=SALARIES[0], fg3m=1, fg3a=1)
    card = build_card(build(), NightRater(players), "2025-11-14")
    outside = card.ratings[0]
    assert outside.rating == 0
    assert "did not qualify" in outside.note


def test_a_scratched_player_scores_zero():
    players = roster()
    players[2] = box(player_id=3, player_name="P3", salary=SALARIES[2], minutes=0.0)
    card = build_card(build(), NightRater(players), "2025-11-14")
    assert card.ratings[2].rating == 0
    assert card.ratings[2].note == "did not play"


def test_missing_salary_is_excluded_from_the_average_not_treated_as_free():
    """Otherwise absent contract data would masquerade as a bargain."""
    players = roster()
    players[0] = box(player_id=1, player_name="P1", salary=None,
                     fg3m=5, fg3a=10, rim_fgm=5, rim_fga=8, ast=7, tov=2,
                     orb=2, drb=6, rebound_chances_total=12,
                     matchup_minutes=20.0, matchup_fga=10, matchup_fgm=4,
                     defended_at_rim_fga=6, defended_at_rim_fgm=2)
    card = build_card(build(), NightRater(players), "2025-11-14")
    assert card.contract == round(sum(SALARIES[1:]) / 5)


def test_card_id_is_stable_and_scoped_to_uid_and_night():
    assert card_id("uid-v", "2025-11-14") == card_id("uid-v", "2025-11-14")
    assert card_id("uid-v", "2025-11-14") != card_id("uid-pabb", "2025-11-14")
    assert card_id("uid-v", "2025-11-14") != card_id("uid-v", "2025-11-15")


def test_card_id_is_keyed_on_the_uid_not_the_display_name():
    """Two people who both call themselves "demo" must not collide."""
    one = build_card(build(uid="uid-one", display_name="demo"), NightRater(roster()), "2025-11-14")
    two = build_card(build(uid="uid-two", display_name="demo"), NightRater(roster()), "2025-11-14")
    assert one.card_id != two.card_id
    assert one.creator_name == two.creator_name == "demo"


def test_a_card_carries_a_readable_creator_name():
    """The uid keys it; the name is the only part a reader can use."""
    card = build_card(build(uid="uid-v", display_name="Vrishin"), NightRater(roster()), "2025-11-14")
    assert card.uid == "uid-v"
    assert card.creator_name == "Vrishin"
