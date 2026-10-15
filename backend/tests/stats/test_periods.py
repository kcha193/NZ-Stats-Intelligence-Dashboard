import pytest

from nzstats.stats.periods import add_months, month_label, month_range, months_between, parse_month


def test_add_months_crosses_year_boundaries() -> None:
    assert add_months("2026-01", -1) == "2025-12"
    assert add_months("2025-12", 1) == "2026-01"
    assert add_months("2026-07", -12) == "2025-07"
    assert add_months("2026-07", 0) == "2026-07"


def test_months_between_and_range() -> None:
    assert months_between("2025-11", "2026-02") == 3
    assert month_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert month_range("2026-02", "2025-11") == []


def test_label_and_validation() -> None:
    assert month_label("2026-08") == "August 2026"
    with pytest.raises(ValueError):
        parse_month("2026-13")
    with pytest.raises(ValueError):
        parse_month("nonsense")
