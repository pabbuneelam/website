"""Generate the committed test fixture.

Seeded, so the output is reproducible and the golden test means something. Most
rows are ordinary; a handful are deliberately awkward, because the edge cases
are the point of a fixture -- a shooter under the FGA guardrail, a bench player
under the minutes guardrail, an exact tie in rebounds, and a DNP whose backup
has to carry the pick.

    python tools/make_fixture.py > slate/fixtures/2025-11-14.json
"""
from __future__ import annotations

import json
import random

DATE = "2025-11-14"
TEAMS = [("BOS", "NYK"), ("DEN", "LAL"), ("OKC", "MIN")]
HISTORY_GAMES = 6
SEED = 20251114


def line(rng, pid, name, team, opp, *, minutes=None, scale=1.0, pbp=True):
    minutes = rng.uniform(22, 38) if minutes is None else minutes
    if minutes == 0:
        fga = fgm = fta = ftm = fg3a = fg3m = 0
        pts = orb = drb = ast = stl = blk = tov = pf = pm = 0
    else:
        fga = max(0, int(rng.gauss(13 * scale, 4)))
        fgm = max(0, min(fga, int(fga * rng.uniform(0.35, 0.58))))
        fg3a = max(0, min(fga, int(fga * rng.uniform(0.1, 0.55))))
        fg3m = max(0, min(fg3a, int(fg3a * rng.uniform(0.2, 0.5))))
        fta = max(0, int(rng.gauss(4 * scale, 2)))
        ftm = max(0, min(fta, int(fta * rng.uniform(0.6, 0.95))))
        pts = 2 * (fgm - fg3m) + 3 * fg3m + ftm
        orb = max(0, int(rng.gauss(1.4, 1.2)))
        drb = max(0, int(rng.gauss(4.5, 2.4)))
        ast = max(0, int(rng.gauss(4.0, 2.6)))
        stl = max(0, int(rng.gauss(1.0, 0.9)))
        blk = max(0, int(rng.gauss(0.7, 0.9)))
        tov = max(0, int(rng.gauss(2.1, 1.3)))
        pf = max(0, int(rng.gauss(2.3, 1.1)))
        pm = int(rng.gauss(0, 9))
    row = {
        "player_id": pid, "player_name": name, "team": team, "opponent": opp,
        "minutes": round(minutes, 1), "pts": pts, "fgm": fgm, "fga": fga,
        "ftm": ftm, "fta": fta, "fg3m": fg3m, "fg3a": fg3a, "orb": orb,
        "drb": drb, "ast": ast, "stl": stl, "blk": blk, "tov": tov, "pf": pf,
        "plus_minus": pm,
    }
    if pbp:
        corner = min(fg3m, max(0, int(rng.gauss(0.8, 0.9))))
        row.update(
            corner3m=corner,
            wing3m=max(0, fg3m - corner),
            left_side_fgm=max(0, min(fgm, int(fgm * rng.uniform(0.3, 0.6)))),
            lobs=max(0, int(rng.gauss(0.5, 0.8))),
        )
    return row


def build():
    rng = random.Random(SEED)
    games, boxscores, logs = [], [], {}
    pid = 100

    for gid, (home, away) in enumerate(TEAMS, start=1):
        games.append({
            "game_id": gid, "home": home, "away": away,
            "tipoff": f"{DATE}T{18 + gid}:30:00Z",
        })
        for team, opp in ((home, away), (away, home)):
            for slot in range(5):
                pid += 1
                name = f"{team} Player {slot + 1}"
                scale = 1.5 if slot == 0 else 1.0
                boxscores.append(line(rng, pid, name, team, opp, scale=scale))
                logs[str(pid)] = [
                    {"season_offset": 0 if i < 4 else 1,
                     "box": line(rng, pid, name, team, opp, scale=scale)}
                    for i in range(HISTORY_GAMES)
                ]

    by_id = {b["player_id"]: b for b in boxscores}

    # --- deliberate edge cases -------------------------------------------
    # 1-for-1 night: real efficiency, but under the 8 FGA guardrail.
    sharp = boxscores[2]
    sharp.update(minutes=9.0, fga=1, fgm=1, fg3a=1, fg3m=1, fta=0, ftm=0, pts=3)
    # Under the 15-minute plus/minus guardrail, with a flattering number.
    bench = boxscores[3]
    bench.update(minutes=11.0, plus_minus=21)
    # Exact tie in rebounds, to exercise midrank percentiles.
    boxscores[5].update(orb=3, drb=7)
    boxscores[6].update(orb=3, drb=7)
    # DNP, so a pick on him has to fall through to its backup.
    scratched = boxscores[10]
    for key, value in line(rng, scratched["player_id"], scratched["player_name"],
                           scratched["team"], scratched["opponent"], minutes=0).items():
        scratched[key] = value
    # No history at all -- the projector must return None and the pool take over.
    logs.pop(str(boxscores[7]["player_id"]), None)

    assert by_id  # ids are unique by construction
    return {"date": DATE, "games": games, "boxscores": boxscores, "logs": logs}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
