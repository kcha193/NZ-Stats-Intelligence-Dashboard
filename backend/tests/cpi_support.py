"""Captured official CPI releases (Dec 2025, Mar 2026, Jun 2026) for offline tests."""

from __future__ import annotations

from datetime import UTC, datetime

from nzstats.domain import ReleaseRef, ReleaseStatus
from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.release_page import ReleasePage, classify_download, parse_release_page
from nzstats.store import repo
from tests.conftest import FIXTURES, fixture_bytes, fixture_text
from tests.support import BASE

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
KINDS = ("index_numbers", "seasonally_adjusted", "tradables")


def page(month: str = "2026-06") -> ReleasePage:
    return parse_release_page(fixture_text(f"cpi_{month}_page.html"), BASE)


def files(month: str = "2026-06") -> dict[str, bytes]:
    names = {"index_numbers": "cpi_index_numbers", "seasonally_adjusted": "cpi_seasonally_adjusted"}
    return {names.get(k, "cpi_tradables"): fixture_bytes(f"cpi_{month}_{k}.csv") for k in KINDS}


def edited(source: dict[str, bytes], kind: str, old: str, new: str) -> dict[str, bytes]:
    """A copy of `source` with `old` replaced by `new` in one file; fails if `old` is absent."""
    text = source[kind].decode("utf-8")
    assert old in text, f"{old!r} not found in {kind}"
    return {**source, kind: text.replace(old, new, 1).encode("utf-8")}


NOW = datetime(2026, 10, 18, tzinfo=UTC)
KIND_FILE = {
    "cpi_index_numbers": "index_numbers",
    "cpi_seasonally_adjusted": "seasonally_adjusted",
    "cpi_tradables": "tradables",
}


def seed_cpi(rt, site, month="2026-06"):
    """Register a published CPI release and serve its real page and files from the fake site."""
    pg = page(month)
    parts = parse_title(pg.title)
    url = f"{BASE}/information-releases/{parts.series_slug}-{parts.period_label.lower().replace(' ', '-')}/"
    ref = ReleaseRef(
        make_release_key(pg.title),
        parts.series_slug,
        pg.title,
        parts.period_label,
        parts.reference_period,
        pg.published_at,
        ReleaseStatus.PUBLISHED,
        page_url=url,
    )
    rid = repo.upsert_release(rt.conn, ref, NOW)
    site.routes[url] = (200, fixture_bytes(f"cpi_{month}_page.html"), "text/html")
    downloads = {}
    for u in pg.download_urls:
        kind = classify_download(u)
        if kind in KIND_FILE:
            downloads[kind] = u
            site.routes[u] = (200, fixture_bytes(f"cpi_{month}_{KIND_FILE[kind]}.csv"), "text/csv")
        elif kind == "workbook" and (FIXTURES / f"cpi_{month}_workbook.xlsx").exists():
            downloads[kind] = u
            site.routes[u] = (200, fixture_bytes(f"cpi_{month}_workbook.xlsx"), XLSX)
        elif kind == "workbook":
            downloads[kind] = u
    return rid, ref.release_key, url, downloads


def ingest_cpi(rt, site, *months):
    """Seed and ingest real fixture releases, oldest first; returns {month: release id}."""
    from nzstats.pipeline.ingest import ingest_release

    ids = {}
    for month in months:
        rid, key, _, _ = seed_cpi(rt, site, month)
        outcome = ingest_release(rt, key, now_fn=lambda: NOW)
        assert outcome.outcome == "ingested", outcome.detail
        ids[month] = rid
    return ids
