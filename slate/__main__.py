"""Replay a stored slate end to end.

    python -m slate replay 2025-11-14
"""
from __future__ import annotations

import sys

from . import catalog
from .models import Lineup, Pick
from .name import APP_NAME
from .project import BaselineProjector
from .score import NightScorer
from .sources import FixtureSource
from .tune import BoostTuner, night_residuals


def demo_lineup(night) -> Lineup:
    """Allocate across the first few enabled categories, one player each."""
    cats = [c for c in catalog.enabled()][:4]
    players = [b.player_id for b in night.boxscores]
    picks = tuple(
        Pick(category_id=c.id, player_id=players[i], allocated=250.0,
             backup_player_id=players[i + 10])
        for i, c in enumerate(cats)
    )
    return Lineup(entrant="demo", picks=picks)


def replay(date: str) -> int:
    night = FixtureSource().load(date)
    scorer = NightScorer(
        night.boxscores, BaselineProjector(night.logs), night.date, night.games
    )
    result = scorer.score_lineup(demo_lineup(night))

    print(f"{APP_NAME} — {date}")
    if result.void:
        print(f"  VOID: {result.void_reason}")
        return 1

    header = f"{'category':<12}{'player':>7}{'actual':>9}{'proj':>9}{'z':>7}{'pctile':>8}{'boost':>7}{'score':>9}"
    print(header)
    print("-" * len(header))
    for p in result.picks:
        actual = "-" if p.actual is None else f"{p.actual:.2f}"
        proj = "-" if p.projected is None else f"{p.projected:.2f}"
        z = "-" if p.z is None else f"{p.z:+.2f}"
        print(
            f"{p.category_id:<12}{p.scored_player_id:>7}{actual:>9}{proj:>9}"
            f"{z:>7}{p.multiplier:>8.2f}{p.boost:>7.2f}{p.score:>9.1f}"
            + (f"   ({p.note})" if p.note else "")
        )
    print("-" * len(header))
    print(f"{'total':<12}{result.total:>50.1f}")

    ids = [c.id for c in catalog.enabled()]
    tuned = BoostTuner().boosts({k: [v] for k, v in night_residuals(scorer, ids).items()})
    print(f"\nboosts after 1 night (seeds hold until 20): "
          f"{ {k: tuned[k] for k in ids[:4]} }")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "replay":
        print(__doc__.strip())
        return 2
    return replay(argv[2])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
