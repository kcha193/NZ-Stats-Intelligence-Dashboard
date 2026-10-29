"""Every limit that turns an observation into ATTENTION or CRITICAL. Documented in docs/phase-4f-operational-health.md.

ATTENTION means "look at this today"; CRITICAL means "the dashboard is not doing its job, or its data may be wrong".
The numbers are conservative defaults for one operator on one laptop, not tuned values: change them here, in one place,
and the specification table is checked against this file by a test.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    # Process heartbeat: the serve process writes one every `heartbeat_interval_seconds`.
    heartbeat_interval_seconds: int = 30
    heartbeat_stale_seconds: int = (
        300  # ATTENTION: no beat for 5 min (process gone, or alive but stalled)
    )
    heartbeat_critical_seconds: int = 900  # CRITICAL: a live process that has not beaten for 15 min
    suspend_notice_seconds: int = (
        150  # wall clock ran this far ahead of the monotonic clock: the host slept
    )
    resume_grace_seconds: int = (
        600  # after waking, give the scheduler this long before calling it stuck
    )
    startup_grace_seconds: int = (
        180  # a new process has this long before its jobs are expected to have run
    )

    # Scheduler progress: `release_watch` runs every minute and should always have finished recently.
    watch_attention_seconds: int = 300
    watch_critical_seconds: int = 900
    job_running_attention_seconds: int = (
        1200  # one job invocation running for 20 min (ingestion is throttled 10 s/request)
    )
    job_running_critical_seconds: int = 3600
    job_failures_critical: int = 3  # consecutive escaped exceptions of one job

    # Calendar refresh (daily, 06:00 Auckland).
    calendar_grace_minutes: int = 120
    calendar_missed_critical: int = 3  # refreshes missed in a row
    calendar_manual_attention_days: int = (
        7  # without the scheduler: last good refresh older than this
    )

    # Releases and sources.
    release_grace_floor_minutes: int = (
        240  # at least the last polling offset (180 min) plus an hour
    )
    release_critical_days: int = 7  # beyond the automatic catch-up window (config: catch_up_days)
    source_critical_days: int = 3  # a degraded calendar source with no success for this long
    blocked_window_hours: int = 24
    restart_attention_hours: int = 24

    # Backups (see docs/phase-4f-operational-health.md for what "verified" means).
    backup_attention_days: int = 7
    backup_critical_days: int = 30

    # Alerts.
    delivery_window_hours: int = 24
