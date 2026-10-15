from nzstats.stats.rolling import rolling_by_period


def test_rolling_sum_over_contiguous_months() -> None:
    s = {"2026-01": 1.0, "2026-02": 2.0, "2026-03": 3.0, "2026-04": 4.0}
    assert rolling_by_period(s, 3) == {"2026-03": 6.0, "2026-04": 9.0}


def test_rolling_skips_windows_with_gaps() -> None:
    s = {"2026-01": 1.0, "2026-03": 3.0, "2026-04": 4.0, "2026-05": 5.0}
    assert rolling_by_period(s, 3) == {"2026-05": 12.0}


def test_rolling_mean_and_year_boundary() -> None:
    s = {"2025-12": 2.0, "2026-01": 4.0}
    assert rolling_by_period(s, 2, mean=True) == {"2026-01": 3.0}


def test_window_larger_than_data() -> None:
    assert rolling_by_period({"2026-01": 1.0}, 12) == {}
