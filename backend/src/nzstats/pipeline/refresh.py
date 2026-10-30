"""On-open refresh: when the dashboard is opened, one bounded check of Stats NZ for releases it is missing.

There is no timer. A check runs only when the local dashboard asks for one (`POST /api/refresh`), and it reuses the
existing pipeline end to end: `discover` reads the calendar, `ingest_release` downloads, validates and commits each
missing release in one transaction, and every request goes through the shared paced fetcher (10 s apart, retry
limits, Retry-After and block cooldowns all apply unchanged).

What a check may fetch is deliberately narrow:

* the calendar (four requests), then
* releases of a supported series that have no vintage and were published after that series' initial catch-up boundary,
  oldest first. Earlier history is never fetched (that is `backfill`'s job), and a release that already has
  a vintage is never downloaded again (a correction is ingested by hand, `nzstats ingest --release-key`, with a reason).

Each check is bounded by `RefreshSettings` (releases and logical GETs); whatever it could not reach is reported as
pending, never silently treated as current. `RefreshCoordinator` makes checks single-flight within the process
(a thread) and across processes (an flock), and spaces them with a recent-check window and a failure cooldown that
survive restarts because each check is a `refresh_run` row.
"""

from __future__ import annotations

import fcntl
import json
import logging
import shutil
import sqlite3
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO

from nzstats.adapters.base import Adapter
from nzstats.clock import AKL, from_utc_iso, to_akl_iso, to_utc_iso, utc_now
from nzstats.config import RefreshSettings, Settings
from nzstats.domain import ErrorClass, RequestRefused
from nzstats.models import RefreshStatusOut
from nzstats.pipeline.discover import CALENDAR_REFRESH, discover, discovery_months
from nzstats.pipeline.ingest import IngestOutcome, ingest_release
from nzstats.runtime import Runtime, build_runtime
from nzstats.scheduler.planner import BLOCKED_COOLDOWN
from nzstats.stats.periods import add_months, month_range
from nzstats.store.db import connect, transaction

log = logging.getLogger(__name__)

PhaseFn = Callable[[str], None]
NowFn = Callable[[], datetime]

# A file Stats NZ published but we rejected will be rejected again until the code or the file changes: retry it once
# per Auckland day, not on every open. Network trouble and "not published yet" are retried on the next check.
DEFERRED_ERRORS = ("layout_changed", "validation_failed", "unexpected")
# Stop the batch: the site is challenging us or is unreachable, so the remaining releases would fail the same way.
STOP_ERRORS = (ErrorClass.BLOCKED, ErrorClass.NETWORK)
BACKUP_PREFIX = "pre-refresh-"
# How far back a check reads the release-month feeds after a long absence (one request per month).
MAX_LOOKBACK_MONTHS = 6


@dataclass(frozen=True)
class Pending:
    release_key: str
    reason: str  # not_published_yet | rejected_today | blocked_cooldown | catch_up_limit | request_budget | stopped


@dataclass
class RefreshResult:
    state: str = (
        "completed"  # completed | failed | interrupted (the dashboard was stopped mid-check)
    )
    discovered: int = 0
    ingested: int = 0
    unchanged: int = 0
    requests: int = 0
    failures: list[dict] = field(default_factory=list)
    pending: list[Pending] = field(default_factory=list)
    error_class: str | None = None


def months_to_check(conn: sqlite3.Connection, now: datetime) -> list[str]:
    """The usual previous/current/next months, extended back to the month of the last complete calendar refresh
    (at most `MAX_LOOKBACK_MONTHS`), so releases published while the dashboard was not opened are seen."""
    months = discovery_months(now)
    row = conn.execute(
        "SELECT last_success_at FROM source_health WHERE source = ?", (CALENDAR_REFRESH,)
    ).fetchone()
    if row is None or row["last_success_at"] is None:
        return months
    last = from_utc_iso(row["last_success_at"]).astimezone(AKL)
    floor = add_months(months[1], -MAX_LOOKBACK_MONTHS)
    start = max(min(f"{last.year:04d}-{last.month:02d}", months[0]), floor)
    return list(month_range(start, months[-1]))


