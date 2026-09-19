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
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Protocol

from .models import Card, Rating, UserProfile


def _to_dict(card: Card) -> dict:
    d = asdict(card)
    d["ratings"] = [asdict(r) for r in card.ratings]
    return d


def _from_dict(raw: dict) -> Card:
    data = dict(raw)
    data["ratings"] = tuple(Rating(**r) for r in raw.get("ratings", []))
    return Card(**data)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


class MemoryStore:
    """Default. No credentials, no network, forgets everything on restart."""

    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}
        self._users: dict[str, UserProfile] = {}

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


class FirestoreStore:
    """Firebase project questly-7f3a2.

        cards/{card_id}    one created player, id "{date}:{uid}"
        users/{uid}        one signed-in person

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
        docs = self._db.collection("cards").where("uid", "==", uid).stream()
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
