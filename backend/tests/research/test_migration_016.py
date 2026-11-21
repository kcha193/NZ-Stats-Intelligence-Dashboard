"""Migration 016 (Phase 4AP): `xlsx` research documents. A table rebuild that must keep every row, id, trigger and index."""

from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from nzstats.research import purge
from nzstats.research.table_store import store_extraction
from nzstats.sources.artifacts import ArtifactStore
from nzstats.store.db import connect, migrate

from .llm_support import NOW, seed_version
from .test_migration import REPO, _apply_up_to
from .test_table_store import tf

ROLLBACK_016 = REPO / "scripts" / "rollback" / "016_research_xlsx_format_down.sql"
REBUILT = ("research_document_version", "research_manual_import")
TS = "2026-11-21T00:00:00Z"
SHA = "b" * 64


def _populate(conn: sqlite3.Connection, tmp_path: Path) -> None:
    """One row in every research table that references a document version, plus a purged version."""
    kept = seed_version(conn, doc="kept")
    gone = seed_version(conn, doc="gone")
    inst = conn.execute("SELECT institution_id FROM research_publication LIMIT 1").fetchone()[0]
    pub = conn.execute(
        "SELECT publication_id FROM research_document_version WHERE id = ?", (kept,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO research_run(institution_id, started_at, finished_at, outcome) VALUES (?,?,?,'ok')",
        (inst, TS, TS),
    )
    conn.execute(
        "INSERT INTO research_run_item(run_id, url, publication_id, version_id, outcome)"
        " VALUES (1, 'https://research.example.org/kept', ?, ?, 'new')",
        (pub, kept),
    )
    conn.execute(
        "INSERT INTO research_llm_run(provider, model, hosted, prompt_version, processing_version, started_at)"
        " VALUES ('fake', 'm', 0, 'p', 'q', ?)",
        (TS,),
    )
    conn.execute(
        "INSERT INTO research_summary(version_id, run_id, provider, model, hosted, prompt_version,"
        " processing_version, verifier_version, input_sha256, status, error_class, created_at)"
        " VALUES (?, 1, 'fake', 'm', 0, 'p', 'q', 'v', ?, 'provider_error', 'timeout', ?)",
        (kept, SHA, TS),
    )
    conn.execute(
        "INSERT INTO research_llm_usage(run_id, version_id, summary_id, call_no, provider, model, latency_ms,"
        " cost_usd, outcome, created_at) VALUES (1, ?, 1, 1, 'fake', 'm', 5, 0, 'error', ?)",
        (kept, TS),
    )
    conn.execute(
        "INSERT INTO research_llm_reservation(run_id, version_id, call_no, provider, model, reserved_usd,"
        " created_at, expires_at) VALUES (1, ?, 1, 'fake', 'm', 0.1, ?, ?)",
        (kept, TS, TS),
    )
    conn.execute(
        "INSERT INTO research_policy_event(event, policy_id, policy_sha256, version_id, refusal_code,"
        " operator, created_at) VALUES ('refused', 'policy-x', ?, ?, 'no_consent', 'Owner', ?)",
        (SHA, kept, TS),
    )
    conn.execute(
        "INSERT INTO research_manual_import(institution_id, url, publication_id, version_id, outcome,"
        " file_format, content_sha256, text_sha256, imported_by, note, licence_snapshot, imported_at)"
        " VALUES (?, 'https://research.example.org/kept', ?, ?, 'new', 'pdf', ?, ?, 'Owner', 'saved', '{}', ?)",
        (inst, pub, kept, SHA, SHA, TS),
    )
    store_extraction(conn, kept, NOW, [tf()], [], words_sha256=SHA)
    plan = purge.plan_purge(conn, "example", version_ids=[gone])
    purge.apply_purge(
        conn,
        plan,
        ArtifactStore(tmp_path / "raw"),
        reason="takedown",
        purged_by="Owner",
        note="t",
        now=NOW,
    )


def _database_at_15(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "p.db")
    _apply_up_to(conn, 15)
    _populate(conn, tmp_path)
    return conn


def _research_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'research_%'"
        )
    ]


