"""Store contract. MemoryStore runs everywhere; FirestoreStore runs only when
credentials are present, against the real project."""
from __future__ import annotations

import os

import pytest

from slate.models import Card, Rating, UserProfile
from slate.store import MemoryStore, _from_dict, _to_dict

CARD = Card(
    card_id="2025-11-14:uid-vrishin",
    uid="uid-vrishin",
    creator_name="Vrishin",
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


def test_a_collection_is_scoped_to_its_uid(store):
    store.save_card(CARD)
    other = Card(card_id="2025-11-14:uid-pabb", uid="uid-pabb", creator_name="Pabb",
                 date="2025-11-14", ovr=88, contract=10_000_000, ratings=())
    store.save_card(other)
    assert store.cards("uid-vrishin") == [CARD]
    assert store.cards("uid-pabb") == [other]


def test_a_collection_is_scoped_by_uid_not_by_display_name(store):
    """The bug this replaced: two people named "demo" shared a collection."""
    store.save_card(CARD)
    impostor = Card(card_id="2025-11-14:uid-other", uid="uid-other",
                    creator_name="Vrishin", date="2025-11-14",
                    ovr=70, contract=1, ratings=())
    store.save_card(impostor)
    assert store.cards("uid-vrishin") == [CARD]


def test_a_collection_is_newest_first(store):
    older = Card(card_id="2025-11-10:uid-v", uid="uid-v", date="2025-11-10",
                 ovr=80, contract=1, ratings=())
    newer = Card(card_id="2025-11-20:uid-v", uid="uid-v", date="2025-11-20",
                 ovr=90, contract=1, ratings=())
    store.save_card(older)
    store.save_card(newer)
    assert [c.date for c in store.cards("uid-v")] == ["2025-11-20", "2025-11-10"]


def test_rebuilding_the_same_night_replaces_rather_than_duplicates(store):
    """One build per user per night, so the id is a natural key."""
    store.save_card(CARD)
    revised = Card(card_id=CARD.card_id, uid="uid-vrishin", date="2025-11-14",
                   ovr=99, contract=5_000_000, ratings=())
    store.save_card(revised)
    assert store.cards("uid-vrishin") == [revised]


def test_an_empty_collection_is_empty_not_an_error(store):
    assert store.cards("nobody") == []


@pytest.mark.skipif(
    not os.environ.get("SLATE_FIREBASE_PROJECT"),
    reason="set SLATE_FIREBASE_PROJECT and GOOGLE_APPLICATION_CREDENTIALS to run",
)
def test_firestore_satisfies_the_same_contract():
    from slate.store import FirestoreStore

    store = FirestoreStore()
    probe = Card(card_id="_test:contract", uid="_test", creator_name="Test",
                 date="2025-11-14", ovr=93, contract=26_000_000, ratings=CARD.ratings)
    store.save_card(probe)
    assert store.card("_test:contract") == probe
    assert probe in store.cards("_test")


# -- profiles -----------------------------------------------------------

def test_a_profile_survives_a_round_trip(store):
    stored = store.save_user(UserProfile(uid="uid-v", display_name="Vrishin",
                                         email="v@example.com", photo_url="https://x/p.png"))
    assert store.user("uid-v") == stored
    assert stored.email == "v@example.com"


def test_created_at_is_stamped_on_first_sign_in(store):
    stored = store.save_user(UserProfile(uid="uid-v", display_name="Vrishin"))
    assert stored.created_at


def test_created_at_survives_every_later_sign_in(store):
    """Everything else is whatever Google last said; this one field is ours."""
    first = store.save_user(UserProfile(uid="uid-v", display_name="Old"))
    second = store.save_user(UserProfile(uid="uid-v", display_name="New"))
    assert second.created_at == first.created_at
    assert second.display_name == "New"


def test_an_unknown_user_is_none_not_an_error(store):
    assert store.user("nobody") is None


def test_base64_credentials_are_decoded(monkeypatch):
    """A raw service-account JSON carries a PEM key full of newlines and
    quotes; base64 is what survives a platform environment variable intact."""
    import base64

    from slate.store import _credentials_json

    payload = '{"type":"service_account","private_key":"-----BEGIN PRIVATE KEY-----\\nabc\\n"}'
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS_B64",
                       base64.b64encode(payload.encode()).decode())
    assert _credentials_json() == payload


def test_base64_takes_precedence_over_the_raw_form(monkeypatch):
    import base64

    from slate.store import _credentials_json

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", '{"from":"raw"}')
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS_B64",
                       base64.b64encode(b'{"from":"b64"}').decode())
    assert _credentials_json() == '{"from":"b64"}'


def test_malformed_base64_fails_loudly(monkeypatch):
    from slate.store import _credentials_json

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS_B64", "not!valid!base64")
    with pytest.raises(RuntimeError, match="not valid base64"):
        _credentials_json()


def test_no_credentials_in_the_environment_is_none(monkeypatch):
    from slate.store import _credentials_json

    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS_B64", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", raising=False)
    assert _credentials_json() is None
