"""Thin HTTP layer over the engine.

Four endpoints and an in-memory store. The surface is deliberately small because
no UI has been drawn yet -- designing endpoints for screens nobody has sketched
is how you end up with an API you have to throw away.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import catalog
from .models import Lineup, Pick
from .name import APP_NAME
from .project import BaselineProjector
from .rules import BUDGET, MAX_PICKS, MIN_ALLOCATION
from .score import NightScorer, validate
from .sources import FixtureSource

# Replay mode resolves dates whose tipoff is long past, so lock is off by
# default. Flip this on when live data lands.
ENFORCE_LOCK = False

app = FastAPI(title=f"{APP_NAME} engine", version="0.1.0")
source = FixtureSource()

# date -> entrant -> Lineup. A database is a later milestone.
_lineups: dict[str, dict[str, Lineup]] = defaultdict(dict)


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
    _lineups[date][payload.entrant] = lineup
    return {"accepted": True, "entrant": payload.entrant, "picks": len(lineup.picks)}


@app.post("/slates/{date}/resolve")
def resolve(date: str):
    """Run the engine over every lineup submitted for this date."""
    night = _night(date)
    entries = _lineups.get(date, {})
    if not entries:
        raise HTTPException(409, f"no lineups submitted for {date}")

    scorer = NightScorer(
        night.boxscores, BaselineProjector(night.logs), night.date, night.games
    )
    results = [scorer.score_lineup(lu) for lu in entries.values()]
    results.sort(key=lambda r: r.total, reverse=True)
    return {"date": date, "results": results}
