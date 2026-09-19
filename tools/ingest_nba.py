"""Pull one real NBA slate into the fixture schema.

    python tools/ingest_nba.py 2025-11-14 > slate/fixtures/2025-11-14.json

Everything here comes from stats.nba.com via nba_api, which is free and needs
no key. Five endpoints per game, because the fields the attributes need are
spread across them:

    traditional  points, shooting, boards, assists, turnovers, plus/minus
    playertrack  rebound chances, secondary assists, contested/uncontested,
                 defended-at-rim  <- four of the six attributes live here
    hustle       deflections, contested shots, box outs
    defensive    matchup minutes and matchup shooting
    shotchart    shot zones, for the player's own rim and corner shooting

ponytail: sequential with a fixed delay. stats.nba.com is rate limited and
unofficial; concurrency buys nothing but 429s. ~6 calls a game, so a full
slate is a couple of minutes. It runs off-line into a committed file, not on
a request path.

stats.nba.com is also known to refuse datacenter IPs, which is the other
reason this is an offline job whose output is stored rather than a live call
from the API. See docs in README.
"""
from __future__ import annotations

import json
import sys
import time
import warnings

warnings.filterwarnings("ignore")

from nba_api.stats.endpoints import (  # noqa: E402
    boxscoredefensivev2,
    boxscorehustlev2,
    boxscoreplayertrackv3,
    boxscoretraditionalv3,
    scoreboardv2,
    shotchartdetail,
)

PAUSE = 0.8
TIMEOUT = 45


def minutes(raw) -> float:
    """stats.nba.com hands back 'MM:SS', 'PT12M34.00S', '' or None."""
    if not raw:
        return 0.0
    text = str(raw)
    if text.startswith("PT"):
        mins = text[2:].split("M")[0]
        secs = text.split("M")[1].rstrip("S") if "M" in text else "0"
        return round(float(mins) + float(secs or 0) / 60, 1)
    if ":" in text:
        mins, secs = text.split(":")[:2]
        return round(float(mins) + float(secs) / 60, 1)
    try:
        return round(float(text), 1)
    except ValueError:
        return 0.0


