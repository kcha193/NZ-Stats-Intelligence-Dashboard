from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import AKL, utc_now
from nzstats.domain import ErrorClass, IngestError, ReleaseRef
from nzstats.runtime import Runtime
from nzstats.sources.calendar import fetch_calendar, fetch_release_month
from nzstats.stats.periods import add_months
from nzstats.store import repo
from nzstats.store.db import transaction

log = logging.getLogger(__name__)

# Health of a whole calendar refresh (every feed in one run); backfill does not update it.
CALENDAR_REFRESH = "calendar_refresh"


@dataclass(frozen=True)
class DiscoveryResult:
    refs: int
    errors: tuple[str, ...]


def current_and_next_months(now: datetime) -> list[str]:
    local = now.astimezone(AKL)
    current = f"{local.year:04d}-{local.month:02d}"
    return [current, add_months(current, 1)]


def discovery_months(now: datetime) -> list[str]:
    """Previous, current and next Auckland month: published history plus what is coming."""
    current, following = current_and_next_months(now)
    return [add_months(current, -1), current, following]


def _store(rt: Runtime, refs: Sequence[ReleaseRef], now: datetime) -> None:
    with transaction(rt.conn):
        for ref in refs:
            repo.upsert_release(rt.conn, ref, now)


def attempt(
    rt: Runtime,
    source: str,
    now_fn: Callable[[], datetime],
    fetch: Callable[[], list[ReleaseRef]],
    errors: list[str],
    *,
    record_health: bool = True,
) -> int:
    """Fetch, store and record source health; failures degrade health and never raise.

    A caller that makes several requests against one source passes `record_health=False` and
    records the verdict for the whole batch itself (see `record_batch_health`).
    """
    try:
        refs = fetch()
        _store(rt, refs, now_fn())
        if record_health:
            repo.set_source_health(rt.conn, source, now_fn(), ok=True, detail=None)
        return len(refs)
    except IngestError as exc:
        message = f"{source}: {exc.error_class.value}: {exc}"
        log.warning("discovery failed: %s", message)
    except Exception as exc:  # e.g. undecodable bytes: classified and recorded, never swallowed
        log.exception("unexpected error during discovery of %s", source)
        message = f"{source}: {ErrorClass.UNEXPECTED.value}: {type(exc).__name__}; see server log"
    if record_health:
        repo.set_source_health(rt.conn, source, now_fn(), ok=False, detail=message)
    errors.append(message)
    return 0


def record_batch_health(
    rt: Runtime, source: str, now_fn: Callable[[], datetime], errors: Sequence[str]
) -> None:
    """One verdict for several requests to a source: healthy only if every request succeeded, so a
    later success cannot hide an earlier failure that may have left releases undiscovered."""
    repo.set_source_health(
        rt.conn, source, now_fn(), ok=not errors, detail="; ".join(errors) or None
    )


def discover(
    rt: Runtime, *, months: Sequence[str] = (), now_fn: Callable[[], datetime] = utc_now
) -> DiscoveryResult:
    s = rt.settings
    errors: list[str] = []
    total = attempt(
        rt,
        "calendar_ics",
        now_fn,
        lambda: fetch_calendar(rt.fetcher, s.base_url, s.calendar_ics_path),
        errors,
    )
    month_errors: list[str] = []
    for month in months:
        total += attempt(
            rt,
            "calendar_month",
            now_fn,
            lambda m=month: fetch_release_month(rt.fetcher, s.base_url, s.release_month_path, m),
            month_errors,
            record_health=False,
        )
    if months:
        record_batch_health(rt, "calendar_month", now_fn, month_errors)
    all_errors = (*errors, *month_errors)
    # One verdict for the whole run: the calendar is complete only when every feed succeeded in the
    # same run, which per-feed timestamps cannot express (e.g. alternating single-feed successes).
    record_batch_health(rt, CALENDAR_REFRESH, now_fn, all_errors)
    return DiscoveryResult(total, all_errors)
