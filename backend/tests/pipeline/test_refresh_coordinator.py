"""Single-flight and spacing of on-open checks: tabs, reloads, restarts, sleep and other processes. No network."""

from __future__ import annotations

import fcntl
import threading
from datetime import timedelta

import pytest

from nzstats.pipeline.refresh import RefreshCoordinator, refresh_status
from nzstats.store.db import connect
from tests.conftest import fixture_bytes
from tests.pipeline.test_refresh import CALENDAR, seed_july_missing
from tests.support import NOW, ingest_months, page_url


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


@pytest.fixture()
def site(site):
    site.override(CALENDAR[3], 200, fixture_bytes("release_month_2026-10.json"), "application/json")
    return site


@pytest.fixture()
def clock() -> Clock:
    return Clock()


def coordinator(rt, clock, **kw) -> RefreshCoordinator:
    kw.setdefault("backup", None)
    return RefreshCoordinator(rt.settings, runtime_factory=lambda s: rt, now_fn=clock, **kw)


def runs(rt) -> list[tuple]:
    return [
        tuple(r) for r in rt.conn.execute("SELECT id, trigger, state FROM refresh_run ORDER BY id")
    ]


def status(rt, mode="on_open"):
    conn = connect(rt.settings.db_path)
    try:
        return refresh_status(conn, rt.adapters, mode)
    finally:
        conn.close()


def check(c: RefreshCoordinator, **kw) -> bool:
    started = c.trigger(**kw)
    c.join(30)
    return started


def test_first_open_checks_and_reports_new_data(rt, site, clock) -> None:
    seed_july_missing(rt)
    before = status(rt).data_version
    assert status(rt).state == "never"
    assert check(coordinator(rt, clock)) is True
    s = status(rt)
    assert (s.state, s.ingested, s.discovered, s.pending) == ("completed", 1, 1, [])
    assert s.data_version != before and s.last_success_at == s.finished_at
    assert [(x.series_slug, x.reference_period, x.period_label) for x in s.latest] == [
        ("international-migration", "2026-07", "July 2026")
    ]


def test_reopening_within_the_window_reuses_the_result_without_requests(rt, site, clock) -> None:
    seed_july_missing(rt)
    c = coordinator(rt, clock)
    check(c)
    sent = len(site.requests)
    clock.now += timedelta(minutes=29)
    assert check(c) is False and len(site.requests) == sent and len(runs(rt)) == 1


def test_opening_after_several_days_checks_again(rt, site, clock) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    c = coordinator(rt, clock)
    check(c)
    clock.now += timedelta(days=3)
    site.requests.clear()
    assert check(c) is True
    # The calendar listed August for 14 October; three days on it is due, so it is looked for and, with no files
    # yet, reported as pending rather than the data being declared current.
    august = "international-migration:august 2026"
    assert site.requests == [*CALENDAR, page_url("2026-08")]
    assert [(p.release_key, p.reason) for p in status(rt).pending] == [
        (august, "not_published_yet")
    ]
    assert (status(rt).pending[0].label, status(rt).pending[0].period_label) == (
        "International migration",
        "August 2026",
    )
    assert [r[2] for r in runs(rt)] == ["completed", "completed"]


def test_many_tabs_at_once_start_one_check(rt, site, clock) -> None:
    seed_july_missing(rt)
    gate = threading.Event()
    c = RefreshCoordinator(
        rt.settings, runtime_factory=lambda s: (gate.wait(10), rt)[1], now_fn=clock, backup=None
    )
    results: list[bool] = []
    tabs = [threading.Thread(target=lambda: results.append(c.trigger())) for _ in range(8)]
    for t in tabs:
        t.start()
    for t in tabs:
        t.join()
    assert sorted(results) == [False] * 7 + [True]
    assert status(rt).state == "running" and status(rt).phase == "checking"
    # A browser reload while it runs (or React StrictMode's second effect) joins the same check.
    assert c.trigger() is False and c.trigger(manual=True) is False
    gate.set()
    c.join(30)
    assert [r[2] for r in runs(rt)] == ["completed"]
    assert site.requests.count(page_url("2026-07")) == 1


def test_closing_the_dashboard_does_not_stop_a_running_check(rt, site, clock) -> None:
    """The check belongs to the server, not the page: no request from the page is needed for it to finish."""
    seed_july_missing(rt)
    c = coordinator(rt, clock)
    c.trigger()
    c.join(30)  # nothing polls status in between
    assert status(rt).ingested == 1


def test_a_failed_check_is_retried_only_after_the_cooldown(rt, site, clock) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    for url in CALENDAR:
        site.override(url, 503, b"", "text/html")
    c = coordinator(rt, clock)
    check(c)
    assert (status(rt).state, status(rt).error_class) == ("failed", "network")
    clock.now += timedelta(minutes=9)
    assert check(c) is False and check(c, manual=True) is False  # "Check now" respects it too
    clock.now += timedelta(minutes=2)
    assert check(c) is True


def test_check_now_skips_the_window_but_not_the_minimum_spacing(rt, site, clock) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    c = coordinator(rt, clock)
    check(c)
    clock.now += timedelta(seconds=30)
    assert check(c, manual=True) is False
    clock.now += timedelta(seconds=31)
    assert check(c, manual=True) is True
    assert [r[1] for r in runs(rt)] == ["open", "manual"]


def test_a_restart_keeps_the_last_result_and_marks_an_abandoned_check_interrupted(
    rt, site, clock
) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    check(coordinator(rt, clock))
    clock.now += timedelta(minutes=5)
    # The previous server died mid-check: its row is still `running` and nobody holds the lock.
    rt.conn.execute(
        "INSERT INTO refresh_run(trigger, started_at, state, phase) VALUES ('open', '2026-10-11T03:04:00Z', 'running', 'downloading')"
    )
    restarted = coordinator(rt, clock)
    assert restarted.recover() == 1
    assert [r[2] for r in runs(rt)] == ["completed", "interrupted"]
    assert status(rt).state == "interrupted"
    # An interruption is not a failure: the next open checks straight away.
    assert check(restarted) is True


