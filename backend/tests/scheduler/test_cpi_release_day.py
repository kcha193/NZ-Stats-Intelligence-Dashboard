"""Offline release-day REHEARSAL for CPI.

These tests replay the already-published June 2026 release (real fixtures) as if it had just become
available. They prove the discover -> poll -> ingest -> serve path works end to end for a
newly published quarter. They are NOT evidence that the live September 2026 quarter release
(22 October 2026) has been processed: that publication has not been ingested.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.clock import parse_akl_naive
from nzstats.insights.cpi import build_cpi_dashboard
from nzstats.pipeline.discover import discover
from nzstats.scheduler.jobs import build_scheduler, job_catch_up, job_release_watch
from nzstats.store import repo
from tests.cpi_support import ingest_cpi, serve_cpi
from tests.support import BASE

PUB = parse_akl_naive(
    "2026-07-21 10:45:00"
)  # real publication time of the June 2026 quarter release
JUNE_KEY = "consumers-price-index:june 2026 quarter"


def calendar(site, summary: str, start: str, uid: str = "9001") -> None:
    site.routes[f"{BASE}/release-calendar/calendar-export/"] = (
        200,
        (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
            f"UID:{uid}@https://www.stats.govt.nz/\r\n"
            f"DTSTART;TZID=Pacific/Auckland:{start}\r\nDTEND;TZID=Pacific/Auckland:{start}\r\n"
            f"SUMMARY:{summary}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        ).encode(),
        "text/calendar; charset=UTF-8",
    )


def rehearse(rt, site):
    """March is already ingested; June is discovered as scheduled but not yet served."""
    ingest_cpi(rt, site, "2026-03")
    calendar(site, "Consumers price index: June 2026 quarter", "20260721T104500")
    discover(rt, now_fn=lambda: PUB - timedelta(days=30))
    assert repo.get_release(rt.conn, JUNE_KEY)["status"] == "scheduled"
    ref, page_url, downloads = serve_cpi(site, "2026-06")
    live = {u: site.routes.pop(u) for u in (page_url, *downloads.values()) if u in site.routes}
    return live, page_url


def cpi_requests(site):
    return [r for r in site.requests if "consumers-price-index" in r]


def reference(rt):
    return build_cpi_dashboard(rt.conn).reference_period


def test_new_publication_flows_from_calendar_to_dashboard(rt, site):
    live, page_url = rehearse(rt, site)
    before = len(site.requests)
    assert job_release_watch(rt, now_fn=lambda: PUB - timedelta(minutes=5)) == []
    assert len(site.requests) == before  # nothing is requested before the scheduled instant

    first = job_release_watch(rt, now_fn=lambda: PUB + timedelta(seconds=5))
    assert [o.outcome for o in first] == ["not_available"]  # page not live yet
    assert repo.get_release(rt.conn, JUNE_KEY)["status"] == "scheduled"
    assert reference(rt) == "2026-03"  # last-known-good is still what is shown

    site.routes.update(live)  # the official files appear
    assert (
        job_release_watch(rt, now_fn=lambda: PUB + timedelta(seconds=30)) == []
    )  # next poll not due
    later = job_release_watch(rt, now_fn=lambda: PUB + timedelta(minutes=1, seconds=5))
    assert [o.outcome for o in later] == ["ingested"], later[0].detail
    assert repo.get_release(rt.conn, JUNE_KEY)["status"] == "published"
    assert reference(rt) == "2026-06"
    assert len(repo.list_vintages(rt.conn, "cpi.index.nsa.all_groups")) == 2  # March preserved

    app = create_app(rt.settings)
    app.state.now = lambda: PUB + timedelta(hours=1)
    with TestClient(app) as client:
        body = client.get("/api/cpi").json()
        assert round(body["analysis"]["headline_metrics"][0]["value"], 1) == 4.1
        rid = repo.get_release(rt.conn, JUNE_KEY)["id"]
        assert client.get(f"/api/releases/{rid}").json()["release"]["has_analysis"]
        assert any(
            k["metric"]["series_key"].startswith("cpi.")
            for k in client.get("/api/overview").json()["kpis"]
        )

    calls = len(site.requests)
    assert job_release_watch(rt, now_fn=lambda: PUB + timedelta(minutes=10)) == []
    assert len(site.requests) == calls  # published and quiet: no further requests


def test_daylight_saving_publication_is_polled_at_the_right_instant(rt, site):
    calendar(site, "Consumers price index: September 2026 quarter", "20261022T104500")
    discover(rt, now_fn=lambda: datetime(2026, 10, 19, tzinfo=UTC))
    row = repo.get_release(rt.conn, "consumers-price-index:september 2026 quarter")
    assert row["published_at"] == "2026-10-21T21:45:00Z"  # 10:45 NZDT (UTC+13) on 22 October
    assert row["reference_period"] == "2026-09"
    start = datetime(2026, 10, 21, 21, 45, tzinfo=UTC)
    assert job_release_watch(rt, now_fn=lambda: start - timedelta(minutes=1)) == []
    assert (
        site.requests.count(
            f"{BASE}/information-releases/consumers-price-index-september-2026-quarter/"
        )
        == 0
    )
    outcomes = job_release_watch(rt, now_fn=lambda: start + timedelta(seconds=5))
    assert [o.outcome for o in outcomes] == [
        "not_available"
    ]  # no September files exist yet: nothing is invented


def test_a_block_page_pauses_polling_until_the_cooldown_ends(rt, site):
    live, page_url = rehearse(rt, site)
    site.routes[page_url] = (403, b"<html>Request unsuccessful</html>", "text/html")
    first = job_release_watch(rt, now_fn=lambda: PUB + timedelta(seconds=5))
    assert [(o.outcome, o.error_class.value) for o in first] == [("failed", "blocked")]
    requests = len(site.requests)
    assert (
        job_release_watch(rt, now_fn=lambda: PUB + timedelta(minutes=2)) == []
    )  # due by offsets, but cooling down
    assert len(site.requests) == requests
    site.routes.update(live)
    site.clock_now += 3600  # the fetcher's own cooldown clock
    after = job_release_watch(rt, now_fn=lambda: PUB + timedelta(minutes=31))
    assert [o.outcome for o in after] == ["ingested"]


def test_layout_change_on_release_day_fails_safely_and_is_visible(rt, site):
    live, page_url = rehearse(rt, site)
    broken = {
        u: (s, (b.replace(b'"STATUS"', b'"Status"') if u.endswith("index-numbers.csv") else b), c)
        for u, (s, b, c) in live.items()
    }
    site.routes.update(broken)
    outcomes = job_release_watch(rt, now_fn=lambda: PUB + timedelta(seconds=5))
    assert [(o.outcome, o.error_class.value) for o in outcomes] == [("failed", "layout_changed")]
    assert repo.get_release(rt.conn, JUNE_KEY)["status"] == "scheduled"  # never marked published
    assert reference(rt) == "2026-03"
    app = create_app(rt.settings)
    app.state.now = lambda: PUB + timedelta(minutes=5)
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert (
            next(s for s in health["sources"] if s["source"] == "release:consumers-price-index")[
                "state"
            ]
            == "degraded"
        )
        assert health["recent_runs"][0]["error_class"] == "layout_changed"
        assert client.get("/api/cpi").json()["reference_period"] == "2026-03"


def test_catch_up_after_downtime_ingests_the_missed_release(rt, site):
    live, _ = rehearse(rt, site)
    site.routes.update(live)
    outcomes = job_catch_up(rt, now_fn=lambda: PUB + timedelta(days=2))
    assert [(o.release_key, o.outcome) for o in outcomes] == [(JUNE_KEY, "ingested")]
    assert reference(rt) == "2026-06"


def test_the_scheduler_watches_cpi_with_the_existing_jobs(rt):
    assert "consumers-price-index" in rt.adapters
    assert {j.id for j in build_scheduler(rt).get_jobs()} == {
        "refresh_calendar",
        "release_watch",
        "catch_up",
    }
    assert rt.settings.timezone == "Pacific/Auckland" and rt.settings.min_interval_seconds >= 10
