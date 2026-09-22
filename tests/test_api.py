from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from slate import attributes
from slate.api import app, current_user
from slate.auth import AuthUser
from slate.store import MemoryStore

client = TestClient(app)
DATE = "2025-11-14"


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    """Pin the store rather than reading it from the ambient environment --
    these assertions must not flip depending on whether credentials happen to
    be exported in the shell running the tests."""
    from slate import api

    monkeypatch.setattr(api, "store", MemoryStore())


@pytest.fixture(autouse=True)
def signed_in():
    """Every test runs as a verified user by default.

    Substituting the dependency rather than minting real tokens keeps the
    suite offline -- verifying a genuine ID token means fetching Google's
    signing keys.
    """
    as_user("tester")
    yield
    app.dependency_overrides.clear()


def as_user(uid, name=None):
    user = AuthUser(uid=uid, display_name=name or uid, email=f"{uid}@example.com",
                    photo_url=f"https://example.com/{uid}.png")
    app.dependency_overrides[current_user] = lambda: user
    return user


def payload(player_ids=None):
    slate = client.get(f"/slates/{DATE}").json()
    ids = player_ids or [p["player_id"] for p in slate["players"]][:6]
    return {
        "selections": [{"slot": s, "player_id": pid}
                       for s, pid in zip(attributes.SLOTS, ids)],
    }


def test_attributes_expose_the_six_slots_and_their_guardrails():
    body = client.get("/attributes").json()
    assert [a["slot"] for a in body] == list(attributes.SLOTS)
    assert all(a["guardrail"] for a in body)


def test_slate_shows_salaries_but_never_stats():
    """Salary is public and is half the strategy. Performance is the thing
    being predicted, so it must not leak before lock."""
    body = client.get(f"/slates/{DATE}").json()
    player = body["players"][0]
    assert player["salary"] > 0
    leaked = {"pts", "reb", "fg3m", "minutes", "rebound_chances_total"}
    assert not leaked & set(player)


def test_unknown_date_is_a_404():
    assert client.get("/slates/1999-01-01").status_code == 404


def test_submitting_a_build_returns_a_card():
    response = client.post(f"/slates/{DATE}/builds", json=payload())
    assert response.status_code == 200
    card = response.json()
    assert 0 <= card["ovr"] <= 99
    assert card["contract"] > 0
    assert len(card["ratings"]) == 6
    assert card["void"] is False


def test_the_card_explains_every_rating():
    card = client.post(f"/slates/{DATE}/builds", json=payload()).json()
    for r in card["ratings"]:
        assert r["player_name"]
        assert r["label"]
        assert 0 <= r["rating"] <= 99


def test_reusing_one_player_for_two_attributes_is_rejected():
    body = payload()
    body["selections"][1]["player_id"] = body["selections"][0]["player_id"]
    response = client.post(f"/slates/{DATE}/builds", json=body)
    assert response.status_code == 422
    assert "more than one attribute" in response.json()["detail"]


def test_a_short_build_is_rejected_by_the_schema():
    body = payload()
    body["selections"] = body["selections"][:4]
    assert client.post(f"/slates/{DATE}/builds", json=body).status_code == 422


def test_a_card_lands_in_the_signed_in_users_collection():
    as_user("uid-vrishin", "Vrishin")
    client.post(f"/slates/{DATE}/builds", json=payload())
    collection = client.get("/cards/me").json()
    assert len(collection) == 1
    assert collection[0]["uid"] == "uid-vrishin"


def test_a_card_records_a_readable_creator_name_alongside_the_uid():
    """The uid is the key; the name is what the UI can actually show."""
    as_user("uid-vrishin", "Vrishin")
    card = client.post(f"/slates/{DATE}/builds", json=payload()).json()
    assert card["uid"] == "uid-vrishin"
    assert card["creator_name"] == "Vrishin"
    assert card["card_id"] == f"{DATE}:uid-vrishin"


def test_the_body_cannot_choose_whose_card_this_is():
    """The regression this whole feature exists for: identity comes from the
    token, so a creator field in the body is ignored, not honoured."""
    as_user("uid-vrishin", "Vrishin")
    body = payload() | {"creator": "someone-else", "uid": "someone-else"}
    card = client.post(f"/slates/{DATE}/builds", json=body).json()
    assert card["uid"] == "uid-vrishin"


def test_collections_do_not_leak_between_users():
    as_user("uid-vrishin")
    client.post(f"/slates/{DATE}/builds", json=payload())
    as_user("uid-pabb")
    client.post(f"/slates/{DATE}/builds", json=payload())
    assert len(client.get("/cards/me").json()) == 1
    assert len(client.get("/cards/uid-vrishin").json()) == 1
    assert client.get("/cards/nobody").json() == []


