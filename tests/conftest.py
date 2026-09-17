from __future__ import annotations

import pytest

from slate.models import BoxScore
from slate.sources import FixtureSource

DEFAULTS = dict(
    player_id=1, player_name="P", team="BOS", opponent="NYK", minutes=30.0,
    pts=0, fgm=0, fga=0, ftm=0, fta=0, fg3m=0, fg3a=0, orb=0, drb=0,
    ast=0, stl=0, blk=0, tov=0, pf=0, plus_minus=0,
)


def box(**kw) -> BoxScore:
    """A box score with everything zeroed except what the test cares about."""
    return BoxScore(**{**DEFAULTS, **kw})


@pytest.fixture
def night():
    return FixtureSource().load("2025-11-14")
