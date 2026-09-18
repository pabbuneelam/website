"""Thin HTTP layer over the card engine.

Five endpoints and no database of its own. The surface stays small because no
UI has been drawn yet -- designing endpoints for screens nobody has sketched is
how you get an API you throw away.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import attributes
from .card import build_card
from .card import validate as validate_build
from .models import Build, Selection
from .name import APP_NAME
from .score import NightRater
from .sources import FixtureSource
from .store import MemoryStore, Store, default_store

app = FastAPI(title=f"{APP_NAME} engine", version="0.2.0")

# The frontend is a separate static app on its own origin, so it needs CORS
# to call this API directly. No cookies/auth exist yet -- a creator is just a
# free-text name -- so a wildcard origin adds no real exposure today.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

source = FixtureSource()

# Built on first use, never at import. A Firestore client constructed at module
# scope runs credential discovery while the platform is merely importing this
# module to find the ASGI app -- which hangs the build in a sandbox, and costs
# a network round trip on every cold start even when it works.
store: Store | None = None


def get_store() -> Store:
    global store
    if store is None:
        store = default_store()
    return store

# Serverless instances are stateless and scale to zero, so an in-memory store
# there is not merely non-durable -- a card written by one instance is invisible
# to the next. Refuse rather than behave randomly.
ON_SERVERLESS = bool(os.environ.get("VERCEL"))


def _require_durable_store() -> None:
    if ON_SERVERLESS and isinstance(get_store(), MemoryStore):
        raise HTTPException(
            503,
            "no durable store configured. Set SLATE_FIREBASE_PROJECT and "
            "GOOGLE_APPLICATION_CREDENTIALS_JSON; the in-memory store loses "
            "cards between requests on serverless instances.",
        )


class SelectionIn(BaseModel):
    slot: str
    player_id: int


class BuildIn(BaseModel):
    creator: str
    selections: list[SelectionIn] = Field(
        min_length=len(attributes.SLOTS), max_length=len(attributes.SLOTS)
    )


def _night(date: str):
    try:
        return source.load(date)
    except FileNotFoundError:
        raise HTTPException(404, f"no slate for {date}") from None


@app.get("/attributes")
def get_attributes():
    """The six slots a build must fill, and what each one measures."""
    return [
        {
            "slot": a.slot,
            "label": a.label,
            "requires": a.requires,
            "guardrail": a.guardrail,
        }
        for a in attributes.ATTRIBUTES
    ]


@app.get("/slates/{date}")
def get_slate(date: str):
    """Tonight's players and their real salaries. No stats -- the whole game is
    predicting who performs, and salary is public information anyway."""
    night = _night(date)
    return {
        "date": night.date,
        "slots": list(attributes.SLOTS),
        "games": [vars(g) for g in night.games],
        "players": [
            {
                "player_id": b.player_id,
                "name": b.player_name,
                "team": b.team,
                "opponent": b.opponent,
                "salary": b.salary,
            }
            for b in night.boxscores
        ],
    }


@app.post("/slates/{date}/builds")
def submit_build(date: str, payload: BuildIn):
    """Fill six slots, get a player card back.

    Deliberately does NOT require a durable store. Rating a night is pure
    computation, so the game is playable and demoable without persistence --
    only the collection needs somewhere to live.
    """
    night = _night(date)

    build = Build(
        creator=payload.creator,
        selections=tuple(Selection(s.slot, s.player_id) for s in payload.selections),
    )
    problem = validate_build(build)
    if problem:
        raise HTTPException(422, problem)

    card = build_card(build, NightRater(night.boxscores), night.date)
    store = get_store()
    if not isinstance(store, MemoryStore) or not ON_SERVERLESS:
        # Writing to a MemoryStore on a stateless host is a lie -- the next
        # request lands elsewhere. Better to hand back the card and say the
        # collection is off than to pretend it was saved.
        store.save_card(card)
    return card


@app.get("/cards/{creator}")
def get_collection(creator: str):
    """Every card this creator has made, newest first."""
    _require_durable_store()
    return get_store().cards(creator)


@app.get("/health")
def health():
    """Which store is live. A deploy that silently fell back to memory loses
    every card, so it has to be visible over HTTP."""
    live = get_store()
    return {
        "store": type(live).__name__,
        "durable": not isinstance(live, MemoryStore),
        "firebase_project": os.environ.get("SLATE_FIREBASE_PROJECT"),
        "serverless": ON_SERVERLESS,
    }
