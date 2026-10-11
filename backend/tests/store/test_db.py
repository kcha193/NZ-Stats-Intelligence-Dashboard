import sqlite3
from pathlib import Path

import pytest

from nzstats.store.db import connect, migrate, transaction


def test_migrate_creates_schema_and_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    v1 = migrate(conn)
    v2 = migrate(conn)
    assert v1 == v2 >= 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "release",
        "series",
        "vintage",
        "observation",
        "raw_artifact",
        "ingest_run",
        "source_health",
    } <= tables
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO source_health(source, state) VALUES ('x', 'ok')")
            raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM source_health").fetchone()[0] == 0


def test_transaction_commits(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    with transaction(conn):
        conn.execute("INSERT INTO source_health(source, state) VALUES ('x', 'ok')")
    other = sqlite3.connect(tmp_path / "t.db")
    assert other.execute("SELECT COUNT(*) FROM source_health").fetchone()[0] == 1
