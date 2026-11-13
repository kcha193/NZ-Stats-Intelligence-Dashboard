"""Stored table-derived forecasts (Phase 4AF, migration 015): additive, exact, immutable, purge-aware."""

import re
import sqlite3
from decimal import Decimal

import pytest

from nzstats.research import purge
from nzstats.research.table_forecast import INTERPRETER_VERSION, TableForecast
from nzstats.research.table_grid import Rejection
from nzstats.research.table_store import (
    load_forecasts,
    load_rejections,
    store_extraction,
)
from nzstats.sources.artifacts import ArtifactStore
from nzstats.store.db import MIGRATIONS_DIR, connect, migrate

from .conftest import NOW
from .llm_support import seed_version
from .test_migration import _apply_up_to

SHA = "a" * 64


def tf(**kw) -> TableForecast:
    base = dict(
        table=0, page=1, row=0, col=2, indicator="ocr", label="OCR (%)", period_text="Jun-26",
        horizon="June 2026 quarter", kind="forecast", unit="percent", raw_text="3.25",
        value=Decimal("3.25"), missing=False, author_role="author", footnote=None,
        evidence={"page": 1, "cell_text": "3.25", "bbox": [1.0, 2.0, 3.0]},
    )  # fmt: skip
    return TableForecast(**{**base, **kw})


