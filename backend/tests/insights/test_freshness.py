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


def test_overview_reads_only_the_ect_kpi_series(rt, site):
    from nzstats.pipeline.ingest import ingest_release
    from tests.ect_support import seed_ect

    _, release_key, _ = seed_ect(rt, site)
    assert ingest_release(rt, release_key, now_fn=lambda: NOW).outcome == "ingested"
    statements = []
    rt.conn.set_trace_callback(statements.append)
    try:
        result = build_overview(rt.conn, analysable_slugs={"electronic-card-transactions"}, now=NOW)
    finally:
        rt.conn.set_trace_callback(None)

    ect = next(kpi for kpi in result.kpis if kpi.metric.series_key == "ect.m.sa.retail.value")
    observation_reads = [
        sql for sql in statements if "FROM observation" in sql and "WHERE vintage_id" in sql
    ]
    assert (ect.metric.period, ect.metric.value) == ("2026-09", 6976.0)
    assert result.data_updated_at == "2026-10-11T16:00:00+13:00"
    assert len(observation_reads) == 1
