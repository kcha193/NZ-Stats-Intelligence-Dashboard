"""The recorder: heartbeats, unclean-stop detection, host sleep and job state."""

from __future__ import annotations

import sqlite3
import threading
from datetime import timedelta

import pytest
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
    JobExecutionEvent,
    JobSubmissionEvent,
)
from apscheduler.schedulers.background import BackgroundScheduler

from nzstats.clock import utc_now
from nzstats.ops.recorder import SCHEDULER_EVENTS, OpsRecorder, pid_alive
from nzstats.ops.thresholds import Thresholds
from tests.ops.support import keys, status


def make(db_path, clock, *, enabled=True, pid=100, alive=lambda p: False) -> OpsRecorder:
    return OpsRecorder(
        db_path,
        scheduler_enabled=enabled,
        clock=clock,
        mono=lambda: clock.mono,
        pid=lambda: pid,
        alive=alive,
    )


def process_rows(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM ops_process ORDER BY id").fetchall()


def test_start_records_the_process_and_whether_the_scheduler_is_on(db_path, conn, clock) -> None:
    make(db_path, clock, enabled=False, pid=4242).start()
    (row,) = process_rows(conn)
    assert (row["pid"], row["scheduler_enabled"], row["stopped_at"], row["prior_unclean"]) == (
        4242,
        0,
        None,
        0,
    )
    assert row["started_at"] == row["last_heartbeat_at"] == "2026-10-30T03:00:00Z"


def test_beat_advances_the_heartbeat(db_path, conn, clock) -> None:
    rec = make(db_path, clock)
    rec.start()
    clock.advance(seconds=30)
    rec.beat()
    assert process_rows(conn)[0]["last_heartbeat_at"] == "2026-10-30T03:00:30Z"


def test_a_clean_stop_is_recorded_and_closes_running_jobs(db_path, conn, clock) -> None:
    rec = make(db_path, clock)
    rec.start()
    rec.job_started("catch_up")
    clock.advance(minutes=1)
    rec.stop()
    (row,) = process_rows(conn)
    assert (row["stop_reason"], row["stopped_at"]) == ("clean", "2026-10-30T03:01:00Z")
    assert conn.execute("SELECT running_since FROM ops_job").fetchone()[0] is None


def test_a_process_that_vanished_is_stamped_unclean_by_the_next_start(db_path, conn, clock) -> None:
    first = make(db_path, clock, pid=100)
    first.start()
    first.job_started("catch_up")  # mid-run when it died
    clock.advance(seconds=30)
    first.beat()
    clock.advance(hours=2)  # nobody noticed for two hours
    second = make(db_path, clock, pid=200)
    second.start()
    old, new = process_rows(conn)
    assert (old["stop_reason"], old["stopped_at"]) == ("unclean", "2026-10-30T03:00:30Z")
    assert new["prior_unclean"] == 1 and new["stop_reason"] is None
    job = conn.execute("SELECT running_since, last_outcome FROM ops_job").fetchone()
    assert (job["running_since"], job["last_outcome"]) == (None, "interrupted")


def test_a_clean_stop_is_not_counted_as_unclean(db_path, conn, clock) -> None:
    first = make(db_path, clock, pid=100)
    first.start()
    first.stop()
    make(db_path, clock, pid=200).start()
    assert process_rows(conn)[1]["prior_unclean"] == 0


def test_another_live_dashboard_on_the_same_database_is_left_alone(db_path, conn, clock) -> None:
    make(db_path, clock, pid=100).start()
    clock.advance(seconds=10)
    make(db_path, clock, pid=200, alive=lambda p: True).start()
    old, new = process_rows(conn)
    assert old["stop_reason"] is None and new["prior_unclean"] == 0


def test_a_live_pid_with_a_long_silent_heartbeat_is_a_stalled_process_not_a_neighbour(
    db_path, conn, clock
) -> None:
    make(db_path, clock, pid=100).start()
    clock.advance(minutes=10)  # past the 5 minute heartbeat limit
    make(db_path, clock, pid=200, alive=lambda p: True).start()
    assert process_rows(conn)[0]["stop_reason"] == "unclean"


def test_host_sleep_is_recorded_as_a_suspend_not_a_stall(db_path, conn, clock) -> None:
    rec = make(db_path, clock)
    rec.start()
    clock.advance(seconds=30)
    rec.beat()
    clock.sleep(hours=5)  # laptop lid closed: the wall clock moves, the monotonic clock does not
    clock.advance(seconds=1)
    rec.beat()
    row = process_rows(conn)[0]
    assert row["suspend_count"] == 1
    assert row["last_suspend_at"] == "2026-10-30T08:00:31Z"
    assert 5 * 3600 - 5 <= row["last_suspend_seconds"] <= 5 * 3600


def test_a_starved_heartbeat_thread_is_not_mistaken_for_sleep(db_path, conn, clock) -> None:
    rec = make(db_path, clock)
    rec.start()
    clock.advance(hours=1)  # both clocks moved: the thread simply did not run
    rec.beat()
    assert process_rows(conn)[0]["suspend_count"] == 0


def test_a_short_gap_is_not_a_suspend(db_path, conn, clock) -> None:
    rec = make(db_path, clock)
    rec.start()
    clock.sleep(seconds=Thresholds().suspend_notice_seconds - 1)
    rec.beat()
    assert process_rows(conn)[0]["suspend_count"] == 0


def jobs(conn) -> dict[str, sqlite3.Row]:
    return {r["job_id"]: r for r in conn.execute("SELECT * FROM ops_job")}


def test_job_lifecycle_success(db_path, conn, clock) -> None:
    rec = make(db_path, clock)
    rec.start()
    rec.job_started("release_watch")
    assert jobs(conn)["release_watch"]["running_since"] == "2026-10-30T03:00:00Z"
    clock.advance(seconds=5)
    rec.job_finished("release_watch")
    job = jobs(conn)["release_watch"]
    assert (job["running_since"], job["last_outcome"], job["last_success_at"]) == (
        None,
        "ok",
        "2026-10-30T03:00:05Z",
    )


def test_consecutive_failures_count_and_reset_and_keep_only_the_error_class(
    db_path, conn, clock
) -> None:
    rec = make(db_path, clock)
    rec.start()
    for _ in range(3):
        clock.advance(minutes=1)
        rec.job_started("catch_up")
        rec.job_finished("catch_up", error_class="OperationalError")
    job = jobs(conn)["catch_up"]
    assert (job["consecutive_failures"], job["last_error_class"], job["last_success_at"]) == (
        3,
        "OperationalError",
        None,
    )
    rec.job_finished("catch_up")
    job = jobs(conn)["catch_up"]
    assert (job["consecutive_failures"], job["last_error_class"], job["last_outcome"]) == (
        0,
        None,
        "ok",
    )


def test_scheduler_events_drive_the_job_state_and_never_store_exception_text(
    db_path, conn, clock
) -> None:
    rec = make(db_path, clock)
    rec.start()
    rec.on_scheduler_event(
        JobSubmissionEvent(EVENT_JOB_SUBMITTED, "refresh_calendar", "default", [clock.now])
    )
    assert jobs(conn)["refresh_calendar"]["running_since"] is not None
    boom = RuntimeError("GET https://example.test/?token=SECRET-TOKEN failed")
    rec.on_scheduler_event(
        JobExecutionEvent(
            EVENT_JOB_ERROR,
            "refresh_calendar",
            "default",
            clock.now,
            exception=boom,
            traceback="tb",
        )
    )
    job = jobs(conn)["refresh_calendar"]
    assert (job["last_outcome"], job["last_error_class"], job["running_since"]) == (
        "error",
        "RuntimeError",
        None,
    )
    dump = "\n".join(conn.iterdump())
    assert "SECRET-TOKEN" not in dump
    rec.on_scheduler_event(
        JobExecutionEvent(EVENT_JOB_EXECUTED, "refresh_calendar", "default", clock.now)
    )
    assert jobs(conn)["refresh_calendar"]["last_outcome"] == "ok"
    rec.on_scheduler_event(JobExecutionEvent(EVENT_JOB_MISSED, "catch_up", "default", clock.now))
    assert jobs(conn)["catch_up"]["last_outcome"] == "missed"


def test_a_recording_failure_is_logged_and_never_reaches_the_scheduler(
    db_path, clock, caplog
) -> None:
    rec = make(db_path, clock)
    rec.start()
    rec.stop()  # connection closed
    with caplog.at_level("ERROR"):
        rec.on_scheduler_event(
            JobSubmissionEvent(EVENT_JOB_SUBMITTED, "release_watch", "default", [clock.now])
        )
    assert "could not record scheduler event for release_watch" in caplog.text


@pytest.mark.parametrize("job_id", ["startup_catch_up", "release_watch"])
@pytest.mark.parametrize("terminal", [EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED])
@pytest.mark.parametrize("completion_first", [False, True])
def test_scheduler_run_finishes_in_either_event_order(
    db_path, conn, clock, tmp_path, job_id, terminal, completion_first
) -> None:
    rec = make(db_path, clock)
    rec.start()
    for _ in range(2):
        submitted = JobSubmissionEvent(EVENT_JOB_SUBMITTED, job_id, "default", [clock.now])
        finished = JobExecutionEvent(
            terminal,
            job_id,
            "default",
            clock.now,
            exception=RuntimeError("private text") if terminal == EVENT_JOB_ERROR else None,
        )
        events = [finished, submitted] if completion_first else [submitted, finished]
        for event in events:
            rec.on_scheduler_event(event)
        row = jobs(conn)[job_id]
        assert row["running_since"] is None
        if terminal != EVENT_JOB_MISSED:
            assert row["last_started_at"] == row["last_finished_at"]
        assert (
            row["last_outcome"]
            == {EVENT_JOB_EXECUTED: "ok", EVENT_JOB_ERROR: "error", EVENT_JOB_MISSED: "missed"}[
                terminal
            ]
        )
        clock.advance(hours=2)
        rec.beat()
        assert not any("job_running_long" in key for key in keys(status(conn, tmp_path, clock.now)))
    rec.stop()


@pytest.mark.parametrize("terminal", [EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED])
def test_completion_does_not_clear_an_overlapping_run(db_path, conn, clock, terminal) -> None:
    rec = make(db_path, clock)
    rec.start()
    first = clock.now
    rec.on_scheduler_event(JobSubmissionEvent(EVENT_JOB_SUBMITTED, "catch_up", "default", [first]))
    clock.advance(seconds=30)
    second = clock.now
    rec.on_scheduler_event(JobSubmissionEvent(EVENT_JOB_SUBMITTED, "catch_up", "default", [second]))
    rec.on_scheduler_event(JobExecutionEvent(terminal, "catch_up", "default", second))
    assert jobs(conn)["catch_up"]["running_since"] == "2026-10-30T03:00:00Z"
    rec.on_scheduler_event(JobExecutionEvent(EVENT_JOB_EXECUTED, "catch_up", "default", first))
    assert jobs(conn)["catch_up"]["running_since"] is None
    rec.stop()


def test_late_batch_submission_tracks_only_unfinished_runs(db_path, conn, clock) -> None:
    rec = make(db_path, clock)
    rec.start()
    first, second = clock.now - timedelta(minutes=1), clock.now
    rec.on_scheduler_event(JobExecutionEvent(EVENT_JOB_MISSED, "catch_up", "default", first))
    rec.on_scheduler_event(
        JobSubmissionEvent(EVENT_JOB_SUBMITTED, "catch_up", "default", [first, second])
    )
    assert jobs(conn)["catch_up"]["running_since"] == "2026-10-30T03:00:00Z"
    rec.on_scheduler_event(JobExecutionEvent(EVENT_JOB_EXECUTED, "catch_up", "default", second))
    assert jobs(conn)["catch_up"]["running_since"] is None
    rec.stop()


@pytest.mark.parametrize("job_id", ["startup_catch_up", "release_watch"])
@pytest.mark.parametrize("completion_first", [False, True])
def test_fast_jobs_with_real_scheduler_events(
    db_path, conn, clock, job_id, completion_first
) -> None:
    rec = make(db_path, clock)
    rec.start()
    submitted, completed = threading.Event(), threading.Event()
    order = []
    sched = BackgroundScheduler()

    def gate_submission(event):
        if completion_first and event.code == EVENT_JOB_SUBMITTED:
            assert completed.wait(5)

    def observed(event):
        order.append(event.code)
        if event.code == EVENT_JOB_SUBMITTED:
            submitted.set()
        elif event.code == EVENT_JOB_EXECUTED:
            completed.set()

    def fast_job():
        if not completion_first:
            assert submitted.wait(5)
        return []  # an empty catch-up, with no runtime, database or network work

    sched.add_listener(gate_submission, SCHEDULER_EVENTS)
    sched.add_listener(rec.on_scheduler_event, SCHEDULER_EVENTS)
    sched.add_listener(observed, SCHEDULER_EVENTS)
    if job_id == "startup_catch_up":
        sched.add_job(fast_job, "date", run_date=utc_now(), id=job_id)
    else:
        sched.add_job(fast_job, "interval", hours=1, next_run_time=utc_now(), id=job_id)
    try:
        sched.start()
        assert completed.wait(5) and submitted.wait(5)
        expected = [EVENT_JOB_EXECUTED, EVENT_JOB_SUBMITTED]
        assert order == (expected if completion_first else expected[::-1])
        assert jobs(conn)[job_id]["running_since"] is None
        assert jobs(conn)[job_id]["last_outcome"] == "ok"
        assert not rec._active_runs and not rec._early_completions
    finally:
        sched.shutdown(wait=True)
        rec.stop()


@pytest.mark.parametrize(("pid", "expected"), [(1, True), (2**22 + 12345, False)])
def test_pid_alive_probe(pid, expected) -> None:
    assert pid_alive(pid) is expected
