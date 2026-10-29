from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from nzstats.clock import AKL, utc_now
from nzstats.domain import ErrorClass
from nzstats.pipeline.discover import DiscoveryResult, discover, discovery_months
from nzstats.pipeline.ingest import IngestOutcome, ingest_release
from nzstats.runtime import Runtime
from nzstats.scheduler.planner import mark_unavailable, poll_candidates, releases_needing_ingest

log = logging.getLogger(__name__)
NowFn = Callable[[], datetime]

# Auckland wall-clock times of the daily jobs; `nzstats.ops.schedule` reads them to know when a refresh is overdue.
CALENDAR_REFRESH_AT = time(6, 0)
CATCH_UP_AT = time(7, 30)


def job_refresh_calendar(rt: Runtime, *, now_fn: NowFn = utc_now) -> DiscoveryResult:
    with rt.lock:
        return discover(rt, months=discovery_months(now_fn()), now_fn=now_fn)


def _ingest_until_blocked(rt: Runtime, keys: list[str], now_fn: NowFn) -> list[IngestOutcome]:
    """Ingest in order, stopping at the first block: the site is challenging us, so the rest wait."""
    outcomes: list[IngestOutcome] = []
    for key in keys:
        outcomes.append(ingest_release(rt, key, now_fn=now_fn))
        if outcomes[-1].error_class is ErrorClass.BLOCKED:
            break
    return outcomes


def job_release_watch(rt: Runtime, *, now_fn: NowFn = utc_now) -> list[IngestOutcome]:
    """Cheap per-minute tick: touches the network only when a release is due for a poll."""
    with rt.lock:
        now = now_fn()
        offsets = rt.settings.poll_offsets_minutes
        keys = poll_candidates(rt.conn, rt.adapters, now, offsets)
        outcomes = _ingest_until_blocked(rt, keys, now_fn)
        for key in mark_unavailable(rt.conn, rt.adapters, now, offsets):
            log.warning("release %s marked unavailable: polling budget spent", key)
        return outcomes


def job_catch_up(rt: Runtime, *, now_fn: NowFn = utc_now) -> list[IngestOutcome]:
    with rt.lock:
        keys = releases_needing_ingest(rt.conn, rt.adapters, now_fn(), rt.settings.catch_up_days)
        return _ingest_until_blocked(rt, keys, now_fn)


def build_scheduler(rt: Runtime) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=AKL)
    common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
    sched.add_job(
        job_refresh_calendar,
        CronTrigger(hour=CALENDAR_REFRESH_AT.hour, minute=CALENDAR_REFRESH_AT.minute, timezone=AKL),
        args=[rt],
        id="refresh_calendar",
        **common,
    )
    sched.add_job(
        job_release_watch, IntervalTrigger(minutes=1), args=[rt], id="release_watch", **common
    )
    sched.add_job(
        job_catch_up,
        CronTrigger(hour=CATCH_UP_AT.hour, minute=CATCH_UP_AT.minute, timezone=AKL),
        args=[rt],
        id="catch_up",
        **common,
    )
    return sched


def schedule_startup_tasks(sched: BackgroundScheduler, rt: Runtime) -> None:
    """Refresh the calendar and recover anything missed while the process was down."""
    soon = datetime.now(AKL) + timedelta(seconds=5)
    sched.add_job(job_refresh_calendar, "date", run_date=soon, args=[rt], id="startup_refresh")
    sched.add_job(
        job_catch_up,
        "date",
        run_date=soon + timedelta(seconds=60),
        args=[rt],
        id="startup_catch_up",
    )
