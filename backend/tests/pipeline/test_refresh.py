"""On-open refresh: what one check fetches, ingests, reports as pending and never touches. No network: FakeSite."""

from __future__ import annotations

import dataclasses
import json
from datetime import timedelta

import pytest

from nzstats.clock import from_utc_iso
from nzstats.config import RefreshSettings
from nzstats.domain import ReleaseStatus
from nzstats.pipeline.refresh import missing_releases, rolling_backup, run_refresh
from nzstats.store import repo
from nzstats.store.backup_bundle import verify_bundle
from tests.conftest import fixture_bytes
from tests.pipeline.test_ingest import _DIRECTION_CHART, _chart_series, _edit_page
from tests.support import BASE, NOW, ingest_months, page_url, release_ref_for

LIMITS = RefreshSettings()
JUNE, JULY = "international-migration:june 2026", "international-migration:july 2026"
CALENDAR = (
    f"{BASE}/release-calendar/calendar-export/",
    *(f"{BASE}/api/v1/releaseCalendarMonth/{m}" for m in ("2026-09", "2026-10", "2026-11")),
)


@pytest.fixture()
def site(site):
    # discovery_months(NOW) is Sep, Oct and Nov 2026; the fixture set has no November payload of its own.
    site.override(CALENDAR[3], 200, fixture_bytes("release_month_2026-10.json"), "application/json")
    return site


def seed_july_missing(rt) -> None:
    """June is ingested; July is published and listed, but has no vintage yet."""
    ingest_months(rt, "2026-06")
    repo.upsert_release(rt.conn, release_ref_for("2026-07"), NOW)


def snapshot(conn) -> list[tuple]:
    """Every stored vintage and observation, to prove a check never rewrites history."""
    return [
        tuple(r)
        for r in conn.execute(
            "SELECT v.id, v.release_id, v.series_id, v.captured_at, v.source_kind, v.bundle_sha256,"
            " o.period, o.value, o.status, o.std_error, o.released_in"
            " FROM vintage v JOIN observation o ON o.vintage_id = v.id"
            " ORDER BY v.id, o.period"
        )
    ]


def run(rt, limits=LIMITS, **kw):
    phases: list[str] = []
    result = run_refresh(rt, limits, now_fn=lambda: NOW, on_phase=phases.append, **kw)
    return result, phases


def test_a_new_release_is_ingested_after_the_calendar_check(rt, site) -> None:
    seed_july_missing(rt)
    site.requests.clear()
    result, phases = run(rt)
    assert (result.state, result.ingested, result.discovered) == ("completed", 1, 1)
    assert result.pending == [] and result.failures == []
    assert site.requests[:4] == list(CALENDAR)
    assert site.requests[4] == page_url("2026-07")
    assert result.requests == len(site.requests)
    assert phases[0] == "checking" and phases[-1] == "done"
    assert phases.index("downloading") < phases.index("validating")
    assert repo.get_release(rt.conn, JULY)["status"] == "published"


def test_nothing_new_means_only_the_calendar_is_read(rt, site) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    site.requests.clear()
    result, _ = run(rt)
    assert (result.state, result.ingested, result.discovered, result.pending) == (
        "completed",
        0,
        0,
        [],
    )
    assert site.requests == list(CALENDAR)


def test_ingested_releases_and_old_history_are_never_downloaded_again(rt, site) -> None:
    ingest_months(rt, "2026-07")
    # June is older than the newest ingested release and has no vintage: history, which only backfill fetches.
    repo.upsert_release(rt.conn, release_ref_for("2026-06"), NOW)
    site.requests.clear()
    result, _ = run(rt)
    assert result.discovered == 0
    assert page_url("2026-06") not in site.requests and page_url("2026-07") not in site.requests


def test_a_series_with_no_data_only_looks_back_the_catch_up_window(rt) -> None:
    old = release_ref_for("2026-06")
    recent = dataclasses.replace(release_ref_for("2026-07"), published_at=NOW - timedelta(days=2))
    for ref in (old, recent):
        repo.upsert_release(rt.conn, ref, NOW)
    due, deferred = missing_releases(rt.conn, rt.adapters, NOW, rt.settings.catch_up_days)
    assert (due, deferred) == ([JULY], [])


