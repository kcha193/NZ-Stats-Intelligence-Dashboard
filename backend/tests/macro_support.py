"""Captured official GDP and labour market releases (March and June 2026 quarters) for offline tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from nzstats.domain import ReleaseRef, ReleaseStatus
from nzstats.pipeline.ingest import ingest_release
from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.release_page import classify_download, parse_release_page
from nzstats.store import repo
from tests.conftest import fixture_bytes, fixture_text
from tests.support import BASE

NOW = datetime(2026, 10, 28, tzinfo=UTC)
CONTENT_TYPES = {"csv": "text/csv", "zip": "application/zip"}


def serve(site, page_fixture: str, files: Mapping[str, bytes]) -> ReleaseRef:
    """Serve a release's real page and the given download bodies (by kind) from the fake site."""
    pg = parse_release_page(fixture_text(page_fixture), BASE)
    parts = parse_title(pg.title)
    url = f"{BASE}/information-releases/{parts.series_slug}-{parts.period_label.lower().replace(' ', '-')}/"
    site.routes[url] = (200, fixture_bytes(page_fixture), "text/html")
    for u in pg.download_urls:
        kind = classify_download(u)
        if kind in files:
            site.routes[u] = (200, files[kind], CONTENT_TYPES[u.rsplit(".", 1)[-1]])
    return ReleaseRef(
        make_release_key(pg.title),
        parts.series_slug,
        pg.title,
        parts.period_label,
        parts.reference_period,
        pg.published_at,
        ReleaseStatus.PUBLISHED,
        page_url=url,
    )


def gdp_files(month: str) -> dict[str, bytes]:
    return {"gdp_csv": fixture_bytes(f"gdp_{month}.csv")}


def seed(rt, site, page_fixture: str, files: Mapping[str, bytes]) -> str:
    ref = serve(site, page_fixture, files)
    repo.upsert_release(rt.conn, ref, NOW)
    return ref.release_key


def ingest(rt, key: str):
    return ingest_release(rt, key, now_fn=lambda: NOW)


def ingest_gdp(rt, site, *months: str) -> dict[str, str]:
    """Seed and ingest real GDP releases, oldest first; returns {month: release key}."""
    keys = {}
    for month in months:
        keys[month] = seed(rt, site, f"gdp_{month}_page.html", gdp_files(month))
        outcome = ingest(rt, keys[month])
        assert outcome.outcome == "ingested", outcome.detail
    return keys
