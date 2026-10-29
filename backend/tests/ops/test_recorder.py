"""The recorder: heartbeats, unclean-stop detection, host sleep and job state."""

from __future__ import annotations

import sqlite3

import pytest
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
    JobExecutionEvent,
    JobSubmissionEvent,
)

from nzstats.ops.recorder import OpsRecorder, pid_alive
from nzstats.ops.thresholds import Thresholds


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
        JobSubmissionEvent(EVENT_JOB_SUBMITTED, "refresh_calendar", "default", [])
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
            JobSubmissionEvent(EVENT_JOB_SUBMITTED, "release_watch", "default", [])
        )
    assert "could not record scheduler event for release_watch" in caplog.text


@pytest.mark.parametrize(("pid", "expected"), [(1, True), (2**22 + 12345, False)])
def test_pid_alive_probe(pid, expected) -> None:
    assert pid_alive(pid) is expected
