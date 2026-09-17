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


class SlateSource(Protocol):
    def load(self, date: str) -> NightData: ...

    def capabilities(self) -> frozenset[str]:
        """Which `Category.requires` values this source can satisfy."""
        ...
