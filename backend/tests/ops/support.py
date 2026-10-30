"""Builders for operational-health scenarios: raw rows, so each test states exactly the world it is about."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from nzstats.clock import to_utc_iso
from nzstats.config import load_settings
from nzstats.ops.health import build_status
from nzstats.ops.report import BackupEntry, BackupInfo, OpsStatus
from nzstats.runtime import build_adapters

SLUGS = sorted(build_adapters(load_settings({"NZSTATS_DATA_DIR": "."})))


def settings(tmp: Path):
    return load_settings({"NZSTATS_DATA_DIR": str(tmp)})


def iso(dt: datetime) -> str:
    return to_utc_iso(dt)


def add_release(
    conn, key, slug, published, *, status="published", ref="2026-09", title=None, vintage=False
) -> int:
    cur = conn.execute(
        "INSERT INTO release(release_key, series_slug, title, period_label, reference_period, published_at, status,"
        " first_seen_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            key,
            slug,
            title or f"{slug.replace('-', ' ').title()}: {ref}",
            ref,
            ref,
            iso(published),
            status,
            iso(published),
            iso(published),
        ),
    )
    rid = cur.lastrowid
    if vintage:
        add_vintage(conn, rid, published + timedelta(minutes=2))
    return rid


def add_vintage(conn, release_id, captured) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO series(key, name, unit, frequency, seasonal_adjustment, definition, definition_id, category)"
        " VALUES ('t.s','t','n','monthly','none','d','d','test')"
    )
    sid = conn.execute("SELECT id FROM series WHERE key='t.s'").fetchone()[0]
    conn.execute(
        "INSERT INTO vintage(release_id, series_id, captured_at, source_kind, layout_version, bundle_sha256, activation)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            release_id,
            sid,
            iso(captured),
            "release_files",
            "v1",
            f"sha-{release_id}-{captured.timestamp()}",
            release_id,
        ),
    )


def add_run(conn, key, started, outcome, error_class=None, detail=None) -> None:
    conn.execute(
        "INSERT INTO ingest_run(release_key, started_at, finished_at, outcome, error_class, detail) VALUES (?,?,?,?,?,?)",
        (key, iso(started), iso(started + timedelta(seconds=30)), outcome, error_class, detail),
    )


def add_source(conn, source, *, state="ok", checked=None, success=None, detail=None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO source_health(source, state, last_checked_at, last_success_at, detail) VALUES (?,?,?,?,?)",
        (
            source,
            state,
            iso(checked) if checked else None,
            iso(success) if success else None,
            detail,
        ),
    )


def add_process(
    conn, *, boot="aaaaaaaa11", pid=100, started, beat, enabled=True, stopped=None, reason=None,
    prior_unclean=0, suspend_at=None, suspend_seconds=None,
) -> None:  # fmt: skip
    conn.execute(
        "INSERT INTO ops_process(boot_id, pid, started_at, scheduler_enabled, last_heartbeat_at, stopped_at, stop_reason,"
        " prior_unclean, suspend_count, last_suspend_at, last_suspend_seconds) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            boot, pid, iso(started), int(enabled), iso(beat), iso(stopped) if stopped else None, reason, prior_unclean,
            1 if suspend_at else 0, iso(suspend_at) if suspend_at else None, suspend_seconds,
        ),
    )  # fmt: skip


def add_job(conn, job_id, *, boot="aaaaaaaa11", running=None, started=None, finished=None, success=None, outcome="ok", error=None, failures=0) -> None:  # fmt: skip
    conn.execute(
        "INSERT OR REPLACE INTO ops_job(job_id, boot_id, running_since, last_started_at, last_finished_at, last_success_at,"
        " last_outcome, last_error_class, consecutive_failures) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            job_id, boot, iso(running) if running else None, iso(started) if started else None,
            iso(finished) if finished else None, iso(success) if success else None, outcome, error, failures,
        ),
    )  # fmt: skip


def good_backup(age_hours: float = 3.0, name="nzstats-2026-10-30-0000") -> BackupInfo:
    entry = BackupEntry(
        name=name, kind="bundle", created_at="2026-10-30T00:00:00+13:00", age_hours=age_hours,
        verification="verified", raw_artifacts=43, problems=[],
    )  # fmt: skip
    return BackupInfo(
        directory="data/backups", state="ok", latest=entry, latest_good=entry, entries_seen=1
    )


def backup(
    state: str, age_hours: float = 3.0, *, verification="verified", problems=()
) -> BackupInfo:
    if state == "none":
        return BackupInfo(
            directory="data/backups", state="none", latest=None, latest_good=None, entries_seen=0
        )
    entry = BackupEntry(
        name="nzstats-x", kind="bundle", created_at="2026-10-01T00:00:00+13:00", age_hours=age_hours,
        verification=verification, raw_artifacts=43, problems=list(problems),
    )  # fmt: skip
    good = None if verification in ("failed", "incomplete") else entry
    return BackupInfo(
        directory="data/backups", state=state, latest=entry, latest_good=good, entries_seen=1
    )  # type: ignore[arg-type]


def healthy_world(conn: sqlite3.Connection, now: datetime, *, enabled: bool = True) -> None:
    """A dashboard that is running, collecting, refreshed this morning and current for every series."""
    refreshed = now.replace(hour=0, minute=0, second=30)  # placeholder, replaced below
    refreshed = now - timedelta(hours=10)  # ~06:00 NZDT when `now` is 16:00 NZDT
    add_process(
        conn, started=now - timedelta(days=1), beat=now - timedelta(seconds=10), enabled=enabled
    )
    if enabled:
        add_job(
            conn,
            "release_watch",
            started=now - timedelta(seconds=40),
            finished=now - timedelta(seconds=39),
            success=now - timedelta(seconds=39),
        )
        add_job(
            conn,
            "refresh_calendar",
            started=refreshed,
            finished=refreshed + timedelta(minutes=1),
            success=refreshed + timedelta(minutes=1),
        )
    add_source(conn, "calendar_refresh", checked=refreshed, success=refreshed)
    add_source(conn, "calendar_ics", checked=refreshed, success=refreshed)
    add_source(conn, "calendar_month", checked=refreshed, success=refreshed)
    for i, slug in enumerate(SLUGS):
        add_release(
            conn, f"{slug}-2026-09", slug, now - timedelta(days=20 + i), vintage=True, ref="2026-09"
        )
        add_source(
            conn,
            f"release:{slug}",
            checked=now - timedelta(days=20),
            success=now - timedelta(days=20),
        )


def status(conn, tmp_path, now, *, bk=None, **kw) -> OpsStatus:
    return build_status(conn, settings(tmp_path), bk or good_backup(), now=now, **kw)


def keys(s: OpsStatus) -> list[str]:
    return [i.key for i in s.issues]
