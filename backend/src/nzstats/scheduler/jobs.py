from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from nzstats.clock import AKL, utc_now
from nzstats.pipeline.discover import DiscoveryResult, current_and_next_months, discover
from nzstats.pipeline.ingest import IngestOutcome, ingest_release
from nzstats.runtime import Runtime
from nzstats.scheduler.planner import mark_unavailable, poll_candidates, releases_needing_ingest

log = logging.getLogger(__name__)
NowFn = Callable[[], datetime]


def job_refresh_calendar(rt: Runtime, *, now_fn: NowFn = utc_now) -> DiscoveryResult:
    with rt.lock:
        return discover(rt, months=current_and_next_months(now_fn()), now_fn=now_fn)


def job_release_watch(rt: Runtime, *, now_fn: NowFn = utc_now) -> list[IngestOutcome]:
    """Cheap per-minute tick: touches the network only when a release is due for a poll."""
    with rt.lock:
        now = now_fn()
        offsets = rt.settings.poll_offsets_minutes
        keys = poll_candidates(rt.conn, rt.adapters, now, offsets)
        outcomes = [ingest_release(rt, k, now_fn=now_fn) for k in keys]
        for key in mark_unavailable(rt.conn, rt.adapters, now, offsets):
            log.warning("release %s marked unavailable: polling budget spent", key)
        return outcomes


def job_catch_up(rt: Runtime, *, now_fn: NowFn = utc_now) -> list[IngestOutcome]:
    with rt.lock:
        keys = releases_needing_ingest(rt.conn, rt.adapters, now_fn(), rt.settings.catch_up_days)
        return [ingest_release(rt, k, now_fn=now_fn) for k in keys]


def build_scheduler(rt: Runtime) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=AKL)
    common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
    sched.add_job(
        job_refresh_calendar,
        CronTrigger(hour=6, minute=0, timezone=AKL),
        args=[rt],
        id="refresh_calendar",
        **common,
    )
    sched.add_job(
        job_release_watch, IntervalTrigger(minutes=1), args=[rt], id="release_watch", **common
    )
    sched.add_job(
        job_catch_up,
        CronTrigger(hour=7, minute=30, timezone=AKL),
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
