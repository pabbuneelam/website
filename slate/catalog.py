"""The category catalog. Categories are data, not code — adding one is a row here
plus a metric function, never a change to the scoring engine.

``requires`` names the data source a category needs, which is what gates the
location categories: balldontlie exposes shot coordinates only on the GOAT tier,
so they ship declared-but-disabled and flip on with a config change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["basic", "combo", "location"]
Source = Literal["boxscore", "pbp", "odds"]


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    tier: Tier
    requires: Source
    metric: str
    seed_boost: float
    guardrail: str | None = None  # display text; the logic lives in the metric
    enabled: bool = True


CATALOG: tuple[Category, ...] = (
    # --- basic -----------------------------------------------------------
    Category("PTS", "Points", "basic", "boxscore", "pts", 1.0),
    Category("REB", "Rebounds", "basic", "boxscore", "reb", 1.0),
    Category("AST", "Assists", "basic", "boxscore", "ast", 1.0),
    Category("STL", "Steals", "basic", "boxscore", "stl", 1.2),
    Category("BLK", "Blocks", "basic", "boxscore", "blk", 1.2),
    Category("TOV", "Fewest turnovers", "basic", "boxscore", "tov_neg", 1.1),
    # --- combo -----------------------------------------------------------
    Category("STOCKS", "Steals + blocks", "combo", "boxscore", "stocks", 1.2),
    Category("AST_TO", "Assists minus turnovers", "combo", "boxscore", "ast_to", 1.3),
    Category(
        "TS_PCT", "True shooting %", "combo", "boxscore", "ts_pct", 1.4,
        guardrail="min 8 FGA",
    ),
    Category(
        "PLUS_MINUS", "Plus/minus", "combo", "boxscore", "plus_minus", 1.3,
        guardrail="min 15 minutes",
    ),
    Category("GAME_SCORE", "Game Score", "combo", "boxscore", "game_score", 1.1),
    # --- location: needs play-by-play coordinates (GOAT tier) ------------
    Category("CORNER3", "Corner threes", "location", "pbp", "corner3m", 2.1, enabled=False),
    Category("WING3", "Wing threes", "location", "pbp", "wing3m", 1.9, enabled=False),
    Category("LEFT_SIDE", "Left-side makes", "location", "pbp", "left_side_fgm", 1.8, enabled=False),
    Category("LOB", "Lobs finished", "location", "pbp", "lobs", 2.3, enabled=False),
)

BY_ID: dict[str, Category] = {c.id: c for c in CATALOG}


def enabled() -> tuple[Category, ...]:
    return tuple(c for c in CATALOG if c.enabled)


def get(category_id: str) -> Category:
    try:
        return BY_ID[category_id]
    except KeyError:
        raise KeyError(f"unknown category {category_id!r}") from None
