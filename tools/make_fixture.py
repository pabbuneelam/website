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
SEED = 20251114


# Salary tiers, roughly the shape of a real roster: one max, a couple of
# mid-level deals, and minimums/rookie deals at the bottom. The bottom of this
# range is where the value hunting happens.
SALARY_TIERS = [55_000_000, 38_000_000, 24_000_000, 12_000_000, 3_500_000]


def line(rng, pid, name, team, opp, *, minutes=None, scale=1.0, pbp=True, salary=None):
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
    if salary is not None:
        row["salary"] = salary
    if pbp and minutes > 0:
        rim_fga = max(0, min(fga - fg3a, int((fga - fg3a) * rng.uniform(0.4, 0.8))))
        rim_fgm = max(0, min(rim_fga, int(rim_fga * rng.uniform(0.45, 0.78))))
        contested_fga = max(0, min(fga, int(fga * rng.uniform(0.3, 0.75))))
        contested_fgm = max(0, min(contested_fga, int(contested_fga * rng.uniform(0.25, 0.5))))
        matchup_fga = max(0, int(rng.gauss(9, 3)))
        matchup_fgm = max(0, min(matchup_fga, int(matchup_fga * rng.uniform(0.3, 0.6))))
        rim_def_fga = max(0, int(rng.gauss(4, 2.5)))
        rim_def_fgm = max(0, min(rim_def_fga, int(rim_def_fga * rng.uniform(0.4, 0.8))))
        row.update(
            rim_fgm=rim_fgm,
            rim_fga=rim_fga,
            contested_fgm=contested_fgm,
            contested_fga=contested_fga,
            uncontested_fgm=max(0, fgm - contested_fgm),
            uncontested_fga=max(0, fga - contested_fga),
            secondary_assists=max(0, int(rng.gauss(0.8, 0.9))),
            free_throw_assists=max(0, int(rng.gauss(0.4, 0.6))),
            rebound_chances_total=max(orb + drb, int((orb + drb) * rng.uniform(1.2, 2.6))),
            deflections=max(0, int(rng.gauss(1.8, 1.3))),
            matchup_minutes=round(minutes * rng.uniform(0.5, 0.85), 1),
            matchup_fgm=matchup_fgm,
            matchup_fga=matchup_fga,
            defended_at_rim_fgm=rim_def_fgm,
            defended_at_rim_fga=rim_def_fga,
        )
    return row


def build():
    rng = random.Random(SEED)
    games, boxscores = [], []
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
                salary = SALARY_TIERS[slot]
                boxscores.append(line(rng, pid, name, team, opp, scale=scale, salary=salary))

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
    # A bargain night: a minimum-salary player with an excellent line. This is
    # the build the whole value system is supposed to reward.
    bargain = boxscores[9]
    bargain.update(fg3a=11, fg3m=7, contested_fga=14, contested_fgm=7,
                   uncontested_fga=3, uncontested_fgm=2)

    assert by_id  # ids are unique by construction
    return {"date": DATE, "games": games, "boxscores": boxscores}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
