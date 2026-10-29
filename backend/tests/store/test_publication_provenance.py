"""Historical captures must not masquerade as original publication vintages."""

from datetime import datetime

import pytest

from nzstats.store import repo
from nzstats.store.repo import supports_first_publication
from tests.macro_support import ingest_gdp, ingest_labour


def test_late_capture_is_not_evidence_of_first_publication(rt, site):
    ingest_gdp(rt, site, "2026-06")
    vintage = repo.list_vintages(rt.conn, "gdp.production.cv.sa.pct_qoq")[0]
    assert not supports_first_publication(rt.conn, vintage)


@pytest.mark.parametrize(
    "captured, supported",
    [
        ("2026-09-16T22:45:00Z", True),  # release: 17 September, 10:45 NZST
        ("2026-09-17T10:00:00Z", True),  # still 17 September in NZ
        ("2026-09-16T22:44:59Z", False),
        ("2026-09-17T12:00:00Z", False),  # 18 September in NZ
    ],
)
def test_original_source_must_be_captured_on_publication_day_after_release(
    rt, site, captured, supported
):
    ingest_gdp(rt, site, "2026-06")
    rt.conn.execute("UPDATE vintage SET captured_at = ?", (captured,))
    vintage = repo.list_vintages(rt.conn, "gdp.production.cv.sa.pct_qoq")[0]
    assert supports_first_publication(rt.conn, vintage) is supported


def test_revised_archive_is_never_assumed_to_be_first_publication(rt, site):
    ingest_labour(rt, site, "2026-03")
    rt.conn.execute("UPDATE vintage SET captured_at = '2026-05-05T22:45:00Z'")
    vintage = repo.list_vintages(rt.conn, "hlfs.rate.unemployment.sa")[0]
    assert not supports_first_publication(rt.conn, vintage)


def test_missing_source_metadata_is_unverified(rt, site):
    ingest_gdp(rt, site, "2026-06")
    rt.conn.execute("UPDATE vintage SET captured_at = '2026-09-16T22:45:00Z'")
    rt.conn.execute("UPDATE vintage_series_definition SET source_url = NULL")
    vintage = repo.list_vintages(rt.conn, "gdp.production.cv.sa.pct_qoq")[0]
    assert not supports_first_publication(rt.conn, vintage)


def test_a_snapshot_is_not_an_original_release_file(rt, site):
    ingest_gdp(rt, site, "2026-06")
    rt.conn.execute(
        "UPDATE vintage SET captured_at = '2026-09-16T22:45:00Z', source_kind = 'snapshot'"
    )
    vintage = repo.list_vintages(rt.conn, "gdp.production.cv.sa.pct_qoq")[0]
    assert not supports_first_publication(rt.conn, vintage)


def test_a_second_same_day_bundle_under_the_original_url_is_not_original(rt, site):
    ingest_gdp(rt, site, "2026-06")
    captured = "2026-09-16T22:45:00Z"
    rt.conn.execute("UPDATE vintage SET captured_at = ?", (captured,))
    original = repo.list_vintages(rt.conn, "gdp.production.cv.sa.pct_qoq")[0]
    row = rt.conn.execute(
        "SELECT release_id, series_id FROM vintage WHERE id = ?", (original.vintage_id,)
    ).fetchone()
    repo.create_vintage(
        rt.conn,
        row["release_id"],
        row["series_id"],
        datetime.fromisoformat(captured),
        "release_files",
        "gdp-csv-v1",
        "same-day-correction",
    )
    correction = repo.list_vintages(rt.conn, "gdp.production.cv.sa.pct_qoq")[-1]
    assert supports_first_publication(rt.conn, original)
    assert not supports_first_publication(rt.conn, correction)
