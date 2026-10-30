"""`serve` records itself: heartbeat, scheduler on/off, job state and clean or unclean stops (loopback only)."""

from __future__ import annotations

import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.ops.collect import collect_status
from nzstats.ops.recorder import pid_alive as real_pid_alive
from nzstats.scheduler.jobs import job_refresh_calendar
from nzstats.store.db import connect, migrate
from tests.ops import support as S


def rows(db_path, sql="SELECT * FROM ops_process ORDER BY id"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def snapshot(db_path) -> tuple[bytes, bytes]:
    """The database and its write-ahead log, byte for byte (the -shm index is shared memory and changes legitimately)."""
    wal = db_path.with_name(db_path.name + "-wal")
    return db_path.read_bytes(), wal.read_bytes() if wal.exists() else b""


def until(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not reached in time")


@pytest.fixture()
def settings(tmp_path):
    s = S.settings(tmp_path)
    conn = connect(s.db_path)
    migrate(conn)
    conn.close()  # an open connection would postpone the WAL checkpoint and make byte comparisons meaningless
    return s


def test_capabilities_are_off_unless_the_server_turns_them_on(settings) -> None:
    assert TestClient(create_app(settings)).get("/api/capabilities").json() == {
        "research_public": False
    }
    on = create_app(settings, capabilities={"research_public": True})
    assert TestClient(on).get("/api/capabilities").json() == {"research_public": True}


def test_ops_status_endpoint_serves_the_report_read_only(settings, clock) -> None:
    app = create_app(settings)
    app.state.now = lambda: clock.now
    conn = connect(settings.db_path)
    S.healthy_world(conn, clock.now)
    conn.close()
    before = snapshot(settings.db_path)
    body = TestClient(app).get("/api/ops/status").json()
    assert body["overall"] in {"ok", "attention"} and body["collection"]["mode"] == "enabled"
    assert {"issues", "freshness", "backup", "alert_delivery", "next_release"} <= set(body)
    assert snapshot(settings.db_path) == before


def test_without_record_ops_nothing_is_written(settings) -> None:
    with TestClient(create_app(settings)):
        pass
    assert rows(settings.db_path) == []


def test_serving_records_a_heartbeat_and_a_clean_stop(settings) -> None:
    with TestClient(create_app(settings, record_ops=True)):
        (row,) = rows(settings.db_path)
        assert (row["scheduler_enabled"], row["pid"], row["stopped_at"]) == (0, os.getpid(), None)
        status = collect_status(settings)
        assert (status.process.state, status.collection.mode) == ("running", "disabled")
    (row,) = rows(settings.db_path)
    assert row["stop_reason"] == "clean"
    assert collect_status(settings, pid_alive=real_pid_alive).process.state == "stopped"


def test_the_scheduler_flag_and_job_state_reach_the_database(rt, monkeypatch) -> None:
    def soon(sched, runtime) -> None:
        from datetime import datetime

        from nzstats.clock import AKL

        sched.add_job(
            job_refresh_calendar,
            "date",
            run_date=datetime.now(AKL) + timedelta(seconds=0.3),
            args=[runtime],
            id="startup_refresh",
        )

    monkeypatch.setattr("nzstats.scheduler.jobs.schedule_startup_tasks", soon)
    with TestClient(create_app(rt.settings, start_scheduler=True, runtime=rt, record_ops=True)):
        until(
            lambda: rows(
                rt.settings.db_path, "SELECT * FROM ops_job WHERE job_id='startup_refresh'"
            )
        )
        job = until(
            lambda: next(
                (
                    r
                    for r in rows(rt.settings.db_path, "SELECT * FROM ops_job")
                    if r["job_id"] == "startup_refresh" and r["last_finished_at"]
                ),
                None,
            )
        )
        assert (job["last_outcome"], job["running_since"]) == ("ok", None)
        assert rows(rt.settings.db_path)[0]["scheduler_enabled"] == 1
        status = collect_status(rt.settings)
        assert status.collection.mode == "enabled" and any(
            j.job_id == "startup_refresh" for j in status.jobs
        )


# --- real processes (loopback only, scheduler off: nothing is fetched) ---------------------------------------------------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def spawn(tmp_path, settings):
    procs: list[subprocess.Popen] = []

    def start() -> subprocess.Popen:
        port = free_port()
        env = {**os.environ, "NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_PUBLIC_RESEARCH": ""}
        proc = subprocess.Popen(
            [sys.executable, "-m", "nzstats.cli", "serve", "--no-scheduler", "--host", "127.0.0.1", "--port", str(port)],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        procs.append(proc)
        until(lambda: _answers(port) or proc.poll() is not None and pytest.fail("server exited"))
        return proc

    yield start
    for proc in procs:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def _answers(port: int) -> bool:
    try:
        return (
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/capabilities", timeout=1).status
            == 200
        )
    except OSError:
        return False


@pytest.mark.parametrize(
    "sig", [signal.SIGTERM, signal.SIGHUP], ids=["terminate", "terminal-closed"]
)
def test_a_normal_stop_and_a_closed_terminal_are_both_clean(spawn, settings, sig) -> None:
    proc = spawn()
    proc.send_signal(sig)
    # uvicorn finishes its graceful shutdown, then re-raises the signal it captured: exit 0 or -SIGTERM both mean it ran.
    assert proc.wait(timeout=20) in (0, -signal.SIGTERM)
    (row,) = rows(settings.db_path)
    assert row["stop_reason"] == "clean" and row["stopped_at"]


def test_a_killed_process_is_lost_at_once_and_the_next_start_notes_the_unclean_restart(
    spawn, settings
) -> None:
    first = spawn()
    until(lambda: rows(settings.db_path))
    first.kill()
    first.wait(timeout=10)
    lost = collect_status(settings, pid_alive=real_pid_alive)
    assert lost.process.state == "lost" and lost.collection.mode == "paused"
    assert "process:lost" in {i.key for i in lost.issues}

    second = spawn()
    old, new = until(lambda: len(rows(settings.db_path)) == 2 and rows(settings.db_path))
    assert (old["stop_reason"], new["prior_unclean"]) == ("unclean", 1)
    status = collect_status(settings, pid_alive=real_pid_alive)
    assert status.process.state == "running" and status.process.unexpected_restarts_7d == 1
    assert any(i.key.startswith("process:unexpected_restart:") for i in status.issues)
    second.send_signal(signal.SIGTERM)
    assert second.wait(timeout=20) in (0, -signal.SIGTERM)
    assert rows(settings.db_path)[1]["stop_reason"] == "clean"


def test_a_failed_startup_still_records_a_clean_stop_and_stops_the_heartbeat(
    rt, monkeypatch
) -> None:
    def explode(sched, runtime) -> None:
        raise RuntimeError("startup failed")

    monkeypatch.setattr("nzstats.scheduler.jobs.schedule_startup_tasks", explode)
    with pytest.raises(RuntimeError):
        with TestClient(create_app(rt.settings, start_scheduler=True, runtime=rt, record_ops=True)):
            pass
    (row,) = rows(rt.settings.db_path)
    assert row["stop_reason"] == "clean"


def test_ops_status_is_not_served_when_the_server_is_bound_beyond_loopback(settings) -> None:
    off = TestClient(create_app(settings, ops_status_enabled=False))
    assert off.get("/api/ops/status").status_code == 404
    assert off.get("/api/capabilities").status_code == 200  # a feature flag, not operational detail
