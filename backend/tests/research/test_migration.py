import sqlite3
from pathlib import Path

import pytest

from nzstats.store.db import MIGRATIONS_DIR, connect, migrate

REPO = Path(__file__).resolve().parents[3]
ROLLBACK = REPO / "scripts" / "rollback" / "004_research_down.sql"


def _schema(conn: sqlite3.Connection, *, research: bool) -> dict[str, str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"]: r["sql"] for r in rows if r["name"].startswith("research_") == research}


def _apply_up_to(conn: sqlite3.Connection, last: int) -> None:
    conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.name.split("_", 1)[0])
        if version <= last:
            conn.executescript(sql_file.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))


def _populated_pre_research(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "old.db")
    _apply_up_to(conn, 3)
    conn.execute(
        "INSERT INTO release(release_key, series_slug, title, published_at, status,"
        " first_seen_at, updated_at) VALUES ('k','s','t','2026-01-01T00:00:00Z','published',"
        "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
    )
    conn.execute("INSERT INTO source_health(source, state) VALUES ('calendar','ok')")
    return conn


def test_migration_is_additive_on_populated_db(tmp_path):
    conn = _populated_pre_research(tmp_path)
    old_schema = _schema(conn, research=False)
    old_rows = {
        t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in ("release", "source_health")
    }
    assert migrate(conn) >= 4
    assert _schema(conn, research=False) == old_schema
    for table, rows in old_rows.items():
        assert [tuple(r) for r in conn.execute(f"SELECT * FROM {table}")] == [
            tuple(r) for r in rows
        ]
    assert {"research_institution", "research_publication", "research_document_version",
            "research_section", "research_run", "research_run_item",
            "research_source_health"} <= set(_schema(conn, research=True))  # fmt: skip


def test_no_foreign_key_from_old_tables_to_research(conn):
    for name, sql in _schema(conn, research=False).items():
        assert "research_" not in sql, name


def test_research_tables_do_not_use_stats_nz_health_or_ingest_tables(conn):
    for name, sql in _schema(conn, research=True).items():
        for forbidden in (
            "source_health(",
            "ingest_run",
            "REFERENCES release",
            "REFERENCES vintage",
        ):
            assert forbidden not in sql.replace("research_source_health(", ""), (name, forbidden)


def test_rollback_script_removes_only_research_objects(tmp_path):
    conn = _populated_pre_research(tmp_path)
    old_schema = _schema(conn, research=False)
    migrate(conn)
    inst = conn.execute(
        "INSERT INTO research_institution(key,name,review_status,content_policy,synced_at)"
        " VALUES ('anz','ANZ','needs_review','metadata_only','2026-10-25T00:00:00Z')"
    ).lastrowid
    pub = conn.execute(
        "INSERT INTO research_publication(institution_id,doc_key,canonical_url,title,content_status,"
        "first_seen_at,last_seen_at) VALUES (?,'anz:x','https://x','T','link_only','a','a')",
        (inst,),
    ).lastrowid
    ver = conn.execute(
        "INSERT INTO research_document_version(publication_id,version_no,content_sha256,text_sha256,"
        "format,fetched_at,extracted_at,extractor_version,title,char_count,licence_snapshot)"
        " VALUES (?,1,'a','b','html','a','a','html-1','T',3,'{}')",
        (pub,),
    ).lastrowid
    conn.execute("UPDATE research_publication SET current_version_id=? WHERE id=?", (ver, pub))
    conn.executescript(ROLLBACK.read_text(encoding="utf-8"))
    assert _schema(conn, research=True) == {}
    assert _schema(conn, research=False) == old_schema
    assert conn.execute("SELECT COUNT(*) FROM release").fetchone()[0] == 1
    assert 4 not in {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert migrate(conn) >= 4  # and it can be re-applied


def test_check_constraints_reject_unknown_policy(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO research_institution(key,name,review_status,content_policy,synced_at)"
            " VALUES ('x','X','approved','everything','t')"
        )
