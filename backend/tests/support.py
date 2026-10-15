import calendar
from datetime import UTC, datetime

import httpx

from nzstats.domain import ReleaseRef, ReleaseStatus
from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.fetcher import Fetcher
from nzstats.sources.release_page import classify_download, parse_release_page
from tests.conftest import fixture_bytes, fixture_text

BASE = "https://www.stats.govt.nz"
NOW = datetime(2026, 10, 11, 3, 0, tzinfo=UTC)


def page_url(month: str) -> str:
    year, mm = month.split("-")
    return (
        f"{BASE}/information-releases/international-migration-"
        f"{calendar.month_name[int(mm)].lower()}-{year}/"
    )


def release_ref_for(month: str, status: ReleaseStatus = ReleaseStatus.PUBLISHED) -> ReleaseRef:
    page = parse_release_page(fixture_text(f"im_{month}_page.html"), BASE)
    parts = parse_title(page.title)
    return ReleaseRef(
        release_key=make_release_key(page.title),
        series_slug=parts.series_slug,
        title=page.title,
        period_label=parts.period_label,
        reference_period=parts.reference_period,
        published_at=page.published_at,
        status=status,
        page_url=page_url(month),
    )


class FakeSite:
    """Serves real fixture bytes; individual URLs can be overridden to simulate failures."""

    def __init__(self, months=("2026-06", "2026-07")) -> None:
        self.routes: dict[str, tuple[int, bytes, str]] = {}
        self.requests: list[str] = []
        self.clock_now = 0.0  # the fetcher's monotonic clock; advance it to end a cooldown
        for month in months:
            html_text = fixture_text(f"im_{month}_page.html")
            self.routes[page_url(month)] = (200, html_text.encode(), "text/html; charset=utf-8")
            for url in parse_release_page(html_text, BASE).download_urls:
                kind = classify_download(url)
                name = {"age_sex": "age_sex", "citizenship_visa_country": "citizenship_country"}
                if kind in name:
                    self.routes[url] = (
                        200,
                        fixture_bytes(f"im_{month}_{name[kind]}.csv"),
                        "application/octet-stream",
                    )
        self.routes[f"{BASE}/release-calendar/calendar-export/"] = (
            200,
            fixture_bytes("calendar_export_excerpt.ics"),
            "text/calendar; charset=UTF-8",
        )
        for m in ("2026-09", "2026-10"):
            self.routes[f"{BASE}/api/v1/releaseCalendarMonth/{m}"] = (
                200,
                fixture_bytes(f"release_month_{m}.json"),
                "application/json",
            )

    def file_url(self, month: str, kind: str) -> str:
        page = parse_release_page(fixture_text(f"im_{month}_page.html"), BASE)
        return next(u for u in page.download_urls if classify_download(u) == kind)

    def override(
        self,
        url: str,
        status: int = 200,
        body: bytes = b"",
        ctype: str = "application/octet-stream",
    ) -> None:
        self.routes[url] = (status, body, ctype)

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        status, body, ctype = self.routes.get(url, (404, b"", "text/html"))
        return httpx.Response(status, content=body, headers={"content-type": ctype})

    def fetcher(self) -> Fetcher:
        client = httpx.Client(transport=httpx.MockTransport(self.handler))
        return Fetcher(client, sleep=lambda s: None, clock=lambda: self.clock_now)


def ingest_months(rt, *months: str) -> dict[str, int]:
    """Seed releases as published and ingest their real fixture files, oldest first."""
    from nzstats.pipeline.ingest import ingest_release
    from nzstats.store import repo

    ids: dict[str, int] = {}
    for month in months:
        ref = release_ref_for(month)
        ids[month] = repo.upsert_release(rt.conn, ref, NOW)
        outcome = ingest_release(rt, ref.release_key, now_fn=lambda: NOW)
        assert outcome.outcome == "ingested", outcome.detail
    return ids


def seed_from_fixtures(data_dir) -> None:
    """Build a database from the real fixture files (June + July 2026 releases plus the calendar).

    Used for frontend fixtures and end-to-end tests; never for production data.
    """
    from pathlib import Path

    from nzstats.config import load_settings
    from nzstats.pipeline.discover import discover
    from nzstats.runtime import build_runtime

    settings = load_settings({"NZSTATS_DATA_DIR": str(Path(data_dir)), "NZSTATS_BASE_URL": BASE})
    site = FakeSite()
    rt = build_runtime(settings, fetcher=site.fetcher())
    ingest_months(rt, "2026-06", "2026-07")
    discover(rt, months=["2026-09", "2026-10"], now_fn=lambda: NOW)
