import pytest

from nzstats.insights.cpi import build_cpi_dashboard
from tests.cpi_support import ingest_cpi, seed_cpi


@pytest.fixture()
def june(rt, site):
    ingest_cpi(rt, site, "2026-03", "2026-06")
    return build_cpi_dashboard(rt.conn)


def test_nothing_is_built_before_a_release_is_ingested(rt):
    assert build_cpi_dashboard(rt.conn) is None


def test_headline_metrics_are_rates_with_correct_comparisons(june):
    annual, quarterly, trad, non = june.analysis.headline_metrics[:4]
    assert (annual.series_key, annual.unit) == ("cpi.index.nsa.all_groups", "percent")
    assert round(annual.value, 1) == 4.1 and round(quarterly.value, 1) == 1.5
    assert round(trad.value, 1) == 4.9 and round(non.value, 1) == 3.4
    assert "annual" in annual.label.lower() and "quarterly" in quarterly.label.lower()
    prior = annual.change_prior
    assert prior.comparison_period == "2026-03" and round(prior.previous, 1) == 3.1
    assert prior.absolute == pytest.approx(annual.value - prior.previous)
    assert prior.percent is None  # a change in a rate is in percentage points, never a percent of a percent
    assert round(annual.change_year_ago.previous, 1) == 2.7
    assert annual.period == "2026-06" and annual.period_label == "Quarter ended June 2026"


def test_series_carry_derived_changes_without_bridging_gaps(june):
    series = {s.key: s for s in june.series}
    points = series["cpi.index.nsa.all_groups"].points
    assert points[0].quarterly_pct is None and points[0].annual_pct is None
    assert points[1].quarterly_pct is not None and points[3].annual_pct is None
    assert points[4].annual_pct is not None
    last = points[-1]
    assert (last.period, last.index) == ("2026-06", 1359.0)
    assert round(last.quarterly_pct, 1) == 1.5 and round(last.annual_pct, 1) == 4.1
    group = series["cpi.index.nsa.household_contents"]
    assert group.name.startswith("Household contents and services")
    assert group.classification == "Level 1 group" and group.source_reference == "CPIQ.SE905"
    assert series["cpi.index.nsa.electricity"].classification == "Level 3 class"
    assert series["cpi.index.sa.all_groups"].adjustment == "seasonally_adjusted"
    assert all(s.unit == "index" for s in june.series)
    assert not [s for s in june.series if "contrib" in s.key or "underlying" in s.key]


def test_contributions_are_published_values_with_the_gap_disclosed(june):
    q, a = june.contributions
    assert (q.horizon, a.horizon) == ("quarterly", "annual")
    assert q.unit == a.unit == "percentage points" and q.available
    assert (q.items[0].slug, q.items[0].points, q.items[0].rank) == ("transport", 0.824, 1)
    assert q.items[-1].slug == "miscellaneous" and q.items[-1].points == -0.009
    assert [i.points for i in q.items] == sorted((i.points for i in q.items), reverse=True)
    assert next(i for i in a.items if i.slug == "housing").points == 1.066
    assert q.sum_points == pytest.approx(1.400) and a.sum_points == pytest.approx(4.000)
    assert round(q.headline_pct, 3) == 1.494 and q.gap_points == pytest.approx(q.headline_pct - q.sum_points)
    assert "unrounded" in q.note


def test_underlying_measures_are_official_and_labelled_as_published(june):
    names = {u.key: u.name for u in june.underlying}
    assert len(names) == 11 and "cpi.underlying.median" in names
    assert all(u.unit == "percent" and u.points for u in june.underlying)
    assert not any("core" in n.lower() for n in names.values())


def test_missing_contribution_charts_are_reported_not_invented(rt, site):
    _, key, page_url, _ = seed_cpi(rt, site, "2026-06")
    status, body, ctype = site.routes[page_url]
    site.routes[page_url] = (status, body.replace(b"percentage point contribution", b"xx"), ctype)
    from nzstats.pipeline.ingest import ingest_release
    from tests.cpi_support import NOW

    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    dashboard = build_cpi_dashboard(rt.conn)
    assert [b.available for b in dashboard.contributions] == [False, False]
    assert all(b.items == [] and "not published" in b.note for b in dashboard.contributions)


def test_failed_newer_ingestion_leaves_the_last_known_good_dashboard(rt, site):
    ingest_cpi(rt, site, "2026-03")
    _, june, _, downloads = seed_cpi(rt, site, "2026-06")
    site.override(downloads["cpi_index_numbers"], body=b"broken", ctype="text/csv")
    from nzstats.pipeline.ingest import ingest_release
    from tests.cpi_support import NOW

    assert ingest_release(rt, june, now_fn=lambda: NOW).outcome == "failed"
    assert build_cpi_dashboard(rt.conn).reference_period == "2026-03"
