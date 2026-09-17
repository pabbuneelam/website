"""Reads a stored night from JSON. This is what the tests and Replay mode run on."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import BoxScore, SlateGame
from .base import NightData

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _box(raw: dict) -> BoxScore:
    return BoxScore(**raw)


class FixtureSource:
    def __init__(self, directory: Path | str = FIXTURE_DIR) -> None:
        self.directory = Path(directory)

    def capabilities(self) -> frozenset[str]:
        # The committed fixture carries play-by-play fields too, so the location
        # categories can be exercised in tests without paying for GOAT.
        return frozenset({"boxscore", "pbp"})

    def load(self, date: str) -> NightData:
        path = self.directory / f"{date}.json"
        if not path.exists():
            raise FileNotFoundError(f"no fixture for {date} at {path}")
        raw = json.loads(path.read_text())

        games = tuple(SlateGame(**g) for g in raw["games"])
        boxscores = tuple(_box(b) for b in raw["boxscores"])
        logs = {
            int(pid): [(int(e["season_offset"]), _box(e["box"])) for e in entries]
            for pid, entries in raw.get("logs", {}).items()
        }
        return NightData(date=raw["date"], games=games, boxscores=boxscores, logs=logs)
