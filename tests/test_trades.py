"""Trades: card for card, between two members of one league.

Almost every test here is about a refusal. Proposing and accepting are three
lines each; what makes a trade system correct is everything it declines to do
-- trading outside your league, trading a card you no longer own, accepting
twice, and above all handing over one card without receiving the other.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from slate.api import app, current_user
from slate.auth import AuthUser
from slate.models import Card, Membership, Trade
from slate.store import MemoryStore, TradeConflict

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    from slate import api

    monkeypatch.setattr(api, "store", MemoryStore())


@pytest.fixture(autouse=True)
def signed_in():
    as_user("uid-a", "Ada")
    yield
    app.dependency_overrides.clear()


def as_user(uid, name=None):
    user = AuthUser(uid=uid, display_name=name or uid, email=f"{uid}@example.com")
    app.dependency_overrides[current_user] = lambda: user
    return user


def store():
    from slate import api

    return api.get_store()


def card(card_id: str, uid: str, ovr: int = 90, contract: int = 20_000_000) -> Card:
    """A card owned by `uid`. The engine is not under test here, so this skips
    building one -- what matters is only who owns it."""
    made = Card(
        card_id=card_id, uid=uid, date=card_id.split(":")[0], ovr=ovr,
        contract=contract, ratings=(), creator_name=uid,
    )
    store().save_card(made)
    return made


def owner(card_id: str) -> str | None:
    found = store().card(card_id)
    return found.uid if found else None


def league_of(*uids, league_id="lg1"):
    for uid in uids:
        store().save_membership(
            Membership(uid=uid, league_id=league_id, display_name=uid, joined_at=uid)
        )


def propose(recipient="uid-b", offered="2025-11-14:uid-a", requested="2025-11-14:uid-b"):
    return client.post(
        "/trades",
        json={
            "recipient_uid": recipient,
            "offered_card_id": offered,
            "requested_card_id": requested,
        },
    )


def a_pending_trade():
    """Ada and Bo in one league, one card each, one offer on the table."""
    league_of("uid-a", "uid-b")
    card("2025-11-14:uid-a", "uid-a")
    card("2025-11-14:uid-b", "uid-b", ovr=95)
    response = propose()
    assert response.status_code == 200, response.text
    return response.json()["trade"]["trade_id"]


# ------------------------------------------------- rule 1: one league

def test_both_sides_must_be_in_the_same_league():
    league_of("uid-a", league_id="lg1")
    league_of("uid-b", league_id="lg2")
    card("2025-11-14:uid-a", "uid-a")
    card("2025-11-14:uid-b", "uid-b")

    response = propose()
    assert response.status_code == 409
    assert "your own league" in response.json()["detail"]


def test_trading_with_someone_in_no_league_is_refused():
    league_of("uid-a")
    card("2025-11-14:uid-a", "uid-a")
    card("2025-11-14:uid-b", "uid-b")
    assert propose().status_code == 409


def test_you_cannot_propose_a_trade_while_in_no_league():
    card("2025-11-14:uid-a", "uid-a")
    card("2025-11-14:uid-b", "uid-b")
    response = propose()
    assert response.status_code == 409
    assert "not in a league" in response.json()["detail"]


def test_you_cannot_trade_with_yourself():
    league_of("uid-a")
    card("2025-11-14:uid-a", "uid-a")
    card("2025-11-15:uid-a", "uid-a")
    response = propose(
        recipient="uid-a", requested="2025-11-15:uid-a"
    )
    assert response.status_code == 422


# -------------------------------------- rule 2: ownership, at propose time

def test_you_can_only_offer_a_card_you_own():
    league_of("uid-a", "uid-b")
    card("2025-11-14:uid-b", "uid-b")
    card("2025-11-13:uid-b", "uid-b")
    response = propose(offered="2025-11-13:uid-b")
    assert response.status_code == 409
    assert "you does not own" in response.json()["detail"]


def test_you_can_only_request_a_card_they_own():
    league_of("uid-a", "uid-b")
    card("2025-11-14:uid-a", "uid-a")
    card("2025-11-13:uid-c", "uid-c")
    response = propose(requested="2025-11-13:uid-c")
    assert response.status_code == 409
    assert "uid-b does not own" in response.json()["detail"]


def test_a_card_that_does_not_exist_is_a_404():
    league_of("uid-a", "uid-b")
    card("2025-11-14:uid-a", "uid-a")
    assert propose().status_code == 404


def test_a_trade_needs_two_different_cards():
    league_of("uid-a", "uid-b")
    card("2025-11-14:uid-a", "uid-a")
    response = propose(offered="2025-11-14:uid-a", requested="2025-11-14:uid-a")
    assert response.status_code == 422


# --------------------------------------------- rule 3: the swap is atomic

def test_accepting_swaps_both_cards_at_once():
    trade_id = a_pending_trade()
    as_user("uid-b", "Bo")

    body = client.post(f"/trades/{trade_id}/accept")
    assert body.status_code == 200, body.text
    assert body.json()["trade"]["status"] == "accepted"
    assert owner("2025-11-14:uid-a") == "uid-b"
    assert owner("2025-11-14:uid-b") == "uid-a"


def test_a_traded_card_keeps_its_id_and_its_creator():
    """The id encodes who built it, and a card outlives its first roster --
    so a trade moves ownership and nothing else."""
    trade_id = a_pending_trade()
    as_user("uid-b", "Bo")
    client.post(f"/trades/{trade_id}/accept")

    moved = store().card("2025-11-14:uid-a")
    assert moved.card_id == "2025-11-14:uid-a"
    assert moved.creator_name == "uid-a"
    assert moved.uid == "uid-b"


def test_a_failed_accept_moves_neither_card():
    """The worst possible bug here is a half-applied swap."""
    trade_id = a_pending_trade()
    # Ada's card leaves her hands after the offer is made.
    card("2025-11-14:uid-a", "uid-c")

    as_user("uid-b", "Bo")
    response = client.post(f"/trades/{trade_id}/accept")
    assert response.status_code == 409
    assert "changed hands" in response.json()["detail"]
    # Neither side moved: Bo did not pay for a card he never received.
    assert owner("2025-11-14:uid-a") == "uid-c"
    assert owner("2025-11-14:uid-b") == "uid-b"
    assert store().trade(trade_id).status == "pending"


def test_a_card_that_vanished_fails_the_accept_rather_than_corrupting_state():
    trade_id = a_pending_trade()
    store()._cards.pop("2025-11-14:uid-a")

    as_user("uid-b", "Bo")
    assert client.post(f"/trades/{trade_id}/accept").status_code == 409
    assert owner("2025-11-14:uid-b") == "uid-b"


# ------------------------------------- rule 2 again: ownership at accept

def test_the_same_card_cannot_be_traded_away_twice():
    """Two offers of one card to two people. Exactly one can be accepted --
    re-checking ownership at accept is what makes that true."""
    league_of("uid-a", "uid-b", "uid-c")
    card("2025-11-14:uid-a", "uid-a")
    card("2025-11-14:uid-b", "uid-b")
    card("2025-11-14:uid-c", "uid-c")

    to_b = propose("uid-b", "2025-11-14:uid-a", "2025-11-14:uid-b").json()["trade"]
    to_c = propose("uid-c", "2025-11-14:uid-a", "2025-11-14:uid-c").json()["trade"]

    as_user("uid-b", "Bo")
    assert client.post(f"/trades/{to_b['trade_id']}/accept").status_code == 200

    as_user("uid-c", "Cy")
    second = client.post(f"/trades/{to_c['trade_id']}/accept")
    assert second.status_code == 409
    assert "changed hands" in second.json()["detail"]

    # Ada's card went to exactly one person, and Cy still has his own.
    assert owner("2025-11-14:uid-a") == "uid-b"
    assert owner("2025-11-14:uid-c") == "uid-c"


# ----------------------------------------------- rule 4: who may do what

def test_only_the_recipient_can_accept():
    trade_id = a_pending_trade()
    response = client.post(f"/trades/{trade_id}/accept")  # still Ada, the proposer
    assert response.status_code == 403
    assert owner("2025-11-14:uid-b") == "uid-b"


def test_only_the_recipient_can_reject():
    trade_id = a_pending_trade()
    assert client.post(f"/trades/{trade_id}/reject").status_code == 403


def test_only_the_proposer_can_cancel():
    trade_id = a_pending_trade()
    as_user("uid-b", "Bo")
    assert client.post(f"/trades/{trade_id}/cancel").status_code == 403


def test_a_bystander_cannot_see_or_touch_a_trade():
    """404 rather than 403 -- a trade id is not something to probe for."""
    trade_id = a_pending_trade()
    as_user("uid-c", "Cy")
    for action in ("accept", "reject", "cancel"):
        assert client.post(f"/trades/{trade_id}/{action}").status_code == 404
    assert client.get("/trades").json() == {"incoming": [], "outgoing": []}


def test_the_recipient_can_reject_and_the_proposer_can_cancel():
    trade_id = a_pending_trade()
    as_user("uid-b", "Bo")
    assert client.post(f"/trades/{trade_id}/reject").json()["trade"]["status"] == "rejected"
    assert owner("2025-11-14:uid-a") == "uid-a"

    as_user("uid-a", "Ada")
    trade_id = propose().json()["trade"]["trade_id"]
    assert client.post(f"/trades/{trade_id}/cancel").json()["trade"]["status"] == "cancelled"
    assert owner("2025-11-14:uid-b") == "uid-b"


def test_trade_endpoints_need_a_signed_in_caller():
    app.dependency_overrides.clear()
    assert client.get("/trades").status_code == 401
    assert client.post("/trades", json={
        "recipient_uid": "uid-b",
        "offered_card_id": "x",
        "requested_card_id": "y",
    }).status_code == 401
    assert client.post("/trades/anything/accept").status_code == 401
    assert client.post("/trades/anything/reject").status_code == 401
    assert client.post("/trades/anything/cancel").status_code == 401


# ------------------------------------------------- rule 5: resolved is final

def test_an_accepted_trade_cannot_be_accepted_again():
    trade_id = a_pending_trade()
    as_user("uid-b", "Bo")
    assert client.post(f"/trades/{trade_id}/accept").status_code == 200

    again = client.post(f"/trades/{trade_id}/accept")
    assert again.status_code == 409
    assert "already accepted" in again.json()["detail"]
    # and the cards did not swap back
    assert owner("2025-11-14:uid-a") == "uid-b"
    assert owner("2025-11-14:uid-b") == "uid-a"


def test_a_rejected_trade_cannot_then_be_accepted():
    trade_id = a_pending_trade()
    as_user("uid-b", "Bo")
    client.post(f"/trades/{trade_id}/reject")
    assert client.post(f"/trades/{trade_id}/accept").status_code == 409
    assert owner("2025-11-14:uid-a") == "uid-a"


def test_a_cancelled_trade_cannot_then_be_accepted():
    trade_id = a_pending_trade()
    client.post(f"/trades/{trade_id}/cancel")  # Ada, the proposer
    as_user("uid-b", "Bo")
    assert client.post(f"/trades/{trade_id}/accept").status_code == 409
    assert owner("2025-11-14:uid-b") == "uid-b"


# --------------------------------------------------------- the two inboxes

def test_trades_are_split_by_side_with_both_cards_attached():
    a_pending_trade()
    mine = client.get("/trades").json()
    assert mine["incoming"] == []
    assert len(mine["outgoing"]) == 1
    view = mine["outgoing"][0]
    assert view["offered_card"]["card_id"] == "2025-11-14:uid-a"
    assert view["requested_card"]["ovr"] == 95
    assert view["trade"]["recipient_name"] == "uid-b"

    as_user("uid-b", "Bo")
    theirs = client.get("/trades").json()
    assert theirs["outgoing"] == []
    assert len(theirs["incoming"]) == 1


def test_an_inbox_with_nothing_in_it_is_two_empty_lists():
    assert client.get("/trades").json() == {"incoming": [], "outgoing": []}


# -------------------------------------------------- leaving with a trade open

def test_leaving_a_league_cancels_your_pending_trades():
    """Deliberate: a trade is an offer between leaguemates, so it does not
    survive one of them walking out. Cancelled, not deleted -- both sides can
    see what became of it."""
    trade_id = a_pending_trade()
    assert client.post("/leagues/leave").status_code == 200

    trade = store().trade(trade_id)
    assert trade.status == "cancelled"
    assert "left the league" in trade.resolution_note
    assert owner("2025-11-14:uid-b") == "uid-b"

    # and the other side cannot accept the corpse
    as_user("uid-b", "Bo")
    assert client.post(f"/trades/{trade_id}/accept").status_code == 409


def test_leaving_also_cancels_trades_proposed_to_you():
    trade_id = a_pending_trade()
    as_user("uid-b", "Bo")
    client.post("/leagues/leave")
    assert store().trade(trade_id).status == "cancelled"


def test_leaving_does_not_disturb_already_resolved_trades():
    trade_id = a_pending_trade()
    as_user("uid-b", "Bo")
    client.post(f"/trades/{trade_id}/accept")
    client.post("/leagues/leave")

    trade = store().trade(trade_id)
    assert trade.status == "accepted" and trade.resolution_note == ""


# ---------------------------------------- a traded card and a rebuild

def test_rebuilding_a_night_whose_card_you_traded_away_is_refused(night):
    """card_id is keyed on the creator and does not change in a trade, so a
    rebuild would otherwise overwrite the card in its new owner's collection."""
    from slate import api

    league_of("uid-a", "uid-b")
    card(f"{night.date}:uid-a", "uid-b")  # already traded to Bo

    selections = [
        {"slot": slot, "player_id": box.player_id}
        for slot, box in zip(api.attributes.SLOTS, night.boxscores)
    ]
    response = client.post(f"/slates/{night.date}/builds", json={"selections": selections})
    assert response.status_code == 409
    assert "traded away" in response.json()["detail"]
    assert owner(f"{night.date}:uid-a") == "uid-b"


