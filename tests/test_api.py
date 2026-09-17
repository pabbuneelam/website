from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from slate import attributes
from slate.api import app
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


def payload(creator="tester", player_ids=None):
    slate = client.get(f"/slates/{DATE}").json()
    ids = player_ids or [p["player_id"] for p in slate["players"]][:6]
    return {
        "creator": creator,
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


def test_a_card_lands_in_the_creators_collection():
    client.post(f"/slates/{DATE}/builds", json=payload("vrishin"))
    collection = client.get("/cards/vrishin").json()
    assert len(collection) == 1
    assert collection[0]["creator"] == "vrishin"


def test_collections_do_not_leak_between_creators():
    client.post(f"/slates/{DATE}/builds", json=payload("vrishin"))
    client.post(f"/slates/{DATE}/builds", json=payload("pabb"))
    assert len(client.get("/cards/vrishin").json()) == 1
    assert client.get("/cards/nobody").json() == []


def test_health_reports_which_store_is_live():
    body = client.get("/health").json()
    assert body["store"] == "MemoryStore"
    assert body["durable"] is False


def test_serverless_without_a_durable_store_refuses_rather_than_misbehaving(monkeypatch):
    """On a stateless host a card written by one instance is invisible to the
    next, so an in-memory store silently loses them. Fail loudly."""
    from slate import api

    monkeypatch.setattr(api, "ON_SERVERLESS", True)
    response = client.post(f"/slates/{DATE}/builds", json=payload("ghost"))
    assert response.status_code == 503
    assert "durable store" in response.json()["detail"]
    assert client.get("/cards/ghost").status_code == 503


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
