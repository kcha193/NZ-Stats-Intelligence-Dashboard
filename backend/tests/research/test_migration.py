import sqlite3
from pathlib import Path

import pytest

from nzstats.store.db import MIGRATIONS_DIR, connect, migrate

REPO = Path(__file__).resolve().parents[3]
ROLLBACK = REPO / "scripts" / "rollback" / "004_research_down.sql"
ROLLBACK_006 = REPO / "scripts" / "rollback" / "006_research_summaries_down.sql"
TABLES_006 = {"research_llm_run", "research_summary", "research_forecast_claim", "research_llm_usage",
              "research_summary_review"}  # fmt: skip
ROLLBACK_007 = REPO / "scripts" / "rollback" / "007_research_publication_down.sql"
TABLES_007 = {"research_summary_publication"}


def _schema(conn: sqlite3.Connection, *, research: bool) -> dict[str, str]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    # `ops_*` (Phase 4F) and `refresh_run*` (Phase 4G) objects arrive with later, unrelated migrations and are not part
    # of the pre-research schema.
    return {
        r["name"]: r["sql"]
        for r in rows
        if r["name"].startswith("research_") == research
        and not r["name"].startswith(("ops_", "refresh_run"))
    }


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
    copy = conn.execute(
        "INSERT INTO research_publication(institution_id,doc_key,canonical_url,title,content_status,"
        "first_seen_at,last_seen_at,duplicate_of_id,duplicate_of_version_id)"
        " VALUES (?,'anz:y','https://y','T','link_only','a','a',?,?)",
        (inst, pub, ver),
    ).lastrowid
    assert copy != pub
    conn.executescript(ROLLBACK.read_text(encoding="utf-8"))
    assert _schema(conn, research=True) == {}
    assert _schema(conn, research=False) == old_schema
    assert conn.execute("SELECT COUNT(*) FROM release").fetchone()[0] == 1
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert not applied & {4, 5}
    assert migrate(conn) >= 5  # and both research migrations can be re-applied
    columns = {r[1] for r in conn.execute("PRAGMA table_info(research_publication)")}
    assert "duplicate_of_version_id" in columns


def test_check_constraints_reject_unknown_policy(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO research_institution(key,name,review_status,content_policy,synced_at)"
            " VALUES ('x','X','approved','everything','t')"
        )


def test_migration_005_adds_one_nullable_column_and_keeps_existing_research_rows(tmp_path):
    conn = connect(tmp_path / "at004.db")
    _apply_up_to(conn, 4)
    conn.execute(
        "INSERT INTO research_institution(key, name, review_status, content_policy, synced_at)"
        " VALUES ('anz','ANZ','approved','full_text','2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO research_publication(institution_id, doc_key, canonical_url, title,"
        " categories, content_status, first_seen_at, last_seen_at) VALUES (1,'anz:h/a',"
        " 'https://h/a','T','[]','link_only','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
    )
    before = {r[1] for r in conn.execute("PRAGMA table_info(research_publication)")}
    assert migrate(conn) >= 5
    after = {r[1] for r in conn.execute("PRAGMA table_info(research_publication)")}
    assert after - before == {"duplicate_of_version_id"}
    row = conn.execute("SELECT doc_key, duplicate_of_id, duplicate_of_version_id"
                       " FROM research_publication").fetchone()  # fmt: skip
    assert tuple(row) == ("anz:h/a", None, None)
    assert migrate(conn) >= 5  # idempotent


def test_migration_006_is_additive_on_a_populated_schema_5_database(tmp_path):
    conn = _populated_pre_research(tmp_path)
    migrate(conn)  # to the latest, then roll 006 back to compare
    conn.executescript(ROLLBACK_006.read_text(encoding="utf-8"))
    before = {**_schema(conn, research=False), **_schema(conn, research=True)}
    rows = conn.execute("SELECT * FROM release").fetchall()
    assert migrate(conn) >= 6
    after = {**_schema(conn, research=False), **_schema(conn, research=True)}
    assert {k: v for k, v in after.items() if k in before} == before
    assert TABLES_006 <= set(after)
    assert [tuple(r) for r in conn.execute("SELECT * FROM release")] == [tuple(r) for r in rows]


def test_migration_006_references_no_statistical_table(conn):
    for name, sql in _schema(conn, research=True).items():
        if any(t in name for t in TABLES_006):
            for table in ("release", "series", "vintage", "observation", "ingest_run"):
                assert f"REFERENCES {table} " not in sql and f"REFERENCES {table}(" not in sql