def missing_releases(
    conn: sqlite3.Connection, adapters: Mapping[str, object], now: datetime, catch_up_days: int
) -> tuple[list[str], list[Pending]]:
    """Releases to ingest now, in publication order, and those deliberately left for later.

    A release is missing when its series is supported, its publication time has passed, it has no vintage, and either
    it was published after the newest stored release or the persisted initial catch-up boundary, or was already
    attempted and never stored. A later vintage cannot hide a release discovered after a partial calendar failure.
    The initial boundary for a series with no data is `catch_up_days` before its first check; earlier history remains
    `backfill`'s job. A stored vintage is always excluded, regardless of the boundary.
    """
    slugs = list(adapters)
    marks = ",".join("?" * len(slugs))
    floor = to_utc_iso(now - timedelta(days=catch_up_days))
    rows = conn.execute(
        f"SELECT r.release_key, r.published_at FROM release r"
        f" WHERE r.series_slug IN ({marks}) AND r.published_at <= ?"
        " AND NOT EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
        " AND (r.published_at > COALESCE((SELECT MAX(r2.published_at) FROM release r2"
        "  WHERE r2.series_slug = r.series_slug"
        "  AND EXISTS (SELECT 1 FROM vintage v2 WHERE v2.release_id = r2.id)), ?)"
        "  OR r.published_at > (SELECT after_published_at FROM refresh_catch_up"
        "   WHERE series_slug = r.series_slug)"
        "  OR EXISTS (SELECT 1 FROM ingest_run i WHERE i.release_key = r.release_key"
        "  AND i.started_at >= r.published_at))"
        " ORDER BY r.published_at, r.id",
        (*slugs, to_utc_iso(now), floor),
    ).fetchall()
    due, deferred = [], []
    today = now.astimezone(AKL).date()
    for r in rows:
        last = conn.execute(
            "SELECT started_at, error_class FROM ingest_run WHERE release_key = ? AND started_at >= ?"
            " ORDER BY started_at DESC, id DESC LIMIT 1",
            (r["release_key"], r["published_at"]),
        ).fetchone()
        if last is not None:
            started = from_utc_iso(last["started_at"])
            if last["error_class"] == "blocked" and now < started + BLOCKED_COOLDOWN:
                deferred.append(Pending(r["release_key"], "blocked_cooldown"))
                continue
            if last["error_class"] in DEFERRED_ERRORS and started.astimezone(AKL).date() >= today:
                deferred.append(Pending(r["release_key"], "rejected_today"))
                continue
        due.append(r["release_key"])
    return due, deferred


class _BudgetedFetcher:
    """Counts logical GETs (each may include the fetcher's own bounded retries and redirect hops) and refuses, sending
    nothing, once the check's budget is spent or the dashboard is stopping. A request already in flight always finishes,
    so the shared pacing journal is never left holding an open reservation."""

    def __init__(self, inner, limit: int, stop: threading.Event | None = None) -> None:
        self._inner, self.limit, self.used, self._stop = inner, limit, 0, stop
        self.stopped = False

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def get(self, url: str, **kwargs):
        if self._stop is not None and self._stop.is_set():
            self.stopped = True
            raise RequestRefused(ErrorClass.NETWORK, "not requested: the dashboard is stopping")
        if self.used >= self.limit:
            raise RequestRefused(ErrorClass.NETWORK, "not requested: refresh request budget spent")
        self.used += 1
        try:
            return self._inner.get(url, stop=self._stop, **kwargs)
        except RequestRefused:
            if self._stop is not None and self._stop.is_set():
                self.stopped = True
            raise


class _ReportingAdapter:
    """The adapter, unchanged, except that parsing (the start of validation) is reported as a phase."""

    def __init__(self, inner: Adapter, on_phase: PhaseFn) -> None:
        self._inner, self._on_phase = inner, on_phase

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def parse(self, *args, **kwargs):
        self._on_phase("validating")
        return self._inner.parse(*args, **kwargs)


