import dataclasses
from datetime import timedelta

import pytest

from nzstats.clock import parse_akl_naive, to_utc_iso
from nzstats.domain import ReleaseStatus
from nzstats.scheduler.jobs import (
    build_scheduler,
    job_catch_up,
    job_refresh_calendar,
    job_release_watch,
)
from nzstats.store import repo
from tests.support import NOW, page_url, release_ref_for

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


def _seed_unavailable(rt, site, now, *, age_days=61) -> str:
    ref = dataclasses.replace(
        release_ref_for("2026-07"),
        status=ReleaseStatus.UNAVAILABLE,
        published_at=now - timedelta(days=age_days),
    )
    repo.upsert_release(rt.conn, ref, now)
    site.override(page_url("2026-07"), 404, b"", "text/html")
    return ref.release_key


def _runs(rt, key):
    return rt.conn.execute(
        "SELECT started_at, outcome, error_class FROM ingest_run WHERE release_key = ? ORDER BY id",
        (key,),
    ).fetchall()


@pytest.mark.parametrize(("catch_up_days", "age_days"), [(7, 8), (60, 61), (7, 400)])
def test_catch_up_retries_unavailable_releases_beyond_the_age_window(
    rt, site, catch_up_days, age_days
) -> None:
    rt.settings = dataclasses.replace(rt.settings, catch_up_days=catch_up_days)
    key = _seed_unavailable(rt, site, NOW, age_days=age_days)

    outcomes = job_catch_up(rt, now_fn=lambda: NOW)

    assert [(o.release_key, o.outcome) for o in outcomes] == [(key, "not_available")]
    assert [tuple(r) for r in _runs(rt, key)] == [(to_utc_iso(NOW), "not_available", "not_found")]
    assert repo.get_release(rt.conn, key)["status"] == "unavailable"


def test_unavailable_catch_up_retries_once_per_auckland_day(rt, site) -> None:
    morning = parse_akl_naive("2026-10-11 09:00:00")
    evening = parse_akl_naive("2026-10-11 23:55:00")  # UTC date changed; Auckland date did not
    tomorrow = parse_akl_naive("2026-10-12 00:05:00")  # Auckland date changed; UTC date did not
    key = _seed_unavailable(rt, site, morning, age_days=1)
    assert [o.outcome for o in job_catch_up(rt, now_fn=lambda: morning)] == ["not_available"]
    requests = len(site.requests)

    assert job_catch_up(rt, now_fn=lambda: morning) == []
    assert job_catch_up(rt, now_fn=lambda: evening) == []
    assert len(site.requests) == requests
    assert len(_runs(rt, key)) == 1
    assert [o.outcome for o in job_catch_up(rt, now_fn=lambda: tomorrow)] == ["not_available"]
    assert [r["started_at"] for r in _runs(rt, key)] == [
        "2026-10-10T20:00:00Z",
        "2026-10-11T11:05:00Z",
    ]


@pytest.mark.parametrize("day", ["2026-04-05", "2026-09-27"])
def test_unavailable_daily_retry_follows_local_dates_through_both_dst_transitions(
    rt, site, day
) -> None:
    first = parse_akl_naive(f"{day} 00:30:00")
    evening = parse_akl_naive(f"{day} 23:55:00")
    tomorrow = first + timedelta(days=1, minutes=-15)
    key = _seed_unavailable(rt, site, first, age_days=1)
    assert [o.outcome for o in job_catch_up(rt, now_fn=lambda: first)] == ["not_available"]
    requests = len(site.requests)

    assert job_catch_up(rt, now_fn=lambda: evening) == []
    assert len(site.requests) == requests
    assert [o.outcome for o in job_catch_up(rt, now_fn=lambda: tomorrow)] == ["not_available"]
    assert len(_runs(rt, key)) == 2


@pytest.mark.parametrize(
    ("catch_up_days", "age_days", "eligible"), [(7, 8, False), (60, 8, True), (60, 61, False)]
)
def test_catch_up_keeps_the_age_window_for_ordinary_releases(
    rt, site, catch_up_days, age_days, eligible
) -> None:
    rt.settings = dataclasses.replace(rt.settings, catch_up_days=catch_up_days)
    ref = dataclasses.replace(
        release_ref_for("2026-07"), published_at=NOW - timedelta(days=age_days)
    )
    repo.upsert_release(rt.conn, ref, NOW)

    outcomes = job_catch_up(rt, now_fn=lambda: NOW)

    assert [o.outcome for o in outcomes] == (["ingested"] if eligible else [])
    assert len(_runs(rt, ref.release_key)) == int(eligible)
    assert bool(site.requests) is eligible


def test_unavailable_retry_recovers_and_stops_after_a_vintage_exists(rt, site) -> None:
    good = site.routes[page_url("2026-07")]
    key = _seed_unavailable(rt, site, NOW)
    assert [o.outcome for o in job_catch_up(rt, now_fn=lambda: NOW)] == ["not_available"]
    site.routes[page_url("2026-07")] = good
    assert job_catch_up(rt, now_fn=lambda: NOW + timedelta(hours=1)) == []

    outcomes = job_catch_up(rt, now_fn=lambda: NOW + timedelta(days=1))

    assert [o.outcome for o in outcomes] == ["ingested"]
    assert repo.get_release(rt.conn, key)["status"] == "published"
    assert repo.has_any_vintage(rt.conn, repo.get_release(rt.conn, key)["id"])
    requests = len(site.requests)
    assert job_catch_up(rt, now_fn=lambda: NOW + timedelta(days=2)) == []
    assert len(site.requests) == requests
    assert [r["outcome"] for r in _runs(rt, key)] == ["not_available", "ingested"]


