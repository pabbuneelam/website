"""Where a night's data comes from. One protocol, so the tier decision is a
config flip rather than a rewrite."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..models import BoxScore, SlateGame


@dataclass(frozen=True)
class NightData:
    date: str
    games: tuple[SlateGame, ...]
    boxscores: tuple[BoxScore, ...]
    # Set when `date` has no data of its own and this is another night's
    # players standing in for it. Holds the date the data really comes from.
    sample_of: str | None = None


class SlateSource(Protocol):
    def load(self, date: str) -> NightData: ...

    def capabilities(self) -> frozenset[str]:
        """Which `Category.requires` values this source can satisfy."""
        ...
