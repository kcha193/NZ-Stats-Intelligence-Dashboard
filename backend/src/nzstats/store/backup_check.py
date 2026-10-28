"""Restore validation for a database backup (Phase 3E). Read-only: the copy is opened immutable and never written.

A copy passes when SQLite's integrity and foreign-key checks are clean, its schema version is the latest migration,
and every table, index and trigger a freshly migrated database has is present, so the append-only guards on research
summaries, reviews, publication decisions and manual imports survive a restore. Optionally every raw artifact the
copy references must exist under a raw directory, and row counts are compared with the live database (a difference is
reported, not failed: the live database keeps changing after a backup).
"""

from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from nzstats.store.db import connect, migrate


@dataclass
class BackupReport:
    path: str
    schema_version: int | None = None
    expected_schema_version: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    count_differences: dict[str, tuple[int, int]] = field(
        default_factory=dict
    )  # table: (backup, live)
    missing_raw: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _read_only(path: Path, *, immutable: bool) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro{'&immutable=1' if immutable else ''}"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _objects(conn: sqlite3.Connection) -> dict[str, str]:
    return {r[0]: r[1] for r in conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'index', 'trigger')"
        " AND name NOT LIKE 'sqlite_%'")}  # fmt: skip


def _reference() -> tuple[dict[str, str], int]:
    """The objects and schema version of a freshly migrated database."""
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "reference.db")
        try:
            version = migrate(conn)
            return _objects(conn), version
        finally:
            conn.close()


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [n for n, t in _objects(conn).items() if t == "table"]
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in sorted(tables)}


def verify_backup(
    path: Path | str, *, live: Path | str | None = None, raw_dir: Path | str | None = None
) -> BackupReport:
    path = Path(path)
    report = BackupReport(str(path))
    expected, report.expected_schema_version = _reference()
    if not path.is_file():
        report.problems.append("the backup file does not exist")
        return report
    try:
        conn = _read_only(path, immutable=True)
        result = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError:
        report.problems.append("the file is not a readable SQLite database")
        return report
    try:
        if result != ["ok"]:
            report.problems.append(f"integrity check failed ({len(result)} messages)")
            return report
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            report.problems.append("foreign key check failed")
        objects = _objects(conn)
        if "schema_version" in objects:
            report.schema_version = conn.execute(
                "SELECT MAX(version) FROM schema_version"
            ).fetchone()[0]
        if report.schema_version != report.expected_schema_version:
            report.problems.append(
                f"schema version {report.schema_version} is not the latest ({report.expected_schema_version})"
            )
        for name, kind in sorted(expected.items()):
            if objects.get(name) != kind:
                report.problems.append(f"missing {kind} {name}")
        report.counts = _counts(conn)
        if raw_dir is not None and "raw_artifact" in objects:
            base = Path(raw_dir)
            report.missing_raw = sum(
                1
                for (rel,) in conn.execute("SELECT path FROM raw_artifact")
                if not (base / rel).is_file()
            )
            if report.missing_raw:
                report.problems.append(
                    f"{report.missing_raw} raw artifacts are missing from the raw directory"
                )
    finally:
        conn.close()
    if live is not None:
        live_conn = _read_only(Path(live), immutable=False)
        try:
            live_counts = _counts(live_conn)
        finally:
            live_conn.close()
        report.count_differences = {
            t: (report.counts.get(t, 0), n)
            for t, n in live_counts.items()
            if report.counts.get(t, 0) != n
        }
    return report
