from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import AKL, utc_now
from nzstats.domain import IngestError, ReleaseRef
from nzstats.runtime import Runtime
from nzstats.sources.calendar import fetch_calendar, fetch_release_month
from nzstats.stats.periods import add_months
from nzstats.store import repo
from nzstats.store.db import transaction

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveryResult:
    refs: int
    errors: tuple[str, ...]


def current_and_next_months(now: datetime) -> list[str]:
    local = now.astimezone(AKL)
    current = f"{local.year:04d}-{local.month:02d}"
    return [current, add_months(current, 1)]


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
) -> int:
    """Fetch, store and record source health; failures degrade health and never raise."""
    try:
        refs = fetch()
        _store(rt, refs, now_fn())
        repo.set_source_health(rt.conn, source, now_fn(), ok=True, detail=None)
        return len(refs)
    except IngestError as exc:
        message = f"{source}: {exc.error_class.value}: {exc}"
        log.warning("discovery failed: %s", message)
        repo.set_source_health(rt.conn, source, now_fn(), ok=False, detail=message)
        errors.append(message)
        return 0


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
    for month in months:
        total += attempt(
            rt,
            "calendar_month",
            now_fn,
            lambda m=month: fetch_release_month(rt.fetcher, s.base_url, s.release_month_path, m),
            errors,
        )
    return DiscoveryResult(total, tuple(errors))