def _snapshot(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    return {
        t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid")]
        for t in _research_tables(conn)
    }


def _objects(conn: sqlite3.Connection) -> dict[str, tuple[str, str, str | None]]:
    return {
        r[1]: (r[0], r[2], r[3])
        for r in conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master")
    }


def _without_format_checks(sql: str | None) -> str | None:
    if sql is None:
        return None
    return re.sub(r"(file_)?format TEXT NOT NULL CHECK \(\w+ IN \([^)]*\)\)", "FORMAT", sql)


def _rollback(conn: sqlite3.Connection) -> None:
    """The down script as Python runs it: `.bail on` is a sqlite3 shell directive, not SQL."""
    body = "\n".join(
        line
        for line in ROLLBACK_016.read_text(encoding="utf-8").splitlines()
        if not line.startswith(".")
    )
    conn.executescript(body)


def _xlsx_version(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE research_document_version SET format = 'xlsx' WHERE id = (SELECT MIN(id) FROM research_document_version)"
    )


def test_016_accepts_xlsx_versions_and_imports(tmp_path):
    conn = _database_at_15(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        _xlsx_version(conn)
    assert migrate(conn) >= 16
    _xlsx_version(conn)
    conn.execute(
        "INSERT INTO research_manual_import(institution_id, url, outcome, file_format, content_sha256,"
        " text_sha256, imported_by, note, licence_snapshot, imported_at)"
        " VALUES (1, 'https://research.example.org/w', 'new', 'xlsx', ?, ?, 'Owner', 'saved', '{}', ?)",
        (SHA, SHA, TS),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE research_document_version SET format = 'docx' WHERE id = 1")


def test_016_keeps_every_row_id_trigger_and_index(tmp_path):
    conn = _database_at_15(tmp_path)
    rows, objects = _snapshot(conn), _objects(conn)
    assert all(rows[t] for t in REBUILT)
    assert migrate(conn) >= 16
    assert _snapshot(conn) == rows
    after = _objects(conn)
    assert set(after) == set(objects)
    for name, (kind, table, sql) in objects.items():
        a_kind, a_table, a_sql = after[name]
        assert (a_kind, a_table) == (kind, table), name
        assert _without_format_checks(a_sql) == _without_format_checks(sql), name
    changed = {n for n in objects if after[n][2] != objects[n][2]}
    assert changed == set(REBUILT)
    assert (
        "'xlsx'" in after["research_document_version"][2]
        and "'xlsx'" in after["research_manual_import"][2]
    )


def test_016_fk_and_integrity_checks_are_clean(tmp_path):
    conn = _database_at_15(tmp_path)
    migrate(conn)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert not [r for r in conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%m016%'")]


def test_016_purge_triggers_still_fire(tmp_path):
    conn = _database_at_15(tmp_path)
    migrate(conn)
    purged = conn.execute(
        "SELECT id FROM research_document_version WHERE purged_at IS NOT NULL"
    ).fetchone()[0]
    kept = conn.execute(
        "SELECT id FROM research_document_version WHERE purged_at IS NULL"
    ).fetchone()[0]
    with pytest.raises(sqlite3.DatabaseError, match="a purge cannot be undone"):
        conn.execute(
            "UPDATE research_document_version SET purged_at = NULL WHERE id = ?", (purged,)
        )
    with pytest.raises(sqlite3.DatabaseError, match="recorded purge"):
        conn.execute("UPDATE research_document_version SET purged_at = ? WHERE id = ?", (TS, kept))
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("UPDATE research_manual_import SET note = 'x'")
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("DELETE FROM research_manual_import")
    with pytest.raises(sqlite3.DatabaseError, match="purged"):
        store_extraction(conn, purged, NOW, [tf()], [], words_sha256=SHA)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM research_document_version WHERE id = ?", (kept,))


def test_016_rollback_restores_the_old_checks(tmp_path):
    conn = _database_at_15(tmp_path)
    rows, objects = _snapshot(conn), _objects(conn)
    migrate(conn)
    _rollback(conn)
    assert _snapshot(conn) == rows
    assert _objects(conn) == objects
    assert 16 not in {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert migrate(conn) >= 16


def test_016_rollback_refuses_while_xlsx_rows_exist(tmp_path):
    conn = _database_at_15(tmp_path)
    migrate(conn)
    _xlsx_version(conn)
    rows, objects = _snapshot(conn), _objects(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _rollback(conn)
    conn.execute("ROLLBACK")
    assert _snapshot(conn) == rows
    assert _objects(conn) == objects


@pytest.mark.skipif(shutil.which("sqlite3") is None, reason="needs the sqlite3 shell")
def test_016_rollback_through_the_sqlite3_shell_stops_at_the_first_error(tmp_path):
    """The documented route (`sqlite3 DB < script`) must not run on past a refused row and lose data.

    The xlsx row is an import record only: no foreign key would then stop a shell that ran on to COMMIT.
    """
    conn = _database_at_15(tmp_path)
    migrate(conn)
    conn.execute(
        "INSERT INTO research_manual_import(institution_id, url, outcome, file_format, content_sha256,"
        " text_sha256, imported_by, note, licence_snapshot, imported_at)"
        " VALUES (1, 'https://research.example.org/w', 'duplicate', 'xlsx', ?, ?, 'Owner', 'saved', '{}', ?)",
        (SHA, SHA, TS),
    )
    rows, objects = _snapshot(conn), _objects(conn)
    conn.close()
    db = tmp_path / "p.db"
    with ROLLBACK_016.open("rb") as script:
        done = subprocess.run(["sqlite3", str(db)], stdin=script, capture_output=True, check=False)
    assert done.returncode != 0
    conn = connect(db)
    assert _snapshot(conn) == rows
    assert _objects(conn) == objects