def _requests_for(adapter: Adapter) -> int:
    return 1 + len(adapter.required_downloads) + len(getattr(adapter, "optional_downloads", ()))


def _error_class(message: str) -> str:
    """Discovery errors read '<source>: <class>: <detail>'; only the class is kept."""
    parts = message.split(": ", 2)
    return parts[1] if len(parts) > 1 else ErrorClass.UNEXPECTED.value


def run_refresh(
    rt: Runtime,
    limits: RefreshSettings,
    *,
    now_fn: NowFn = utc_now,
    on_phase: PhaseFn = lambda phase: None,
    backup: Callable[[], None] | None = None,
    stop: threading.Event | None = None,
) -> RefreshResult:
    """One check: refresh the calendar, then ingest missing releases until a limit or a stop condition."""
    budget = _BudgetedFetcher(rt.fetcher, limits.max_requests, stop)
    adapters = {slug: _ReportingAdapter(a, on_phase) for slug, a in rt.adapters.items()}
    run_rt = replace(rt, fetcher=budget, adapters=adapters)
    result = RefreshResult()
    try:
        # Save once, before any discovery or newer ingestion. Never derive this boundary from a
        # later vintage: a feed may reveal an older release only on a subsequent check or restart.
        with transaction(rt.conn):
            for slug in rt.adapters:
                rt.conn.execute(
                    "INSERT OR IGNORE INTO refresh_catch_up(series_slug, after_published_at)"
                    " SELECT ?, COALESCE(MAX(r.published_at), ?) FROM release r"
                    " WHERE r.series_slug = ? AND EXISTS"
                    " (SELECT 1 FROM vintage v WHERE v.release_id = r.id)",
                    (slug, to_utc_iso(now_fn() - timedelta(days=rt.settings.catch_up_days)), slug),
                )
        on_phase("checking")
        months = months_to_check(rt.conn, now_fn())
        found = discover(run_rt, months=months, now_fn=now_fn)
        result.failures += [
            {"key": "calendar", "outcome": "failed", "error_class": _error_class(e)}
            for e in found.errors
        ]
        if budget.stopped:
            result.failures, result.state = [], "interrupted"
            return result
        if len(found.errors) == 1 + len(months):  # every calendar feed failed: nothing to go on
            result.state, result.error_class = "failed", result.failures[0]["error_class"]
            return result

        due, deferred = missing_releases(rt.conn, rt.adapters, now_fn(), rt.settings.catch_up_days)
        result.discovered = len(due) + len(deferred)
        result.pending += deferred
        batch = due[: limits.max_releases]
        result.pending += [Pending(k, "catch_up_limit") for k in due[limits.max_releases :]]
        if batch and backup is not None:
            try:
                backup()
            except Exception:  # fail closed: no verified backup, no update
                log.exception("pre-refresh backup failed; nothing was ingested")
                result.pending = [Pending(k, "stopped") for k in batch] + result.pending
                result.state, result.error_class = "failed", "backup_failed"
                return result

        for i, key in enumerate(batch):
            slug = rt.conn.execute(
                "SELECT series_slug FROM release WHERE release_key = ?", (key,)
            ).fetchone()[0]
            if budget.remaining < _requests_for(rt.adapters[slug]):
                result.pending += [Pending(k, "request_budget") for k in batch[i:]]
                break
            on_phase("downloading")
            outcome = ingest_release(run_rt, key, now_fn=now_fn)
            if (
                budget.stopped
            ):  # refused before sending: no run was recorded and nothing was committed
                result.pending += [Pending(k, "stopped") for k in batch[i:]]
                result.state = "interrupted"
                break
            _tally(result, outcome, budget)
            if outcome.error_class in STOP_ERRORS:
                result.pending += [Pending(k, "stopped") for k in batch[i + 1 :]]
                break
        return result
    finally:
        if stop is not None and stop.is_set():
            result.state = "interrupted"
        result.requests = budget.used
        on_phase("done")


