from datetime import UTC, datetime

from nzstats.pipeline.discover import discovery_months


def test_discovery_months_include_the_previous_month() -> None:
    assert discovery_months(datetime(2026, 10, 11, tzinfo=UTC)) == ["2026-09", "2026-10", "2026-11"]
    assert discovery_months(datetime(2027, 1, 5, tzinfo=UTC)) == ["2026-12", "2027-01", "2027-02"]
