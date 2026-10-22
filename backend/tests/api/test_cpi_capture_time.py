"""Freshness of the CPI dashboard follows when the active bundle's data was captured (review #4334641077).

Enrichment from the optional workbook lands in the release's existing bundle at a later capture time.
The dashboard must not claim its underlying measures were captured before they were available, and
the core statistics, publication time and correction history must not move because of it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.clock import to_akl_iso
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.cpi_support import NOW, seed_cpi
from tests.pipeline.test_cpi_ingest import BROKEN, corrected_index

T = [NOW + timedelta(days=n) for n in range(8)]


@pytest.fixture()
def client(rt):
    app = create_app(rt.settings)
    app.state.now = lambda: datetime(2026, 12, 1, tzinfo=UTC)
    with TestClient(app) as c:
        yield c


def ingest_at(rt, key, when):
    return ingest_release(rt, key, now_fn=lambda: when)


def persisted_capture(rt, release_id):
    """Latest capture among the vintages of the release's active bundle, straight from storage."""
    bundle = repo.release_bundle(rt.conn, release_id)
    return rt.conn.execute(
        "SELECT MAX(captured_at) FROM vintage WHERE release_id=? AND bundle_sha256=?",
        (release_id, bundle),
    ).fetchone()[0]


def shown(client):
    """Every freshness timestamp the API exposes for CPI."""
    body = client.get("/api/cpi").json()
    overview = client.get("/api/overview").json()
    return {
        "dashboard": body["captured_at"],
        "analysis": body["analysis"]["vintage_captured_at"],
        "correction_current": body["analysis"]["corrections"]["captured_at"],
        "published": body["published_at"],
        "data_updated": overview["data_updated_at"],
    }


def assert_fresh(client, rt, rid, expected):
    got = shown(client)
    assert persisted_capture(rt, rid) == expected.astimezone(UTC).isoformat().replace("+00:00", "Z")
    assert got["dashboard"] == got["analysis"] == to_akl_iso(expected)
    return got


def test_complete_first_ingest_reports_its_own_capture_time(rt, site, client):
    rid, june, _, _ = seed_cpi(rt, site)
    assert ingest_at(rt, june, T[0]).outcome == "ingested"
    got = assert_fresh(client, rt, rid, T[0])
    assert got["data_updated"] == to_akl_iso(T[0])


def test_workbook_recovery_moves_freshness_but_not_the_publication_or_core_capture(
    rt, site, client
):
    rid, june, _, downloads = seed_cpi(rt, site)
    url = downloads["cpi_workbook"]
    good = site.routes[url]
    site.routes[url] = BROKEN["http_503"]()
    assert ingest_at(rt, june, T[0]).outcome == "ingested"
    first = assert_fresh(client, rt, rid, T[0])  # initial ingestion without the workbook
    assert not repo.latest_points(rt.conn, "cpi.underlying.median")

    site.routes[url] = good
    assert ingest_at(rt, june, T[1]).outcome == "ingested"  # recovery adds the underlying measures
    recovered = assert_fresh(client, rt, rid, T[1])
    median = repo.list_vintages(rt.conn, "cpi.underlying.median")[0]
    assert median.captured_at.startswith(T[1].strftime("%Y-%m-%d"))  # never earlier than this
    assert to_akl_iso(median.captured_at) == recovered["dashboard"]

    assert recovered["published"] == first["published"]  # official publication time untouched
    assert recovered["correction_current"] == first["correction_current"]  # core capture untouched
    assert repo.get_release(rt.conn, june)["status"] == "published"  # not a false correction
    core = repo.release_vintage(rt.conn, "cpi.index.nsa.all_groups", rid)
    assert core.captured_at.startswith(T[0].strftime("%Y-%m-%d"))
    assert client.get("/api/cpi").json()["analysis"]["corrections"]["available"] is False

    assert ingest_at(rt, june, T[2]).outcome == "unchanged"  # another unchanged ingest
    assert shown(client) == recovered

    site.routes[url] = BROKEN["junk"]()  # workbook unavailable again: recovered measures stand
    assert ingest_at(rt, june, T[3]).outcome == "unchanged"
    assert shown(client) == recovered


def test_true_correction_with_workbook_reports_the_new_bundle_capture(rt, site, client):
    rid, june, _, downloads = seed_cpi(rt, site)
    assert ingest_at(rt, june, T[0]).outcome == "ingested"
    original = site.routes[downloads["cpi_index_numbers"]]
    site.routes[downloads["cpi_index_numbers"]] = corrected_index(site, downloads)
    assert ingest_at(rt, june, T[1]).outcome == "ingested"
    got = assert_fresh(client, rt, rid, T[1])
    assert got["correction_current"] == to_akl_iso(T[1])
    assert repo.get_release(rt.conn, june)["status"] == "corrected"

    site.routes[downloads["cpi_index_numbers"]] = original  # the correction is reverted
    assert ingest_at(rt, june, T[2]).outcome == "ingested"
    assert_fresh(client, rt, rid, T[0])  # the reactivated bundle was captured at T[0]


def test_correction_then_late_workbook_then_reversion(rt, site, client):
    rid, june, _, downloads = seed_cpi(rt, site)
    workbook, index = downloads["cpi_workbook"], downloads["cpi_index_numbers"]
    good, original = site.routes[workbook], site.routes[index]
    site.routes[workbook] = BROKEN["http_503"]()
    assert ingest_at(rt, june, T[0]).outcome == "ingested"
    site.routes[index] = corrected_index(site, downloads)
    assert ingest_at(rt, june, T[1]).outcome == "ingested"
    site.routes[workbook] = good
    assert ingest_at(rt, june, T[2]).outcome == "ingested"  # enriches the corrected bundle
    got = assert_fresh(client, rt, rid, T[2])
    assert got["correction_current"] == to_akl_iso(T[1])  # the correction itself was captured at T1

    site.routes[workbook] = BROKEN["http_503"]()
    site.routes[index] = original
    assert ingest_at(rt, june, T[3]).outcome == "ingested"  # reverts to the first bundle
    assert_fresh(client, rt, rid, T[0])  # whose data (no workbook yet) was captured at T0

    site.routes[workbook] = good  # the workbook then reaches the reverted bundle in place
    assert ingest_at(rt, june, T[4]).outcome == "ingested"
    assert_fresh(client, rt, rid, T[4])
    assert repo.get_release(rt.conn, june)["status"] == "corrected"  # history keeps the correction