def _tally(result: RefreshResult, outcome: IngestOutcome, budget: _BudgetedFetcher) -> None:
    if outcome.outcome == "ingested":
        result.ingested += 1
    elif outcome.outcome == "unchanged":
        result.unchanged += 1
    elif outcome.outcome == "not_available":
        result.pending.append(Pending(outcome.release_key, "not_published_yet"))
    elif budget.remaining <= 0 and outcome.error_class is ErrorClass.NETWORK:
        result.pending.append(Pending(outcome.release_key, "request_budget"))
    else:
        result.failures.append(
            {
                "key": outcome.release_key,
                "outcome": outcome.outcome,
                "error_class": outcome.error_class.value if outcome.error_class else None,
            }
        )


# --- verified backup before an update ----------------------------------------------------------------------------


def _activation(conn: sqlite3.Connection) -> int | None:
    """Every new vintage and every reactivated bundle takes the next number: equal numbers mean equal data."""
    return conn.execute("SELECT MAX(activation) FROM vintage").fetchone()[0]


def _held_activation(bundle: Path) -> int | None:
    from nzstats.store.backup_bundle import DB_NAME

    copy = sqlite3.connect(f"{(bundle / DB_NAME).resolve().as_uri()}?mode=ro", uri=True)
    try:
        return _activation(copy)
    finally:
        copy.close()


def rolling_backup(conn: sqlite3.Connection, settings: Settings, now: datetime) -> Path | None:
    """One verified pre-refresh bundle, replaced only by a newer verified one.

    Skipped when the newest pre-refresh bundle verified and already holds exactly the live data (the same newest
    activation), so retrying a release that is not published yet does not copy the database again. Older pre-refresh
    bundles are removed only after the new one has been written and verified; manual backups are never touched.
    """
    from nzstats.store.backup_bundle import create_bundle, read_manifest

    root = settings.backup_dir
    existing = (
        sorted(
            p
            for p in root.glob(BACKUP_PREFIX + "*")
            if p.is_dir() and not p.is_symlink() and read_manifest(p) is not None
        )
        if root.is_dir()
        else []
    )
    newest = read_manifest(existing[-1]) if existing else None
    if newest and (newest.get("verified") or {}).get("ok"):
        try:
            if _held_activation(existing[-1]) == _activation(conn):
                return None
        except sqlite3.Error:
            log.warning("pre-refresh backup %s is unreadable; taking a new one", existing[-1].name)
    dest = root / f"{BACKUP_PREFIX}{now.strftime('%Y%m%dT%H%M%SZ')}"
    create_bundle(conn, settings.raw_dir, dest, now=now)
    for old in existing:
        if old != dest:
            shutil.rmtree(old)
    return dest


# --- single-flight coordination ----------------------------------------------------------------------------------


def _row(conn: sqlite3.Connection, run_id: int | None = None) -> sqlite3.Row | None:
    if run_id is not None:
        return conn.execute("SELECT * FROM refresh_run WHERE id = ?", (run_id,)).fetchone()
    return conn.execute("SELECT * FROM refresh_run ORDER BY id DESC LIMIT 1").fetchone()