def test_a_release_not_yet_published_is_not_requested(rt, site) -> None:
    ingest_months(rt, "2026-06")
    future = dataclasses.replace(
        release_ref_for("2026-07"),
        status=ReleaseStatus.SCHEDULED,
        published_at=NOW + timedelta(hours=3),
    )
    repo.upsert_release(rt.conn, future, NOW)
    site.requests.clear()
    result, _ = run(rt)
    assert result.discovered == 0 and page_url("2026-07") not in site.requests


def test_files_not_out_yet_are_pending_and_retried_next_time(rt, site) -> None:
    seed_july_missing(rt)
    url = site.file_url("2026-07", "age_sex")
    good = site.routes[url]
    site.override(url, 404, b"", "text/html")
    result, _ = run(rt)
    assert result.state == "completed" and result.ingested == 0 and result.failures == []
    assert [(p.release_key, p.reason) for p in result.pending] == [(JULY, "not_published_yet")]
    site.routes[url] = good
    again, _ = run(rt)
    assert again.ingested == 1 and again.pending == []


def test_a_malformed_file_is_rejected_last_known_good_kept_and_not_refetched_today(
    rt, site
) -> None:
    seed_july_missing(rt)
    before = snapshot(rt.conn)
    site.override(site.file_url("2026-07", "age_sex"), 200, b"not,a,stats,nz,file\n1,2,3,4,5\n")
    result, _ = run(rt)
    assert result.ingested == 0 and result.state == "completed"
    assert [f["key"] for f in result.failures] == [JULY]
    assert result.failures[0]["error_class"] in ("layout_changed", "validation_failed")
    assert snapshot(rt.conn) == before  # nothing partial was committed
    site.requests.clear()
    again, _ = run(rt)
    assert [(p.release_key, p.reason) for p in again.pending] == [(JULY, "rejected_today")]
    assert page_url("2026-07") not in site.requests


def _break_net_rolling(obj) -> None:
    """The published year-ended net migration no longer equals the total derived from the monthly files."""
    series = _chart_series(obj, _DIRECTION_CHART)
    lines = series["GraphCsvData"].splitlines()
    row = next(i for i, ln in enumerate(lines) if ln.startswith('"Net migration"'))
    cells = lines[row].split(",")
    cells[-1] = str(int(cells[-1]) + 5_000)
    lines[row] = ",".join(cells)
    series["GraphCsvData"] = "\n".join(lines)


def test_a_statistical_identity_failure_commits_nothing(rt, site) -> None:
    seed_july_missing(rt)
    before = snapshot(rt.conn)
    _edit_page(site, "2026-07", _break_net_rolling)
    result, _ = run(rt)
    assert result.ingested == 0 and snapshot(rt.conn) == before
    assert [(f["key"], f["error_class"]) for f in result.failures] == [(JULY, "validation_failed")]


def test_stats_nz_unavailable_fails_the_check_without_trying_releases(rt, site) -> None:
    seed_july_missing(rt)
    for url in CALENDAR:
        site.override(url, 503, b"", "text/html")
    site.requests.clear()
    result, _ = run(rt)
    assert (result.state, result.error_class, result.ingested) == ("failed", "network", 0)
    assert page_url("2026-07") not in site.requests


def test_a_block_page_stops_the_batch_and_leaves_the_rest_pending(rt, site) -> None:
    ingest_months(rt, "2026-06")
    july = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, july, NOW)
    later = dataclasses.replace(
        july,
        release_key="international-migration:august 2026",
        reference_period="2026-08",
        published_at=july.published_at + timedelta(days=20),
        page_url=page_url("2026-07"),
    )
    repo.upsert_release(rt.conn, later, NOW)
    site.override(
        page_url("2026-07"), 200, b"Request unsuccessful. Incapsula incident ID: 1", "text/html"
    )
    site.requests.clear()
    result, _ = run(rt)
    assert [f["error_class"] for f in result.failures] == ["blocked"]
    assert [(p.release_key, p.reason) for p in result.pending][-1] == (later.release_key, "stopped")
    assert site.requests.count(page_url("2026-07")) == 1  # nothing after the block
    # The next check, within the cooldown, sends nothing at all to the blocked site.
    site.requests.clear()
    again, _ = run(rt)
    assert site.requests == [] and again.ingested == 0


def test_the_catch_up_batch_is_bounded_and_reports_what_is_left(rt, site) -> None:
    for month, days in (("2026-06", 3), ("2026-07", 2)):
        ref = dataclasses.replace(release_ref_for(month), published_at=NOW - timedelta(days=days))
        repo.upsert_release(rt.conn, ref, NOW)
    result, _ = run(rt, dataclasses.replace(LIMITS, max_releases=1))
    assert result.ingested == 1 and result.discovered == 2
    assert [(p.release_key, p.reason) for p in result.pending] == [(JULY, "catch_up_limit")]
    rest, _ = run(rt, dataclasses.replace(LIMITS, max_releases=1))
    assert rest.ingested == 1 and rest.pending == []


