"""GDP dashboard and release analysis, built from the real March and June 2026 quarter releases."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.domain import Observation
from nzstats.insights.gdp import build_gdp_analysis, build_gdp_dashboard
from nzstats.store import repo
from nzstats.store.db import transaction
from tests.macro_support import NOW, ingest, ingest_gdp


@pytest.fixture()
def client(rt):
    app = create_app(rt.settings)
    app.state.now = lambda: datetime(2026, 10, 28, 12, tzinfo=UTC)
    with TestClient(app) as c:
        yield c


def test_nothing_is_built_before_ingestion(rt):
    assert build_gdp_dashboard(rt.conn) is None


def test_headline_metrics_name_three_different_growth_measures(rt, site):
    ingest_gdp(rt, site, "2026-06")
    d = build_gdp_dashboard(rt.conn)
    assert d.reference_period == "2026-06"
    metrics = {m.series_key: (m.label, m.value) for m in d.analysis.headline_metrics}
    assert metrics["gdp.production.cv.sa.pct_qoq"] == (
        "Quarterly GDP growth (production, real, seasonally adjusted)",
        0.2,
    )
    assert metrics["gdp.production.cv.nsa.pct_annual_avg"] == (
        "Annual average GDP growth (production, real)",
        1.7,
    )
    assert metrics["gdp.production.cv.sa.pct_yoy"][1] == 2.6
    assert all(m.unit == "percent" and m.period == "2026-06" for m in d.analysis.headline_metrics)


def test_summary_text_states_each_measure_and_its_period(rt, site):
    ingest_gdp(rt, site, "2026-06")
    texts = [i.text for i in build_gdp_dashboard(rt.conn).analysis.executive_summary]
    joined = " ".join(texts)
    assert "rose 0.2% in the June 2026 quarter" in joined
    assert "annual average" in joined and "year ended June 2026" in joined and "1.7%" in joined
    assert "2.6% higher than in the June 2025 quarter" in joined
    assert "annual growth" not in joined.lower().replace("annual average", "")


def test_every_insight_cites_stored_evidence(rt, site):
    keys = ingest_gdp(rt, site, "2026-06")
    a = build_gdp_dashboard(rt.conn).analysis
    for insight in [*a.executive_summary, *a.context]:
        assert insight.evidence, insight.id
        for e in insight.evidence:
            assert e.release_key == keys["2026-06"]
            assert repo.latest_points(rt.conn, e.series_key)[e.period].value == e.value


def test_series_keep_measures_bases_and_adjustments_apart(rt, site):
    ingest_gdp(rt, site, "2026-06")
    series = {s.key: s for s in build_gdp_dashboard(rt.conn).series}
    assert len(series) == 12
    assert series["gdp.production.cv.sa"].measure == "level"
    assert series["gdp.production.cv.sa"].price_basis == "chain_volume"
    assert series["gdp.expenditure.cp.nsa"].price_basis == "current_prices"
    assert series["gdp.expenditure.cp.nsa"].adjustment == "none"
    assert series["gdp.per_capita.production.cv.sa"].per_capita is True
    assert series["gdp.production.cv.sa.pct_yoy"].measure == "annual_change"
    assert series["gdp.production.cv.nsa.pct_annual_avg"].measure == "annual_average_change"
    assert series["gdp.expenditure.cv.sa.pct_qoq"].approach == "expenditure"
    assert series["gdp.production.cv.sa"].points[-1].value == 71805


def test_revision_table_separates_first_published_from_latest(rt, site):
    ingest_gdp(rt, site, "2026-03", "2026-06")
    table = next(
        t for t in build_gdp_dashboard(rt.conn).revisions if t.series_key.endswith("pct_qoq")
    )
    rows = {r.period: r for r in table.rows}
    march = rows["2026-03"]
    assert (march.first_value, march.latest_value, march.revision) == (0.8, 0.9, 0.1)
    assert march.first_is_publication is True
    assert march.first_release == "Gross domestic product: March 2026 quarter"
    assert march.latest_release == "Gross domestic product: June 2026 quarter"
    june = rows["2026-06"]
    assert (june.first_value, june.latest_value, june.revision) == (0.2, 0.2, 0.0)
    december = rows["2025-12"]
    assert december.first_is_publication is False  # its own release is not stored: earliest stored
    assert "earliest stored" in table.note


def test_revision_table_is_unavailable_with_one_release(rt, site):
    ingest_gdp(rt, site, "2026-06")
    table = build_gdp_dashboard(rt.conn).revisions[0]
    assert table.available is False and table.rows == []


def _store_correction(rt, release_id, key, period, value):
    """Simulate a corrected stored bundle; leave the approved fixture files untouched."""
    original = repo.release_bundle(rt.conn, release_id)
    corrected = f"test-correction-{release_id}"
    with transaction(rt.conn):
        for definition, obs in repo.bundle_series(rt.conn, release_id, original):
            sid = repo.upsert_series(rt.conn, definition)
            vid = repo.create_vintage(
                rt.conn, release_id, sid, NOW, "release_files", "gdp-csv-v1", corrected
            )
            repo.insert_observations(
                rt.conn,
                vid,
                [
                    Observation(
                        definition.key,
                        o.period,
                        value if definition.key == key and o.period == period else o.value,
                        o.status,
                        o.std_error,
                        o.released_in,
                    )
                    for o in obs
                ],
            )
    return original, corrected


@pytest.mark.parametrize(
    "key", ["gdp.production.cv.sa.pct_qoq", "gdp.production.cv.nsa.pct_annual_avg"]
)
@pytest.mark.parametrize("backfill", [False, True])
def test_first_published_survives_correction_and_restoration(rt, site, key, backfill):
    # Also cover a newer release ingested before its older publication is backfilled.
    if backfill:
        ingest_gdp(rt, site, "2026-06")
    march_key = ingest_gdp(rt, site, "2026-03")["2026-03"]
    march_id = repo.get_release(rt.conn, march_key)["id"]
    original, corrected = _store_correction(rt, march_id, key, "2026-03", 1.0)
    correction = repo.bundle_vintage(rt.conn, key, march_id, corrected)
    assert repo.vintage_points(rt.conn, correction.vintage_id)["2026-03"].value == 1.0

    # Re-ingesting the original 0.8 bundle reactivates it, without inserting new vintages.
    assert ingest(rt, march_key).outcome == "ingested"
    assert repo.release_bundle(rt.conn, march_id) == original
    assert ingest(rt, march_key).outcome == "unchanged"
    if not backfill:
        ingest_gdp(rt, site, "2026-06")

    # Repeatedly reactivate both bundles after the subsequent release exists, too.
    for bundle in (original, corrected, original):
        with transaction(rt.conn):
            repo.reactivate_bundle(rt.conn, march_id, bundle)
        dashboard = build_gdp_dashboard(rt.conn)
        table = next(t for t in dashboard.revisions if t.series_key == key)
        rows = {r.period: r for r in table.rows}
        march = rows["2026-03"]
        assert (march.first_value, march.latest_value, march.revision) == (0.8, 0.9, 0.1)
        assert march.first_is_publication is True
        assert march.first_release == "Gross domestic product: March 2026 quarter"
        june = rows["2026-06"]
        assert (june.first_value, june.latest_value, june.revision) == (
            (0.2, 0.2, 0.0) if key.endswith("pct_qoq") else (1.7, 1.7, 0.0)
        )
        december = rows["2025-12"]
        assert december.first_is_publication is False
        assert december.first_release == "Gross domestic product: March 2026 quarter"
        # The shared current-vintage lookup still follows activation, including corrections.
        previous = repo.previous_vintage(rt.conn, key, "2026-09-16T22:45:00Z")
        assert repo.vintage_points(rt.conn, previous.vintage_id)["2026-03"].value == (
            1.0 if bundle == corrected else 0.8
        )

    assert len(repo.list_vintages(rt.conn, key)) == 3
    assert repo.vintage_points(rt.conn, correction.vintage_id)["2026-03"].value == 1.0
    assert ingest(rt, march_key).outcome == "unchanged"


def test_analysis_revisions_block_compares_with_the_previous_release(rt, site):
    ingest_gdp(rt, site, "2026-03", "2026-06")
    block = build_gdp_dashboard(rt.conn).analysis.revisions
    assert block.available and block.against_title == "Gross domestic product: March 2026 quarter"
    assert block.series_key == "gdp.production.cv.sa.pct_qoq"
    assert block.n_revised >= 1


def test_a_historical_release_analysis_uses_its_own_bundle(rt, site):
    ingest_gdp(rt, site, "2026-03", "2026-06")
    march_id = repo.get_release(rt.conn, "gross-domestic-product:march 2026 quarter")["id"]
    a = build_gdp_analysis(rt.conn, march_id)
    assert {m.period for m in a.headline_metrics} == {"2026-03"}
    assert next(m for m in a.headline_metrics if m.series_key.endswith("pct_qoq")).value == 0.8


def test_api_gdp_404_then_200(rt, site, client):
    r = client.get("/api/gdp")
    assert r.status_code == 404 and r.json()["detail"] == "GDP data has not been ingested yet"
    ingest_gdp(rt, site, "2026-06")
    body = client.get("/api/gdp").json()
    assert body["reference_period"] == "2026-06"
    assert body["published_at"].startswith("2026-09-17T10:45")
    assert any("stats.govt.nz" in s for s in body["sources"])


def test_release_detail_for_a_gdp_release_has_its_analysis(rt, site, client):
    ingest_gdp(rt, site, "2026-06")
    rid = repo.get_release(rt.conn, "gross-domestic-product:june 2026 quarter")["id"]
    body = client.get(f"/api/releases/{rid}").json()
    assert body["unavailable_reason"] is None
    assert body["analysis"]["release"]["category"] == "Economic growth"
    assert body["analysis"]["headline_metrics"][0]["series_key"] == "gdp.production.cv.sa.pct_qoq"
