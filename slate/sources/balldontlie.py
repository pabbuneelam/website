"""balldontlie.io adapter -- live NBA data instead of a fixture.

Tier map, verified against https://docs.balldontlie.io/ (checked 2026-09-22):

    free      $0        teams, players, games. No player stats at all.
    ALL-STAR  $9.99/mo  + /v1/stats: pts, fgm/fga, fg3m/fga, ftm/fta,
                          oreb/dreb, ast, stl, blk, turnover, pf, plus_minus,
                          min. Enough for OUTSIDE and PLAYMAKING.
    GOAT      $39.99/mo + /v2/stats/advanced: contested/uncontested FGA/FGM,
                          matchup_*, defended_at_rim_*, rebound_chances_total,
                          deflections, secondary/free-throw assists.
                          Unlocks REBOUNDING and PERIMETER_D (INTERIOR_D
                          still needs blocks, which /v1/stats already has).

There is a 48-hour GOAT trial (5 req/min); ALL-STAR is 60 req/min, GOAT is
600 req/min once paid.

One real gap: nothing in balldontlie's schema is an *offensive* rim_fga/
rim_fgm (shots this player took at the rim) -- only `defended_at_rim_*`
(shots taken against this player). So FINISHING stays unavailable
(rim_fgm/rim_fga come back None) even on GOAT, until that field turns up
somewhere in their API.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from ..models import BoxScore, SlateGame
from .base import NightData

BASE_URL = "https://api.balldontlie.io"
TIMEOUT = 10
PER_PAGE = 100

TIER_CAPABILITIES = {
    "free": frozenset(),
    "allstar": frozenset({"boxscore"}),
    "goat": frozenset({"boxscore", "pbp", "advanced"}),
}


class BallDontLieError(RuntimeError):
    """A balldontlie request failed or came back in an unexpected shape."""


def _minutes(raw: object) -> float:
    """`min` comes back as a string -- "30", "" for a DNP, occasionally
    "MM:SS" on older data. Never worth failing the whole slate over."""
    if not raw:
        return 0.0
    text = str(raw)
    if ":" in text:
        mins, _, secs = text.partition(":")
        try:
            return int(mins or 0) + int(secs or 0) / 60
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _player_name(player: dict) -> str:
    return f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()


def _parse_game(raw: dict) -> SlateGame:
    return SlateGame(
        game_id=raw["id"],
        home=raw["home_team"]["abbreviation"],
        away=raw["visitor_team"]["abbreviation"],
        tipoff=raw["datetime"],
    )


def _matchups(games: list[dict]) -> dict[int, dict[str, object]]:
    """game_id -> the two teams in it, so a stat row (which only carries its
    own team) can work out who the opponent was."""
    return {
        g["id"]: {
            "home_id": g["home_team"]["id"],
            "away_id": g["visitor_team"]["id"],
            "home_abbr": g["home_team"]["abbreviation"],
            "away_abbr": g["visitor_team"]["abbreviation"],
        }
        for g in games
    }


def _opponent(team_id: int, matchup: dict[str, object]) -> str:
    if team_id == matchup.get("home_id"):
        return str(matchup.get("away_abbr", ""))
    return str(matchup.get("home_abbr", ""))


def _parse_box(
    row: dict,
    matchups: dict[int, dict[str, object]],
    advanced: dict | None,
) -> BoxScore:
    player = row["player"]
    team = row["team"]
    matchup = matchups.get(row["game"]["id"], {})
    adv = advanced or {}
    return BoxScore(
        player_id=player["id"],
        player_name=_player_name(player),
        team=team["abbreviation"],
        opponent=_opponent(team["id"], matchup),
        minutes=_minutes(row.get("min")),
        pts=row.get("pts") or 0,
        fgm=row.get("fgm") or 0,
        fga=row.get("fga") or 0,
        ftm=row.get("ftm") or 0,
        fta=row.get("fta") or 0,
        fg3m=row.get("fg3m") or 0,
        fg3a=row.get("fg3a") or 0,
        orb=row.get("oreb") or 0,
        drb=row.get("dreb") or 0,
        ast=row.get("ast") or 0,
        stl=row.get("stl") or 0,
        blk=row.get("blk") or 0,
        tov=row.get("turnover") or 0,
        pf=row.get("pf") or 0,
        plus_minus=row.get("plus_minus") or 0,
        contested_fgm=adv.get("contested_fgm"),
        contested_fga=adv.get("contested_fga"),
        uncontested_fgm=adv.get("uncontested_fgm"),
        uncontested_fga=adv.get("uncontested_fga"),
        secondary_assists=adv.get("secondary_assists"),
        free_throw_assists=adv.get("free_throw_assists"),
        rebound_chances_total=adv.get("rebound_chances_total"),
        deflections=adv.get("deflections"),
        matchup_minutes=adv.get("matchup_minutes"),
        matchup_fgm=adv.get("matchup_fgm"),
        matchup_fga=adv.get("matchup_fga"),
        defended_at_rim_fgm=adv.get("defended_at_rim_fgm"),
        defended_at_rim_fga=adv.get("defended_at_rim_fga"),
    )


class BallDontLieSource:
    def __init__(self, api_key: str, tier: str = "allstar") -> None:
        if tier not in TIER_CAPABILITIES:
            raise ValueError(f"unknown balldontlie tier {tier!r}")
        self.api_key = api_key
        self.tier = tier

    def capabilities(self) -> frozenset[str]:
        return TIER_CAPABILITIES[self.tier]

    def load(self, date: str) -> NightData:
        games = self._paginate("/v1/games", {"dates[]": date})
        if not games:
            # Same signal FixtureSource gives for a night it doesn't have --
            # api.py._night() catches this and falls back to the sample
            # night rather than a hard 500.
            raise FileNotFoundError(f"balldontlie has no games for {date}")

        matchups = _matchups(games)
        slate_games = tuple(_parse_game(g) for g in games)

        advanced_by_player: dict[int, dict] = {}
        if "advanced" in self.capabilities():
            for row in self._paginate("/v2/stats/advanced", {"dates[]": date}):
                player = row.get("player") or {}
                if "id" in player:
                    advanced_by_player[player["id"]] = row

        boxscores = tuple(
            _parse_box(row, matchups, advanced_by_player.get(row["player"]["id"]))
            for row in self._paginate("/v1/stats", {"dates[]": date})
            if _minutes(row.get("min")) > 0
        )
        return NightData(date=date, games=slate_games, boxscores=boxscores)

    def _get(self, path: str, params: dict[str, object]) -> dict:
        query = urllib.parse.urlencode(params, doseq=True)
        request = urllib.request.Request(
            f"{BASE_URL}{path}?{query}",
            headers={"Authorization": self.api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise BallDontLieError(f"{path} -> {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise BallDontLieError(f"{path} unreachable: {exc.reason}") from exc

    def _paginate(self, path: str, params: dict[str, object]) -> list[dict]:
        rows: list[dict] = []
        cursor: object | None = None
        while True:
            page = dict(params, per_page=PER_PAGE)
            if cursor is not None:
                page["cursor"] = cursor
            payload = self._get(path, page)
            rows.extend(payload.get("data", []))
            cursor = (payload.get("meta") or {}).get("next_cursor")
            if not cursor:
                return rows