# ------------------------------------------------------------------ store

@pytest.fixture(params=[MemoryStore], ids=["memory"])
def trade_store(request):
    return request.param()


def a_trade(trade_id="t1", created_at="2025-11-14T00:00:00+00:00", **kw) -> Trade:
    return Trade(
        trade_id=trade_id,
        league_id="lg1",
        proposer_uid="uid-a",
        recipient_uid="uid-b",
        offered_card_id="c-a",
        requested_card_id="c-b",
        created_at=created_at,
        **kw,
    )


def stocked(store_):
    store_.save_card(Card("c-a", "uid-a", "2025-11-14", 90, 1, ()))
    store_.save_card(Card("c-b", "uid-b", "2025-11-14", 95, 1, ()))
    store_.save_trade(a_trade())
    return store_


def test_a_trade_is_readable_by_id(trade_store):
    trade_store.save_trade(a_trade())
    assert trade_store.trade("t1").recipient_uid == "uid-b"
    assert trade_store.trade("nope") is None


def test_both_sides_see_the_trade_newest_first(trade_store):
    trade_store.save_trade(a_trade(trade_id="t1", created_at="2025-11-14T00:00:00+00:00"))
    trade_store.save_trade(a_trade(trade_id="t2", created_at="2025-11-15T00:00:00+00:00"))
    assert [t.trade_id for t in trade_store.trades("uid-a")] == ["t2", "t1"]
    assert [t.trade_id for t in trade_store.trades("uid-b")] == ["t2", "t1"]
    assert trade_store.trades("uid-c") == []


