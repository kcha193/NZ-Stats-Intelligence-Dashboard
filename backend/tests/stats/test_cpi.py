import pytest

from nzstats.stats.cpi import (
    annual_changes,
    contiguous_run,
    is_quarter_end,
    quarterly_changes,
)

# Published June 2026 index levels (Stats NZ, base June 2017 = 1000).
ALL = {"2025-06": 1306, "2025-09": 1319, "2025-12": 1327, "2026-03": 1339, "2026-06": 1359}
TRADABLES = {"2025-06": 1198, "2025-09": 1208, "2025-12": 1216, "2026-03": 1224, "2026-06": 1257}
NON_TRADABLES = {
    "2025-06": 1391,
    "2025-09": 1406,
    "2025-12": 1415,
    "2026-03": 1430,
    "2026-06": 1438,
}


@pytest.mark.parametrize(
    ("levels", "quarterly", "annual"),
    [(ALL, 1.5, 4.1), (TRADABLES, 2.7, 4.9), (NON_TRADABLES, 0.6, 3.4)],
)
def test_june_2026_benchmarks(levels, quarterly, annual):
    assert round(quarterly_changes(levels)["2026-06"], 1) == quarterly
    assert round(annual_changes(levels)["2026-06"], 1) == annual


def test_changes_use_formula_on_unrounded_ratio():
    assert quarterly_changes(ALL)["2026-06"] == pytest.approx((1359 / 1339 - 1) * 100)
    assert annual_changes(ALL)["2026-06"] == pytest.approx((1359 / 1306 - 1) * 100)


def test_first_observations_have_no_change_and_gaps_are_not_bridged():
    levels = {k: v for k, v in ALL.items() if k != "2025-12"}
    assert set(quarterly_changes(levels)) == {"2025-09", "2026-06"}
    assert "2026-03" not in quarterly_changes(levels)  # its predecessor 2025-12 is missing
    assert set(annual_changes(levels)) == {"2026-06"}  # 2025-06 exists, 2025-03 does not


def test_annual_requires_the_same_quarter_a_year_earlier():
    levels = {**ALL, "2024-06": 1272}
    assert set(annual_changes(levels)) == {"2025-06", "2026-06"}


@pytest.mark.parametrize("bad", [0, -5, float("nan"), float("inf")])
def test_non_positive_or_non_finite_levels_are_rejected(bad):
    with pytest.raises(ValueError):
        quarterly_changes({"2026-03": 1339, "2026-06": bad})


def test_non_quarter_end_period_is_rejected():
    with pytest.raises(ValueError):
        quarterly_changes({"2026-04": 1339, "2026-07": 1359})
    assert is_quarter_end("2026-06") and not is_quarter_end("2026-05")


def test_contiguous_run_returns_latest_unbroken_quarters():
    periods = ["2025-06", "2025-09", "2026-03", "2026-06", "2025-12"]
    assert contiguous_run(periods) == ["2025-06", "2025-09", "2025-12", "2026-03", "2026-06"]
    assert contiguous_run(["2024-12", "2025-09", "2025-12", "2026-03"]) == [
        "2025-09",
        "2025-12",
        "2026-03",
    ]
    assert contiguous_run([]) == []
