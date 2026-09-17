from __future__ import annotations

from fastapi.testclient import TestClient

from slate.api import app
from slate.rules import BUDGET

client = TestClient(app)
DATE = "2025-11-14"


def valid_payload(entrant="tester"):
    slate = client.get(f"/slates/{DATE}").json()
    ids = [p["player_id"] for p in slate["players"]]
    return {
        "entrant": entrant,
        "picks": [
            {"category_id": "PTS", "player_id": ids[0], "allocated": 300.0,
             "backup_player_id": ids[20]},
            {"category_id": "REB", "player_id": ids[1], "allocated": 300.0},
            {"category_id": "AST_TO", "player_id": ids[2], "allocated": 400.0},
        ],
    }


def test_categories_expose_the_tier_and_the_data_each_one_needs():
    body = client.get("/categories").json()
    by_id = {c["id"]: c for c in body}
    assert by_id["PTS"]["enabled"] is True
    assert by_id["CORNER3"]["requires"] == "pbp"
    assert by_id["CORNER3"]["enabled"] is False
    assert by_id["TS_PCT"]["guardrail"] == "min 8 FGA"


def test_slate_lists_players_but_never_their_stats():
    body = client.get(f"/slates/{DATE}").json()
    assert body["budget"] == BUDGET
    assert len(body["players"]) == 30
    leaked = {"pts", "reb", "minutes", "plus_minus"}
    assert not leaked & set(body["players"][0]), "drafting is supposed to be blind"


def test_unknown_date_is_a_404():
    assert client.get("/slates/1999-01-01").status_code == 404


def test_submit_then_resolve():
    assert client.post(f"/slates/{DATE}/lineups", json=valid_payload()).status_code == 200
    body = client.post(f"/slates/{DATE}/resolve").json()
    assert body["date"] == DATE
    me = [r for r in body["results"] if r["entrant"] == "tester"][0]
    assert me["void"] is False
    assert me["total"] > 0
    assert len(me["picks"]) == 3


def test_results_come_back_ranked():
    for name in ("alpha", "beta", "gamma"):
        client.post(f"/slates/{DATE}/lineups", json=valid_payload(name))
    totals = [r["total"] for r in client.post(f"/slates/{DATE}/resolve").json()["results"]]
    assert totals == sorted(totals, reverse=True)


def test_an_over_budget_lineup_is_rejected_at_submit_not_at_resolve():
    payload = valid_payload("greedy")
    payload["picks"][0]["allocated"] = BUDGET
    response = client.post(f"/slates/{DATE}/lineups", json=payload)
    assert response.status_code == 422
    assert "over budget" in response.json()["detail"]


def test_a_disabled_category_cannot_be_submitted():
    payload = valid_payload("sneaky")
    payload["picks"][0]["category_id"] = "CORNER3"
    response = client.post(f"/slates/{DATE}/lineups", json=payload)
    assert response.status_code == 422
    assert "not enabled" in response.json()["detail"]


def test_resolving_with_nothing_submitted_is_a_conflict():
    assert client.post("/slates/1999-01-01/resolve").status_code == 404


def test_health_reports_which_store_is_live():
    """A deploy that silently fell back to memory loses every lineup on
    restart, so it has to be visible over HTTP."""
    body = client.get("/health").json()
    assert body["store"] == "MemoryStore"
    assert body["durable"] is False


def test_resolve_reports_the_boosts_it_used():
    client.post(f"/slates/{DATE}/lineups", json=valid_payload("boostcheck"))
    body = client.post(f"/slates/{DATE}/resolve").json()
    assert body["boosts"]["PTS"] == 1.0
    assert body["boosts"]["TS_PCT"] == 1.4  # seed still standing


def test_seeds_still_stand_after_a_single_night():
    """One night is not 20, so nothing should have tuned yet."""
    from slate import catalog
    client.post(f"/slates/{DATE}/lineups", json=valid_payload("once"))
    boosts = client.post(f"/slates/{DATE}/resolve").json()["boosts"]
    assert all(boosts[c.id] == c.seed_boost for c in catalog.enabled())


def test_serverless_without_a_durable_store_refuses_rather_than_misbehaving(monkeypatch):
    """On a stateless host a submit and its resolve can hit different
    instances, so an in-memory store silently drops lineups. Fail loudly."""
    from slate import api

    monkeypatch.setattr(api, "ON_SERVERLESS", True)
    response = client.post(f"/slates/{DATE}/lineups", json=valid_payload("ghost"))
    assert response.status_code == 503
    assert "durable store" in response.json()["detail"]
    assert client.post(f"/slates/{DATE}/resolve").status_code == 503


def test_local_runs_are_unaffected_by_that_guard():
    assert client.post(f"/slates/{DATE}/lineups", json=valid_payload("local")).status_code == 200