def i(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def fetch(label, fn):
    time.sleep(PAUSE)
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - one flaky endpoint must not sink the slate
        print(f"  ! {label} failed: {type(exc).__name__}", file=sys.stderr)
        return None


def shot_zones(game_id):
    """player_id -> rim and corner-three makes/attempts for their own shots."""
    df = fetch("shotchart", lambda: shotchartdetail.ShotChartDetail(
        team_id=0, player_id=0, game_id_nullable=game_id,
        context_measure_simple="FGA", season_type_all_star="Regular Season",
        timeout=TIMEOUT).get_data_frames()[0])
    out: dict[int, dict] = {}
    if df is None:
        return out
    for _, row in df.iterrows():
        pid = int(row["PLAYER_ID"])
        z = row["SHOT_ZONE_BASIC"]
        made = int(row["SHOT_MADE_FLAG"])
        rec = out.setdefault(pid, {"rim_fga": 0, "rim_fgm": 0, "corner3a": 0, "corner3m": 0})
        if z == "Restricted Area":
            rec["rim_fga"] += 1
            rec["rim_fgm"] += made
        elif z in ("Left Corner 3", "Right Corner 3"):
            rec["corner3a"] += 1
            rec["corner3m"] += made
    return out


def index(df, key="personId"):
    return {} if df is None else {int(r[key]): r for _, r in df.iterrows()}


def ingest(date: str) -> dict:
    board = scoreboardv2.ScoreboardV2(game_date=date, timeout=TIMEOUT).game_header.get_data_frame()
    if board.empty:
        raise SystemExit(f"no games on {date}")

    games, boxscores = [], []
    for _, g in board.iterrows():
        gid = g["GAME_ID"]
        matchup = str(g.get("GAMECODE", "")).split("/")[-1]
        away, home = (matchup[:3], matchup[3:]) if len(matchup) == 6 else ("", "")
        print(f"  {gid}  {away} @ {home}", file=sys.stderr)

        trad = fetch("traditional", lambda: boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=gid, timeout=TIMEOUT).player_stats.get_data_frame())
        if trad is None:
            continue
        track = index(fetch("playertrack", lambda: boxscoreplayertrackv3.BoxScorePlayerTrackV3(
            game_id=gid, timeout=TIMEOUT).player_stats.get_data_frame()))
        hustle = index(fetch("hustle", lambda: boxscorehustlev2.BoxScoreHustleV2(
            game_id=gid, timeout=TIMEOUT).player_stats.get_data_frame()))
        defend = index(fetch("defensive", lambda: boxscoredefensivev2.BoxScoreDefensiveV2(
            game_id=gid, timeout=TIMEOUT).player_stats.get_data_frame()))
        zones = shot_zones(gid)

        games.append({"game_id": int(str(gid)[-4:]), "home": home, "away": away,
                      "tipoff": f"{date}T23:00:00Z"})

        for _, p in trad.iterrows():
            pid = int(p["personId"])
            team = p["teamTricode"]
            t = track.get(pid, {})
            h = hustle.get(pid, {})
            d = defend.get(pid, {})
            z = zones.get(pid, {})
            boxscores.append({
                "player_id": pid,
                "player_name": f"{str(p['firstName'])[:1]}. {p['familyName']}".strip(". "),
                "team": team,
                "opponent": away if team == home else home,
                "minutes": minutes(p["minutes"]),
                "pts": i(p["points"]), "fgm": i(p["fieldGoalsMade"]), "fga": i(p["fieldGoalsAttempted"]),
                "ftm": i(p["freeThrowsMade"]), "fta": i(p["freeThrowsAttempted"]),
                "fg3m": i(p["threePointersMade"]), "fg3a": i(p["threePointersAttempted"]),
                "orb": i(p["reboundsOffensive"]), "drb": i(p["reboundsDefensive"]),
                "ast": i(p["assists"]), "stl": i(p["steals"]), "blk": i(p["blocks"]),
                "tov": i(p["turnovers"]), "pf": i(p["foulsPersonal"]),
                "plus_minus": i(p["plusMinusPoints"]),
                "salary": None,  # filled by tools/attach_salaries.py
                "rim_fgm": z.get("rim_fgm"), "rim_fga": z.get("rim_fga"),
                "contested_fgm": i(t.get("contestedFieldGoalsMade")) if len(t) else None,
                "contested_fga": i(t.get("contestedFieldGoalsAttempted")) if len(t) else None,
                "uncontested_fgm": i(t.get("uncontestedFieldGoalsMade")) if len(t) else None,
                "uncontested_fga": i(t.get("uncontestedFieldGoalsAttempted")) if len(t) else None,
                "secondary_assists": i(t.get("secondaryAssists")) if len(t) else None,
                "free_throw_assists": i(t.get("freeThrowAssists")) if len(t) else None,
                "rebound_chances_total": i(t.get("reboundChancesTotal")) if len(t) else None,
                "deflections": i(h.get("deflections")) if len(h) else None,
                "matchup_minutes": minutes(d.get("matchupMinutes")) if len(d) else None,
                "matchup_fgm": i(d.get("matchupFieldGoalsMade")) if len(d) else None,
                "matchup_fga": i(d.get("matchupFieldGoalsAttempted")) if len(d) else None,
                "defended_at_rim_fgm": i(t.get("defendedAtRimFieldGoalsMade")) if len(t) else None,
                "defended_at_rim_fga": i(t.get("defendedAtRimFieldGoalsAttempted")) if len(t) else None,
            })

    return {"date": date, "games": games, "boxscores": boxscores}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/ingest_nba.py YYYY-MM-DD > out.json")
    print(json.dumps(ingest(sys.argv[1]), indent=1))
