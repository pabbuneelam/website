"""Store contract. MemoryStore runs everywhere; FirestoreStore runs only when
credentials are present, against the real project."""
from __future__ import annotations

import os

import pytest

from slate.models import Card, Rating
from slate.store import MemoryStore, _from_dict, _to_dict

CARD = Card(
    card_id="2025-11-14:vrishin",
    creator="vrishin",
    date="2025-11-14",
    ovr=93,
    contract=26_000_000,
    ratings=(
        Rating("OUTSIDE", "Outside Shooting", 101, "Curry", 97, 12.4, 0.98, 55_000_000),
        Rating("REBOUNDING", "Rebounding", 102, "Sabonis", 79, 1.2, 0.80, 30_000_000, note=""),
    ),
)


@pytest.fixture(params=[MemoryStore], ids=["memory"])
def store(request):
    # A factory, not an instance -- each test needs its own empty store.
    return request.param()


def test_a_card_survives_a_round_trip_through_json():
    """Ratings are nested frozen dataclasses; the store has to flatten and
    rebuild them without losing the performance detail behind each number."""
    assert _from_dict(_to_dict(CARD)) == CARD


def test_saving_a_card_makes_it_readable_by_id(store):
    store.save_card(CARD)
    assert store.card(CARD.card_id) == CARD


def test_unknown_card_is_none_not_an_error(store):
    assert store.card("nope") is None


def test_a_collection_is_scoped_to_its_creator(store):
    store.save_card(CARD)
    other = Card(card_id="2025-11-14:pabb", creator="pabb", date="2025-11-14",
                 ovr=88, contract=10_000_000, ratings=())
    store.save_card(other)
    assert store.cards("vrishin") == [CARD]
    assert store.cards("pabb") == [other]


def test_a_collection_is_newest_first(store):
    older = Card(card_id="2025-11-10:v", creator="v", date="2025-11-10",
                 ovr=80, contract=1, ratings=())
    newer = Card(card_id="2025-11-20:v", creator="v", date="2025-11-20",
                 ovr=90, contract=1, ratings=())
    store.save_card(older)
    store.save_card(newer)
    assert [c.date for c in store.cards("v")] == ["2025-11-20", "2025-11-10"]


def test_rebuilding_the_same_night_replaces_rather_than_duplicates(store):
    """One build per creator per night, so the id is a natural key."""
    store.save_card(CARD)
    revised = Card(card_id=CARD.card_id, creator="vrishin", date="2025-11-14",
                   ovr=99, contract=5_000_000, ratings=())
    store.save_card(revised)
    assert store.cards("vrishin") == [revised]


def test_an_empty_collection_is_empty_not_an_error(store):
    assert store.cards("nobody") == []


@pytest.mark.skipif(
    not os.environ.get("SLATE_FIREBASE_PROJECT"),
    reason="set SLATE_FIREBASE_PROJECT and GOOGLE_APPLICATION_CREDENTIALS to run",
)
def test_firestore_satisfies_the_same_contract():
    from slate.store import FirestoreStore

    store = FirestoreStore()
    probe = Card(card_id="_test:contract", creator="_test", date="2025-11-14",
                 ovr=93, contract=26_000_000, ratings=CARD.ratings)
    store.save_card(probe)
    assert store.card("_test:contract") == probe
    assert probe in store.cards("_test")
