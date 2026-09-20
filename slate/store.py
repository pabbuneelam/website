"""Where created cards live.

Two implementations behind one protocol, and both are needed: the in-memory one
runs tests with no credentials, the Firestore one is what a deployed instance
uses. A card is the game's durable artifact -- it survives its creator's roster
and can later be waived, claimed and signed by other teams -- so this is not an
optional convenience.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import threading
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Protocol

from .models import (
    TRADE_ACCEPTED,
    Card,
    League,
    Membership,
    Rating,
    Trade,
    UserProfile,
)


def _to_dict(card: Card) -> dict:
    d = asdict(card)
    d["ratings"] = [asdict(r) for r in card.ratings]
    return d


def _from_dict(raw: dict) -> Card:
    data = dict(raw)
    data["ratings"] = tuple(Rating(**r) for r in raw.get("ratings", []))
    return Card(**data)


def _normalise_code(code: str) -> str:
    """Codes are stored and compared upper-case, stripped. People type them."""
    return code.strip().upper()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    """Microseconds, because two trades resolved in the same second is the
    normal case and this is what orders an inbox."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class TradeConflict(Exception):
    """The world moved between proposing a trade and accepting it.

    Carries the sentence shown to the user, because every one of these is
    something they can act on: the trade is gone, already resolved, or a
    card in it has changed hands.
    """


def _acceptance(
    trade: Trade | None,
    recipient_uid: str,
    offered: Card | None,
    requested: Card | None,
) -> tuple[Card, Card, Trade]:
    """The three documents an accepted trade writes, or a TradeConflict.

    Pure, and shared by both stores, so the memory and Firestore paths
    cannot drift on what an accept is allowed to do. Ownership is checked
    HERE -- at accept time, inside whatever transaction the caller opened
    -- and not only at propose time, because that is the check that stops
    one card being traded away twice.
    """
    if trade is None:
        raise TradeConflict("that trade no longer exists")
    if trade.recipient_uid != recipient_uid:
        raise TradeConflict("only the recipient can accept this trade")
    if not trade.pending:
        raise TradeConflict(f"this trade was already {trade.status}")
    if offered is None or requested is None:
        raise TradeConflict("a card in this trade no longer exists")
    if offered.uid != trade.proposer_uid:
        raise TradeConflict(
            "the offered card has changed hands since this trade was proposed"
        )
    if requested.uid != trade.recipient_uid:
        raise TradeConflict(
            "the requested card has changed hands since this trade was proposed"
        )
    return (
        replace(offered, uid=trade.recipient_uid),
        replace(requested, uid=trade.proposer_uid),
        replace(trade, status=TRADE_ACCEPTED, resolved_at=_stamp()),
    )


def _resolution(trade: Trade | None, status: str, note: str) -> Trade:
    """A pending trade closed without a swap, or a TradeConflict.

    The `pending` check is made HERE, on the copy read inside the caller's
    transaction, for the same reason `_acceptance` re-checks ownership: an
    accept can land between an endpoint reading the trade and writing to it,
    and a blind write would then mark a completed swap as rejected.
    """
    if trade is None:
        raise TradeConflict("that trade no longer exists")
    if not trade.pending:
        raise TradeConflict(f"this trade was already {trade.status}")
    return replace(trade, status=status, resolved_at=_stamp(), resolution_note=note)


