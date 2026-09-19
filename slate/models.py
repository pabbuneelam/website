"""Core data types. Everything here is frozen and free of behaviour beyond arithmetic."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BoxScore:
    """One player's line in one game.

    The four trailing fields are play-by-play derived and stay ``None`` on any
    data source below the GOAT tier. Metrics that need them return ``None``,
    which is the same path a guardrail failure takes.
    """

    player_id: int
    player_name: str
    team: str
    opponent: str
    minutes: float
    pts: int
    fgm: int
    fga: int
    ftm: int
    fta: int
    fg3m: int
    fg3a: int
    orb: int
    drb: int
    ast: int
    stl: int
    blk: int
    tov: int
    pf: int
    plus_minus: int
    # --- annual salary, from the contracts endpoint (GOAT tier) -----------
    salary: int | None = None

    # --- advanced / tracking, all GOAT tier ------------------------------
    # None below GOAT. Any attribute needing one of these returns None, which
    # is the same path a guardrail failure takes.
    rim_fgm: int | None = None
    rim_fga: int | None = None
    contested_fgm: int | None = None
    contested_fga: int | None = None
    uncontested_fgm: int | None = None
    uncontested_fga: int | None = None
    secondary_assists: int | None = None
    free_throw_assists: int | None = None
    rebound_chances_total: int | None = None
    deflections: int | None = None
    matchup_minutes: float | None = None
    matchup_fgm: int | None = None
    matchup_fga: int | None = None
    defended_at_rim_fgm: int | None = None
    defended_at_rim_fga: int | None = None

    @property
    def reb(self) -> int:
        return self.orb + self.drb

    @property
    def contested_share(self) -> float | None:
        """Fraction of this player's shots that were contested. The closest
        thing to shot difficulty that exists below Second Spectrum."""
        if self.contested_fga is None or self.uncontested_fga is None:
            return None
        total = self.contested_fga + self.uncontested_fga
        return self.contested_fga / total if total else None

    @property
    def played(self) -> bool:
        return self.minutes > 0


@dataclass(frozen=True)
class SlateGame:
    game_id: int
    home: str
    away: str
    tipoff: str  # ISO 8601; lock is the earliest tipoff on the slate


@dataclass(frozen=True)
class Selection:
    """One attribute slot filled by one NBA player playing tonight."""

    slot: str
    player_id: int


@dataclass(frozen=True)
class Build:
    """A user's six selections for one night.

    ``uid`` is the verified Firebase identity and is the only thing that keys
    anything. ``display_name`` is user-controlled text carried along so a card
    can say who made it.
    """

    uid: str
    selections: tuple[Selection, ...]
    display_name: str = ""


@dataclass(frozen=True)
class Rating:
    """One attribute of a created player, and the real performance behind it."""

    slot: str
    label: str
    player_id: int
    player_name: str
    rating: int          # 0-99
    value: float | None  # difficulty-adjusted production over league average
    percentile: float
    salary: int | None
    note: str = ""

    # --- raw box score, revealed only once a card exists ------------------
    # The build screen never shows these (no stats before tip, see api.py) --
    # a card is the one place "the real performances behind every number"
    # actually shows up.
    pts: int = 0
    reb: int = 0
    ast: int = 0
    fantasy: float = 0.0


@dataclass(frozen=True)
class Card:
    """A created player. This is the artifact the whole game produces.

    A card outlives the roster it was made for -- it can be waived, claimed,
    signed and retired by other teams -- so it carries a stable id and records
    who created it from the moment it exists.
    """

    card_id: str
    uid: str                   # verified Firebase identity of the creator
    date: str
    ovr: int
    contract: int              # average annual salary of the players used
    ratings: tuple[Rating, ...]
    # Denormalised on purpose: a card outlives rosters and leagues, and the
    # UI has to name its creator without a second read. It is a snapshot --
    # the profile document is the current truth.
    creator_name: str = ""
    void: bool = False
    void_reason: str = ""

    @property
    def value_per_million(self) -> float:
        """OVR per $M/yr. The Moneyball number -- a 94 at $14M beats a 96 at $50M."""
        millions = self.contract / 1_000_000
        return self.ovr / millions if millions else 0.0


@dataclass(frozen=True)
class UserProfile:
    """One signed-in person.

    Written on first sign-in and refreshed on later ones. The uid comes from a
    verified token; everything else is whatever Google handed the browser.
    """

    uid: str
    display_name: str
    email: str | None = None
    photo_url: str | None = None
    created_at: str = ""       # ISO 8601 UTC, set once and never rewritten
