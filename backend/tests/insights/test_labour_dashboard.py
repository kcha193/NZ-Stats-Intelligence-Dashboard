"""Labour market dashboard and release analysis from the real March (revised) and June 2026 releases."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.insights.labour import build_labour_analysis, build_labour_dashboard
from nzstats.store import repo
from tests.macro_support import ingest_labour

RATE = "hlfs.rate.unemployment.sa"


@pytest.fixture()
def client(rt):
    app = create_app(rt.settings)
    app.state.now = lambda: datetime(2026, 10, 28, 12, tzinfo=UTC)
    with TestClient(app) as c:
        yield c


def test_nothing_is_built_before_ingestion(rt):
    assert build_labour_dashboard(rt.conn) is None


def test_headline_metrics_are_hlfs_rates_and_the_lci(rt, site):
    ingest_labour(rt, site, "2026-06")
    d = build_labour_dashboard(rt.conn)
    assert d.reference_period == "2026-06"
    metrics = {m.series_key: m for m in d.analysis.headline_metrics}
    assert [k for k in metrics] == [
        RATE,
        "hlfs.rate.employment.sa",
        "hlfs.rate.participation.sa",
        "hlfs.rate.underutilisation.sa",
        "lci.all_wages.pct_yoy",
    ]
    assert metrics[RATE].value == 5.6
    assert metrics[RATE].change_prior.previous == 5.4  # the March rate as revised in this release
    assert metrics[RATE].change_prior.absolute == 0.2
    assert metrics["lci.all_wages.pct_yoy"].label == "Labour Cost Index, annual change"


def test_summary_states_the_revision_of_the_previous_quarter(rt, site):
    ingest_labour(rt, site, "2026-03", "2026-06")
    text = build_labour_dashboard(rt.conn).analysis.executive_summary[0].text
    assert "5.6% in the June 2026 quarter" in text
    assert "5.4% in the March 2026 quarter" in text
    assert "first published as 5.3%" in text


def test_summary_does_not_claim_a_revision_with_one_release(rt, site):
    ingest_labour(rt, site, "2026-06")
    text = build_labour_dashboard(rt.conn).analysis.executive_summary[0].text
    assert "first published" not in text


def test_lci_is_described_as_wage_rates_not_earnings(rt, site):
    ingest_labour(rt, site, "2026-06")
    a = build_labour_dashboard(rt.conn).analysis
    lci = next(i for i in [*a.executive_summary, *a.context] if i.id == "lci")
    assert "0.6%" in lci.text and "2.0%" in lci.text
    assert "not average earnings" in lci.text


def test_every_insight_cites_stored_evidence(rt, site):
    keys = ingest_labour(rt, site, "2026-06")
    a = build_labour_dashboard(rt.conn).analysis
    for insight in [*a.executive_summary, *a.context]:
        assert insight.evidence, insight.id
        for e in insight.evidence:
            assert e.release_key == keys["2026-06"]
            assert repo.latest_points(rt.conn, e.series_key)[e.period].value == e.value


def test_series_say_which_survey_and_measure(rt, site):
    ingest_labour(rt, site, "2026-06")
    series = {s.key: s for s in build_labour_dashboard(rt.conn).series}
    assert len(series) == 11
    assert (series[RATE].survey, series[RATE].measure) == ("hlfs", "rate")
    assert series["hlfs.level.employed.sa"].measure == "level"
    assert (series["lci.all_wages.index"].survey, series["lci.all_wages.index"].measure) == (
        "lci",
        "index",
    )
    assert series["lci.all_wages.pct_qoq"].measure == "quarterly_change"
    assert series["lci.all_wages.index"].adjustment == "none"


def test_caveats_cover_sampling_and_survey_differences(rt, site):
    ingest_labour(rt, site, "2026-06")
    caveats = " ".join(build_labour_dashboard(rt.conn).caveats)
    assert "sample survey" in caveats
    assert "Quarterly Employment Survey" in caveats


def test_first_latest_table_for_the_unemployment_rate(rt, site):
    ingest_labour(rt, site, "2026-03", "2026-06")
    table = build_labour_dashboard(rt.conn).revisions[0]
    assert table.series_key == RATE and table.available
    march = next(r for r in table.rows if r.period == "2026-03")
    assert (march.first_value, march.latest_value, march.revision, march.first_is_publication) == (
        5.3,
        5.4,
        0.1,
        True,
    )


def test_historical_analysis_uses_its_own_release(rt, site):
    ingest_labour(rt, site, "2026-03", "2026-06")
    march_id = repo.get_release(rt.conn, "labour-market-statistics:march 2026 quarter")["id"]
    a = build_labour_analysis(rt.conn, march_id)
    assert next(m for m in a.headline_metrics if m.series_key == RATE).value == 5.3


def test_api_labour_market_404_then_200(rt, site, client):
    r = client.get("/api/labour-market")
    assert (
        r.status_code == 404
        and r.json()["detail"] == "Labour market data has not been ingested yet"
    )
    ingest_labour(rt, site, "2026-06")
    body = client.get("/api/labour-market").json()
    assert body["reference_period"] == "2026-06"
    assert body["published_at"].startswith("2026-08-05T10:45")


def test_release_detail_for_a_labour_release_has_its_analysis(rt, site, client):
    ingest_labour(rt, site, "2026-06")
    rid = repo.get_release(rt.conn, "labour-market-statistics:june 2026 quarter")["id"]
    body = client.get(f"/api/releases/{rid}").json()
    assert body["unavailable_reason"] is None
    assert body["analysis"]["release"]["category"] == "Labour market"
