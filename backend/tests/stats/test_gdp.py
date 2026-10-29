import pytest

from nzstats.stats.gdp import annual_average_changes, round_1dp


def _quarters(start_year: int, values: list[float]) -> dict[str, float]:
    out, y, q = {}, start_year, 0
    for v in values:
        out[f"{y}-{(q + 1) * 3:02d}"] = v
        q += 1
        if q == 4:
            y, q = y + 1, 0
    return out


def test_annual_average_compares_sums_of_four_quarters():
    levels = _quarters(2024, [100, 100, 100, 100, 101, 102, 103, 104])
    # year ended Dec 2025 (410) against year ended Dec 2024 (400)
    assert annual_average_changes(levels) == {"2025-12": pytest.approx(2.5)}


def test_annual_average_needs_eight_consecutive_quarters():
    levels = _quarters(2024, [100, 100, 100, 100, 101, 102, 103, 104])
    del levels["2024-06"]
    assert annual_average_changes(levels) == {}


def test_annual_average_differs_from_annual_change_of_the_quarter():
    levels = _quarters(2024, [100, 100, 100, 100, 101, 102, 103, 110])
    # annual change of the quarter would be 10%; the annual average is 4%
    assert annual_average_changes(levels)["2025-12"] == pytest.approx(4.0)


def test_annual_average_rejects_non_quarter_periods():
    with pytest.raises(ValueError):
        annual_average_changes({"2025-01": 1.0})


@pytest.mark.parametrize(
    ("value", "rounded"),
    [(0.25, 0.3), (-0.25, -0.3), (0.249999, 0.2), (1.75, 1.8), (0.05, 0.1), (-0.04, -0.0)],
)
def test_round_half_away_from_zero(value, rounded):
    assert round_1dp(value) == rounded
