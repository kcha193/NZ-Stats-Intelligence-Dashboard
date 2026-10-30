"""Read-only operational health. Never starts the scheduler, never writes, never contacts a network.

`build_status` turns the local database (and a backup scan) into an `OpsStatus`: an overall OK / ATTENTION / CRITICAL,
the facts behind it and the action for each problem. The limits are in `thresholds.Thresholds`.

Two rules shape the whole module:

* A scheduler that is deliberately off is not a fault. Whether collection is meant to be running comes from what the
  last dashboard process recorded (`ops_process.collection_mode`, or `scheduler_enabled` on older rows), and only a
  scheduler that should be running can be "stalled" or "behind". The on-open refresh (Phase 4G) runs no scheduler:
  it checks when the dashboard is opened, so it is judged by its last check (`refresh_run`), never by missed timers.
* Old observations are not missed releases. Data is out of date only when the calendar lists a release whose
  publication time has passed and which has no vintage. A series whose latest reference period is old because Stats NZ
  has not published again is current.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta

from nzstats.clock import from_utc_iso, to_akl_iso, to_utc_iso
from nzstats.config import Settings
from nzstats.ops import recorder
from nzstats.ops.report import (
    AlertDelivery,
    BackupInfo,
    CalendarInfo,
    CollectionInfo,
    DatabaseInfo,
    FailedRun,
    FreshnessRow,
    Issue,
    JobInfo,
    LatestIngestion,
    OpsStatus,
    OverdueRelease,
    ProcessInfo,
    RefreshInfo,
    ReleaseRefInfo,
    SourceStatus,
    worst,
)
from nzstats.ops.schedule import missed_refreshes, next_refresh_due
from nzstats.ops.text import akl, clean, duration
from nzstats.ops.thresholds import Thresholds
from nzstats.store import repo
from nzstats.store.db import MIGRATIONS_DIR

CALENDAR_SOURCES = ("calendar_refresh", "calendar_ics", "calendar_month")
OPEN_TO_CHECK = (
    "The dashboard checks Stats NZ each time it is opened: open it, or press Check now in its header, and the"
    " missing release is fetched (one request per 10 s, a few releases per check)."
)


def expected_schema_version() -> int:
    return max(int(f.name.split("_", 1)[0]) for f in MIGRATIONS_DIR.glob("*.sql"))


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _dt(value: str | None) -> datetime | None:
    return from_utc_iso(value) if value else None


def _akl(value: str | None) -> str | None:
    return to_akl_iso(value) if value else None


def _secs(now: datetime, value: str | None) -> int | None:
    then = _dt(value)
    return int((now - then).total_seconds()) if then else None


class _Collector:
    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.notes: list[str] = []

    def add(self, key, severity, category, title, detail, action) -> None:
        self.issues.append(
            Issue(
                key=key,
                severity=severity,
                category=category,
                title=title,
                detail=detail,
                action=action,
            )
        )


# --- database ---------------------------------------------------------------------------------------------------


def _database(conn, tables: set[str], out: _Collector, deep: bool) -> DatabaseInfo:
    version = (
        conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        if "schema_version" in tables
        else None
    )
    expected = expected_schema_version()
    info = DatabaseInfo(
        readable=True,
        schema_version=version,
        expected_schema_version=expected,
        instrumented="ops_process" in tables,
    )
    if version is None or version < expected:
        out.add(
            "database:schema_behind",
            "attention",
            "database",
            "Database schema is behind this version of the code",
            f"Schema {version} on disk, {expected} expected. Heartbeat and alert history are recorded only after upgrading.",
            "Run `scripts/run.sh migrate` (a local change; it does not contact Stats NZ), or start the dashboard.",
        )
    if deep:
        result = [r[0] for r in conn.execute("PRAGMA quick_check")]
        info.integrity = "ok" if result == ["ok"] else "failed"
        if info.integrity == "failed":
            out.add(
                "database:integrity",
                "critical",
                "database",
                "SQLite integrity check failed",
                f"quick_check reported {len(result)} problem(s).",
                "Stop the dashboard. Restore the latest verified backup into a NEW data directory"
                " (docs/phase-4f-runbook.md, 'Restore'); do not delete the damaged database.",
            )
    return info


# --- process and collection mode ---------------------------------------------------------------------------------


def _process(conn, tables, now, t, alive, out):
    if "ops_process" not in tables:
        return ProcessInfo(state="never_started"), None
    rows = conn.execute("SELECT * FROM ops_process ORDER BY id DESC LIMIT 100").fetchall()
    if not rows:
        return ProcessInfo(state="never_started"), None

    def age(r) -> int:
        return int((now - from_utc_iso(r["last_heartbeat_at"])).total_seconds())

    # A fresh heartbeat from a process that no longer exists (crash, kill) is already "lost": the database is
    # local, so the process id can be checked instead of waiting for the heartbeat to go stale.
    live = [
        r
        for r in rows
        if r["stopped_at"] is None and age(r) <= t.heartbeat_stale_seconds and alive(r["pid"])
    ]
    primary = max(live, key=lambda r: (r["scheduler_enabled"], r["id"])) if live else rows[0]
    if live:
        state = "running"
    elif primary["stopped_at"] is not None:
        state = "lost" if primary["stop_reason"] == "unclean" else "stopped"
    else:
        state = "stalled" if alive(primary["pid"]) else "lost"
    week = now - timedelta(days=7)
    restarts = sum(1 for r in rows if r["prior_unclean"] and from_utc_iso(r["started_at"]) >= week)
    info = ProcessInfo(
        state=state,
        pid=primary["pid"],
        started_at=_akl(primary["started_at"]),
        last_heartbeat_at=_akl(primary["last_heartbeat_at"]),
        heartbeat_age_seconds=age(primary),
        scheduler_enabled=bool(primary["scheduler_enabled"]),
        collection_mode=_mode(primary),
        stop_reason=primary["stop_reason"],
        suspend_count=primary["suspend_count"],
        last_suspend_at=_akl(primary["last_suspend_at"]),
        last_suspend_seconds=primary["last_suspend_seconds"],
        unexpected_restarts_7d=restarts,
    )
    last_beat = akl(from_utc_iso(primary["last_heartbeat_at"]))
    if state == "stalled":
        severity = "critical" if age(primary) > t.heartbeat_critical_seconds else "attention"
        out.add(
            "process:stalled",
            severity,
            "process",
            "The dashboard process is alive but has stopped reporting",
            f"Process {primary['pid']} has not updated its heartbeat for {duration(age(primary))} (last {last_beat})."
            " It is running, so this is a hung process, not a closed one.",
            "Check the terminal running it. If it is not responding, stop it (Ctrl+C, or `kill <pid>`) and start it again;"
            " the startup catch-up recovers anything missed.",
        )
    elif state == "lost":
        out.add(
            "process:lost",
            "attention",
            "process",
            "The dashboard stopped without a clean shutdown",
            f"Last heartbeat {last_beat}; the process ({primary['pid']}) is gone and recorded no clean stop"
            " (killed, crashed, power loss or a reboot).",
            "Start it again with `scripts/run.sh`. Look at the terminal output or the system log for a crash.",
        )
    for r in rows:
        if r["prior_unclean"] and (now - from_utc_iso(r["started_at"])) <= timedelta(
            hours=t.restart_attention_hours
        ):
            out.add(
                f"process:unexpected_restart:{r['boot_id'][:8]}",
                "attention",
                "process",
                "The dashboard restarted after an unclean stop",
                f"A new process started {akl(from_utc_iso(r['started_at']))} and found its predecessor had not shut down cleanly.",
                "Nothing to do if you expected it (reboot, power cut). Otherwise find out why the previous run died.",
            )
    return info, primary


def _mode(row) -> str:
    """How a process collected. Rows written before Phase 4G have no collection_mode: read scheduler_enabled."""
    recorded = row["collection_mode"] if "collection_mode" in row.keys() else None
    return recorded or ("scheduler" if row["scheduler_enabled"] else "off")


def _collection(process: ProcessInfo) -> CollectionInfo:
    if process.state == "never_started":
        return CollectionInfo(
            mode="unknown", summary="No dashboard process has recorded itself on this database yet."
        )
    if process.state in ("running", "stalled"):
        if process.collection_mode == "scheduler":
            return CollectionInfo(
                mode="enabled",
                summary="Scheduled collection is on: the dashboard checks Stats NZ by itself.",
            )
        if process.collection_mode == "on_open":
            return CollectionInfo(
                mode="on_open",
                summary="On-open refresh: Stats NZ is checked once each time the dashboard is opened (or on Check now)."
                " No scheduler runs, by design.",
            )
        return CollectionInfo(
            mode="disabled",
            summary="Collection is deliberately off (offline mode: started with --offline or --no-scheduler)."
            " Nothing is fetched until you run it.",
        )
    intended = {
        "scheduler": "the scheduler on",
        "on_open": "on-open refresh",
        "off": "offline mode",
    }[process.collection_mode or "off"]
    return CollectionInfo(
        mode="paused",
        summary=f"The dashboard is not running, so nothing is being collected (it last ran with {intended}).",
    )


# --- on-open refresh ---------------------------------------------------------------------------------------------


def _refresh(conn, tables, now, t, process, out) -> RefreshInfo:
    if "refresh_run" not in tables:
        return RefreshInfo(state="never")
    row = conn.execute("SELECT * FROM refresh_run ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return RefreshInfo(state="never")
    success = conn.execute(
        "SELECT MAX(finished_at) FROM refresh_run WHERE state = 'completed'"
    ).fetchone()[0]
    running = _secs(now, row["started_at"]) if row["state"] == "running" else None
    info = RefreshInfo(
        state=row["state"],
        phase=row["phase"] if row["state"] == "running" else None,
        started_at=_akl(row["started_at"]),
        finished_at=_akl(row["finished_at"]),
        running_for_seconds=running,
        last_success_at=_akl(success),
        ingested=row["ingested"],
        pending=len(json.loads(row["pending"])),
        failures=len(json.loads(row["failures"])),
        error_class=row["error_class"],
    )
    if row["state"] == "failed":
        out.add(
            "refresh:failed",
            "attention",
            "refresh",
            "The last check for new Stats NZ data failed",
            f"The check started {akl(from_utc_iso(row['started_at']))} ended with {row['error_class'] or 'an error'};"
            " the dashboard is showing the last verified data.",
            "Nothing is lost. `network` or `blocked` usually clear by themselves: press Check now later (a failed check"
            " waits out a short cooldown; never retry a block in a loop). `backup_failed` means the pre-update backup"
            " could not be written: free disk space. Otherwise read the dashboard's terminal output.",
        )
    elif row["state"] == "interrupted":
        out.notes.append(
            "The last check was interrupted (the dashboard stopped mid-check); nothing partial was kept and the next"
            " opening checks again."
        )
    elif (
        running is not None
        and process.state == "running"
        and running > t.job_running_attention_seconds
    ):
        out.add(
            "refresh:running_long",
            "critical" if running > t.job_running_critical_seconds else "attention",
            "refresh",
            f"A check for new data has been running for {duration(running)}",
            "A check is bounded (a few releases, one request per 10 s), so this one has gone on longer than it should.",
            "Watch the terminal output. If it is hung, restart the dashboard: an interrupted ingestion rolls back and"
            " last-known-good data is kept.",
        )
    return info


# --- scheduler jobs ----------------------------------------------------------------------------------------------


def _jobs(conn, tables, now, t, process, primary, collection, out) -> list[JobInfo]:
    if "ops_job" not in tables:
        return []
    mine = primary["boot_id"] if primary is not None else None
    infos, rows = [], conn.execute("SELECT * FROM ops_job ORDER BY job_id").fetchall()
    for r in rows:
        running = _secs(now, r["running_since"])
        if (
            running is not None
            and primary is not None
            and primary["last_suspend_at"]
            and primary["last_suspend_at"] >= r["running_since"]
        ):
            running = max(
                0, running - (primary["last_suspend_seconds"] or 0)
            )  # the host slept mid-run
        state = (
            "running" if running is not None else ("idle" if r["last_finished_at"] else "never_ran")
        )
        infos.append(
            JobInfo(
                job_id=r["job_id"],
                state=state,
                running_for_seconds=running,
                last_started_at=_akl(r["last_started_at"]),
                last_finished_at=_akl(r["last_finished_at"]),
                last_success_at=_akl(r["last_success_at"]),
                last_outcome=r["last_outcome"],
                last_error_class=r["last_error_class"],
                consecutive_failures=r["consecutive_failures"],
            )
        )
        if process.state != "running" or r["boot_id"] != mine:
            continue
        if running is not None and running > t.job_running_attention_seconds:
            out.add(
                f"scheduler:job_running_long:{r['job_id']}",
                "critical" if running > t.job_running_critical_seconds else "attention",
                "scheduler",
                f"Scheduler job {r['job_id']} has been running for {duration(running)}",
                "Ingestion is throttled to one request per 10 s, so a long run can be legitimate (many releases), but this one"
                " is beyond the expected duration and may be stuck.",
                "Watch the terminal output. If it is hung, restart the dashboard: an interrupted ingestion rolls back and last-known-good data is kept.",
            )
        if r["last_outcome"] == "error":
            out.add(
                f"scheduler:job_failing:{r['job_id']}",
                "critical" if r["consecutive_failures"] >= t.job_failures_critical else "attention",
                "scheduler",
                f"Scheduler job {r['job_id']} is raising errors",
                f"{r['consecutive_failures']} run(s) in a row ended with an unhandled {r['last_error_class'] or 'error'}.",
                "Read the traceback in the dashboard's terminal output (the log, not this report, carries it).",
            )
    if collection.mode == "enabled" and process.state == "running":
        _watch_progress(rows, process, primary, now, t, out)
    return infos


def _watch_progress(rows, process, primary, now, t, out) -> None:
    resumed = (
        process.last_suspend_at is not None
        and (now - from_utc_iso(primary["last_suspend_at"])).total_seconds()
        < t.resume_grace_seconds
    )
    if resumed:
        out.notes.append(
            "The host woke from sleep a few minutes ago; the scheduler is given time to catch up."
        )
        return
    watch = next((r for r in rows if r["job_id"] == "release_watch"), None)
    if watch is not None and watch["running_since"]:
        return  # busy ingesting; the long-running rule covers it
    last = max(
        from_utc_iso(v)
        for v in (watch["last_finished_at"] if watch else None, primary["started_at"])
        if v
    )
    idle = (now - last).total_seconds()
    if idle > t.watch_attention_seconds:
        out.add(
            "scheduler:no_progress",
            "critical" if idle > t.watch_critical_seconds else "attention",
            "scheduler",
            "The scheduler is enabled but is not completing its checks",
            f"The one-minute release watch last finished {duration(idle)} ago, although the process is alive and reporting.",
            "Restart the dashboard. If it recurs, check the terminal output for errors from `release_watch`.",
        )


# --- sources and calendar ----------------------------------------------------------------------------------------


def _sources(conn, now, t, collection) -> list[SourceStatus]:
    out = []
    for r in conn.execute("SELECT * FROM source_health ORDER BY source"):
        daily = r["source"] in CALENDAR_SOURCES
        success = _dt(r["last_success_at"])
        if not daily:
            expired = False
        elif collection.mode == "enabled":
            expired = (
                missed_refreshes(success, now, timedelta(minutes=t.calendar_grace_minutes)) > 0
            )
        else:
            expired = success is None or (now - success) > timedelta(
                days=t.calendar_manual_attention_days
            )
        out.append(
            SourceStatus(
                source=r["source"],
                state=r["state"],
                last_checked_at=_akl(r["last_checked_at"]),
                last_success_at=_akl(r["last_success_at"]),
                age_hours=round((now - success).total_seconds() / 3600, 1) if success else None,
                expected="daily" if daily else "per_release",
                expired=expired,
            )
        )
    return out


def _calendar(conn, sources, now, t, collection, primary, out) -> CalendarInfo:
    row = conn.execute("SELECT * FROM source_health WHERE source = 'calendar_refresh'").fetchone()
    last_success = _dt(row["last_success_at"]) if row else None
    enabled = collection.mode == "enabled"
    uptime = (
        (now - from_utc_iso(primary["started_at"])).total_seconds() if primary is not None else 0
    )
    settling = (
        enabled and uptime < t.startup_grace_seconds
    )  # the startup refresh has not had its turn yet
    missed = 0
    if enabled and not settling:
        missed = missed_refreshes(last_success, now, timedelta(minutes=t.calendar_grace_minutes))
    age_days = (now - last_success).days if last_success else None
    if last_success is None:
        state = "never"
    elif missed:
        state = "missed"
    elif not enabled and age_days is not None and age_days > t.calendar_manual_attention_days:
        state = "stale"
    else:
        state = "current"
    shown = next((s for s in sources if s.source == "calendar_refresh"), None)
    info = CalendarInfo(
        state=state,
        last_checked_at=_akl(row["last_checked_at"]) if row else None,
        last_success_at=_akl(row["last_success_at"]) if row else None,
        last_success_age_hours=shown.age_hours if shown else None,
        missed_refreshes=missed,
        next_refresh_at=to_akl_iso(next_refresh_due(now)) if enabled else None,
    )
    if state == "missed":
        out.add(
            "calendar:missed",
            "critical" if missed >= t.calendar_missed_critical else "attention",
            "calendar",
            f"{missed} scheduled calendar refresh{'es' if missed > 1 else ''} did not complete",
            f"The 06:00 Auckland refresh is due daily; the last complete one was {akl(last_success)}."
            " A laptop that sleeps through 06:00 drops that day's refresh (the scheduler's grace is one hour).",
            "Restart the dashboard (it refreshes the calendar on startup) or run `scripts/run.sh discover`"
            " (contacts Stats NZ, one request per 10 s).",
        )
    elif state == "stale":
        out.add(
            "calendar:stale",
            "attention",
            "calendar",
            f"The release calendar has not been refreshed for {age_days} days",
            f"Collection is {collection.mode}; the last complete refresh was {akl(last_success)}."
            " New releases and date changes since then are unknown to the dashboard.",
            OPEN_TO_CHECK
            if collection.mode == "on_open"
            else "Run `scripts/run.sh discover` (contacts Stats NZ, one request per 10 s), or start the dashboard"
            " with `scripts/run.sh` (it checks when opened).",
        )
    elif state == "never" and not settling:
        out.add(
            "calendar:never",
            "attention",
            "calendar",
            "The release calendar has never been refreshed successfully",
            "No complete calendar refresh is recorded, so no release dates are known.",
            "Run `scripts/run.sh discover` (contacts Stats NZ, one request per 10 s).",
        )
    return info


# --- releases and freshness --------------------------------------------------------------------------------------


def _label(title: str | None, slug: str) -> str:
    return clean((title or slug).split(":")[0], 60) or slug


def _freshness(conn, adapters, settings, now, t, collection, out):
    grace = timedelta(
        minutes=max(t.release_grace_floor_minutes, max(settings.poll_offsets_minutes) + 60)
    )
    rows, empty = [], []
    boundaries = (
        dict(conn.execute("SELECT series_slug, after_published_at FROM refresh_catch_up"))
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'refresh_catch_up'").fetchone()
        else {}
    )
    for slug in sorted(adapters):
        latest = conn.execute(
            "SELECT r.release_key, r.title, r.reference_period, r.published_at,"
            " (SELECT MAX(v.captured_at) FROM vintage v WHERE v.release_id = r.id) AS captured_at"
            " FROM release r WHERE r.series_slug = ? AND EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
            " ORDER BY r.published_at DESC LIMIT 1",
            (slug,),
        ).fetchone()
        nxt = conn.execute(
            "SELECT published_at, reference_period FROM release WHERE series_slug = ? AND status IN ('scheduled','delayed')"
            " AND published_at > ? ORDER BY published_at LIMIT 1",
            (slug, to_utc_iso(now)),
        ).fetchone()
        title = (
            latest["title"]
            if latest
            else conn.execute(
                "SELECT title FROM release WHERE series_slug = ? ORDER BY published_at DESC LIMIT 1",
                (slug,),
            ).fetchone()
        )
        label = _label(latest["title"] if latest else (title[0] if title else None), slug)
        overdue = []
        if latest is not None:
            for r in conn.execute(
                "SELECT r.release_key, r.series_slug, r.published_at, r.status, r.reference_period, r.title FROM release r"
                " WHERE r.series_slug = ? AND r.published_at <= ?"
                " AND NOT EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
                # Retain the initial refresh boundary too: a later vintage must not hide a release
                # discovered after a partial feed failure, or one attempted and never stored.
                " AND (r.published_at > ? OR EXISTS (SELECT 1 FROM ingest_run i"
                " WHERE i.release_key = r.release_key AND i.started_at >= r.published_at))"
                " ORDER BY r.published_at",
                (
                    slug,
                    to_utc_iso(now - grace),
                    min(latest["published_at"], boundaries.get(slug, latest["published_at"])),
                ),
            ):
                run = conn.execute(
                    "SELECT outcome, error_class, started_at FROM ingest_run WHERE release_key = ? ORDER BY id DESC LIMIT 1",
                    (r["release_key"],),
                ).fetchone()
                published = from_utc_iso(r["published_at"])
                late = (now - published).total_seconds()
                overdue.append(
                    OverdueRelease(
                        release_key=r["release_key"],
                        published_at=to_akl_iso(published),
                        hours_late=round(late / 3600, 1),
                        status=r["status"],
                        last_outcome=run["outcome"] if run else None,
                        last_error_class=run["error_class"] if run else None,
                    )
                )
                _overdue_issue(out, r, run, late, collection, t)
        else:
            empty.append(slug)
        rows.append(
            FreshnessRow(
                series_slug=slug,
                label=label,
                state="no_data" if latest is None else ("overdue" if overdue else "current"),
                latest_release_key=latest["release_key"] if latest else None,
                latest_reference_period=latest["reference_period"] if latest else None,
                latest_published_at=_akl(latest["published_at"]) if latest else None,
                latest_captured_at=_akl(latest["captured_at"]) if latest else None,
                overdue=overdue,
                next_release_at=_akl(nxt["published_at"]) if nxt else None,
                next_reference_period=nxt["reference_period"] if nxt else None,
            )
        )
    if empty:
        out.add(
            "freshness:no_data",
            "attention",
            "freshness",
            f"No data has been ingested for {len(empty)} supported release series",
            "No vintage exists for: " + ", ".join(empty) + ".",
            "On a new install run `scripts/run.sh discover` then `scripts/run.sh backfill` (slow, throttled).",
        )
    return rows


def _overdue_issue(out, release, run, late_seconds, collection, t) -> None:
    attempt = (
        f"The last attempt ended '{run['outcome']}'"
        + (f" ({run['error_class']})" if run["error_class"] else "")
        if run
        else "No ingestion attempt is recorded"
    )
    error = run["error_class"] if run else None
    if error in ("layout_changed", "validation_failed"):
        action = (
            "Stats NZ published, but the file was rejected and last-known-good data is still shown. This needs a code or"
            " validation review; do not loosen a threshold without evidence from the real file."
        )
    elif collection.mode == "enabled":
        action = (
            "The scheduler polls for 3 hours after publication, then once a day for a week. Check the Data health page for"
            " the source state; run `scripts/run.sh ingest --release-key <key>` to retry now."
        )
    elif collection.mode == "on_open":
        action = OPEN_TO_CHECK
    else:
        action = (
            "Collection is not running. Start the dashboard with `scripts/run.sh` and open it (it checks when opened),"
            " or run `scripts/run.sh ingest --due` (contacts Stats NZ, one request per 10 s)."
        )
    out.add(
        f"release:overdue:{release['release_key']}",
        "critical" if late_seconds > t.release_critical_days * 86400 else "attention",
        "release",
        # Built from the series slug and reference period, not the upstream page title, so alert text carries no free text.
        f"{release['series_slug']}: {clean(release['reference_period'] or '')} release not ingested",
        f"{release['release_key']} was due {akl(from_utc_iso(release['published_at']))} ({duration(late_seconds)} ago) and has no data."
        f" {attempt}.",
        action,
    )


def _release_sources(sources, rows, collection, out) -> None:
    overdue_slugs = {r.series_slug for r in rows if r.overdue}
    for s in sources:
        if s.state == "ok":
            continue
        if s.source.startswith("release:") and s.source.removeprefix("release:") in overdue_slugs:
            continue  # already reported as an overdue release
        daily = s.expected == "daily"
        stale = (
            s.last_success_at is None or (s.age_hours or 0) > 24 * Thresholds().source_critical_days
        )
        out.add(
            f"source:degraded:{s.source}",
            # A calendar nobody is meant to refresh (collection off or paused) is `calendar:stale`, never CRITICAL.
            "critical" if daily and stale and collection.mode == "enabled" else "attention",
            "source",
            f"Source {s.source} is degraded",
            "The last check failed"
            + (
                f"; its last success was {s.last_success_at}."
                if s.last_success_at
                else " and it has never succeeded."
            )
            + " Last-known-good data is still being served.",
            "Open Data health for the error class. `network` usually clears itself; `blocked` means Stats NZ is challenging"
            " requests (do not retry in a loop); `layout_changed` or `validation_failed` need a code review.",
        )


def _blocked(conn, now, t, out) -> None:
    since = (now - timedelta(hours=t.blocked_window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs = conn.execute(
        "SELECT COUNT(*) FROM ingest_run WHERE error_class = 'blocked' AND started_at >= ?",
        (since,),
    ).fetchone()[0]
    sources = conn.execute(
        "SELECT COUNT(*) FROM source_health WHERE state != 'ok' AND detail LIKE '%: blocked:%' AND last_checked_at >= ?",
        (since,),
    ).fetchone()[0]
    if runs or sources:
        out.add(
            "source:blocked",
            "attention",
            "source",
            "Stats NZ has challenged recent requests",
            f"{runs} ingestion attempt(s) and {sources} calendar source(s) hit a block page in the last {t.blocked_window_hours} h.",
            "Do nothing and do not retry by hand: polling pauses for 30 minutes after a block. If it persists for a day,"
            " review the contact string in NZSTATS_CONTACT and the request rate (never below 10 s).",
        )


# --- the rest ----------------------------------------------------------------------------------------------------


def _next_release(conn, adapters, now):
    slugs = list(adapters)
    marks = ",".join("?" * len(slugs))
    args = (*slugs, to_utc_iso(now))
    where = f"series_slug IN ({marks}) AND status IN ('scheduled','delayed') AND published_at > ?"
    row = conn.execute(
        f"SELECT release_key, title, series_slug, reference_period, published_at, status FROM release WHERE {where}"
        " ORDER BY published_at LIMIT 1",
        args,
    ).fetchone()
    count = conn.execute(f"SELECT COUNT(*) FROM release WHERE {where}", args).fetchone()[0]
    if row is None:
        return None, count
    return (
        ReleaseRefInfo(
            release_key=row["release_key"],
            title=clean(row["title"]),
            series_slug=row["series_slug"],
            reference_period=row["reference_period"],
            scheduled_at=to_akl_iso(row["published_at"]),
            status=row["status"],
        ),
        count,
    )


def _ingestion(conn, adapters):
    ok = conn.execute(
        "SELECT release_key, finished_at, outcome FROM ingest_run WHERE outcome IN (?, ?) ORDER BY id DESC LIMIT 1",
        repo.INGEST_SUCCESSES,
    ).fetchone()
    latest = (
        LatestIngestion(
            release_key=ok["release_key"],
            finished_at=to_akl_iso(ok["finished_at"]),
            outcome=ok["outcome"],
        )
        if ok
        else None
    )
    failed = []
    for slug in sorted(adapters):
        for f in repo.failing_releases(conn, slug):
            run = conn.execute(
                "SELECT started_at, outcome, error_class FROM ingest_run WHERE release_key = ? ORDER BY id DESC LIMIT 1",
                (f["release_key"],),
            ).fetchone()
            failed.append(
                FailedRun(
                    release_key=f["release_key"],
                    series_slug=slug,
                    started_at=_akl(run["started_at"]) if run else None,
                    outcome=run["outcome"] if run else None,
                    error_class=run["error_class"] if run else None,
                )
            )
    return latest, failed[:20]


def _backup(info: BackupInfo, t: Thresholds, out: _Collector) -> None:
    if info.state == "none":
        out.add(
            "backup:none",
            "attention",
            "backup",
            "No native backup exists",
            f"Nothing found in {info.directory}.",
            "Take one: `scripts/run.sh backup --bundle data/backups/nzstats-$(date +%F-%H%M)` (database plus raw files).",
        )
    elif info.state == "failed":
        problems = "; ".join(info.latest.problems) if info.latest else ""
        out.add(
            "backup:failed",
            "attention",
            "backup",
            "The newest backup is incomplete or failed verification",
            f"{info.latest.name if info.latest else '?'}: {problems or info.latest.verification}.",
            "Leave it in place for inspection and take a fresh bundle. Do not delete backups to make this go away.",
        )
    elif info.state == "stale":
        good = info.latest_good
        age = good.age_hours if good else None
        critical = good is None or age >= t.backup_critical_days * 24
        out.add(
            "backup:stale",
            "critical" if critical else "attention",
            "backup",
            "The newest usable backup is old" if good else "No usable backup exists",
            f"Newest usable backup: {good.name} ({duration(age * 3600)} old)."
            if good
            else "Every backup found has a problem.",
            "Take a fresh bundle: `scripts/run.sh backup --bundle data/backups/nzstats-$(date +%F-%H%M)`.",
        )


def _delivery(conn, tables, now, t) -> AlertDelivery:
    empty = AlertDelivery(
        state="none_recorded",
        last_attempt_at=None,
        last_success_at=None,
        failures=0,
        rate_limited=0,
        window_hours=t.delivery_window_hours,
    )
    if "ops_notification" not in tables:
        return empty
    since = (now - timedelta(hours=t.delivery_window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    attempts = one("SELECT MAX(attempted_at) FROM ops_notification WHERE outcome != 'rate_limited'")
    if attempts is None and not one("SELECT COUNT(*) FROM ops_notification"):
        return empty
    failures = one(
        "SELECT COUNT(*) FROM ops_notification WHERE outcome='failed' AND attempted_at >= ?", since
    )
    limited = one(
        "SELECT COUNT(*) FROM ops_notification WHERE outcome='rate_limited' AND attempted_at >= ?",
        since,
    )
    success = one("SELECT MAX(attempted_at) FROM ops_notification WHERE outcome='sent'")
    # Channels are chosen per alert-check invocation (including --channels), so use the
    # recorded notifier names. A success must only clear failures on the same channel.
    channels = conn.execute(
        "SELECT notifier, SUM(outcome='sent') AS sent, SUM(outcome='failed') AS failed"
        " FROM ops_notification WHERE attempted_at >= ? GROUP BY notifier",
        (since,),
    ).fetchall()
    state = "none_recorded"
    if any(c["failed"] and not c["sent"] for c in channels):
        state = "failing"
    elif any(c["sent"] for c in channels):
        state = "ok"
    return AlertDelivery(
        state=state,
        last_attempt_at=_akl(attempts),
        last_success_at=_akl(success),
        failures=failures,
        rate_limited=limited,
        window_hours=t.delivery_window_hours,
    )


def build_status(
    conn: sqlite3.Connection,
    settings: Settings,
    backup: BackupInfo,
    *,
    now: datetime,
    thresholds: Thresholds | None = None,
    pid_alive: Callable[[int], bool] | None = None,
    deep: bool = False,
) -> OpsStatus:
    from nzstats.runtime import build_adapters

    t = thresholds or Thresholds()
    alive = pid_alive or recorder.pid_alive  # looked up now so tests can substitute the probe
    out = _Collector()
    tables = _tables(conn)
    adapters = build_adapters(settings)
    database = _database(conn, tables, out, deep)
    process, primary = _process(conn, tables, now, t, alive, out)
    collection = _collection(process)
    if collection.mode == "paused":
        out.notes.append(collection.summary)
    refresh = _refresh(conn, tables, now, t, process, out)
    jobs = _jobs(conn, tables, now, t, process, primary, collection, out)
    sources = _sources(conn, now, t, collection) if "source_health" in tables else []
    calendar = _calendar(conn, sources, now, t, collection, primary, out)
    freshness = (
        _freshness(conn, adapters, settings, now, t, collection, out) if "release" in tables else []
    )
    _release_sources(sources, freshness, collection, out)
    _blocked(conn, now, t, out)
    upcoming, count = _next_release(conn, adapters, now)
    latest, failed = _ingestion(conn, adapters)
    _backup(backup, t, out)
    if process.last_suspend_at:
        out.notes.append(
            f"The host last slept for about {duration(process.last_suspend_seconds or 0)} (woke {process.last_suspend_at}); this is not a fault in itself."
        )
    if process.unexpected_restarts_7d:
        out.notes.append(f"{process.unexpected_restarts_7d} unclean restart(s) in the last 7 days.")
    issues = sorted(out.issues, key=lambda i: (i.severity != "critical", i.key))
    overall = worst([i.severity for i in issues])
    summary = {
        "ok": "Everything checked is within its limits.",
        "attention": f"{len(issues)} item(s) need a look today.",
        "critical": f"{sum(i.severity == 'critical' for i in issues)} critical item(s) need action now.",
    }[overall]
    return OpsStatus(
        generated_at=to_akl_iso(now),
        overall=overall,
        summary=summary,
        database=database,
        process=process,
        collection=collection,
        refresh=refresh,
        jobs=jobs,
        calendar=calendar,
        next_release=upcoming,
        known_upcoming_releases=count,
        latest_ingestion=latest,
        failed_runs=failed,
        freshness=freshness,
        sources=sources,
        backup=backup,
        alert_delivery=_delivery(conn, tables, now, t),
        issues=issues,
        notes=out.notes,
    )
