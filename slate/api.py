"""Thin HTTP layer over the card engine.

No database of its own, and a deliberately small surface -- designing
endpoints for screens nobody has sketched is how you get an API you throw
away. Identity is the one thing this layer owns: a Firebase ID token arrives
as a bearer header, `current_user` verifies it, and the uid it yields is what
keys every write.
"""
from __future__ import annotations

import os

import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import attributes
from .auth import AuthError, AuthUser, bearer_token, verify
from .card import build_card
from .card import validate as validate_build
from .leagues import unique_code
from .models import Build, League, Membership, Selection, UserProfile
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


# ---------------------------------------------------------------- leagues
# A user belongs to exactly one league at a time. No switcher, no team layer:
# uid keys a membership exactly as it keys a card, so "which league am I in"
# is a single document read and "am I already in one" is the same read.


class LeagueIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)


def _now() -> str:
    # Microseconds, not seconds: joined_at is what orders a roster, and two
    # people joining inside the same second is the normal case when a code
    # has just been pasted into a group chat.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _league_view(league: League, store: Store) -> dict:
    """A league and its roster -- the only shape the frontend ever needs."""
    return {"league": league, "members": store.members(league.league_id)}


def _refuse_if_already_in_a_league(uid: str, store: Store) -> None:
    """One league at a time, said out loud.

    Silently switching would strand whatever the old league knew about this
    user, so this is a refusal rather than a move. 409, not 400: the request
    is well formed, the state is what says no.
    """
    existing = store.membership(uid)
    if existing is None:
        return
    league = store.league(existing.league_id)
    where = f'"{league.name}"' if league else existing.league_id
    raise HTTPException(
        409,
        f"you are already in {where}. Leave it before joining another league.",
    )


@app.post("/leagues")
def create_league(payload: LeagueIn, user: AuthUser = Depends(current_user)):
    """Start a league and join it. The response carries the invite code,
    which is the only way anyone else gets in."""
    _require_durable_store()
    store = get_store()
    _refuse_if_already_in_a_league(user.uid, store)

    league = League(
        league_id=uuid.uuid4().hex[:12],
        name=payload.name.strip(),
        code=unique_code(lambda code: store.league_by_code(code) is not None),
        owner_uid=user.uid,
        created_at=_now(),
    )
    store.save_league(league)
    store.save_membership(
        Membership(
            uid=user.uid,
            league_id=league.league_id,
            display_name=user.display_name,
            joined_at=_now(),
        )
    )
    return _league_view(league, store)


@app.post("/leagues/join")
def join_league(payload: JoinIn, user: AuthUser = Depends(current_user)):
    """Join by invite code. An unknown code is a 404, not a 500."""
    _require_durable_store()
    store = get_store()
    _refuse_if_already_in_a_league(user.uid, store)

    league = store.league_by_code(payload.code)
    if league is None:
        raise HTTPException(404, f"no league with invite code {payload.code.strip().upper()}")

    store.save_membership(
        Membership(
            uid=user.uid,
            league_id=league.league_id,
            display_name=user.display_name,
            joined_at=_now(),
        )
    )
    return _league_view(league, store)


@app.post("/leagues/leave")
def leave_league(user: AuthUser = Depends(current_user)):
    """Leave whatever league you are in.

    Cards are owned by the uid and do not move -- a collection is global, and
    since a user is only ever in one league that is the same thing.
    """
    _require_durable_store()
    store = get_store()
    if store.membership(user.uid) is None:
        raise HTTPException(409, "you are not in a league")
    store.remove_membership(user.uid)
    return {"league": None, "members": []}


@app.get("/leagues/me")
def get_my_league(user: AuthUser = Depends(current_user)):
    """The caller's league and its members, or a null league.

    Not in a league is an ordinary state, not an error -- returning 404 here
    would make the frontend guess which 404s are real failures.
    """
    _require_durable_store()
    store = get_store()
    membership = store.membership(user.uid)
    if membership is None:
        return {"league": None, "members": []}
    league = store.league(membership.league_id)
    if league is None:
        # The membership outlived its league. Treat it as not being in one
        # rather than 500-ing a user who can do nothing about it.
        return {"league": None, "members": []}
    return _league_view(league, store)


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
