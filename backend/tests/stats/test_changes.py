import pytest

from nzstats.stats.changes import abs_change, lagged_change, pct_change, pp_diff


@pytest.mark.parametrize(
    ("cur", "prev", "expected"),
    [
        (110.0, 100.0, 10.0),
        (90.0, 100.0, -10.0),
        (0.0, 100.0, -100.0),
        (5.0, 0.0, None),  # zero denominator
        (5.0, None, None),  # missing
        (None, 5.0, None),
        (-5.0, -10.0, None),  # negative base: undefined
        (5.0, -10.0, None),  # sign flip
        (-5.0, 10.0, None),  # sign flip
    ],
)
def test_pct_change_is_only_defined_for_positive_base(cur, prev, expected) -> None:
    result = pct_change(cur, prev)
    assert result == (pytest.approx(expected) if expected is not None else None)


def test_abs_change_handles_negatives_and_missing() -> None:
    assert abs_change(5.0, 3.0) == 2.0
    assert abs_change(-5.0, 3.0) == -8.0
    assert abs_change(None, 3.0) is None
    assert abs_change(5.0, None) is None


def test_pp_diff() -> None:
    assert pp_diff(5.1, 4.9) == pytest.approx(0.2)
    assert pp_diff(None, 4.9) is None


def test_lagged_change_year_on_year() -> None:
    series = {"2025-07": 100.0, "2026-07": 110.0}
    ch = lagged_change(series, "2026-07", 12)
    assert ch is not None
    assert ch.comparison_period == "2025-07"
    assert ch.absolute == 10.0
    assert ch.percent == pytest.approx(10.0)


def test_lagged_change_missing_or_nonpositive_base() -> None:
    assert lagged_change({"2026-07": 1.0}, "2026-07", 12) is None
    ch = lagged_change({"2025-07": -4.0, "2026-07": 6.0}, "2026-07", 12)
    assert ch is not None and ch.absolute == 10.0 and ch.percent is None
