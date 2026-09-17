"""Store contract. MemoryStore runs everywhere; FirestoreStore runs only when
credentials are present, against the real project."""
from __future__ import annotations

import os

import pytest

from slate.models import Lineup, Pick
from slate.store import MemoryStore, _from_dict, _to_dict

LINEUP = Lineup(
    entrant="vrishin",
    picks=(
        Pick("PTS", 101, 300.0, backup_player_id=121),
        Pick("AST_TO", 105, 400.0),
    ),
)


@pytest.fixture(params=[MemoryStore], ids=["memory"])
def store(request):
    # A factory, not an instance -- each test needs its own empty store.
    return request.param()


def test_lineup_survives_a_round_trip_through_json():
    """Picks are frozen dataclasses; the store has to flatten and rebuild them
    without losing the optional backup."""
    assert _from_dict(_to_dict(LINEUP)) == LINEUP


def test_backupless_pick_round_trips():
    lu = Lineup(entrant="x", picks=(Pick("REB", 1, 100.0),))
    assert _from_dict(_to_dict(lu)).picks[0].backup_player_id is None


def test_saving_a_lineup_makes_it_readable(store):
    store.save_lineup("2025-11-14", LINEUP)
    assert store.lineups("2025-11-14") == [LINEUP]


def test_resubmitting_replaces_rather_than_duplicates(store):
    """One lineup per entrant per night. Editing before lock must not stack."""
    store.save_lineup("2025-11-14", LINEUP)
    revised = Lineup(entrant="vrishin", picks=(Pick("REB", 999, 500.0),))
    store.save_lineup("2025-11-14", revised)
    assert store.lineups("2025-11-14") == [revised]


def test_entrants_do_not_collide(store):
    store.save_lineup("2025-11-14", LINEUP)
    store.save_lineup("2025-11-14", Lineup(entrant="pabb", picks=(Pick("REB", 7, 100.0),)))
    assert {lu.entrant for lu in store.lineups("2025-11-14")} == {"vrishin", "pabb"}


def test_unknown_date_is_empty_not_an_error(store):
    assert store.lineups("1999-01-01") == []


def test_history_accumulates_one_entry_per_night(store):
    """This is the point of persisting anything: the boost tuner cannot reach
    its 20-night threshold if history dies with the process."""
    store.save_residuals("2025-11-14", {"PTS": [0.1, -0.4]})
    store.save_residuals("2025-11-15", {"PTS": [1.2], "REB": [0.3]})
    history = store.history()
    assert history["PTS"] == [[0.1, -0.4], [1.2]]
    assert history["REB"] == [[0.3]]


def test_history_is_ordered_by_date(store):
    store.save_residuals("2025-11-15", {"PTS": [2.0]})
    store.save_residuals("2025-11-14", {"PTS": [1.0]})
    assert store.history()["PTS"] == [[1.0], [2.0]]


def test_history_is_empty_before_anything_is_resolved(store):
    assert store.history() == {}


@pytest.mark.skipif(
    not os.environ.get("SLATE_FIREBASE_PROJECT"),
    reason="set SLATE_FIREBASE_PROJECT and GOOGLE_APPLICATION_CREDENTIALS to run",
)
def test_firestore_satisfies_the_same_contract():
    from slate.store import FirestoreStore

    store = FirestoreStore()
    store.save_lineup("_test", LINEUP)
    assert LINEUP in store.lineups("_test")


def test_boosts_stay_on_seeds_at_nineteen_nights_and_tune_at_twenty():
    """The whole reason the store exists. Wired end to end: residuals land in
    the store, the store feeds the tuner, the tuner moves off the seed."""
    from slate import catalog
    from slate.tune import BoostTuner

    store = MemoryStore()
    for night in range(19):
        store.save_residuals(f"2025-11-{night + 1:02d}", {"PTS": [-3.0, 0.0, 3.0]})
    assert BoostTuner().boosts(store.history())["PTS"] == catalog.get("PTS").seed_boost

    store.save_residuals("2025-12-01", {"PTS": [-3.0, 0.0, 3.0]})
    assert BoostTuner().boosts(store.history())["PTS"] > catalog.get("PTS").seed_boost