class Store(Protocol):
    def save_card(self, card: Card) -> None: ...

    def card(self, card_id: str) -> Card | None: ...

    def cards(self, uid: str) -> list[Card]:
        """One user's collection, newest first."""
        ...

    def user(self, uid: str) -> UserProfile | None: ...

    def save_user(self, profile: UserProfile) -> UserProfile:
        """Upsert a profile on sign-in and return what is now stored.

        ``created_at`` is written once, on the first sign-in, and never
        rewritten -- it is the only field here that is not simply whatever
        the identity provider last said.
        """
        ...

    # --- leagues ------------------------------------------------------
    # A user belongs to exactly one league at a time, so a membership is
    # keyed by uid alone. That is the rule expressed as a data shape:
    # there is nowhere to put a second one.

    def save_league(self, league: League) -> None: ...

    def league(self, league_id: str) -> League | None: ...

    def league_by_code(self, code: str) -> League | None:
        """The league an invite code opens, or None. Case-insensitive --
        codes get typed by hand."""
        ...

    def save_membership(self, membership: Membership) -> None: ...

    def membership(self, uid: str) -> Membership | None:
        """The one league this user is in, or None."""
        ...

    def remove_membership(self, uid: str) -> None:
        """Leave. A no-op if the user is not in a league."""
        ...

    def members(self, league_id: str) -> list[Membership]:
        """Everyone in one league, oldest member first."""
        ...

    # --- trades -------------------------------------------------------
    # Card for card, between two members of one league. The interesting
    # method is the last one: accepting has to move both cards or neither.

    def save_trade(self, trade: Trade) -> None: ...

    def trade(self, trade_id: str) -> Trade | None: ...

    def trades(self, uid: str) -> list[Trade]:
        """Every trade this user is party to, either side, newest first."""
        ...

    def resolve_trade(self, trade_id: str, status: str, note: str = "") -> Trade:
        """Reject or cancel: close a trade that is still pending, atomically.

        Raises ``TradeConflict`` -- writing nothing -- if it is gone or was
        resolved first. Who may do this is the API's question; whether it is
        still possible is this one's.
        """
        ...

    def accept_trade(self, trade_id: str, recipient_uid: str) -> Trade:
        """Swap both cards and close the trade, atomically.

        Raises ``TradeConflict`` -- writing nothing -- if the trade is gone,
        already resolved, not this caller's to accept, or if either card has
        changed hands since it was proposed. A half-applied swap would give a
        card away without handing one back, so this is all or nothing.
        """
        ...


class MemoryStore:
    """Default. No credentials, no network, forgets everything on restart."""

    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}
        self._users: dict[str, UserProfile] = {}
        self._leagues: dict[str, League] = {}
        self._memberships: dict[str, Membership] = {}
        self._trades: dict[str, Trade] = {}
        # Taken by accept_trade and resolve_trade: the two operations that
        # decide on a trade's status and then write, which must not interleave.
        self._lock = threading.Lock()

    def save_card(self, card: Card) -> None:
        self._cards[card.card_id] = card

    def card(self, card_id: str) -> Card | None:
        return self._cards.get(card_id)

    def cards(self, uid: str) -> list[Card]:
        found = [c for c in self._cards.values() if c.uid == uid]
        return sorted(found, key=lambda c: c.date, reverse=True)

    def user(self, uid: str) -> UserProfile | None:
        return self._users.get(uid)

    def save_user(self, profile: UserProfile) -> UserProfile:
        existing = self._users.get(profile.uid)
        stored = replace(profile, created_at=existing.created_at if existing else _now())
        self._users[profile.uid] = stored
        return stored

    def save_league(self, league: League) -> None:
        self._leagues[league.league_id] = league

    def league(self, league_id: str) -> League | None:
        return self._leagues.get(league_id)

    def league_by_code(self, code: str) -> League | None:
        wanted = _normalise_code(code)
        return next((lg for lg in self._leagues.values() if lg.code == wanted), None)

    def save_membership(self, membership: Membership) -> None:
        self._memberships[membership.uid] = membership

    def membership(self, uid: str) -> Membership | None:
        return self._memberships.get(uid)

    def remove_membership(self, uid: str) -> None:
        self._memberships.pop(uid, None)

    def members(self, league_id: str) -> list[Membership]:
        found = [m for m in self._memberships.values() if m.league_id == league_id]
        return sorted(found, key=lambda m: (m.joined_at, m.uid))

    def save_trade(self, trade: Trade) -> None:
        self._trades[trade.trade_id] = trade

    def trade(self, trade_id: str) -> Trade | None:
        return self._trades.get(trade_id)

    def trades(self, uid: str) -> list[Trade]:
        found = [
            t
            for t in self._trades.values()
            if uid in (t.proposer_uid, t.recipient_uid)
        ]
        return sorted(found, key=lambda t: t.created_at, reverse=True)

    def resolve_trade(self, trade_id: str, status: str, note: str = "") -> Trade:
        with self._lock:
            done = _resolution(self._trades.get(trade_id), status, note)
            self._trades[trade_id] = done
            return done

    def accept_trade(self, trade_id: str, recipient_uid: str) -> Trade:
        # Firestore gets a transaction; here the equivalent is a lock plus
        # the ordering below -- every check and every replacement object is
        # computed first, and the three dict writes that follow cannot fail
        # or be interleaved. Nothing is mutated on the raising path.
        with self._lock:
            trade = self._trades.get(trade_id)
            offered = requested = None
            if trade is not None:
                offered = self._cards.get(trade.offered_card_id)
                requested = self._cards.get(trade.requested_card_id)
            new_offered, new_requested, done = _acceptance(
                trade, recipient_uid, offered, requested
            )
            self._cards[new_offered.card_id] = new_offered
            self._cards[new_requested.card_id] = new_requested
            self._trades[done.trade_id] = done
            return done


