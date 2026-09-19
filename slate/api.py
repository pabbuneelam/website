"""Thin HTTP layer over the card engine.

No database of its own, and a deliberately small surface -- designing
endpoints for screens nobody has sketched is how you get an API you throw
away. Identity is the one thing this layer owns: a Firebase ID token arrives
as a bearer header, `current_user` verifies it, and the uid it yields is what
keys every write.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import attributes
from .auth import AuthError, AuthUser, bearer_token, verify
from .card import build_card
from .card import validate as validate_build
from .models import Build, Selection, UserProfile
from .name import APP_NAME
from .score import NightRater
from .sources import FixtureSource
from .store import MemoryStore, Store, default_store

app = FastAPI(title=f"{APP_NAME} engine", version="0.2.0")

# The SPA is a separate static app on its own origin, so it needs CORS to call
# this API directly. A wildcard origin is still safe with accounts in play:
# identity rides in an Authorization header, not a cookie, so a hostile page
# cannot make the browser attach it. `allow_credentials` must stay off for
# that to remain true.
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


def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """The signed-in caller, from `Authorization: Bearer <firebase id token>`.

    A FastAPI dependency rather than middleware so each endpoint declares
    whether it needs an identity, and so tests can substitute one through
    `app.dependency_overrides`.
    """
    try:
        return verify(bearer_token(authorization))
    except AuthError as exc:
        raise HTTPException(401, str(exc)) from None


class SelectionIn(BaseModel):
    slot: str
    player_id: int


class BuildIn(BaseModel):
    # No creator field: identity comes from the verified token, never from the
    # request body. That is the whole point -- two people typing "demo" used to
    # be the same user.
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
def submit_build(date: str, payload: BuildIn, user: AuthUser = Depends(current_user)):
    """Fill six slots, get a player card back.

    Deliberately does NOT require a durable store. Rating a night is pure
    computation, so the game is playable and demoable without persistence --
    only the collection needs somewhere to live.
    """
    night = _night(date)

    build = Build(
        uid=user.uid,
        display_name=user.display_name,
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


@app.post("/users/me")
def upsert_profile(user: AuthUser = Depends(current_user)):
    """Record the signed-in user. Called by the frontend when auth state
    changes; `created_at` is stamped on the first call and never rewritten."""
    _require_durable_store()
    return get_store().save_user(
        UserProfile(
            uid=user.uid,
            display_name=user.display_name,
            email=user.email,
            photo_url=user.photo_url,
        )
    )


@app.get("/users/me")
def get_profile(user: AuthUser = Depends(current_user)):
    """The stored profile, or the token's own claims if nothing is stored yet."""
    _require_durable_store()
    stored = get_store().user(user.uid)
    return stored or UserProfile(
        uid=user.uid,
        display_name=user.display_name,
        email=user.email,
        photo_url=user.photo_url,
    )


# Declared before /cards/{uid} on purpose -- otherwise "me" matches as a uid.
@app.get("/cards/me")
def get_my_collection(user: AuthUser = Depends(current_user)):
    """The signed-in user's collection, newest first."""
    _require_durable_store()
    return get_store().cards(user.uid)


@app.get("/cards/{uid}")
def get_collection(uid: str):
    """Every card one user has made, newest first.

    Public: a uid is an opaque identifier, not a secret, and leagues will need
    to show other people's collections.
    """
    _require_durable_store()
    return get_store().cards(uid)


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
