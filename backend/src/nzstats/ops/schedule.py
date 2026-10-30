"""When the scheduler's daily jobs are due, in Auckland wall-clock time.

Everything is computed from the Auckland calendar date, never as "24 hours after the last run": a day is 23 or 25
hours long across a daylight-saving change, and 06:00 local is neither skipped nor repeated on those days.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from nzstats.clock import AKL
from nzstats.scheduler.jobs import CALENDAR_REFRESH_AT


def _at(day, when) -> datetime:
    return datetime.combine(day, when, tzinfo=AKL)


def last_refresh_due(now: datetime) -> datetime:
    """The most recent 06:00 Auckland instant at or before `now`."""
    local = now.astimezone(AKL)
    due = _at(local.date(), CALENDAR_REFRESH_AT)
    return due if due <= local else _at(local.date() - timedelta(days=1), CALENDAR_REFRESH_AT)


def next_refresh_due(now: datetime) -> datetime:
    """The first 06:00 Auckland instant strictly after `now`."""
    local = now.astimezone(AKL)
    due = _at(local.date(), CALENDAR_REFRESH_AT)
    return due if due > local else _at(local.date() + timedelta(days=1), CALENDAR_REFRESH_AT)


def missed_refreshes(
    last_success: datetime | None, now: datetime, grace: timedelta, *, horizon_days: int = 30
) -> int:
    """How many scheduled refreshes have come and gone (plus `grace`) with no successful refresh after them.

    A success after a due instant covers it and every earlier one. With no success at all the count is capped at
    `horizon_days` so a brand-new database does not report an unbounded number.
    """
    count, due = 0, last_refresh_due(now)
    for _ in range(horizon_days):
        if due + grace >= now:  # still inside its grace window: not missed yet
            due = _at(due.astimezone(AKL).date() - timedelta(days=1), CALENDAR_REFRESH_AT)
            continue
        if last_success is not None and last_success >= due:
            break
        count += 1
        due = _at(due.astimezone(AKL).date() - timedelta(days=1), CALENDAR_REFRESH_AT)
    return count
