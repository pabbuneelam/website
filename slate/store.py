"""Where created cards live.

Two implementations behind one protocol, and both are needed: the in-memory one
runs tests with no credentials, the Firestore one is what a deployed instance
uses. A card is the game's durable artifact -- it survives its creator's roster
and can later be waived, claimed and signed by other teams -- so this is not an
optional convenience.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import asdict
from typing import Protocol

from .models import Card, Rating


def _to_dict(card: Card) -> dict:
    d = asdict(card)
    d["ratings"] = [asdict(r) for r in card.ratings]
    return d


def _from_dict(raw: dict) -> Card:
    data = dict(raw)
    data["ratings"] = tuple(Rating(**r) for r in raw.get("ratings", []))
    return Card(**data)


class Store(Protocol):
    def save_card(self, card: Card) -> None: ...

    def card(self, card_id: str) -> Card | None: ...

    def cards(self, creator: str) -> list[Card]:
        """One creator's collection, newest first."""
        ...


class MemoryStore:
    """Default. No credentials, no network, forgets everything on restart."""

    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}

    def save_card(self, card: Card) -> None:
        self._cards[card.card_id] = card

    def card(self, card_id: str) -> Card | None:
        return self._cards.get(card_id)

    def cards(self, creator: str) -> list[Card]:
        found = [c for c in self._cards.values() if c.creator == creator]
        return sorted(found, key=lambda c: c.date, reverse=True)


class FirestoreStore:
    """Firebase project questly-7f3a2.

        cards/{card_id}    one created player

    Auth is a service account, so security rules are bypassed -- this is server
    side. Rules only start mattering when a browser reads these directly.
    """

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        project = project or os.environ["SLATE_FIREBASE_PROJECT"]
        # Serverless hosts have no filesystem to park a key file on, so accept
        # the service-account JSON inline as well as the usual
        # GOOGLE_APPLICATION_CREDENTIALS path.
        raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
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

    def cards(self, creator: str) -> list[Card]:
        docs = self._db.collection("cards").where("creator", "==", creator).stream()
        found = [_from_dict(d.to_dict()) for d in docs]
        return sorted(found, key=lambda c: c.date, reverse=True)


def default_store() -> Store:
    """Firestore when a project is configured, memory otherwise.

    Deliberately silent about which it picked at import time -- /health reports
    it instead, so a misconfigured deploy is visible over HTTP.
    """
    if os.environ.get("SLATE_FIREBASE_PROJECT"):
        return FirestoreStore()
    return MemoryStore()
