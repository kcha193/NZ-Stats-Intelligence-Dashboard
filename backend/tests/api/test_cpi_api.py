from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.domain import ReleaseRef, ReleaseStatus
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.cpi_support import NOW, ingest_cpi, seed_cpi


@pytest.fixture()
def client(rt):
    app = create_app(rt.settings)
    app.state.now = lambda: datetime(2026, 10, 19, 12, tzinfo=UTC)
    with TestClient(app) as c:
        yield c


def test_empty_database_returns_a_plain_404(client):
    r = client.get("/api/cpi")
    assert r.status_code == 404 and r.json()["detail"] == "CPI data has not been ingested yet"
    overview = client.get("/api/overview").json()
    assert "Prices and inflation" in [c["name"] for c in overview["inactive_categories"]]
    assert not [k for k in overview["kpis"] if k["metric"]["series_key"].startswith("cpi.")]


def test_dashboard_contract_and_units(rt, site, client):
    ingest_cpi(rt, site, "2026-03", "2026-06")
    body = client.get("/api/cpi").json()
    assert body["reference_period"] == "2026-06" and body["published_at"].startswith(
        "2026-07-21T10:45"
    )
    assert all(b["unit"] == "percentage points" for b in body["contributions"])
    assert all(m["unit"] == "percent" for m in body["analysis"]["headline_metrics"])
    assert body["base"] == "June 2017 quarter (=1000)" and body["caveats"]
    assert {s["unit"] for s in body["series"]} == {"index"}


def test_release_detail_overview_and_calendar_recognise_cpi(rt, site, client):
    ids = ingest_cpi(rt, site, "2026-06")
    detail = client.get(f"/api/releases/{ids['2026-06']}").json()
    assert detail["release"]["has_analysis"] and detail["unavailable_reason"] is None
    assert detail["analysis"]["headline_metrics"][0]["series_key"] == "cpi.index.nsa.all_groups"
    overview = client.get("/api/overview").json()
    kpi = next(k for k in overview["kpis"] if k["metric"]["series_key"].startswith("cpi."))
    assert round(kpi["metric"]["value"], 1) == 4.1 and kpi["release_id"] == ids["2026-06"]
    assert "Prices and inflation" not in [c["name"] for c in overview["inactive_categories"]]
    items = client.get("/api/calendar?from=2026-07-01&to=2026-07-31").json()["items"]
    assert any(i["id"] == ids["2026-06"] and i["has_analysis"] for i in items)


def test_future_scheduled_cpi_release_is_kept_and_not_analysable(rt, site, client):
    ingest_cpi(rt, site, "2026-06")
    scheduled = ReleaseRef(
        "consumers-price-index:september 2026 quarter",
        "consumers-price-index",
        "Consumers price index: September 2026 quarter",
        "September 2026 quarter",
        "2026-09",
        datetime(2026, 10, 22, 10, 45, tzinfo=UTC),
        ReleaseStatus.SCHEDULED,
    )
    repo.upsert_release(rt.conn, scheduled, NOW)
    upcoming = client.get("/api/overview").json()["upcoming"]
    row = next(r for r in upcoming if r["release_key"] == scheduled.release_key)
    assert row["status"] == "scheduled" and not row["has_analysis"]
    assert client.get("/api/cpi").json()["reference_period"] == "2026-06"


def test_failed_ingestion_is_visible_while_last_known_good_is_served(rt, site, client):
    ingest_cpi(rt, site, "2026-03")
    _, june, _, downloads = seed_cpi(rt, site, "2026-06")
    site.override(downloads["cpi_tradables"], body=b"broken", ctype="text/csv")
    assert ingest_release(rt, june, now_fn=lambda: NOW).outcome == "failed"
    health = client.get("/api/health").json()
    source = next(s for s in health["sources"] if s["source"] == "release:consumers-price-index")
    assert source["state"] == "degraded"
    assert health["recent_runs"][0]["outcome"] == "failed"
    assert client.get("/api/cpi").json()["reference_period"] == "2026-03"


def test_recovered_optional_workbook_reaches_the_dashboard_without_a_correction(rt, site, client):
    from tests.cpi_support import XLSX

    _, june, _, downloads = seed_cpi(rt, site)
    url = downloads["cpi_workbook"]
    good = site.routes[url]
    site.routes[url] = (503, b"", "text/html")
    assert ingest_release(rt, june, now_fn=lambda: NOW).outcome == "ingested"
    before = client.get("/api/cpi").json()
    assert before["underlying"] == []

    site.routes[url] = good
    assert ingest_release(rt, june, now_fn=lambda: NOW).outcome == "ingested"
    after = client.get("/api/cpi").json()
    assert len(after["underlying"]) == 11
    for key in ("reference_period", "published_at", "series", "contributions"):
        assert after[key] == before[key]  # required statistics are untouched
    assert after["analysis"]["revisions"] == before["analysis"]["revisions"]
    assert repo.get_release(rt.conn, june)["status"] == "published"
    releases = client.get("/api/releases").json()
    assert {r["status"] for r in releases if r["release_key"] == june} == {"published"}

    site.routes[url] = (200, b"junk", XLSX)  # a later bad workbook cannot remove them
    assert ingest_release(rt, june, now_fn=lambda: NOW).outcome == "unchanged"
    assert client.get("/api/cpi").json()["underlying"] == after["underlying"]
