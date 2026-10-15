import pytest

from nzstats.stats.percentile import percentile_context


def test_highest_value() -> None:
    ctx = percentile_context(5, [1, 2, 3, 4, 5])
    assert ctx is not None
    assert (ctx.rank, ctx.n, ctx.percentile) == (1, 5, 100.0)


def test_middle_value() -> None:
    ctx = percentile_context(3, [1, 2, 3, 4, 5])
    assert ctx is not None
    assert (ctx.rank, ctx.percentile) == (3, 60.0)


def test_ties_share_best_rank() -> None:
    ctx = percentile_context(3, [3, 3, 1])
    assert ctx is not None
    assert ctx.rank == 1 and ctx.percentile == pytest.approx(100.0)


def test_too_little_history() -> None:
    assert percentile_context(3, [3]) is None
    assert percentile_context(3, []) is None
