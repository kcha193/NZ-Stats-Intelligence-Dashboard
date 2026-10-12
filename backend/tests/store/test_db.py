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


def test_a_failing_migration_leaves_no_partial_schema_and_can_be_retried(
    tmp_path: Path, monkeypatch
) -> None:
    """Review #4246141437: the script and its version marker commit together or not at all."""
    import nzstats.store.db as db

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    script = migrations / "001_init.sql"
    script.write_text(
        "CREATE TABLE first_table (id INTEGER PRIMARY KEY);\n"
        "INSERT INTO table_that_does_not_exist VALUES (1);\n"
    )
    monkeypatch.setattr(db, "MIGRATIONS_DIR", migrations)
    conn = connect(tmp_path / "t.db")
    with pytest.raises(sqlite3.Error):
        migrate(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "first_table" not in names
    assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0
    assert not conn.in_transaction

    script.write_text("CREATE TABLE first_table (id INTEGER PRIMARY KEY);\n")  # the fixed migration
    assert migrate(conn) == 1
    assert migrate(conn) == 1  # and re-running stays a no-op