def test_store_accept_swaps_both_owners_and_closes_the_trade(trade_store):
    stocked(trade_store)
    done = trade_store.accept_trade("t1", "uid-b")
    assert done.status == "accepted" and done.resolved_at
    assert trade_store.card("c-a").uid == "uid-b"
    assert trade_store.card("c-b").uid == "uid-a"


def test_store_accept_refuses_a_stale_trade_and_writes_nothing(trade_store):
    stocked(trade_store)
    trade_store.save_card(Card("c-a", "uid-c", "2025-11-14", 90, 1, ()))

    with pytest.raises(TradeConflict, match="changed hands"):
        trade_store.accept_trade("t1", "uid-b")
    assert trade_store.card("c-a").uid == "uid-c"
    assert trade_store.card("c-b").uid == "uid-b"
    assert trade_store.trade("t1").status == "pending"


def test_store_accept_refuses_anyone_but_the_recipient(trade_store):
    stocked(trade_store)
    with pytest.raises(TradeConflict, match="only the recipient"):
        trade_store.accept_trade("t1", "uid-a")
    assert trade_store.card("c-a").uid == "uid-a"


def test_store_accept_refuses_a_trade_that_is_already_resolved(trade_store):
    stocked(trade_store)
    trade_store.accept_trade("t1", "uid-b")
    with pytest.raises(TradeConflict, match="already accepted"):
        trade_store.accept_trade("t1", "uid-b")
    # still one swap, not two
    assert trade_store.card("c-a").uid == "uid-b"


