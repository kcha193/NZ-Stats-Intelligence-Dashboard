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


def test_upgrade_from_the_initial_schema_keeps_vintage_order(tmp_path: Path, monkeypatch) -> None:
    """Existing databases gain `activation` = id, so "latest" is unchanged until a revert."""
    import nzstats.store.db as db

    real = db.MIGRATIONS_DIR
    first_only = tmp_path / "migrations"
    first_only.mkdir()
    (first_only / "001_init.sql").write_text((real / "001_init.sql").read_text())
    monkeypatch.setattr(db, "MIGRATIONS_DIR", first_only)
    conn = connect(tmp_path / "t.db")
    assert migrate(conn) == 1
    conn.execute(
        "INSERT INTO release(id, release_key, series_slug, title, published_at, status,"
        " first_seen_at, updated_at) VALUES (1, 'r', 's', 't', '2026-01-01T00:00:00Z',"
        " 'published', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO series(id, key, name, unit, frequency, seasonal_adjustment, definition,"
        " definition_id, category) VALUES (1, 'k', 'n', 'people', 'monthly', 'none', 'd', 'x', 'c')"
    )
    for vid, sha in ((1, "a"), (2, "b")):
        conn.execute(
            "INSERT INTO vintage(id, release_id, series_id, captured_at, source_kind,"
            " layout_version, bundle_sha256) VALUES (?, 1, 1, '2026-01-01T00:00:00Z',"
            " 'release_files', 'v', ?)",
            (vid, sha),
        )
    monkeypatch.setattr(db, "MIGRATIONS_DIR", real)
    assert migrate(conn) >= 2
    rows = conn.execute("SELECT id, activation FROM vintage ORDER BY id").fetchall()
    assert [(r["id"], r["activation"]) for r in rows] == [(1, 1), (2, 2)]
