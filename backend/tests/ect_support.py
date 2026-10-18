"""Captured official ECT releases for offline pipeline and browser fixtures."""

from datetime import UTC, datetime

from nzstats.domain import ReleaseRef, ReleaseStatus
from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.release_page import parse_release_page
from nzstats.store import repo
from tests.conftest import fixture_bytes, fixture_text
from tests.support import BASE

NOW = datetime(2026, 10, 18, tzinfo=UTC)


def seed_ect(rt, site, month="2026-09"):
    page = parse_release_page(fixture_text(f"ect_{month}_page.html"), BASE)
    parts = parse_title(page.title)
    url = f"{BASE}/information-releases/{parts.series_slug}-{parts.period_label.lower().replace(' ', '-')}/"
    ref = ReleaseRef(
        make_release_key(page.title),
        parts.series_slug,
        page.title,
        parts.period_label,
        parts.reference_period,
        page.published_at,
        ReleaseStatus.PUBLISHED,
        page_url=url,
    )
    rid = repo.upsert_release(rt.conn, ref, NOW)
    site.routes[url] = (200, fixture_bytes(f"ect_{month}_page.html"), "text/html")
    download = next(u for u in page.download_urls if u.endswith(".zip"))
    site.routes[download] = (200, fixture_bytes(f"ect_{month}.zip"), "application/zip")
    return rid, ref.release_key, download
