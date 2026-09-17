from __future__ import annotations

import pytest

from slate.score import percentile_rank


def test_empty_pool_scores_zero():
    assert percentile_rank(5.0, []) == 0.0


def test_single_player_pool_sits_in_the_middle():
    assert percentile_rank(5.0, [5.0]) == 0.5


def test_ties_split_the_difference():
    """Two identical nights must score identically, not arbitrarily ordered."""
    # one value below, two equal -> (1 + 0.5*2) / 4
    pool = [1.0, 2.0, 2.0, 3.0]
    assert percentile_rank(2.0, pool) == pytest.approx(0.5)


def test_bounds():
    pool = [1.0, 2.0, 3.0, 4.0]
    assert percentile_rank(0.0, pool) == 0.0
    assert percentile_rank(9.0, pool) == 1.0


def test_result_is_always_within_zero_and_one():
    pool = [-3.0, 0.0, 0.0, 7.5, 100.0]
    for v in (-99.0, -3.0, 0.0, 7.5, 1e9):
        assert 0.0 <= percentile_rank(v, pool) <= 1.0
