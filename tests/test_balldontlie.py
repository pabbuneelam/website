from __future__ import annotations

import pytest

from slate.sources.balldontlie import (
    BallDontLieSource,
    _matchups,
    _minutes,
    _opponent,
    _parse_box,
    _parse_game,
    _player_name,
)

GAME = {
    "id": 1,
    "datetime": "2025-11-14T19:30:00.000Z",
    "home_team": {"id": 2, "abbreviation": "BOS"},
    "visitor_team": {"id": 3, "abbreviation": "NYK"},
}

STAT_ROW = {
    "min": "34",
    "pts": 21,
    "fgm": 8,
    "fga": 15,
    "fg3m": 3,
    "fg3a": 7,
    "ftm": 2,
    "fta": 2,
    "oreb": 1,
    "dreb": 5,
    "ast": 4,
    "stl": 1,
    "blk": 0,
    "turnover": 2,
    "pf": 3,
    "plus_minus": 8,
    "player": {"id": 101, "first_name": "R.", "last_name": "Okonkwo"},
    "team": {"id": 2, "abbreviation": "BOS"},
    "game": {"id": 1},
}

ADVANCED_ROW = {
    "player": {"id": 101},
    "contested_fgm": 4,
    "contested_fga": 7,
    "uncontested_fgm": 4,
    "uncontested_fga": 8,
    "rebound_chances_total": 6,
    "deflections": 2,
    "matchup_minutes": 12.0,
    "matchup_fgm": 3,
    "matchup_fga": 9,
    "defended_at_rim_fgm": 1,
    "defended_at_rim_fga": 4,
}


def test_minutes_parses_plain_number_string():
    assert _minutes("34") == 34.0


def test_minutes_parses_mm_ss():
    assert _minutes("34:30") == pytest.approx(34.5)


def test_minutes_handles_dnp():
    assert _minutes("") == 0.0
    assert _minutes(None) == 0.0


def test_minutes_handles_garbage_without_raising():
    assert _minutes("DNP") == 0.0


def test_player_name_joins_first_and_last():
    assert _player_name({"first_name": "R.", "last_name": "Okonkwo"}) == "R. Okonkwo"


def test_parse_game_maps_teams_and_tipoff():
    game = _parse_game(GAME)
    assert game.game_id == 1
    assert game.home == "BOS"
    assert game.away == "NYK"
    assert game.tipoff == "2025-11-14T19:30:00.000Z"


def test_opponent_is_the_other_team_in_the_matchup():
    matchup = _matchups([GAME])[1]
    assert _opponent(2, matchup) == "NYK"
    assert _opponent(3, matchup) == "BOS"


def test_parse_box_without_advanced_leaves_tracking_fields_none():
    matchups = _matchups([GAME])
    box = _parse_box(STAT_ROW, matchups, None)
    assert box.player_id == 101
    assert box.player_name == "R. Okonkwo"
    assert box.team == "BOS"
    assert box.opponent == "NYK"
    assert box.minutes == 34.0
    assert box.pts == 21
    assert box.orb == 1 and box.drb == 5
    assert box.tov == 2
    assert box.rim_fgm is None and box.rim_fga is None
    assert box.contested_fga is None


def test_parse_box_with_advanced_fills_tracking_fields():
    matchups = _matchups([GAME])
    box = _parse_box(STAT_ROW, matchups, ADVANCED_ROW)
    assert box.contested_fga == 7
    assert box.rebound_chances_total == 6
    assert box.matchup_fga == 9
    assert box.defended_at_rim_fgm == 1
    # balldontlie has no offensive rim_fga/rim_fgm field at all.
    assert box.rim_fgm is None and box.rim_fga is None


def test_capabilities_by_tier():
    assert BallDontLieSource("k", tier="free").capabilities() == frozenset()
    assert BallDontLieSource("k", tier="allstar").capabilities() == {"boxscore"}
    assert BallDontLieSource("k", tier="goat").capabilities() == {
        "boxscore",
        "pbp",
        "advanced",
    }


def test_unknown_tier_rejected():
    with pytest.raises(ValueError):
        BallDontLieSource("k", tier="rookie")


def test_load_raises_file_not_found_when_no_games(monkeypatch):
    """api._night() only catches FileNotFoundError to fall back to the sample
    night -- a date with no games on balldontlie must raise that, not a
    generic error, or every off night 500s instead of degrading."""
    source = BallDontLieSource("k", tier="allstar")
    monkeypatch.setattr(source, "_paginate", lambda path, params: [])
    with pytest.raises(FileNotFoundError):
        source.load("2099-01-01")


def test_load_skips_advanced_fetch_below_goat_tier(monkeypatch):
    source = BallDontLieSource("k", tier="allstar")
    calls: list[str] = []

    def fake_paginate(path, params):
        calls.append(path)
        if path == "/v1/games":
            return [GAME]
        if path == "/v1/stats":
            return [STAT_ROW]
        raise AssertionError(f"should not call {path} below GOAT tier")

    monkeypatch.setattr(source, "_paginate", fake_paginate)
    night = source.load("2025-11-14")
    assert "/v2/stats/advanced" not in calls
    assert len(night.boxscores) == 1
    assert night.boxscores[0].rim_fgm is None


def test_load_fetches_advanced_stats_at_goat_tier(monkeypatch):
    source = BallDontLieSource("k", tier="goat")

    def fake_paginate(path, params):
        return {
            "/v1/games": [GAME],
            "/v1/stats": [STAT_ROW],
            "/v2/stats/advanced": [ADVANCED_ROW],
        }[path]

    monkeypatch.setattr(source, "_paginate", fake_paginate)
    night = source.load("2025-11-14")
    assert night.boxscores[0].rebound_chances_total == 6


def test_load_drops_players_who_did_not_play(monkeypatch):
    source = BallDontLieSource("k", tier="allstar")
    dnp_row = dict(STAT_ROW, min="", player={"id": 202, "first_name": "B", "last_name": "Bench"})

    def fake_paginate(path, params):
        if path == "/v1/games":
            return [GAME]
        if path == "/v1/stats":
            return [STAT_ROW, dnp_row]
        return []

    monkeypatch.setattr(source, "_paginate", fake_paginate)
    night = source.load("2025-11-14")
    assert [b.player_id for b in night.boxscores] == [101]
