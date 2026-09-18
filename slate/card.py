"""Assembling six selections into a created player.

The contract is the honest half of the game: a card's cost is the average of
the real annual salaries of the six players who supplied its attributes. That
is what makes a 94 at $14M a better asset than a 96 at $50M, and what makes
rookie deals and minimum contracts worth hunting for.
"""
from __future__ import annotations

from . import attributes
from .models import Build, Card, Rating, Selection
from .score import NightRater


def card_id(creator: str, date: str) -> str:
    """One build per creator per night, so this is a natural key. Deterministic
    rather than random, which keeps replays and tests reproducible."""
    return f"{date}:{creator}"


def validate(build: Build) -> str:
    """Empty string when the build is legal, else why it is not."""
    selections = build.selections
    if len(selections) != len(attributes.SLOTS):
        return f"a build needs exactly {len(attributes.SLOTS)} selections"

    seen_slots: set[str] = set()
    seen_players: set[int] = set()
    for sel in selections:
        try:
            attributes.get(sel.slot)
        except KeyError as exc:
            return str(exc)
        if sel.slot in seen_slots:
            return f"{sel.slot} filled twice"
        seen_slots.add(sel.slot)
        # One player supplies one quality. Otherwise the best night of the
        # slate would fill the whole card.
        if sel.player_id in seen_players:
            return f"player {sel.player_id} used for more than one attribute"
        seen_players.add(sel.player_id)

    missing = set(attributes.SLOTS) - seen_slots
    if missing:
        return f"missing {', '.join(sorted(missing))}"
    return ""


def build_card(build: Build, rater: NightRater, date: str) -> Card:
    problem = validate(build)
    if problem:
        return Card(
            card_id=card_id(build.creator, date), creator=build.creator,
            date=date, ovr=0, contract=0, ratings=(),
            void=True, void_reason=problem,
        )

    ratings: list[Rating] = []
    for sel in build.selections:
        attribute = attributes.get(sel.slot)
        rating, value, percentile, note = rater.rate(sel.slot, sel.player_id)
        box = rater.boxes.get(sel.player_id)
        ratings.append(
            Rating(
                slot=sel.slot,
                label=attribute.label,
                player_id=sel.player_id,
                player_name=box.player_name if box else "unknown",
                rating=rating,
                value=value,
                percentile=percentile,
                salary=box.salary if box else None,
                note=note,
                pts=box.pts if box else 0,
                reb=box.reb if box else 0,
                ast=box.ast if box else 0,
                # A standard points-reb-ast fantasy formula -- not the OVR
                # scoring, just a familiar single number for the recap chart.
                fantasy=round(box.pts + 1.2 * box.reb + 1.5 * box.ast + 3 * box.stl + 3 * box.blk - box.tov, 1)
                if box
                else 0.0,
            )
        )

    ovr = round(sum(r.rating for r in ratings) / len(ratings))

    # A player with no salary on file is treated as absent from the average
    # rather than as free -- otherwise missing data would look like a bargain.
    salaries = [r.salary for r in ratings if r.salary is not None]
    contract = round(sum(salaries) / len(salaries)) if salaries else 0

    return Card(
        card_id=card_id(build.creator, date), creator=build.creator,
        date=date, ovr=ovr, contract=contract, ratings=tuple(ratings),
    )