class FirestoreStore:
    """Firebase project questly-7f3a2.

        cards/{card_id}        one created player, id "{date}:{uid}"
        users/{uid}            one signed-in person
        leagues/{league_id}    one league, carrying its invite code
        memberships/{uid}      which league that user is in -- at most one,
                               which is why the uid is the document id
        trades/{trade_id}      one card offered for one card

    Auth is a service account, so security rules are bypassed -- this is server
    side. Rules only start mattering when a browser reads these directly.
    """

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        project = project or os.environ["SLATE_FIREBASE_PROJECT"]
        # Serverless hosts have no filesystem to park a key file on, so accept
        # the service account inline as well as via the usual
        # GOOGLE_APPLICATION_CREDENTIALS path.
        #
        # Prefer the base64 form. A raw service-account JSON carries a PEM
        # private key full of newlines, quotes and slashes, and shipping that
        # through a platform environment variable is a reliable way to break
        # things in ways that are hard to see.
        raw = _credentials_json()
        if raw:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_info(
                json.loads(raw)
            )
            self._db = firestore.Client(project=project, credentials=credentials)
        else:
            self._db = firestore.Client(project=project)

    def save_card(self, card: Card) -> None:
        self._db.collection("cards").document(card.card_id).set(_to_dict(card))

    def card(self, card_id: str) -> Card | None:
        doc = self._db.collection("cards").document(card_id).get()
        return _from_dict(doc.to_dict()) if doc.exists else None

    def cards(self, uid: str) -> list[Card]:
        from google.cloud.firestore_v1.base_query import FieldFilter
        docs = self._db.collection("cards").where(filter=FieldFilter("uid", "==", uid)).stream()
        found = [_from_dict(d.to_dict()) for d in docs]
        return sorted(found, key=lambda c: c.date, reverse=True)

    def user(self, uid: str) -> UserProfile | None:
        doc = self._db.collection("users").document(uid).get()
        return UserProfile(**doc.to_dict()) if doc.exists else None

    def save_user(self, profile: UserProfile) -> UserProfile:
        # Read first so created_at survives every later sign-in. One extra
        # read per sign-in, not per request -- the frontend calls this once
        # when the auth state changes.
        existing = self.user(profile.uid)
        stored = replace(profile, created_at=existing.created_at if existing else _now())
        self._db.collection("users").document(profile.uid).set(asdict(stored))
        return stored

    def save_league(self, league: League) -> None:
        self._db.collection("leagues").document(league.league_id).set(asdict(league))

    def league(self, league_id: str) -> League | None:
        doc = self._db.collection("leagues").document(league_id).get()
        return League(**doc.to_dict()) if doc.exists else None

    def league_by_code(self, code: str) -> League | None:
        from google.cloud.firestore_v1.base_query import FieldFilter
        # Single-field equality needs no composite index, same as cards().
        docs = (
            self._db.collection("leagues")
            .where(filter=FieldFilter("code", "==", _normalise_code(code)))
            .limit(1)
            .stream()
        )
        return next((League(**d.to_dict()) for d in docs), None)

    def save_membership(self, membership: Membership) -> None:
        self._db.collection("memberships").document(membership.uid).set(
            asdict(membership)
        )

    def membership(self, uid: str) -> Membership | None:
        doc = self._db.collection("memberships").document(uid).get()
        return Membership(**doc.to_dict()) if doc.exists else None

    def remove_membership(self, uid: str) -> None:
        # The only delete in this file. A membership is a join, not an
        # artifact -- leaving a league has to actually remove it, or the next
        # join would find the user still in the old one.
        self._db.collection("memberships").document(uid).delete()

    def members(self, league_id: str) -> list[Membership]:
        from google.cloud.firestore_v1.base_query import FieldFilter
        docs = (
            self._db.collection("memberships")
            .where(filter=FieldFilter("league_id", "==", league_id))
            .stream()
        )
        found = [Membership(**d.to_dict()) for d in docs]
        return sorted(found, key=lambda m: (m.joined_at, m.uid))

    def save_trade(self, trade: Trade) -> None:
        self._db.collection("trades").document(trade.trade_id).set(asdict(trade))

    def trade(self, trade_id: str) -> Trade | None:
        doc = self._db.collection("trades").document(trade_id).get()
        return Trade(**doc.to_dict()) if doc.exists else None

    def trades(self, uid: str) -> list[Trade]:
        from google.cloud.firestore_v1.base_query import FieldFilter
        # Two single-field equality queries rather than one OR, so this needs
        # no composite index -- same reason cards() and league_by_code() are
        # shaped the way they are. A user is on at most one side of a trade,
        # so the two result sets cannot overlap.
        collection = self._db.collection("trades")
        found = [
            Trade(**d.to_dict())
            for field in ("proposer_uid", "recipient_uid")
            for d in collection.where(filter=FieldFilter(field, "==", uid)).stream()
        ]
        return sorted(found, key=lambda t: t.created_at, reverse=True)

    def resolve_trade(self, trade_id: str, status: str, note: str = "") -> Trade:
        from google.cloud import firestore

        trade_ref = self._db.collection("trades").document(trade_id)

        @firestore.transactional
        def close(transaction) -> Trade:
            snapshot = trade_ref.get(transaction=transaction)
            trade = Trade(**snapshot.to_dict()) if snapshot.exists else None
            done = _resolution(trade, status, note)
            transaction.set(trade_ref, asdict(done))
            return done

        return close(self._db.transaction())

    def accept_trade(self, trade_id: str, recipient_uid: str) -> Trade:
        """Three documents, one transaction: both cards and the trade itself.

        Firestore transactions require every read before every write, which
        is exactly the shape this needs anyway -- read the trade and both
        cards, decide, then write all three or none of them. The transaction
        retries if any of the three changed underneath it, so two recipients
        racing to accept trades for the same card cannot both win.
        """
        from google.cloud import firestore

        trade_ref = self._db.collection("trades").document(trade_id)
        cards = self._db.collection("cards")

        @firestore.transactional
        def swap(transaction) -> Trade:
            snapshot = trade_ref.get(transaction=transaction)
            trade = Trade(**snapshot.to_dict()) if snapshot.exists else None
            if trade is None:
                raise TradeConflict("that trade no longer exists")

            offered_ref = cards.document(trade.offered_card_id)
            requested_ref = cards.document(trade.requested_card_id)
            offered_doc = offered_ref.get(transaction=transaction)
            requested_doc = requested_ref.get(transaction=transaction)

            new_offered, new_requested, done = _acceptance(
                trade,
                recipient_uid,
                _from_dict(offered_doc.to_dict()) if offered_doc.exists else None,
                _from_dict(requested_doc.to_dict()) if requested_doc.exists else None,
            )
            transaction.set(offered_ref, _to_dict(new_offered))
            transaction.set(requested_ref, _to_dict(new_requested))
            transaction.set(trade_ref, asdict(done))
            return done

        return swap(self._db.transaction())


def _credentials_json() -> str | None:
    """Service-account JSON from the environment, base64 preferred."""
    encoded = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_B64")
    if encoded:
        try:
            return base64.b64decode(encoded, validate=True).decode()
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise RuntimeError(
                "GOOGLE_APPLICATION_CREDENTIALS_B64 is not valid base64"
            ) from exc
    return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")


def default_store() -> Store:
    """Firestore when a project is configured, memory otherwise.

    Deliberately silent about which it picked at import time -- /health reports
    it instead, so a misconfigured deploy is visible over HTTP.
    """
    if os.environ.get("SLATE_FIREBASE_PROJECT"):
        return FirestoreStore()
    return MemoryStore()
