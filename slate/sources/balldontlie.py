"""balldontlie adapter -- not implemented yet, on purpose.

Tier map, verified against the docs:

    free      $0        teams, players, games. No player stats at all.
    ALL-STAR  $9.99/mo  + per-game box scores, injuries
    GOAT      $39.99/mo + play-by-play (coordinate_x/y), advanced stats,
                          odds & props, contracts

So: every `location` category and any odds work needs GOAT. Play-by-play only
exists from the 2025 season forward, which caps how far the "decay into previous
seasons" idea can reach for niche categories -- points have years of history,
corner threes have one season.

There is a 48-hour GOAT trial (5 req/min). Pulling one real slate through it,
play-by-play included, is the cheapest way to validate the location categories
before committing to a subscription.
"""
from __future__ import annotations

from .base import NightData

BASE_URL = "https://api.balldontlie.io/v1"
TIER_CAPABILITIES = {
    "free": frozenset(),
    "allstar": frozenset({"boxscore"}),
    "goat": frozenset({"boxscore", "pbp", "odds"}),
}


class BallDontLieSource:
    def __init__(self, api_key: str, tier: str = "allstar") -> None:
        self.api_key = api_key
        self.tier = tier

    def capabilities(self) -> frozenset[str]:
        return TIER_CAPABILITIES[self.tier]

    def load(self, date: str) -> NightData:
        raise NotImplementedError(
            "Live ingestion is a separate milestone. Run against FixtureSource "
            "until the engine is settled."
        )
