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

    ``uid`` is the *current owner* and moves when the card is traded;
    ``creator_name`` and the uid baked into ``card_id`` are the creator and
    never move. That is why a card's id is stable across a trade.
    """

    card_id: str
    uid: str                   # verified Firebase identity of the current owner
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


@dataclass(frozen=True)
class League:
    """A group of players, joined by invite code.

    One league holds many users; a user belongs to exactly one league at a
    time (see `Membership`), so there is no team layer here -- `uid` keys
    everything league-scoped, exactly as it keys a card.

    ``code`` is the whole join flow: there is no browse, no discovery and no
    moderation surface, so the code is the only way in and is meant to be
    pasted into a group chat.
    """

    league_id: str
    name: str
    code: str
    owner_uid: str
    created_at: str = ""       # ISO 8601 UTC


@dataclass(frozen=True)
class Membership:
    """One user's place in one league.

    Keyed by uid alone, which is what enforces "exactly one league at a time"
    structurally rather than by checking: there is nowhere to put a second
    one.
    """

    uid: str
    league_id: str
    # Denormalised like Card.creator_name -- a roster has to name its members
    # without a read per member. A snapshot; the profile is current truth.
    display_name: str = ""
    joined_at: str = ""        # ISO 8601 UTC


# Status values a trade can hold. `pending` is the only actionable one; the
# other three are terminal, which is what stops a trade being accepted twice.
TRADE_PENDING = "pending"
TRADE_ACCEPTED = "accepted"
TRADE_REJECTED = "rejected"
TRADE_CANCELLED = "cancelled"
TRADE_TERMINAL = (TRADE_ACCEPTED, TRADE_REJECTED, TRADE_CANCELLED)


@dataclass(frozen=True)
class Trade:
    """One card offered for one card, between two members of one league.

    Card-for-card and nothing else: no currency, because a currency turns
    good predictors into farmers running a secondary market. Build picks and
    cap space are the other two tradeable assets in the design and are
    deliberately absent -- neither has an entitlement model yet, and there is
    no payroll cap for "both sides must end cap-legal" to validate against.

    ``league_id`` is stamped at propose time so a trade records the league it
    was made in even after someone leaves it. Both display names are
    denormalised like ``Card.creator_name`` -- an inbox has to name the other
    side without a read per row.
    """

    trade_id: str
    league_id: str
    proposer_uid: str
    recipient_uid: str
    offered_card_id: str        # the proposer's card, going out
    requested_card_id: str      # the recipient's card, coming back
    status: str = TRADE_PENDING
    proposer_name: str = ""
    recipient_name: str = ""
    created_at: str = ""        # ISO 8601 UTC
    resolved_at: str = ""       # ISO 8601 UTC; empty while pending
    resolution_note: str = ""   # why, when it was not a plain accept/reject

    @property
    def pending(self) -> bool:
        return self.status == TRADE_PENDING
