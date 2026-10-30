"""The serve process records that it is alive, whether it is collecting, and what its jobs are doing.

This is the only writer of `ops_process` and `ops_job`. It writes to the database only: no network, no files. A
reader (`ops.health`) never needs the process itself, so a stalled scheduler and a deliberately disabled one can be
told apart from a separate command, and from a different process, after the fact.

Laptop sleep is detected here: `time.monotonic()` does not advance while the host sleeps but the wall clock does, so
a heartbeat that finds the wall clock far ahead of the monotonic clock records a suspend rather than a stall.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED,
    JobEvent,
)

from nzstats.clock import from_utc_iso, to_utc_iso, utc_now
from nzstats.ops.thresholds import Thresholds
from nzstats.store.db import connect, transaction

log = logging.getLogger(__name__)

SCHEDULER_EVENTS = EVENT_JOB_SUBMITTED | EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED


def pid_alive(pid: int) -> bool:
    """Whether a process with this id exists on this machine. Signal 0 sends nothing; a reused id is possible."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class OpsRecorder:
    def __init__(
        self,
        db_path: Path | str,
        *,
        scheduler_enabled: bool,
        collection_mode: str | None = None,
        version: str = "",
        thresholds: Thresholds | None = None,
        clock: Callable[[], datetime] = utc_now,
        mono: Callable[[], float] = time.monotonic,
        pid: Callable[[], int] = os.getpid,
        alive: Callable[[int], bool] = pid_alive,
    ) -> None:
        self._conn = connect(db_path)
        self._enabled = scheduler_enabled
        self._mode = collection_mode or ("scheduler" if scheduler_enabled else "off")
        self._version = version
        self._t = thresholds or Thresholds()
        self._clock, self._mono, self._pid, self._alive = clock, mono, pid, alive
        self._lock = (
            threading.RLock()
        )  # the heartbeat thread and scheduler listener threads share the connection
        self.boot_id = uuid.uuid4().hex
        self._last_wall: datetime | None = None
        self._last_mono = 0.0
        self._active_runs: dict[tuple[str, str, datetime], str] = {}
        self._early_completions: set[tuple[str, str, datetime]] = set()

    def start(self) -> str:
        """Register this process. Earlier processes found dead without a clean stop are stamped 'unclean'."""
        with self._lock:
            now = self._clock()
            with transaction(self._conn):
                unclean = self._stamp_dead_processes(now)
                self._conn.execute(
                    "INSERT INTO ops_process(boot_id, pid, started_at, scheduler_enabled, last_heartbeat_at,"
                    " prior_unclean, version, collection_mode) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        self.boot_id,
                        self._pid(),
                        to_utc_iso(now),
                        int(self._enabled),
                        to_utc_iso(now),
                        unclean,
                        self._version,
                        self._mode,
                    ),
                )
            self._last_wall, self._last_mono = now, self._mono()
            return self.boot_id

    def _stamp_dead_processes(self, now: datetime) -> int:
        stale = self._t.heartbeat_stale_seconds
        dead = 0
        for row in self._conn.execute(
            "SELECT boot_id, pid, last_heartbeat_at FROM ops_process WHERE stopped_at IS NULL"
        ).fetchall():
            age = (now - from_utc_iso(row["last_heartbeat_at"])).total_seconds()
            if row["pid"] != self._pid() and self._alive(row["pid"]) and age <= stale:
                continue  # another live dashboard on the same database
            dead += 1
            self._conn.execute(
                "UPDATE ops_process SET stopped_at=last_heartbeat_at, stop_reason='unclean' WHERE boot_id=?",
                (row["boot_id"],),
            )
            self._conn.execute(
                "UPDATE ops_job SET running_since=NULL, last_outcome='interrupted'"
                " WHERE boot_id=? AND running_since IS NOT NULL",
                (row["boot_id"],),
            )
        return dead

    def beat(self) -> None:
        with self._lock:
            now, mono = self._clock(), self._mono()
            suspended = 0
            if self._last_wall is not None:
                suspended = int((now - self._last_wall).total_seconds() - (mono - self._last_mono))
            self._last_wall, self._last_mono = now, mono
            if suspended > self._t.suspend_notice_seconds:
                log.info("host was suspended for about %d s", suspended)
                self._conn.execute(
                    "UPDATE ops_process SET last_heartbeat_at=?, suspend_count=suspend_count+1,"
                    " last_suspend_at=?, last_suspend_seconds=? WHERE boot_id=?",
                    (to_utc_iso(now), to_utc_iso(now), suspended, self.boot_id),
                )
            else:
                self._conn.execute(
                    "UPDATE ops_process SET last_heartbeat_at=? WHERE boot_id=?",
                    (to_utc_iso(now), self.boot_id),
                )

    def stop(self) -> None:
        """Record a clean shutdown and release the connection."""
        with self._lock:
            now = to_utc_iso(self._clock())
            self._conn.execute(
                "UPDATE ops_process SET last_heartbeat_at=?, stopped_at=?, stop_reason='clean' WHERE boot_id=?",
                (now, now, self.boot_id),
            )
            self._conn.execute(
                "UPDATE ops_job SET running_since=NULL WHERE boot_id=? AND running_since IS NOT NULL",
                (self.boot_id,),
            )
            self._conn.close()

    # --- scheduler jobs -------------------------------------------------------------------------------------

    def job_started(self, job_id: str) -> None:
        with self._lock:
            now = to_utc_iso(self._clock())
            self._conn.execute(
                "INSERT INTO ops_job(job_id, boot_id, running_since, last_started_at) VALUES (?,?,?,?)"
                " ON CONFLICT(job_id) DO UPDATE SET boot_id=excluded.boot_id,"
                " running_since=excluded.running_since, last_started_at=excluded.last_started_at",
                (job_id, self.boot_id, now, now),
            )

    def job_finished(self, job_id: str, *, error_class: str | None = None) -> None:
        """Record the end of one run. Only the exception's class is kept: messages can carry upstream text."""
        with self._lock:
            now = to_utc_iso(self._clock())
            ok = error_class is None
            self._conn.execute(
                "INSERT INTO ops_job(job_id, boot_id, last_finished_at, last_success_at, last_outcome,"
                " last_error_class, consecutive_failures) VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(job_id) DO UPDATE SET boot_id=excluded.boot_id, running_since=NULL,"
                " last_finished_at=excluded.last_finished_at,"
                " last_success_at=COALESCE(excluded.last_success_at, ops_job.last_success_at),"
                " last_outcome=excluded.last_outcome, last_error_class=excluded.last_error_class,"
                " consecutive_failures=CASE WHEN excluded.last_outcome='ok' THEN 0"
                " ELSE ops_job.consecutive_failures + 1 END",
                (
                    job_id,
                    self.boot_id,
                    now,
                    now if ok else None,
                    "ok" if ok else "error",
                    error_class,
                    0 if ok else 1,
                ),
            )

    def job_missed(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO ops_job(job_id, boot_id, last_outcome) VALUES (?,?, 'missed')"
                " ON CONFLICT(job_id) DO UPDATE SET boot_id=excluded.boot_id, last_outcome='missed'",
                (job_id, self.boot_id),
            )

    def on_scheduler_event(self, event: JobEvent) -> None:
        """APScheduler listener. A failure to record is logged and never reaches the job or the scheduler."""
        try:
            with self._lock, transaction(self._conn):
                if event.code == EVENT_JOB_SUBMITTED:
                    for run_time in event.scheduled_run_times:
                        key = (event.job_id, event.jobstore, run_time)
                        if key in self._early_completions:
                            # Executor callbacks can finish before submit_job returns. Retire the
                            # pair once both events have arrived, without reopening the run.
                            self._early_completions.remove(key)
                        else:
                            self._active_runs[key] = to_utc_iso(self._clock())
                            self.job_started(event.job_id)
                elif event.code in (EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED):
                    key = (event.job_id, event.jobstore, event.scheduled_run_time)
                    if self._active_runs.pop(key, None) is None:
                        self._early_completions.add(key)
                        if event.code != EVENT_JOB_MISSED:
                            # The first observation of a fast run is its completion. Keep that
                            # timestamp as its best-known start, rather than a stale prior run.
                            self.job_started(event.job_id)
                    if event.code == EVENT_JOB_MISSED:
                        self.job_missed(event.job_id)
                    else:
                        self.job_finished(
                            event.job_id,
                            error_class=type(event.exception).__name__
                            if event.code == EVENT_JOB_ERROR
                            else None,
                        )
                running = min(
                    (
                        started
                        for (job, _, _), started in self._active_runs.items()
                        if job == event.job_id
                    ),
                    default=None,
                )
                # Finishing one execution must not hide another overlapping/batched run.
                self._conn.execute(
                    "UPDATE ops_job SET running_since=? WHERE job_id=? AND boot_id=?",
                    (running, event.job_id, self.boot_id),
                )
        except Exception:
            log.exception("could not record scheduler event for %s", getattr(event, "job_id", "?"))


class HeartbeatThread(threading.Thread):
    def __init__(self, recorder: OpsRecorder, interval_seconds: float) -> None:
        super().__init__(name="ops-heartbeat", daemon=True)
        self._recorder, self._interval = recorder, interval_seconds
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.wait(self._interval):
            try:
                self._recorder.beat()
            except Exception:
                log.exception("heartbeat could not be recorded")

    def stop(self) -> None:
        self._halt.set()
        self.join(timeout=5)
