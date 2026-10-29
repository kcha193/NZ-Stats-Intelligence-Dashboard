"""A later historical vintage can be displayed but cannot replace a first-published outcome."""

from nzstats.research.accuracy import evaluate_forecasts
from nzstats.research.macro_outcomes import gdp_actuals
from tests.macro_support import ingest_gdp

from .test_compare import claim


def test_unverified_baseline_is_not_scored_or_included_in_accuracy_samples(rt, site):
    ingest_gdp(rt, site, "2026-06")
    forecast = claim(
        indicator="gdp",
        indicator_label="Real GDP growth, quarterly",
        horizon="June 2026 quarter",
        value=0.5,
        published_on="2026-05-01",
    )
    out = evaluate_forecasts([forecast], gdp_actuals(rt.conn), indicator="gdp")
    row = out.evaluated[0]
    assert row.first.value == 0.2 and row.first.first_release is False
    assert row.latest.value == 0.2 and row.error_latest == 0.3
    assert row.error_first is None and row.outcome_revision is None
    assert out.summaries == []
    assert all(not ranking.available and ranking.matched_cells == 0 for ranking in out.rankings)


def test_release_day_original_capture_can_be_scored(rt, site):
    ingest_gdp(rt, site, "2026-06")
    # Simulated acquisition timing, independent of the actual fixture's historical capture.
    rt.conn.execute("UPDATE vintage SET captured_at = '2026-09-16T22:45:00Z'")
    forecast = claim(
        indicator="gdp",
        indicator_label="Real GDP growth, quarterly",
        horizon="June 2026 quarter",
        value=0.5,
        published_on="2026-05-01",
    )
    out = evaluate_forecasts([forecast], gdp_actuals(rt.conn), indicator="gdp")
    assert out.evaluated[0].first.first_release
    assert out.evaluated[0].error_first == 0.3
    assert out.summaries[0].n == 1
