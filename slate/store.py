"""Where submitted lineups and nightly residuals live.

Two implementations behind one protocol, and both are needed today: the
in-memory one runs the tests and Replay mode with no credentials, the Firestore
one is what a deployed instance uses.

Persistence is not just storage here. The boost tuner needs MIN_NIGHTS_TO_TUNE
nights of residual history before it will move off the seed values, and nothing
accumulates across a restart without this.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from typing import Protocol

from .models import Lineup, Pick


def _to_dict(lineup: Lineup) -> dict:
    return {"entrant": lineup.entrant, "picks": [asdict(p) for p in lineup.picks]}


def _from_dict(raw: dict) -> Lineup:
    return Lineup(
        entrant=raw["entrant"],
        picks=tuple(Pick(**p) for p in raw["picks"]),
    )


class Store(Protocol):
    def save_lineup(self, date: str, lineup: Lineup) -> None: ...

    def lineups(self, date: str) -> list[Lineup]: ...

    def save_residuals(self, date: str, residuals: dict[str, Sequence[float]]) -> None: ...

    def history(self) -> dict[str, list[list[float]]]:
        """category_id -> one list of z-values per night, ready for BoostTuner."""
        ...


class MemoryStore:
    """Default. No credentials, no network, forgets everything on restart."""

    def __init__(self) -> None:
        self._lineups: dict[str, dict[str, Lineup]] = defaultdict(dict)
        self._residuals: dict[str, dict[str, list[float]]] = {}

    def save_lineup(self, date: str, lineup: Lineup) -> None:
        self._lineups[date][lineup.entrant] = lineup

    def lineups(self, date: str) -> list[Lineup]:
        return list(self._lineups.get(date, {}).values())

    def save_residuals(self, date: str, residuals: dict[str, Sequence[float]]) -> None:
        self._residuals[date] = {k: list(v) for k, v in residuals.items()}

    def history(self) -> dict[str, list[list[float]]]:
        out: dict[str, list[list[float]]] = defaultdict(list)
        for date in sorted(self._residuals):
            for category_id, zs in self._residuals[date].items():
                out[category_id].append(zs)
        return dict(out)


class FirestoreStore:
    """Firebase project `questly-7f3a2`, reused from the Questly app.

    Layout:

        slates/{date}/lineups/{entrant}    one submitted lineup
        nights/{date}                      {residuals: {category_id: [z, ...]}}

    Auth is a service account, so security rules do not apply -- this is server
    side. Rules only start mattering when a browser reads these collections
    directly, which is a later milestone.
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

    def save_lineup(self, date: str, lineup: Lineup) -> None:
        (
            self._db.collection("slates").document(date)
            .collection("lineups").document(lineup.entrant)
            .set(_to_dict(lineup))
        )

    def lineups(self, date: str) -> list[Lineup]:
        docs = (
            self._db.collection("slates").document(date)
            .collection("lineups").stream()
        )
        return [_from_dict(d.to_dict()) for d in docs]

    def save_residuals(self, date: str, residuals: dict[str, Sequence[float]]) -> None:
        self._db.collection("nights").document(date).set(
            {"residuals": {k: list(v) for k, v in residuals.items()}}
        )

    def history(self) -> dict[str, list[list[float]]]:
        out: dict[str, list[list[float]]] = defaultdict(list)
        # ponytail: reads every night. Fine for one season (~170 docs); page or
        # keep a rolling aggregate if it ever gets past a few thousand.
        for doc in self._db.collection("nights").order_by("__name__").stream():
            for category_id, zs in (doc.to_dict().get("residuals") or {}).items():
                out[category_id].append(list(zs))
        return dict(out)


def default_store() -> Store:
    """Firestore when a project is configured, memory otherwise.

    Deliberately silent about which one it picked at import time -- `/health`
    reports it instead, so a misconfigured deploy is visible over HTTP rather
    than only in the logs.
    """
    if os.environ.get("SLATE_FIREBASE_PROJECT"):
        return FirestoreStore()
    return MemoryStore()