def test_a_restart_inside_the_window_does_not_check_again(rt, site, clock) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    check(coordinator(rt, clock))
    clock.now += timedelta(minutes=10)
    restarted = coordinator(rt, clock)
    restarted.recover()
    site.requests.clear()
    assert check(restarted) is False and site.requests == []


def test_waking_from_sleep_measures_the_window_on_the_wall_clock(rt, site, clock) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    c = coordinator(rt, clock)
    check(c)
    clock.now += timedelta(hours=9)  # the laptop slept overnight; monotonic time barely moved
    assert check(c) is True


def test_a_clock_moved_backwards_does_not_suppress_checks(rt, site, clock) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    c = coordinator(rt, clock)
    check(c)
    clock.now -= timedelta(hours=2)
    assert check(c) is True


def test_another_process_checking_is_not_duplicated(rt, site, clock) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    lock = (rt.settings.data_dir / ".refresh-lock").open("a+b")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        c = coordinator(rt, clock)
        site.requests.clear()
        assert c.trigger() is False and c.recover() == 0 and site.requests == []
    finally:
        lock.close()
    assert check(c) is True


def test_an_unexpected_crash_is_a_failed_check_with_last_known_good_data(rt, site, clock) -> None:
    seed_july_missing(rt)
    vintages = rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0]

    def broken(settings):
        raise RuntimeError("secret upstream text")

    c = RefreshCoordinator(rt.settings, runtime_factory=broken, now_fn=clock, backup=None)
    check(c)
    s = status(rt)
    assert (s.state, s.error_class) == ("failed", "unexpected")
    assert "secret" not in s.model_dump_json()
    assert rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0] == vintages


def test_an_ingestion_interrupted_mid_release_commits_nothing(rt, site, clock) -> None:
    seed_july_missing(rt)
    vintages = rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0]
    adapter = rt.adapters["international-migration"]
    original = adapter.parse

    def dies(*a, **k):
        original(*a, **k)
        raise KeyboardInterrupt  # stands in for SIGKILL between parse and commit

    adapter.parse = dies
    try:
        c = coordinator(rt, clock)
        with pytest.raises(KeyboardInterrupt):
            # Run on this thread so the interruption is not swallowed by the worker.
            c._rt = rt
            run_id = rt.conn.execute(
                "INSERT INTO refresh_run(trigger, started_at, state, phase) VALUES ('open', ?, 'running', 'checking')",
                ("2026-10-11T03:00:00Z",),
            ).lastrowid
            from nzstats.pipeline.refresh import run_refresh

            run_refresh(rt, rt.settings.refresh, now_fn=clock)
    finally:
        adapter.parse = original
    assert rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0] == vintages
    assert coordinator(rt, clock).recover() == 1 and runs(rt)[-1] == (run_id, "open", "interrupted")
    assert check(coordinator(rt, clock)) is True and status(rt).ingested == 1


def test_the_backup_runs_before_the_update(rt, site, clock) -> None:
    seed_july_missing(rt)
    check(
        coordinator(
            rt, clock, backup=__import__("nzstats.pipeline.refresh", fromlist=["x"]).rolling_backup
        )
    )
    backups = list(rt.settings.backup_dir.glob("pre-refresh-*"))
    assert len(backups) == 1 and status(rt).ingested == 1


def test_shutdown_waits_for_the_check_to_stop_and_records_it_interrupted(rt, site, clock) -> None:
    seed_july_missing(rt)
    gate = threading.Event()
    c = RefreshCoordinator(
        rt.settings, runtime_factory=lambda s: (gate.wait(10), rt)[1], now_fn=clock, backup=None
    )
    assert c.trigger() is True
    threading.Timer(0.2, gate.set).start()
    c.stop()
    assert not c.running() and status(rt).state == "interrupted"
    assert c.trigger() is False  # a stopping coordinator starts nothing new


def test_shutdown_waits_past_fifteen_seconds_for_inflight_request(rt, site, clock):
    """The worker owns a durable reservation for >15s; stop must wait for its result."""
    import json
    import time

    from nzstats.sources.fetcher import FilePacer

    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    original = site.handler

    def slow(request):
        entered.set()
        assert release.wait(25)
        return original(request)

    rt.fetcher._client._transport.handler = slow
    pace_path = rt.settings.data_dir / ".request-pace"
    rt.fetcher._pacer = FilePacer(pace_path, 10)
    c = coordinator(rt, clock)
    assert c.trigger() and entered.wait(5)
    stopper = threading.Thread(target=lambda: (c.stop(), stopped.set()))
    started = time.monotonic()
    stopper.start()
    try:
        assert not stopped.wait(15.2), (
            "shutdown returned while the HTTP request still owned its reservation"
        )
    finally:
        release.set()
        stopper.join(10)
        c.join(10)
    assert time.monotonic() - started >= 15.2
    assert stopped.is_set() and not c.running()
    assert status(rt).state == "interrupted" and status(rt).finished_at is not None
    assert len(site.requests) == 1
    journal = json.loads(pace_path.read_text().strip().splitlines()[-1])
    assert journal["pending"] is False and journal["blocked_until"] is None
    restarted = coordinator(rt, clock)
    assert restarted.recover() == 0
    # New process can take the pacer without a recovery cooldown (normal 10-second spacing still applies).
    with FilePacer(pace_path, 10, sleep=lambda _: None).turn() as turn:
        assert turn.blocked_until is None
