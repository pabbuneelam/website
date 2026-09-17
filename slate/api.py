"""Thin HTTP layer over the engine.

Four endpoints and an in-memory store. The surface is deliberately small because
no UI has been drawn yet -- designing endpoints for screens nobody has sketched
is how you end up with an API you have to throw away.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import catalog
from .models import Lineup, Pick
from .name import APP_NAME
from .project import BaselineProjector
from .rules import BUDGET, MAX_PICKS, MIN_ALLOCATION
from .score import NightScorer, validate
from .sources import FixtureSource
from .store import MemoryStore, default_store
from .tune import BoostTuner, night_residuals

# Replay mode resolves dates whose tipoff is long past, so lock is off by
# default. Flip this on when live data lands.
ENFORCE_LOCK = False

app = FastAPI(title=f"{APP_NAME} engine", version="0.1.0")
source = FixtureSource()

# Firestore when SLATE_FIREBASE_PROJECT is set, in-memory otherwise.
store = default_store()

# Serverless instances are stateless and scale to zero, so a submit and its
# resolve can land on different ones. In memory there is not merely
# non-durable there, it is wrong -- so refuse rather than behave randomly.
ON_SERVERLESS = bool(os.environ.get("VERCEL"))


def _require_durable_store() -> None:
    if ON_SERVERLESS and isinstance(store, MemoryStore):
        raise HTTPException(
            503,
            "no durable store configured. Set SLATE_FIREBASE_PROJECT and "
            "GOOGLE_APPLICATION_CREDENTIALS_JSON; the in-memory store loses "
            "lineups between requests on serverless instances.",
        )


class PickIn(BaseModel):
    category_id: str
    player_id: int
    allocated: float = Field(ge=MIN_ALLOCATION)
    backup_player_id: int | None = None


class LineupIn(BaseModel):
    entrant: str
    picks: list[PickIn] = Field(min_length=1, max_length=MAX_PICKS)


def _night(date: str):
    try:
        return source.load(date)
    except FileNotFoundError:
        raise HTTPException(404, f"no slate for {date}") from None


@app.get("/categories")
def get_categories():
    """The catalog, with the boost currently in force for each category."""
    return [
        {
            "id": c.id,
            "label": c.label,
            "tier": c.tier,
            "requires": c.requires,
            "guardrail": c.guardrail,
            "boost": c.seed_boost,
            "enabled": c.enabled,
        }
        for c in catalog.CATALOG
    ]


@app.get("/slates/{date}")
def get_slate(date: str):
    """Games and players. No stats -- the whole game is drafting blind."""
    night = _night(date)
    return {
        "date": night.date,
        "budget": BUDGET,
        "max_picks": MAX_PICKS,
        "games": [vars(g) for g in night.games],
        "players": [
            {"player_id": b.player_id, "name": b.player_name,
             "team": b.team, "opponent": b.opponent}
            for b in night.boxscores
        ],
    }


@app.post("/slates/{date}/lineups")
def submit_lineup(date: str, payload: LineupIn):
    _require_durable_store()
    _night(date)
    lineup = Lineup(
        entrant=payload.entrant,
        picks=tuple(
            Pick(p.category_id, p.player_id, p.allocated, p.backup_player_id)
            for p in payload.picks
        ),
    )
    problem = validate(lineup)
    if problem:
        raise HTTPException(422, problem)
    store.save_lineup(date, lineup)
    return {"accepted": True, "entrant": payload.entrant, "picks": len(lineup.picks)}


@app.post("/slates/{date}/resolve")
def resolve(date: str):
    """Run the engine over every lineup submitted for this date.

    Boosts come from history accumulated BEFORE tonight -- a night must not
    tune the boosts it is itself scored under. Tonight's residuals are written
    afterwards, for the nights that follow.
    """
    _require_durable_store()
    night = _night(date)
    entries = store.lineups(date)
    if not entries:
        raise HTTPException(409, f"no lineups submitted for {date}")

    boosts = BoostTuner().boosts(store.history())
    scorer = NightScorer(
        night.boxscores, BaselineProjector(night.logs), night.date, night.games
    )
    results = [scorer.score_lineup(lu, boosts) for lu in entries]
    results.sort(key=lambda r: r.total, reverse=True)

    category_ids = [c.id for c in catalog.enabled()]
    store.save_residuals(date, night_residuals(scorer, category_ids))

    return {
        "date": date,
        "boosts": {cid: boosts[cid] for cid in category_ids},
        "results": results,
    }


@app.get("/health")
def health():
    """Which store is live. A misconfigured deploy shows up here rather than
    silently falling back to memory and losing every lineup on restart."""
    backend = type(store).__name__
    return {
        "store": backend,
        "durable": not isinstance(store, MemoryStore),
        "firebase_project": os.environ.get("SLATE_FIREBASE_PROJECT"),
        "serverless": ON_SERVERLESS,
    }
