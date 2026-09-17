"""One pure function per metric, over a single BoxScore.

Returning ``None`` means "this player has no valid value in this category
tonight". That single signal does two jobs: it drops the player from the
category's percentile pool, and it scores any pick on him as zero. That is what
stops a 1-for-1 night from winning the shooting category.
"""
from __future__ import annotations

from collections.abc import Callable

from .models import BoxScore
from .rules import MIN_FGA_FOR_TS, MIN_MINUTES_FOR_PM

Metric = Callable[[BoxScore], float | None]


def _pts(b: BoxScore) -> float | None:
    return float(b.pts)


def _reb(b: BoxScore) -> float | None:
    return float(b.reb)


def _ast(b: BoxScore) -> float | None:
    return float(b.ast)


def _stl(b: BoxScore) -> float | None:
    return float(b.stl)


def _blk(b: BoxScore) -> float | None:
    return float(b.blk)


def _tov(b: BoxScore) -> float | None:
    # Lower is better, so the sign is flipped before it ever reaches a percentile.
    return float(-b.tov)


def _stocks(b: BoxScore) -> float | None:
    return float(b.stl + b.blk)


def _ast_to(b: BoxScore) -> float | None:
    return float(b.ast - b.tov)


def _ts_pct(b: BoxScore) -> float | None:
    if b.fga < MIN_FGA_FOR_TS:
        return None
    denom = 2.0 * (b.fga + 0.44 * b.fta)
    if denom <= 0:
        return None
    return b.pts / denom


def _plus_minus(b: BoxScore) -> float | None:
    if b.minutes < MIN_MINUTES_FOR_PM:
        return None
    return float(b.plus_minus)


def _game_score(b: BoxScore) -> float | None:
    """Hollinger Game Score, exactly as written in SLATE.md."""
    return (
        b.pts
        + 0.4 * b.fgm
        - 0.7 * b.fga
        - 0.4 * (b.fta - b.ftm)
        + 0.7 * b.orb
        + 0.3 * b.drb
        + b.stl
        + 0.7 * b.ast
        + 0.7 * b.blk
        - 0.4 * b.pf
        - b.tov
    )


def _pbp(attr: str) -> Metric:
    """Play-by-play derived metric. ``None`` on any source below GOAT tier."""

    def metric(b: BoxScore) -> float | None:
        value = getattr(b, attr)
        return None if value is None else float(value)

    return metric


METRICS: dict[str, Metric] = {
    "pts": _pts,
    "reb": _reb,
    "ast": _ast,
    "stl": _stl,
    "blk": _blk,
    "tov_neg": _tov,
    "stocks": _stocks,
    "ast_to": _ast_to,
    "ts_pct": _ts_pct,
    "plus_minus": _plus_minus,
    "game_score": _game_score,
    "corner3m": _pbp("corner3m"),
    "wing3m": _pbp("wing3m"),
    "left_side_fgm": _pbp("left_side_fgm"),
    "lobs": _pbp("lobs"),
}
