import dataclasses
from datetime import timedelta

from nzstats.clock import parse_akl_naive
from nzstats.domain import ReleaseStatus
from nzstats.scheduler.jobs import (
    build_scheduler,
    job_catch_up,
    job_refresh_calendar,
    job_release_watch,
)
from nzstats.store import repo
from tests.support import NOW, release_ref_for

PUB = parse_akl_naive("2026-09-14 10:45:00")  # real publication time of the July 2026 release


def _seed_scheduled(rt) -> str:
    ref = dataclasses.replace(
        release_ref_for("2026-07"), status=ReleaseStatus.SCHEDULED, page_url=None
    )
    repo.upsert_release(rt.conn, ref, NOW)
    return ref.release_key


def test_watch_does_nothing_and_makes_no_requests_before_publication(rt, site) -> None:
    _seed_scheduled(rt)
    outcomes = job_release_watch(rt, now_fn=lambda: PUB - timedelta(minutes=5))
    assert outcomes == [] and site.requests == []


def test_watch_ingests_at_publication_time_then_goes_quiet(rt, site) -> None:
    key = _seed_scheduled(rt)
    at = PUB + timedelta(seconds=5)
    outcomes = job_release_watch(rt, now_fn=lambda: at)
    assert [o.outcome for o in outcomes] == ["ingested"]
    assert repo.get_release(rt.conn, key)["status"] == "published"
    requests = len(site.requests)
    assert job_release_watch(rt, now_fn=lambda: at + timedelta(minutes=2)) == []
    assert len(site.requests) == requests


def test_watch_retries_when_files_appear_late(rt, site) -> None:
    key = _seed_scheduled(rt)
    url = site.file_url("2026-07", "age_sex")
    good = site.routes[url]
    site.override(url, 404, b"", "text/html")
    first = job_release_watch(rt, now_fn=lambda: PUB + timedelta(seconds=5))
    assert [o.outcome for o in first] == ["not_available"]
    site.routes[url] = good  # files appear
    assert job_release_watch(rt, now_fn=lambda: PUB + timedelta(seconds=30)) == []  # not due yet
    later = job_release_watch(rt, now_fn=lambda: PUB + timedelta(minutes=1, seconds=5))
    assert [o.outcome for o in later] == ["ingested"]
    assert repo.get_release(rt.conn, key)["status"] == "published"


def test_catch_up_recovers_after_downtime(rt, site) -> None:
    key = _seed_scheduled(rt)
    outcomes = job_catch_up(rt, now_fn=lambda: PUB + timedelta(days=2))
    assert [o.release_key for o in outcomes] == [key]
    assert outcomes[0].outcome == "ingested"


def test_refresh_calendar_job_reports_result(rt) -> None:
    result = job_refresh_calendar(rt, now_fn=lambda: NOW)
    assert result.refs > 0


def test_scheduler_registers_three_jobs_in_auckland_time(rt) -> None:
    sched = build_scheduler(rt)
    assert {j.id for j in sched.get_jobs()} == {"refresh_calendar", "release_watch", "catch_up"}
    assert str(sched.timezone) == "Pacific/Auckland"
    assert not sched.running