class RefreshCoordinator:
    """At most one check at a time on this data directory; checks are spaced by `RefreshSettings`.

    `trigger` never blocks on the network: it decides, records a `running` row and hands the work to a short-lived
    thread. A request that arrives while a check runs (another tab, a reload, React StrictMode) or inside the
    recent-check window or failure cooldown reuses the previous result instead.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        runtime_factory: Callable[[Settings], Runtime] = build_runtime,
        now_fn: NowFn = utc_now,
        backup: Callable[[sqlite3.Connection, Settings, datetime], object] | None = rolling_backup,
    ) -> None:
        self._settings, self._limits = settings, settings.refresh
        self._factory, self._now, self._backup = runtime_factory, now_fn, backup
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rt: Runtime | None = None
        self._lock_path = settings.data_dir / ".refresh-lock"

    def _try_flock(self) -> IO[bytes] | None:
        handle = self._lock_path.open("a+b")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        return handle

    def recover(self) -> int:
        """Mark checks left `running` by a process that died (or slept through a restart) as interrupted."""
        with self._lock:
            handle = self._try_flock()
            if handle is None:
                return 0  # another process is checking right now; its row is live
            conn = connect(self._settings.db_path)
            try:
                return conn.execute(
                    "UPDATE refresh_run SET state = 'interrupted', phase = 'done', finished_at = ?"
                    " WHERE state = 'running'",
                    (to_utc_iso(self._now()),),
                ).rowcount
            finally:
                conn.close()
                handle.close()

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """For shutdown: let the request in flight finish, send nothing more, and wait for the check to record itself.
        Killing it mid-request instead would leave a pacing reservation that blocks Stats NZ for 30 minutes."""
        with self._lock:
            self._stop.set()
            thread = self._thread
        if thread is not None:
            thread.join()

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _recent(self, last: sqlite3.Row | None, now: datetime, manual: bool) -> bool:
        if last is None or last["state"] in ("running", "interrupted"):
            return False
        started = from_utc_iso(last["started_at"])
        finished = from_utc_iso(last["finished_at"]) if last["finished_at"] else started
        if now < started:  # the clock moved back: do not let a future stamp suppress checks
            return False
        if last["state"] == "failed" and now - finished < timedelta(
            minutes=self._limits.failure_cooldown_minutes
        ):
            return True
        if manual:
            return now - started < timedelta(seconds=self._limits.manual_min_interval_seconds)
        return last["state"] == "completed" and now - finished < timedelta(
            minutes=self._limits.fresh_window_minutes
        )

    def trigger(self, *, manual: bool = False) -> bool:
        """Start a check unless one is running or a recent result stands. True when this call started one."""
        with self._lock:
            if self.running() or self._stop.is_set():
                return False
            conn = connect(self._settings.db_path)
            try:
                now = self._now()
                if self._recent(_row(conn), now, manual):
                    return False
                handle = self._try_flock()
                if handle is None:
                    return False  # another dashboard process on this data directory is checking
                if self._recent(
                    _row(conn), now, manual
                ):  # it may have finished just before we took the lock
                    handle.close()
                    return False
                try:
                    # Anything still `running` belonged to a process that no longer holds the lock.
                    conn.execute(
                        "UPDATE refresh_run SET state = 'interrupted', phase = 'done', finished_at = ?"
                        " WHERE state = 'running'",
                        (to_utc_iso(now),),
                    )
                    run_id = conn.execute(
                        "INSERT INTO refresh_run(trigger, started_at, state, phase) VALUES (?,?, 'running', 'checking')",
                        ("manual" if manual else "open", to_utc_iso(now)),
                    ).lastrowid
                except BaseException:
                    handle.close()
                    raise
            finally:
                conn.close()
            self._thread = threading.Thread(
                target=self._work, args=(run_id, handle), name="on-open-refresh", daemon=True
            )
            self._thread.start()
            return True

    def _work(self, run_id: int, handle: IO[bytes]) -> None:
        result = RefreshResult(state="failed", error_class=ErrorClass.UNEXPECTED.value)
        try:
            if self._rt is None:
                self._rt = self._factory(self._settings)
            rt = self._rt

            def phase(name: str) -> None:
                if name == "done":
                    return  # _finish publishes done and the terminal state in one transaction
                rt.conn.execute("UPDATE refresh_run SET phase = ? WHERE id = ?", (name, run_id))

            backup = (
                (lambda: self._backup(rt.conn, self._settings, self._now()))
                if self._backup
                else None
            )
            with rt.lock:
                result = run_refresh(
                    rt,
                    self._limits,
                    now_fn=self._now,
                    on_phase=phase,
                    backup=backup,
                    stop=self._stop,
                )
        except Exception:  # recorded as a failed check; the traceback goes to the log only
            log.exception("on-open refresh failed")
        finally:
            try:
                self._finish(run_id, result)
            except Exception:
                log.exception("could not record the end of refresh %s", run_id)
            finally:
                handle.close()
        log.info(
            "refresh %s %s: %d ingested, %d unchanged, %d pending, %d failure(s), %d request(s)",
            run_id,
            result.state,
            result.ingested,
            result.unchanged,
            len(result.pending),
            len(result.failures),
            result.requests,
        )

    def _finish(self, run_id: int, result: RefreshResult) -> None:
        conn = connect(self._settings.db_path)
        try:
            with transaction(conn):
                conn.execute(
                    "UPDATE refresh_run SET finished_at = ?, state = ?, phase = 'done', discovered = ?,"
                    " ingested = ?, unchanged = ?, requests = ?, failures = ?, pending = ?, error_class = ?"
                    " WHERE id = ?",
                    (
                        to_utc_iso(self._now()),
                        result.state,
                        result.discovered,
                        result.ingested,
                        result.unchanged,
                        result.requests,
                        json.dumps(result.failures),
                        json.dumps([p.__dict__ for p in result.pending]),
                        result.error_class,
                        run_id,
                    ),
                )
        finally:
            conn.close()


# --- status for the API and the operations report ----------------------------------------------------------------


def _label(title: str | None, slug: str) -> str:
    return (title or slug).split(":")[0].strip() or slug


def refresh_status(conn: sqlite3.Connection, series: Iterable[str], mode: str) -> RefreshStatusOut:
    """What the dashboard header shows: the last check, what is pending, and how current the statistics are."""
    slugs = list(series)
    marks = ",".join("?" * len(slugs))
    latest = [
        {
            "series_slug": r["series_slug"],
            "label": _label(r["title"], r["series_slug"]),
            "reference_period": r["reference_period"],
            "period_label": r["period_label"],
            "published_at": to_akl_iso(r["published_at"]),
        }
        for r in conn.execute(
            f"SELECT r.series_slug, r.title, r.reference_period, r.period_label,"
            " MAX(r.published_at) AS published_at"
            f" FROM release r WHERE r.series_slug IN ({marks})"
            " AND EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
            " GROUP BY r.series_slug ORDER BY r.series_slug",
            slugs,
        )
    ]
    # Every new vintage and every reactivated bundle takes the next activation number, so this changes whenever
    # verified data is committed, by any process, even twice within one second.
    activation = conn.execute("SELECT MAX(activation) FROM vintage").fetchone()[0]
    data_version = f"a{activation}" if activation is not None else None
    base = {"mode": mode, "latest": latest, "data_version": data_version}
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    row = _row(conn) if "refresh_run" in tables else None
    if row is None:
        return RefreshStatusOut(state="never", **base)
    success = conn.execute(
        "SELECT MAX(finished_at) FROM refresh_run WHERE state = 'completed'"
    ).fetchone()[0]
    pending = []
    for p in json.loads(row["pending"]):
        rel = conn.execute(
            "SELECT series_slug, title, reference_period, period_label, published_at FROM release"
            " WHERE release_key = ?",
            (p["release_key"],),
        ).fetchone()
        pending.append(
            {
                "release_key": p["release_key"],
                "reason": p["reason"],
                "series_slug": rel["series_slug"] if rel else None,
                "label": _label(rel["title"], rel["series_slug"]) if rel else None,
                "reference_period": rel["reference_period"] if rel else None,
                "period_label": rel["period_label"] if rel else None,
                "published_at": to_akl_iso(rel["published_at"]) if rel else None,
            }
        )
    return RefreshStatusOut(
        state=row["state"],
        phase=row["phase"] if row["state"] == "running" else None,
        run_id=row["id"],
        trigger=row["trigger"],
        started_at=to_akl_iso(row["started_at"]),
        finished_at=to_akl_iso(row["finished_at"]) if row["finished_at"] else None,
        last_success_at=to_akl_iso(success) if success else None,
        discovered=row["discovered"],
        ingested=row["ingested"],
        unchanged=row["unchanged"],
        requests=row["requests"],
        failures=json.loads(row["failures"]),
        pending=pending,
        error_class=row["error_class"],
        **base,
    )