def test_the_request_budget_is_never_exceeded(rt, site) -> None:
    seed_july_missing(rt)
    site.requests.clear()
    result, _ = run(rt, dataclasses.replace(LIMITS, max_requests=6))
    assert result.requests <= 6 and len(site.requests) <= 6
    assert [(p.release_key, p.reason) for p in result.pending] == [(JULY, "request_budget")]
    assert (
        page_url("2026-07") not in site.requests
    )  # never start a release the budget cannot finish
    # A release the budget never reached has no ingestion run: its polling history is untouched.
    assert (
        rt.conn.execute(
            "SELECT COUNT(*) FROM ingest_run WHERE release_key = ?", (JULY,)
        ).fetchone()[0]
        == 0
    )


def test_revisions_arrive_as_a_new_vintage_and_history_is_preserved(rt, site) -> None:
    seed_july_missing(rt)
    before = snapshot(rt.conn)
    result, _ = run(rt)
    after = snapshot(rt.conn)
    assert result.ingested == 1
    assert after[: len(before)] == before  # June's vintages, capture times and values are untouched
    june_periods = {r[6] for r in before}
    revised = [r for r in after[len(before) :] if r[6] in june_periods]
    assert revised  # the July files restate earlier months: a new vintage, never an edit


def test_historical_backfill_provenance_is_untouched(rt, site) -> None:
    """A backfilled release stays "earliest stored": its capture time and publication time are never rewritten."""
    seed_july_missing(rt)
    late = "2026-10-29T00:00:00Z"  # captured weeks after publication, like the Phase 4E backfill
    rt.conn.execute("UPDATE vintage SET captured_at = ?", (late,))
    query = (
        "SELECT v.id, v.captured_at, r.published_at, r.status FROM vintage v"
        " JOIN release r ON r.id = v.release_id ORDER BY v.id"
    )
    before = [tuple(r) for r in rt.conn.execute(query)]
    result, _ = run(rt)
    after = [tuple(r) for r in rt.conn.execute(query)]
    assert result.ingested == 1 and after[: len(before)] == before
    assert {r[1] for r in after[len(before) :]} == {
        "2026-10-11T03:00:00Z"
    }  # the new release: captured now


def test_only_stats_nz_is_contacted(rt, site) -> None:
    seed_july_missing(rt)
    site.requests.clear()
    run(rt)
    assert site.requests and all(u.startswith(BASE + "/") for u in site.requests)
    research = [
        r[0]
        for r in rt.conn.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'research_%' AND type='table'"
        )
    ]
    assert all(rt.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0 for t in research)


def test_a_backup_is_taken_before_an_update(rt, site) -> None:
    seed_july_missing(rt)
    calls: list[str] = []
    result, _ = run(rt, backup=lambda: calls.append("backup"))
    assert calls == ["backup"] and result.ingested == 1


def test_a_failed_backup_stops_the_update(rt, site) -> None:
    seed_july_missing(rt)
    before = snapshot(rt.conn)

    def broken() -> None:
        raise OSError("disk full")

    site.requests.clear()
    failed, _ = run(rt, backup=broken)
    assert (failed.state, failed.error_class, failed.ingested) == ("failed", "backup_failed", 0)
    assert [(p.release_key, p.reason) for p in failed.pending] == [(JULY, "stopped")]
    assert snapshot(rt.conn) == before and page_url("2026-07") not in site.requests


def test_no_backup_when_there_is_nothing_to_ingest(rt, site) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    calls: list[str] = []
    run(rt, backup=lambda: calls.append("backup"))
    assert calls == []


def test_the_rolling_backup_is_verified_kept_single_and_not_duplicated(rt) -> None:
    ingest_months(rt, "2026-06")
    first = rolling_backup(rt.conn, rt.settings, NOW)
    assert first is not None and verify_bundle(first).ok
    assert (
        rolling_backup(rt.conn, rt.settings, NOW + timedelta(hours=1)) is None
    )  # no new data: no copy
    manual = rt.settings.backup_dir / "nzstats-manual"
    manual.mkdir()
    ingest_months(rt, "2026-07")
    rt.conn.execute(
        "UPDATE vintage SET captured_at = ? WHERE captured_at = (SELECT MAX(captured_at) FROM vintage)",
        ((NOW + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),),
    )
    second = rolling_backup(rt.conn, rt.settings, NOW + timedelta(hours=3))
    assert second is not None and verify_bundle(second).ok
    kept = sorted(p.name for p in rt.settings.backup_dir.iterdir())
    assert kept == [
        "nzstats-manual",
        second.name,
    ]  # the older rolling copy went; manual backups never do