def test_two_users_with_the_same_display_name_are_not_the_same_creator():
    """Two people typing "demo" used to share one card id."""
    as_user("uid-one", "demo")
    first = client.post(f"/slates/{DATE}/builds", json=payload()).json()
    as_user("uid-two", "demo")
    second = client.post(f"/slates/{DATE}/builds", json=payload()).json()
    assert first["card_id"] != second["card_id"]
    assert len(client.get("/cards/me").json()) == 1


# -- who is asking ------------------------------------------------------

def test_building_without_a_token_is_rejected():
    app.dependency_overrides.clear()
    assert client.post(f"/slates/{DATE}/builds", json=payload()).status_code == 401


def test_a_malformed_authorization_header_is_rejected():
    app.dependency_overrides.clear()
    response = client.post(f"/slates/{DATE}/builds", json=payload(),
                           headers={"Authorization": "Basic abc123"})
    assert response.status_code == 401
    assert "Bearer" in response.json()["detail"]


def test_ones_own_collection_needs_a_token():
    app.dependency_overrides.clear()
    assert client.get("/cards/me").status_code == 401


def test_reading_a_slate_stays_public():
    """Nothing about tonight's games is private, and forcing a sign-in just to
    look would be a worse product."""
    app.dependency_overrides.clear()
    assert client.get(f"/slates/{DATE}").status_code == 200
    assert client.get("/attributes").status_code == 200


# -- profiles -----------------------------------------------------------

def test_first_sign_in_stores_a_profile():
    as_user("uid-new", "New Person")
    profile = client.post("/users/me").json()
    assert profile["uid"] == "uid-new"
    assert profile["display_name"] == "New Person"
    assert profile["email"] == "uid-new@example.com"
    assert profile["photo_url"]
    assert profile["created_at"]


def test_the_stored_profile_never_holds_the_email():
    """users/{uid} is world-readable to signed-in users, so the email rides on
    the caller's own token and never lands in the document."""
    from slate import api

    as_user("uid-new", "New Person")
    client.post("/users/me")
    assert api.get_store().user("uid-new").email is None
    assert client.get("/users/me").json()["email"] == "uid-new@example.com"


def test_signing_in_again_refreshes_the_profile_but_keeps_created_at():
    as_user("uid-new", "Old Name")
    first = client.post("/users/me").json()
    as_user("uid-new", "New Name")
    second = client.post("/users/me").json()
    assert second["display_name"] == "New Name"
    assert second["created_at"] == first["created_at"]


def test_reading_a_profile_before_it_is_stored_falls_back_to_the_token():
    as_user("uid-fresh", "Fresh")
    assert client.get("/users/me").json()["display_name"] == "Fresh"


def test_health_reports_which_store_is_live():
    body = client.get("/health").json()
    assert body["store"] == "MemoryStore"
    assert body["durable"] is False


def test_building_works_on_a_stateless_host_even_with_no_durable_store(monkeypatch):
    """Rating a night is pure computation, so the game stays playable and
    demoable without persistence."""
    from slate import api

    monkeypatch.setattr(api, "ON_SERVERLESS", True)
    as_user("uid-ghost")
    response = client.post(f"/slates/{DATE}/builds", json=payload())
    assert response.status_code == 200
    assert response.json()["ovr"] > 0


def test_the_collection_refuses_rather_than_lying_about_what_it_saved(monkeypatch):
    """A card written to memory on a stateless host is invisible to the next
    request. Returning an empty collection would look like data loss."""
    from slate import api

    monkeypatch.setattr(api, "ON_SERVERLESS", True)
    assert client.get("/cards/uid-ghost").status_code == 503


def test_importing_the_app_never_constructs_a_store(tmp_path):
    """Regression: a Firestore client built at module scope runs credential
    discovery while the platform is merely importing the module to find the
    ASGI app. That hangs the build in a sandbox and costs a network round trip
    on every cold start. Run in a subprocess -- the module is already imported
    in this process, so nothing else can observe it.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c",
         "import slate.api as a; print('STORE', a.store)"],
        env={"SLATE_FIREBASE_PROJECT": "questly-7f3a2",
             "PATH": os.environ.get("PATH", ""),
             "HOME": os.environ.get("HOME", "")},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "STORE None" in result.stdout


def test_get_store_is_built_once_and_reused(monkeypatch):
    from slate import api

    monkeypatch.setattr(api, "store", None)
    monkeypatch.delenv("SLATE_FIREBASE_PROJECT", raising=False)
    assert api.get_store() is api.get_store()