def test_the_migration_adds_tables_and_changes_nothing_that_exists(tmp_path):
    conn = connect(tmp_path / "old.db")
    _apply_up_to(conn, 14)
    seed_version(conn)
    tables = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if r[0] != "schema_version"
    ]
    before = {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
    schema = {r[0]: r[1] for r in conn.execute("SELECT name, sql FROM sqlite_master")}
    migrate(conn)
    assert {n: conn.execute(f"SELECT * FROM {n}").fetchall() for n in tables} == before
    after = {r[0]: r[1] for r in conn.execute("SELECT name, sql FROM sqlite_master")}
    assert {k: v for k, v in after.items() if k in schema} == schema
    assert {k for k in after if k not in schema} >= {
        "research_table_extraction", "research_table_forecast", "research_table_rejection",
    }  # fmt: skip
    assert 15 in {r[0] for r in conn.execute("SELECT version FROM schema_version")}


def test_the_migration_script_only_creates_new_objects():
    sql = next(MIGRATIONS_DIR.glob("015_*.sql")).read_text(encoding="utf-8")
    code = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    created = re.findall(r"CREATE (?:TABLE|INDEX|TRIGGER) (\w+)", code)
    assert created and all(name.startswith("research_table_") for name in created)
    triggers = re.sub(r"BEFORE (?:UPDATE|DELETE|INSERT) ON", "", code)
    assert not re.search(r"\b(?:ALTER|DROP|INSERT|UPDATE|DELETE)\b", triggers, re.IGNORECASE)


def test_a_stored_figure_round_trips_exactly(conn):
    v = seed_version(conn)
    f = tf(value=Decimal("-0.30"), raw_text="–0.30")
    eid = store_extraction(
        conn,
        v,
        NOW,
        [f, tf(col=3, raw_text="-", value=None, missing=True)],
        [Rejection("unit_unstated", 1, 0, 2)],
        words_sha256=SHA,
    )
    assert eid is not None
    got = load_forecasts(conn, v)
    assert [(g.raw_text, g.value, g.missing, g.ordinal) for g in got] == [
        ("–0.30", Decimal("-0.30"), False, 0),
        ("-", None, True, 1),
    ]
    assert got[0].evidence == f.evidence and got[0].extraction_id == eid and got[0].version_id == v
    assert got[0].interpreter_version == INTERPRETER_VERSION
    assert load_rejections(conn, v) == [Rejection("unit_unstated", 1, 0, 2, None)]


def test_a_second_identical_extraction_is_a_no_op(conn):
    v = seed_version(conn)
    assert store_extraction(conn, v, NOW, [tf()], [], words_sha256=SHA) is not None
    assert store_extraction(conn, v, NOW, [tf()], [], words_sha256=SHA) is None
    assert conn.execute("SELECT COUNT(*) FROM research_table_forecast").fetchone()[0] == 1


def test_a_changed_document_adds_an_extraction_and_reads_return_the_latest(conn):
    v = seed_version(conn)
    store_extraction(conn, v, NOW, [tf(value=Decimal("3.25"))], [], words_sha256=SHA)
    store_extraction(
        conn, v, NOW, [tf(value=Decimal("3.50"), raw_text="3.50")], [], words_sha256="b" * 64
    )
    assert [g.value for g in load_forecasts(conn, v)] == [Decimal("3.50")]


def test_rows_are_immutable(conn):
    v = seed_version(conn)
    store_extraction(conn, v, NOW, [tf()], [Rejection("unmapped_row", 1, 0, 1)], words_sha256=SHA)
    for sql in (
        "UPDATE research_table_forecast SET raw_text = '9'",
        "DELETE FROM research_table_forecast",
        "UPDATE research_table_rejection SET code = 'x'",
        "DELETE FROM research_table_rejection",
        "UPDATE research_table_extraction SET forecast_count = 9",
        "DELETE FROM research_table_extraction",
    ):
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            conn.execute(sql)


def test_a_missing_figure_cannot_carry_a_value_and_a_value_cannot_be_missing(conn):
    v = seed_version(conn)
    with pytest.raises(sqlite3.DatabaseError):
        store_extraction(conn, v, NOW, [tf(value=Decimal("1"), missing=True)], [], words_sha256=SHA)
    with pytest.raises(sqlite3.DatabaseError):
        store_extraction(conn, v, NOW, [tf(value=None, missing=False)], [], words_sha256="c" * 64)
    assert conn.execute("SELECT COUNT(*) FROM research_table_extraction").fetchone()[0] == 0


def test_a_failed_store_leaves_nothing_behind(conn):
    v = seed_version(conn)
    with pytest.raises(sqlite3.DatabaseError):
        store_extraction(conn, v, NOW, [tf(), tf(kind="bogus")], [], words_sha256=SHA)
    assert conn.execute("SELECT COUNT(*) FROM research_table_extraction").fetchone()[0] == 0


def purge_version(conn, tmp_path, v):
    plan = purge.plan_purge(conn, "example", version_ids=[v])
    purge.apply_purge(
        conn,
        plan,
        ArtifactStore(tmp_path / "raw"),
        reason="takedown",
        purged_by="Owner",
        note="test",
        now=NOW,
    )


def test_a_purge_removes_the_table_content_and_keeps_a_tombstone(conn, tmp_path):
    v = seed_version(conn)
    store_extraction(
        conn,
        v,
        NOW,
        [tf(label="ZEBRAFISH-QUOKKA row")],
        [Rejection("unmapped_row", 1, 0, 1)],
        words_sha256=SHA,
    )
    purge_version(conn, tmp_path, v)
    assert load_forecasts(conn, v) == [] and load_rejections(conn, v) == []
    row = conn.execute(
        "SELECT version_id, words_sha256, forecast_count FROM research_table_extraction"
    ).fetchone()
    assert tuple(row) == (v, SHA, 1)  # an audit fact, not content
    assert b"ZEBRAFISH" not in b"".join(
        str(tuple(r)).encode() for r in conn.execute("SELECT * FROM research_table_forecast")
    )


def test_purged_text_cannot_be_extracted_again(conn, tmp_path):
    v = seed_version(conn)
    purge_version(conn, tmp_path, v)
    with pytest.raises(sqlite3.DatabaseError, match="purged"):
        store_extraction(conn, v, NOW, [tf()], [], words_sha256=SHA)


def test_the_rollback_removes_only_the_table_objects_and_migrating_again_restores_them(tmp_path):
    rollback = (
        MIGRATIONS_DIR.parents[3].parent
        / "scripts"
        / "rollback"
        / "015_research_table_forecast_down.sql"
    )
    conn = connect(tmp_path / "r.db")
    migrate(conn)
    v = seed_version(conn)
    conn.executescript(rollback.read_text(encoding="utf-8"))
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert not {n for n in names if n.startswith("research_table_")}
    assert (
        "research_forecast_claim" in names
        and conn.execute("SELECT id FROM research_document_version").fetchone()[0] == v
    )
    assert 15 not in {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    assert migrate(conn) >= 15
    assert "research_table_forecast" in {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master")
    }