def test_pending_and_failures_are_json_serialisable(rt, site) -> None:
    seed_july_missing(rt)
    site.override(site.file_url("2026-07", "age_sex"), 404, b"", "text/html")
    result, _ = run(rt)
    json.dumps([p.__dict__ for p in result.pending]) and json.dumps(result.failures)


def test_a_backup_taken_in_the_same_second_as_new_data_is_not_trusted_to_hold_it(rt) -> None:
    """The check backs up, then ingests within the same second: that backup predates the new vintages."""
    ingest_months(rt, "2026-06")
    first = rolling_backup(rt.conn, rt.settings, NOW)
    ingest_months(rt, "2026-07")  # captured at NOW too
    second = rolling_backup(rt.conn, rt.settings, NOW + timedelta(seconds=1))
    assert first is not None and second is not None and second != first


def test_a_reactivated_bundle_counts_as_new_data_for_the_backup(rt) -> None:
    """A correction reverting to earlier content changes the data without a new capture time."""
    ingest_months(rt, "2026-06")
    assert rolling_backup(rt.conn, rt.settings, NOW) is not None
    # What `repo.reactivate_bundle` does when a release reverts to content it published before.
    rt.conn.execute(
        "UPDATE vintage SET activation = (SELECT MAX(activation) + 1 FROM vintage)"
        " WHERE id = (SELECT MIN(id) FROM vintage)"
    )
    assert rolling_backup(rt.conn, rt.settings, NOW + timedelta(hours=1)) is not None


def test_a_rejected_release_is_not_forgotten_once_a_later_one_is_ingested(rt, site) -> None:
    """Review P1: June is rejected, July passes in the same check; June stays due (retried daily) and visible."""
    for month, days in (("2026-06", 3), ("2026-07", 2)):
        ref = dataclasses.replace(release_ref_for(month), published_at=NOW - timedelta(days=days))
        repo.upsert_release(rt.conn, ref, NOW)
    june = "international-migration:june 2026"
    site.override(site.file_url("2026-06", "age_sex"), 200, b"not,a,stats,nz,file\n1,2,3,4,5\n")
    result, _ = run(rt)
    assert result.ingested == 1 and [f["key"] for f in result.failures] == [june]
    # Same day: still listed (deferred), never silently "up to date".
    due, deferred = missing_releases(rt.conn, rt.adapters, NOW, rt.settings.catch_up_days)
    assert (due, [(p.release_key, p.reason) for p in deferred]) == ([], [(june, "rejected_today")])
    # Next day: retried, like the scheduler's daily catch-up.
    due, _ = missing_releases(
        rt.conn, rt.adapters, NOW + timedelta(days=1), rt.settings.catch_up_days
    )
    assert due == [june]


def test_an_attempted_release_older_than_the_newest_stays_due_but_unattempted_history_does_not(
    rt,
) -> None:
    ingest_months(rt, "2026-07")
    june = release_ref_for("2026-06")
    repo.upsert_release(rt.conn, june, NOW)
    assert missing_releases(rt.conn, rt.adapters, NOW, 7) == ([], [])  # history: backfill's job
    published = rt.conn.execute(
        "SELECT published_at FROM release WHERE release_key = ?", (june.release_key,)
    ).fetchone()[0]
    repo.record_ingest_run(
        rt.conn, june.release_key, from_utc_iso(published) + timedelta(minutes=1),
        from_utc_iso(published) + timedelta(minutes=2), "not_available", "not_found", None,
    )  # fmt: skip
    assert missing_releases(rt.conn, rt.adapters, NOW, 7) == ([june.release_key], [])


