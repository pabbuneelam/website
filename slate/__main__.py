"""Build a player from a stored slate.

    python -m slate build 2025-11-14
"""
from __future__ import annotations

import sys

from . import attributes
from .card import build_card
from .models import Build, Selection
from .name import APP_NAME
from .score import NightRater
from .sources import FixtureSource


def best_available(rater: NightRater) -> Build:
    """Greedy demo build: take the top rater in each slot, skipping anyone
    already used. Not optimal -- a real user is predicting, not hindsight
    picking -- but it exercises the whole path."""
    used: set[int] = set()
    selections = []
    for slot in attributes.SLOTS:
        pool = rater.pool(slot)
        ranked = sorted(pool.value.items(), key=lambda kv: kv[1], reverse=True)
        for pid, _ in ranked:
            if pid not in used:
                used.add(pid)
                selections.append(Selection(slot, pid))
                break
    return Build(creator="demo", selections=tuple(selections))


def render(card) -> None:
    print(f"\n  {APP_NAME} — created {card.date}")
    print("  " + "─" * 46)
    print(f"  OVR {card.ovr:<3}{'':22}${card.contract / 1_000_000:.1f}M/yr\n")
    for r in card.ratings:
        detail = r.note or f"{r.player_name}"
        salary = f"${r.salary / 1_000_000:.1f}M" if r.salary else "—"
        print(f"  {r.label:<20}{r.rating:>3}   {detail:<16}{salary:>8}")
    print("  " + "─" * 46)
    print(f"  value: {card.value_per_million:.2f} OVR per $M/yr\n")


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "build":
        print(__doc__.strip())
        return 2
    date = argv[2]
    night = FixtureSource().load(date)
    rater = NightRater(night.boxscores)
    card = build_card(best_available(rater), rater, night.date)
    if card.void:
        print(f"VOID: {card.void_reason}")
        return 1
    render(card)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