def test_rollback_006_removes_only_its_objects(tmp_path):
    conn = connect(tmp_path / "r.db")
    migrate(conn)

    def objects() -> dict[str, str]:
        return {r["name"]: r["tbl_name"] for r in conn.execute(
            "SELECT name, tbl_name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}  # fmt: skip

    before = objects()
    conn.executescript(ROLLBACK_006.read_text(encoding="utf-8"))
    after = objects()
    assert set(before) - set(after) == {
        n for n, t in before.items() if t in TABLES_006 | TABLES_007
    }  # 007 references research_summary, so it goes first
    assert {n: before[n] for n in after} == after and "research_document_version" in after
    assert not {6, 7} & {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert migrate(conn) >= 6


def test_full_research_rollback_also_removes_the_006_tables(tmp_path):
    from .llm_support import seed_version

    conn = connect(tmp_path / "f.db")
    migrate(conn)
    version = seed_version(conn)
    run = conn.execute(
        "INSERT INTO research_llm_run(provider, model, hosted, prompt_version, processing_version,"
        " started_at) VALUES ('fake','m',0,'p','3b-1','t')"
    ).lastrowid
    conn.execute(
        "INSERT INTO research_summary(version_id, run_id, attempt, provider, model, hosted,"
        " prompt_version, processing_version, verifier_version, input_sha256, status, created_at)"
        " VALUES (?, ?, 1, 'fake', 'm', 0, 'p', '3b-1', 'v', ?, 'provider_error', 't')",
        (version, run, "a" * 64),
    )
    conn.executescript(ROLLBACK.read_text(encoding="utf-8"))
    assert _schema(conn, research=True) == {}
    assert not {r[0] for r in conn.execute("SELECT version FROM schema_version")} & {4, 5, 6, 7}


def test_migration_007_is_additive_and_its_rollback_removes_only_its_objects(tmp_path):
    conn = connect(tmp_path / "p.db")
    migrate(conn)
    conn.executescript(ROLLBACK_007.read_text(encoding="utf-8"))
    before = {**_schema(conn, research=False), **_schema(conn, research=True)}
    assert not TABLES_007 & set(before)
    assert 7 not in {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert migrate(conn) >= 7
    after = {**_schema(conn, research=False), **_schema(conn, research=True)}
    assert {k: v for k, v in after.items() if k in before} == before
    assert TABLES_007 <= set(after)
    for sql in _schema(conn, research=True).values():
        for table in ("release", "series", "vintage", "observation", "ingest_run"):
            assert f"REFERENCES {table} " not in sql and f"REFERENCES {table}(" not in sql


ROLLBACK_008 = REPO / "scripts" / "rollback" / "008_research_manual_import_down.sql"


def test_migration_008_is_additive_and_its_rollback_removes_only_its_objects(tmp_path):
    from .llm_support import seed_version

    conn = connect(tmp_path / "m.db")
    migrate(conn)
    version = seed_version(conn)
    conn.executescript(ROLLBACK_008.read_text(encoding="utf-8"))
    before = {**_schema(conn, research=False), **_schema(conn, research=True)}
    assert "research_manual_import" not in before
    assert "acquisition" not in before["research_document_version"]
    assert conn.execute("SELECT id FROM research_document_version").fetchone()[0] == version
    assert 8 not in {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert migrate(conn) >= 8
    assert (
        conn.execute("SELECT acquisition FROM research_document_version").fetchone()[0] == "crawler"
    )
    after = _schema(conn, research=True)
    assert "research_manual_import" in after
    for sql in after.values():
        for table in ("release", "series", "vintage", "observation", "ingest_run"):
            assert f"REFERENCES {table} " not in sql and f"REFERENCES {table}(" not in sql


ROLLBACK_009 = REPO / "scripts" / "rollback" / "009_research_llm_reservation_down.sql"


def test_migration_009_is_additive_and_its_rollback_removes_only_its_objects(tmp_path):
    conn = connect(tmp_path / "r.db")
    migrate(conn)
    conn.executescript(ROLLBACK_009.read_text(encoding="utf-8"))
    before = {**_schema(conn, research=False), **_schema(conn, research=True)}
    assert "research_llm_reservation" not in before
    assert 9 not in {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert migrate(conn) >= 9
    after = {**_schema(conn, research=False), **_schema(conn, research=True)}
    assert {k: v for k, v in after.items() if k in before} == before
    assert "research_llm_reservation" in after


ROLLBACK_010 = REPO / "scripts" / "rollback" / "010_research_purge_down.sql"


def test_migration_010_is_additive_and_its_rollback_restores_the_original_triggers(tmp_path):
    from .llm_support import seed_version

    conn = connect(tmp_path / "p.db")
    migrate(conn)
    original = _schema(conn, research=True)
    version = seed_version(conn)
    conn.executescript(ROLLBACK_010.read_text(encoding="utf-8"))
    after = {**_schema(conn, research=False), **_schema(conn, research=True)}
    assert not {"research_purge", "research_purge_artifact"} & set(after)
    assert "purged_at" not in after["research_document_version"]
    assert conn.execute("SELECT id FROM research_document_version").fetchone()[0] == version
    assert "research_summary_content_immutable" in after and "research_claim_no_delete" in after
    assert 10 not in {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert migrate(conn) >= 10
    assert _schema(conn, research=True).keys() == original.keys()