def test_stopping_finishes_the_request_in_flight_then_sends_nothing(rt, site) -> None:
    """Review P2: Ctrl+C mid-check must not leave a pacing reservation open (that would block Stats NZ for 30 min)."""
    import threading

    seed_july_missing(rt)
    stop = threading.Event()
    handler = site.handler

    def stop_on_page(request):
        if str(request.url) == page_url("2026-07"):
            stop.set()  # the dashboard is told to stop while this request is in flight
        return handler(request)

    site.handler = stop_on_page
    rt.fetcher._client._transport.handler = stop_on_page
    before = snapshot(rt.conn)
    site.requests.clear()
    result, _ = run(rt, stop=stop)
    assert result.state == "interrupted"
    assert site.requests[-1] == page_url(
        "2026-07"
    )  # the in-flight request completed; nothing after it
    assert [(p.release_key, p.reason) for p in result.pending] == [(JULY, "stopped")]
    assert snapshot(rt.conn) == before
    assert (
        rt.conn.execute(
            "SELECT COUNT(*) FROM ingest_run WHERE release_key = ?", (JULY,)
        ).fetchone()[0]
        == 0
    )


def test_after_a_long_absence_the_calendar_is_read_back_to_the_last_refresh(rt, site) -> None:
    """Review P2: months the dashboard was never opened in are read again, so their releases are not invisible."""
    from nzstats.pipeline.refresh import months_to_check

    assert months_to_check(rt.conn, NOW) == [
        "2026-09",
        "2026-10",
        "2026-11",
    ]  # never refreshed: the usual three
    repo.set_source_health(
        rt.conn, "calendar_refresh", NOW - timedelta(days=100), ok=True, detail=None
    )
    assert months_to_check(rt.conn, NOW) == ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
    repo.set_source_health(
        rt.conn, "calendar_refresh", NOW - timedelta(days=400), ok=True, detail=None
    )
    assert months_to_check(rt.conn, NOW)[0] == "2026-04"  # bounded: six months back at most
    site.requests.clear()
    run(rt)
    assert f"{BASE}/api/v1/releaseCalendarMonth/2026-04" in site.requests


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("existing_data", [False, True])
def test_partial_calendar_failure_retains_late_release_after_newer_ingestion(
    rt, site, restart, existing_data
):
    """A recovered older feed stays eligible after a newer release advances the vintage watermark."""
    from nzstats.clock import AKL
    from nzstats.runtime import build_runtime
    from tests.ops.support import add_release

    if existing_data:
        add_release(
            rt.conn,
            "migration-baseline",
            "international-migration",
            NOW - timedelta(days=30),
            vintage=True,
        )

    def feed(month, days):
        ref = release_ref_for(month)
        return json.dumps(
            {
                "items": {
                    "published": [
                        {
                            "DateTaxonomyTerm": {
                                "DisplayName": ref.title,
                                "PublicationDate": (NOW - timedelta(days=days))
                                .astimezone(AKL)
                                .strftime("%Y-%m-%d %H:%M:%S"),
                            },
                            "PageLink": page_url(month).removeprefix(BASE),
                        }
                    ],
                    "upcoming": [],
                }
            }
        ).encode()

    # Long absence, and the older feed fails while the newer feed succeeds.
    repo.set_source_health(
        rt.conn, "calendar_refresh", NOW - timedelta(days=100), ok=True, detail=None
    )
    empty = b'{"items":{"published":[],"upcoming":[]}}'
    for month in ("2026-07", "2026-08", "2026-09", "2026-10", "2026-11"):
        site.override(f"{BASE}/api/v1/releaseCalendarMonth/{month}", 200, empty, "application/json")
    older_url = f"{BASE}/api/v1/releaseCalendarMonth/2026-07"
    site.override(older_url, 503, b"", "text/html")
    site.override(CALENDAR[2], 200, feed("2026-07", 2), "application/json")
    first, _ = run(rt)
    assert first.ingested == 1 and first.failures
    assert (
        rt.conn.execute(
            "SELECT COUNT(*) FROM ingest_run WHERE release_key = ?", (JUNE,)
        ).fetchone()[0]
        == 0
    )
    before = snapshot(rt.conn)

    if restart:
        settings = rt.settings
        rt.conn.close()
        rt = build_runtime(settings, fetcher=site.fetcher())
    site.override(older_url, 200, feed("2026-06", 20 if existing_data else 3), "application/json")
    site.requests.clear()
    recovered, _ = run(rt)
    assert recovered.ingested == 1 and recovered.failures == []
    assert page_url("2026-06") in site.requests
    assert page_url("2026-07") not in site.requests
    assert snapshot(rt.conn)[: len(before)] == before
    site.requests.clear()
    again, _ = run(rt)
    assert again.discovered == 0 and again.ingested == 0
    assert all("/information-releases/" not in url for url in site.requests)