def test_store_accept_refuses_a_trade_that_is_gone(trade_store):
    with pytest.raises(TradeConflict, match="no longer exists"):
        trade_store.accept_trade("nope", "uid-b")


# ------------------------------- closing a trade races with accepting it
# Reject, cancel and the leave-league sweep used to read a trade, see
# `pending`, and blind-write the new status. An accept landing in between had
# already swapped the cards, and the record then said it never happened.


def test_store_resolve_closes_a_pending_trade(trade_store):
    stocked(trade_store)
    done = trade_store.resolve_trade("t1", "rejected", "changed my mind")
    assert (done.status, done.resolution_note) == ("rejected", "changed my mind")
    assert done.resolved_at
    assert trade_store.trade("t1").status == "rejected"


def test_store_resolve_never_overwrites_an_accepted_trade(trade_store):
    stocked(trade_store)
    trade_store.accept_trade("t1", "uid-b")
    with pytest.raises(TradeConflict, match="already accepted"):
        trade_store.resolve_trade("t1", "cancelled")
    assert trade_store.trade("t1").status == "accepted"


def test_store_resolve_refuses_a_trade_that_is_gone(trade_store):
    with pytest.raises(TradeConflict, match="no longer exists"):
        trade_store.resolve_trade("nope", "cancelled")


@pytest.mark.parametrize("who, action", [("uid-b", "reject"), ("uid-a", "cancel")])
def test_an_accept_that_lands_first_wins_over_a_reject_or_cancel(monkeypatch, who, action):
    trade_id = a_pending_trade()
    live = store()
    stale = live.trade(trade_id)
    live.accept_trade(trade_id, "uid-b")
    # The endpoint's own read still sees the trade as it was a moment ago.
    real_read = live.trade
    monkeypatch.setattr(live, "trade", lambda _id: stale)

    as_user(who)
    response = client.post(f"/trades/{trade_id}/{action}")

    assert response.status_code == 409, response.text
    assert real_read(trade_id).status == "accepted"
    assert owner("2025-11-14:uid-a") == "uid-b"
