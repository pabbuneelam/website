"""The six attributes, and how a night's performance becomes a rating.

Every attribute uses the same shape:

    value = what he produced
          - what a league-average player produces on the same opportunities
          × how hard those opportunities were

That single idea, instantiated six times. It is why 12 rebounds on 30 chances
rates below 8 on 12, and why eight contested threes rate above three open ones.

Returning ``None`` means the player has no valid value in this attribute
tonight -- guardrail failed, or the data source is below GOAT tier and the
field is absent. Either way he leaves the pool and cannot be picked for it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .models import BoxScore

# League-average rates. Guesses until a real season is loaded, and the single
# place to correct them -- every attribute measures against these.
LEAGUE_3P = 0.36
LEAGUE_RIM = 0.63
LEAGUE_FG = 0.47
LEAGUE_REB_CONVERSION = 0.60

# How much credit contested volume earns. 0 would make difficulty irrelevant.
CONTEST_WEIGHT = 0.5
DEFLECTION_VALUE = 1.2
BLOCK_VALUE = 1.0
TURNOVER_COST = 1.0

Slot = Literal["OUTSIDE", "FINISHING", "PLAYMAKING", "REBOUNDING", "PERIMETER_D", "INTERIOR_D"]
AttributeMetric = Callable[[BoxScore], float | None]


def _difficulty(b: BoxScore) -> float:
    """Scale by the share of shots that were contested. Falls back to 1.0 --
    neutral, not zero -- when tracking data is absent, so an attribute degrades
    to plain efficiency rather than breaking."""
    share = b.contested_share
    return 1.0 if share is None else 1.0 + CONTEST_WEIGHT * share


def outside_shooting(b: BoxScore) -> float | None:
    """Points added from three over a league-average shooter on the same
    attempts, scaled by shot difficulty."""
    if b.fg3a < 4:
        return None
    added = 3.0 * b.fg3m - 3.0 * LEAGUE_3P * b.fg3a
    return added * _difficulty(b)


def finishing(b: BoxScore) -> float | None:
    if b.rim_fga is None or b.rim_fgm is None or b.rim_fga < 3:
        return None
    added = 2.0 * b.rim_fgm - 2.0 * LEAGUE_RIM * b.rim_fga
    return added * _difficulty(b)


def playmaking(b: BoxScore) -> float | None:
    """Assists created, including the passes that do not show up as assists,
    net of turnovers."""
    if b.minutes < 15:
        return None
    secondary = b.secondary_assists or 0
    ft_assists = b.free_throw_assists or 0
    return b.ast + 0.5 * secondary + 0.5 * ft_assists - TURNOVER_COST * b.tov


def rebounding(b: BoxScore) -> float | None:
    """Conversion, not volume. Boards taken over what an average player takes
    from the same number of chances."""
    if b.rebound_chances_total is None or b.rebound_chances_total < 4:
        return None
    return b.reb - LEAGUE_REB_CONVERSION * b.rebound_chances_total


def perimeter_defense(b: BoxScore) -> float | None:
    """Field goals prevented against the man he guarded, plus disruption."""
    if b.matchup_minutes is None or b.matchup_minutes < 10:
        return None
    if b.matchup_fga is None or b.matchup_fgm is None:
        return None
    prevented = LEAGUE_FG * b.matchup_fga - b.matchup_fgm
    return prevented + DEFLECTION_VALUE * (b.deflections or 0)


def interior_defense(b: BoxScore) -> float | None:
    """Rim protection: shots missed at the rim against him, over what an
    average defender allows, plus blocks."""
    if b.defended_at_rim_fga is None or b.defended_at_rim_fga < 3:
        return None
    if b.defended_at_rim_fgm is None:
        return None
    prevented = LEAGUE_RIM * b.defended_at_rim_fga - b.defended_at_rim_fgm
    return prevented + BLOCK_VALUE * b.blk


@dataclass(frozen=True)
class Attribute:
    slot: str
    label: str
    metric: AttributeMetric
    requires: str      # data tier the metric needs
    guardrail: str


ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute("OUTSIDE", "Outside Shooting", outside_shooting, "boxscore", "min 4 3PA"),
    Attribute("FINISHING", "Finishing", finishing, "pbp", "min 3 rim FGA"),
    Attribute("PLAYMAKING", "Playmaking", playmaking, "boxscore", "min 15 minutes"),
    Attribute("REBOUNDING", "Rebounding", rebounding, "advanced", "min 4 rebound chances"),
    Attribute("PERIMETER_D", "Perimeter Defense", perimeter_defense, "advanced", "min 10 matchup minutes"),
    Attribute("INTERIOR_D", "Interior Defense", interior_defense, "advanced", "min 3 rim FGA defended"),
)

BY_SLOT: dict[str, Attribute] = {a.slot: a for a in ATTRIBUTES}
SLOTS: tuple[str, ...] = tuple(a.slot for a in ATTRIBUTES)


def get(slot: str) -> Attribute:
    try:
        return BY_SLOT[slot]
    except KeyError:
        raise KeyError(f"unknown attribute slot {slot!r}") from None
