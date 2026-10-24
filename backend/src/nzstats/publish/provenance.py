"""Whether a data directory holds real ingested data or data built from test fixtures.

Fixture files are real excerpts of official files, and some are byte-identical to production downloads, so
content cannot tell them apart. Provenance is recorded instead: any runtime built with an injected fetcher (tests,
the e2e seed, fixture dumps) marks its data, and a production runtime never does. The mark is in two places so it
survives copying: a marker file in the data directory, and SQLite's `user_version` header field inside the database
itself (which the backup API copies). Either one means fixture data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

FIXTURE_MARKER = "FIXTURE_DATA"
FIXTURE_USER_VERSION = (
    0x46495854  # "FIXT"; the schema is versioned in its own table, so this field is free
)
_NOTE = (
    "This data directory was written by a runtime with an injected fetcher (test or fixture data).\n"
    "It must never be published as Stats NZ releases.\n"
)


def mark_fixture_data(data_dir: Path, conn: sqlite3.Connection | None = None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    marker = data_dir / FIXTURE_MARKER
    if not marker.exists():
        marker.write_text(_NOTE, encoding="utf-8")
    if conn is not None:
        conn.execute(f"PRAGMA user_version = {FIXTURE_USER_VERSION}")


def _database_flag(db: Path) -> bool:
    if not db.exists():
        return False
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
        try:
            return conn.execute("PRAGMA user_version").fetchone()[0] == FIXTURE_USER_VERSION
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def is_fixture_data(data_dir: Path) -> bool:
    return (data_dir / FIXTURE_MARKER).exists() or _database_flag(data_dir / "nzstats.db")
