"""Leagues: invite codes, one-league-at-a-time, and membership listing.

A user belongs to exactly one league at a time, so the interesting cases are
all about refusing rather than doing: a bad code, a second join, a leave that
had nothing to leave.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from slate.api import app, current_user
from slate.auth import AuthUser
from slate.leagues import ALPHABET, CODE_LENGTH, new_code, unique_code
from slate.models import League, Membership
from slate.store import MemoryStore

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    from slate import api

    monkeypatch.setattr(api, "store", MemoryStore())


@pytest.fixture(autouse=True)
def signed_in():
    as_user("uid-vrishin", "Vrishin")
    yield
    app.dependency_overrides.clear()


def as_user(uid, name=None):
    user = AuthUser(uid=uid, display_name=name or uid, email=f"{uid}@example.com")
    app.dependency_overrides[current_user] = lambda: user
    return user


def create(name="The Association"):
    response = client.post("/leagues", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- codes

def test_a_code_avoids_the_characters_people_mistype():
    """0/O and 1/I/L are the pairs that get read wrong off a screenshot, and
    a wrong code is a 404 that names no culprit."""
    assert not set("01OIL") & set(ALPHABET)
    assert set(new_code()) <= set(ALPHABET)
    assert len(new_code()) == CODE_LENGTH


def test_codes_do_not_repeat_across_many_generations():
    codes = {new_code() for _ in range(2000)}
    assert len(codes) > 1990  # 31**6 of them; a few collisions would be a bug


def test_generation_asks_the_store_and_retries_until_the_code_is_free():
    seen = []

    def taken(code):
        seen.append(code)
        return len(seen) < 3  # the first two are "already in use"

    code = unique_code(taken)
    assert len(seen) == 3 and seen[-1] == code


def test_generation_gives_up_loudly_rather_than_returning_a_duplicate():
    with pytest.raises(RuntimeError, match="unused invite code"):
        unique_code(lambda code: True)


def test_two_leagues_never_share_a_code():
    first = create("One")["league"]["code"]
    as_user("uid-pabb", "Pabb")
    second = create("Two")["league"]["code"]
    assert first != second


# ---------------------------------------------------------------- create

def test_creating_a_league_joins_it_and_hands_back_the_invite_code():
    body = create()
    assert body["league"]["name"] == "The Association"
    assert body["league"]["owner_uid"] == "uid-vrishin"
    assert len(body["league"]["code"]) == CODE_LENGTH
    assert [m["uid"] for m in body["members"]] == ["uid-vrishin"]


def test_league_endpoints_need_a_signed_in_caller():
    app.dependency_overrides.clear()
    assert client.post("/leagues", json={"name": "x"}).status_code == 401
    assert client.post("/leagues/join", json={"code": "ABC234"}).status_code == 401
    assert client.get("/leagues/me").status_code == 401
    assert client.post("/leagues/leave").status_code == 401


# ------------------------------------------------------------------ join

def test_joining_with_a_bad_code_is_a_404_not_a_500():
    response = client.post("/leagues/join", json={"code": "ZZZZZZ"})
    assert response.status_code == 404
    assert "ZZZZZZ" in response.json()["detail"]


def test_a_code_is_matched_case_insensitively_and_untrimmed():
    """It arrives pasted out of a group chat, not typed into a form field."""
    code = create()["league"]["code"]
    as_user("uid-pabb", "Pabb")
    body = client.post("/leagues/join", json={"code": f"  {code.lower()} "})
    assert body.status_code == 200
    assert body.json()["league"]["code"] == code


def test_joining_puts_you_on_the_roster_with_everyone_else():
    code = create()["league"]["code"]
    as_user("uid-pabb", "Pabb")
    client.post("/leagues/join", json={"code": code})
    body = client.get("/leagues/me").json()
    assert [m["display_name"] for m in body["members"]] == ["Vrishin", "Pabb"]


def test_joining_while_already_in_a_league_fails_instead_of_switching():
    """The whole point of one-league-at-a-time: a silent switch would strand
    whatever the old league knew about this user."""
    create("First")
    as_user("uid-pabb", "Pabb")
    other = create("Second")["league"]["code"]

    as_user("uid-vrishin", "Vrishin")
    response = client.post("/leagues/join", json={"code": other})
    assert response.status_code == 409
    assert "First" in response.json()["detail"]
    # and the original membership is untouched
    assert client.get("/leagues/me").json()["league"]["name"] == "First"


def test_creating_a_second_league_is_refused_the_same_way():
    create("First")
    response = client.post("/leagues", json={"name": "Second"})
    assert response.status_code == 409


def test_a_blank_league_name_is_rejected_by_validation():
    assert client.post("/leagues", json={"name": ""}).status_code == 422


# -------------------------------------------------------------- read/leave

def test_not_being_in_a_league_is_a_null_league_not_an_error():
    body = client.get("/leagues/me")
    assert body.status_code == 200
    assert body.json() == {"league": None, "members": []}


def test_leaving_frees_you_to_join_another_league():
    create("First")
    as_user("uid-pabb", "Pabb")
    other = create("Second")["league"]["code"]

    as_user("uid-vrishin", "Vrishin")
    assert client.post("/leagues/leave").status_code == 200
    assert client.get("/leagues/me").json()["league"] is None
    assert client.post("/leagues/join", json={"code": other}).status_code == 200


def test_leaving_when_you_are_not_in_a_league_says_so():
    response = client.post("/leagues/leave")
    assert response.status_code == 409


def test_a_membership_whose_league_vanished_reads_as_no_league():
    """Rather than 500-ing a user who can do nothing about it."""
    from slate import api

    api.get_store().save_membership(Membership(uid="uid-vrishin", league_id="gone"))
    assert client.get("/leagues/me").json()["league"] is None


# ------------------------------------------------------------------ store

@pytest.fixture(params=[MemoryStore], ids=["memory"])
def store(request):
    return request.param()


LEAGUE = League(league_id="lg1", name="The Association", code="ABC234",
                owner_uid="uid-vrishin", created_at="2025-11-14T00:00:00+00:00")


def test_a_league_is_readable_by_id_and_by_code(store):
    store.save_league(LEAGUE)
    assert store.league("lg1") == LEAGUE
    assert store.league_by_code("abc234") == LEAGUE
    assert store.league_by_code("NOPE99") is None
    assert store.league("nope") is None


def test_membership_is_keyed_by_uid_so_a_second_one_replaces_the_first(store):
    store.save_membership(Membership("uid-vrishin", "lg1", "Vrishin", "2025-11-14T00:00:00+00:00"))
    store.save_membership(Membership("uid-vrishin", "lg2", "Vrishin", "2025-11-15T00:00:00+00:00"))
    assert store.membership("uid-vrishin").league_id == "lg2"


def test_members_are_listed_per_league_oldest_first(store):
    store.save_membership(Membership("uid-pabb", "lg1", "Pabb", "2025-11-15T00:00:00+00:00"))
    store.save_membership(Membership("uid-vrishin", "lg1", "Vrishin", "2025-11-14T00:00:00+00:00"))
    store.save_membership(Membership("uid-other", "lg2", "Other", "2025-11-14T00:00:00+00:00"))
    assert [m.uid for m in store.members("lg1")] == ["uid-vrishin", "uid-pabb"]
    assert [m.uid for m in store.members("lg2")] == ["uid-other"]


def test_removing_a_membership_is_a_no_op_when_there_is_none(store):
    store.remove_membership("uid-nobody")
    assert store.membership("uid-nobody") is None
