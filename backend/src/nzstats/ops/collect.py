"""Gather the inputs for `build_status` from the local machine and degrade to a CRITICAL report when the database cannot be read.

The database is opened read-only (`mode=ro`): this module cannot create, migrate or modify it, and `status` stays safe
to run beside a live dashboard or against production data.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from nzstats.clock import to_akl_iso, utc_now
from nzstats.config import Settings
from nzstats.ops.backups import scan_backups
from nzstats.ops.health import build_status, expected_schema_version
from nzstats.ops.report import (
    AlertDelivery,
    BackupInfo,
    CalendarInfo,
    CollectionInfo,
    DatabaseInfo,
    Issue,
    OpsStatus,
    ProcessInfo,
)
from nzstats.ops.thresholds import Thresholds

log = logging.getLogger(__name__)


def open_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path.name)
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _unreadable(settings: Settings, backup: BackupInfo, now: datetime, reason: str) -> OpsStatus:
    issue = Issue(
        key="database:unreadable",
        severity="critical",
        category="database",
        title="The database cannot be read",
        detail=f"{settings.db_path.name}: {reason}.",
        action="Check NZSTATS_DATA_DIR points at the right directory. If the file is damaged, restore the latest verified"
        " backup into a NEW directory (docs/phase-4f-runbook.md, 'Restore'); do not delete anything.",
    )
    return OpsStatus(
        generated_at=to_akl_iso(now),
        overall="critical",
        summary="The database cannot be read.",
        database=DatabaseInfo(
            readable=False,
            schema_version=None,
            expected_schema_version=expected_schema_version(),
            instrumented=False,
        ),
        process=ProcessInfo(state="never_started"),
        collection=CollectionInfo(
            mode="unknown", summary="Unknown: there is no readable database to ask."
        ),
        jobs=[],
        calendar=CalendarInfo(
            state="never", last_checked_at=None, last_success_at=None, last_success_age_hours=None
        ),
        next_release=None,
        known_upcoming_releases=0,
        latest_ingestion=None,
        failed_runs=[],
        freshness=[],
        sources=[],
        backup=backup,
        alert_delivery=AlertDelivery(
            state="none_recorded",
            last_attempt_at=None,
            last_success_at=None,
            failures=0,
            rate_limited=0,
            window_hours=24,
        ),
        issues=[issue],
        notes=[],
    )


def collect_status(
    settings: Settings,
    *,
    now: datetime | None = None,
    thresholds: Thresholds | None = None,
    deep: bool = False,
    backup_dir: Path | None = None,
    pid_alive: Callable[[int], bool] | None = None,
) -> OpsStatus:
    now = now or utc_now()
    t = thresholds or Thresholds()
    backup = scan_backups(backup_dir or settings.backup_dir, now, t)
    try:
        conn = open_readonly(settings.db_path)
    except (OSError, sqlite3.Error) as exc:
        return _unreadable(settings, backup, now, type(exc).__name__)
    try:
        return build_status(
            conn, settings, backup, now=now, thresholds=t, deep=deep, pid_alive=pid_alive
        )
    except sqlite3.Error as exc:  # a damaged file passes open() and fails on first read
        log.warning("status could not read the database: %s", type(exc).__name__)
        return _unreadable(settings, backup, now, type(exc).__name__)
    finally:
        conn.close()