def test_unavailable_release_stays_out_of_the_minute_watch(rt, site) -> None:
    key = _seed_unavailable(rt, site, NOW, age_days=0)

    assert job_release_watch(rt, now_fn=lambda: NOW) == []
    assert site.requests == []
    assert _runs(rt, key) == []


def test_reschedule_restores_watch_polling_after_an_unavailable_daily_attempt(rt, site) -> None:
    good = site.routes[page_url("2026-07")]
    key = _seed_unavailable(rt, site, NOW)
    assert [o.outcome for o in job_catch_up(rt, now_fn=lambda: NOW)] == ["not_available"]
    new_pub = NOW + timedelta(hours=1)
    repo.upsert_release(
        rt.conn,
        dataclasses.replace(
            release_ref_for("2026-07", ReleaseStatus.SCHEDULED), published_at=new_pub
        ),
        NOW,
    )
    site.routes[page_url("2026-07")] = good

    assert repo.get_release(rt.conn, key)["status"] == "delayed"
    assert job_catch_up(rt, now_fn=lambda: NOW) == []
    assert [o.outcome for o in job_release_watch(rt, now_fn=lambda: new_pub)] == ["ingested"]
    assert repo.get_release(rt.conn, key)["status"] == "published"


def test_unavailable_daily_retry_keeps_blocked_cooldown_across_midnight(rt, site) -> None:
    first = parse_akl_naive("2026-10-11 23:55:00")
    key = _seed_unavailable(rt, site, first, age_days=1)
    site.override(page_url("2026-07"), 403, b"", "text/html")
    assert [o.error_class.value for o in job_catch_up(rt, now_fn=lambda: first)] == ["blocked"]
    requests = len(site.requests)

    assert job_catch_up(rt, now_fn=lambda: first + timedelta(minutes=10)) == []
    assert len(site.requests) == requests
    assert len(_runs(rt, key)) == 1
    site.clock_now += 30 * 60  # the fetcher's own cooldown ends with the planner's
    assert [
        o.error_class.value for o in job_catch_up(rt, now_fn=lambda: first + timedelta(minutes=30))
    ] == ["blocked"]
    assert len(_runs(rt, key)) == 2


def test_unavailable_network_failure_is_recorded_and_waits_for_the_next_local_day(rt, site) -> None:
    key = _seed_unavailable(rt, site, NOW, age_days=1)
    site.override(page_url("2026-07"), 503, b"", "text/html")

    outcomes = job_catch_up(rt, now_fn=lambda: NOW)

    assert [(o.outcome, o.error_class.value) for o in outcomes] == [("failed", "network")]
    assert [tuple(r) for r in _runs(rt, key)] == [(to_utc_iso(NOW), "failed", "network")]
    requests = len(site.requests)
    assert job_catch_up(rt, now_fn=lambda: NOW + timedelta(hours=1)) == []
    assert len(site.requests) == requests
    site.override(page_url("2026-07"), 404, b"", "text/html")
    assert [o.outcome for o in job_catch_up(rt, now_fn=lambda: NOW + timedelta(days=1))] == [
        "not_available"
    ]


def test_refresh_calendar_job_reports_result(rt) -> None:
    result = job_refresh_calendar(rt, now_fn=lambda: NOW)
    assert result.refs > 0


def test_scheduler_registers_three_jobs_in_auckland_time(rt) -> None:
    sched = build_scheduler(rt)
    assert {j.id for j in sched.get_jobs()} == {"refresh_calendar", "release_watch", "catch_up"}
    assert str(sched.timezone) == "Pacific/Auckland"
    assert not sched.running


def _seed_two_scheduled(rt) -> list[str]:
    """Two releases both due at PUB: July at its real time, June published ten minutes earlier."""
    keys = []
    for month, published in (("2026-06", PUB - timedelta(minutes=10)), ("2026-07", PUB)):
        ref = dataclasses.replace(
            release_ref_for(month),
            status=ReleaseStatus.SCHEDULED,
            page_url=None,
            published_at=published,
        )
        repo.upsert_release(rt.conn, ref, NOW)
        keys.append(ref.release_key)
    return keys


@pytest.mark.parametrize("job", [job_release_watch, job_catch_up], ids=["watch", "catch_up"])
def test_a_block_ends_the_batch_instead_of_spending_every_due_release(job, rt, site) -> None:
    keys = _seed_two_scheduled(rt)
    for month in ("2026-06", "2026-07"):
        site.override(page_url(month), 403, b"", "text/html")
    outcomes = job(rt, now_fn=lambda: PUB + timedelta(seconds=5))
    assert [o.error_class.value for o in outcomes] == ["blocked"]
    assert len(site.requests) == 1
    assert sorted(len(_runs(rt, k)) for k in keys) == [0, 1], "only the release actually requested"
