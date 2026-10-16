"""F03: response time must not masquerade as refreshed statistics."""

from datetime import UTC, datetime

from nzstats.insights.overview import build_overview
from tests.support import NOW, ingest_months


def test_overview_uses_selected_bundle_capture_time_not_response_time(rt):
    ingest_months(rt, "2026-07")
    result = build_overview(
        rt.conn,
        analysable_slugs={"international-migration"},
        now=datetime(2026, 10, 16, tzinfo=UTC),
    )
    assert result.generated_at.startswith("2026-10-16")
    assert result.data_updated_at == "2026-10-11T16:00:00+13:00"


def test_empty_overview_has_no_data_update_timestamp(rt):
    result = build_overview(rt.conn, analysable_slugs={"international-migration"}, now=NOW)
    assert result.data_updated_at is None
