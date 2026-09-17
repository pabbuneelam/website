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
    corner3m: int | None = None
    wing3m: int | None = None
    left_side_fgm: int | None = None
    lobs: int | None = None

    @property
    def reb(self) -> int:
        return self.orb + self.drb

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
class Pick:
    """One allocation. ``backup_player_id`` resolves at BACKUP_FACTOR if the
    starter does not play."""

    category_id: str
    player_id: int
    allocated: float
    backup_player_id: int | None = None


@dataclass(frozen=True)
class Lineup:
    entrant: str
    picks: tuple[Pick, ...]


@dataclass(frozen=True)
class ScoredPick:
    category_id: str
    player_id: int
    scored_player_id: int  # differs from player_id when the backup was used
    allocated: float
    actual: float | None
    projected: float | None
    residual: float | None
    z: float | None
    multiplier: float
    boost: float
    factor: float  # 1.0, or BACKUP_FACTOR when the backup played
    score: float
    note: str = ""


@dataclass(frozen=True)
class Result:
    entrant: str
    total: float
    picks: tuple[ScoredPick, ...] = field(default_factory=tuple)
    void: bool = False
    void_reason: str = ""
