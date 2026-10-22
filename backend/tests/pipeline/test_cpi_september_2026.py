"""The September 2026 quarter release (published 22 October 2026), from its real captured files.

The page and files are the ones Stats NZ served on release day. The quarterly chart there opens with
`Category` instead of `Quarter`, which the adapter used to reject as a layout change. Official figures:
"CPI increased 0.7 percent in the September 2026 quarter and 3.7 percent in the 12 months to September
2026"; the page charts give tradables 4.3 and non-tradables 3.3 percent for the year.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.insights.cpi import build_cpi_dashboard
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.cpi_support import NOW, ingest_cpi, seed_cpi

CORE = "cpi.index.nsa.all_groups"
SEPTEMBER = "consumers-price-index:september 2026 quarter"
JUNE = "consumers-price-index:june 2026 quarter"


@pytest.fixture()
def client(rt):
    app = create_app(rt.settings)
    app.state.now = lambda: datetime(2026, 10, 22, 6, tzinfo=UTC)
    with TestClient(app) as c:
        yield c


def counts(rt):
    tables = ("series", "vintage", "observation", "vintage_series_definition")
    return {t: rt.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def ingest(rt, key):
    return ingest_release(rt, key, now_fn=lambda: NOW)


def test_september_is_ingested_after_june_and_served_with_the_official_rates(rt, site, client):
    ingest_cpi(rt, site, "2026-06")
    assert client.get("/api/cpi").json()["reference_period"] == "2026-06"

    _, key, _, downloads = seed_cpi(rt, site, "2026-09")
    outcome = ingest(rt, key)
    assert key == SEPTEMBER and outcome.outcome == "ingested", outcome.detail
    assert repo.get_release(rt.conn, SEPTEMBER)["status"] == "published"

    body = client.get("/api/cpi").json()
    assert body["reference_period"] == "2026-09"
    assert body["published_at"].startswith("2026-10-22T10:45")  # 10:45 NZDT, shown in Auckland time
    rates = {
        (m["series_key"], m["label"]): round(m["value"], 1)
        for m in body["analysis"]["headline_metrics"]
    }
    assert rates[(CORE, "CPI quarterly inflation, all groups")] == 0.7
    assert rates[(CORE, "CPI annual inflation, all groups")] == 3.7
    assert rates[("cpi.index.nsa.tradables", "Tradables annual inflation")] == 4.3
    assert rates[("cpi.index.nsa.non_tradables", "Non-tradables annual inflation")] == 3.3
    assert {m["unit"] for m in body["analysis"]["headline_metrics"]} == {"percent"}
    assert all(c["unit"] == "percentage points" for c in body["contributions"])

    # June stays as its own vintage, September is the newest, and each cites its own release.
    vintages = repo.list_vintages(rt.conn, CORE)
    assert [v.release_key for v in vintages] == [JUNE, SEPTEMBER]
    assert repo.latest_points(rt.conn, CORE)["2026-09"].value == 1368.0
    assert repo.vintage_points(rt.conn, vintages[0].vintage_id)["2026-06"].value == 1359.0
    row = rt.conn.execute("SELECT source_url FROM series WHERE key=?", (CORE,)).fetchone()
    assert row[0] == downloads["cpi_index_numbers"] and "september-2026-quarter" in row[0]

    # The official underlying measures from the optional workbook arrive in the same ingestion.
    assert body["underlying"]
    health = client.get("/api/health").json()
    assert {s["source"]: s["state"] for s in health["sources"]}[
        "release:consumers-price-index"
    ] == "ok"
    assert health["recent_runs"][0]["outcome"] == "ingested"


def test_reingesting_september_changes_nothing(rt, site):
    _, key, _, _ = seed_cpi(rt, site, "2026-09")
    assert ingest(rt, key).outcome == "ingested"
    first = counts(rt)
    assert ingest(rt, key).outcome == "unchanged"
    assert counts(rt) == first
    assert rt.conn.execute("SELECT COUNT(*) FROM raw_artifact").fetchone()[0] == 5


def test_a_failed_september_keeps_june_on_screen(rt, site, client):
    ingest_cpi(rt, site, "2026-06")
    before = counts(rt)
    _, key, page_url, _ = seed_cpi(rt, site, "2026-09")
    status, page, ctype = site.routes[page_url]
    assert b",1.5,0.7" in page
    site.routes[page_url] = (status, page.replace(b",1.5,0.7", b",1.5,0.9"), ctype)  # wrong rate
    outcome = ingest(rt, key)
    assert outcome.outcome == "failed" and outcome.error_class.value == "validation_failed"
    assert "Traceback" not in (outcome.detail or "")
    assert counts(rt) == before
    assert build_cpi_dashboard(rt.conn).reference_period == "2026-06"
    assert client.get("/api/cpi").json()["reference_period"] == "2026-06"
    health = client.get("/api/health").json()
    assert {s["source"]: s["state"] for s in health["sources"]}[
        "release:consumers-price-index"
    ] == "degraded"


def test_a_missing_workbook_never_blocks_the_september_headline(rt, site, client):
    _, key, _, downloads = seed_cpi(rt, site, "2026-09")
    site.override(downloads["cpi_workbook"], 503, b"", "text/html")
    outcome = ingest(rt, key)
    assert outcome.outcome == "ingested", outcome.detail
    assert any("underlying" in w for w in outcome.warnings)
    body = client.get("/api/cpi").json()
    assert body["reference_period"] == "2026-09" and not body["underlying"]
    assert repo.latest_points(rt.conn, CORE)["2026-09"].value == 1368.0
