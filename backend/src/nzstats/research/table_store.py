"""Persistence for table-derived forecasts (Phase 4AF, migration 015).

One extraction row per (document version, interpreter version, positioned-words hash): storing the same extraction
again is a no-op, a changed document or interpreter adds a new one, and reads return the latest. Figures are exact
decimal text beside the printed text; rows are immutable; a purge of the version removes the text-bearing rows.
Nothing here decides whether a figure may be shown or used: that is `table_view`.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from nzstats.clock import to_utc_iso
from nzstats.research.table_forecast import INTERPRETER_VERSION, TableForecast
from nzstats.research.table_grid import Rejection
from nzstats.store.db import transaction


@dataclass(frozen=True)
class StoredTableForecast:
    id: int
    extraction_id: int
    version_id: int
    interpreter_version: str
    ordinal: int
    indicator: str
    label: str
    period_text: str
    horizon: str
    kind: str
    unit: str
    raw_text: str
    value: Decimal | None
    missing: bool
    author_role: str
    footnote: str | None
    page: int
    table: int
    row: int
    col: int
    evidence: dict[str, Any]


def store_extraction(
    conn: sqlite3.Connection,
    version_id: int,
    extracted_at: datetime,
    forecasts: Sequence[TableForecast],
    rejections: Sequence[Rejection],
    *,
    words_sha256: str,
    interpreter_version: str = INTERPRETER_VERSION,
) -> int | None:
    """The new extraction's id, or None when this exact extraction is already stored. All or nothing."""
    with transaction(conn):
        if conn.execute(
            "SELECT 1 FROM research_table_extraction WHERE version_id=? AND interpreter_version=?"
            " AND words_sha256=?",
            (version_id, interpreter_version, words_sha256),
        ).fetchone():
            return None
        cur = conn.execute(
            "INSERT INTO research_table_extraction(version_id, interpreter_version, words_sha256, extracted_at,"
            " forecast_count, rejection_count) VALUES (?,?,?,?,?,?)",
            (version_id, interpreter_version, words_sha256, to_utc_iso(extracted_at), len(forecasts), len(rejections)),
        )  # fmt: skip
        eid = int(cur.lastrowid)
        for n, f in enumerate(forecasts):
            conn.execute(
                "INSERT INTO research_table_forecast(extraction_id, ordinal, indicator, label, period_text, horizon,"
                " kind, unit, raw_text, value, missing, author_role, footnote, page, tbl, tbl_row, tbl_col,"
                " evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eid, n, f.indicator, f.label, f.period_text, f.horizon, f.kind, f.unit, f.raw_text,
                 None if f.value is None else str(f.value), int(f.missing), f.author_role, f.footnote,
                 f.page, f.table, f.row, f.col, json.dumps(f.evidence, sort_keys=True)),
            )  # fmt: skip
        for n, r in enumerate(rejections):
            conn.execute(
                "INSERT INTO research_table_rejection(extraction_id, ordinal, code, page, tbl, tbl_row, tbl_col)"
                " VALUES (?,?,?,?,?,?,?)",
                (eid, n, r.code, r.page, r.table, r.row, r.col),
            )
    return eid


def _latest(conn: sqlite3.Connection, version_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, interpreter_version FROM research_table_extraction WHERE version_id=? ORDER BY id DESC LIMIT 1",
        (version_id,),
    ).fetchone()


def latest_interpreter(conn: sqlite3.Connection, version_id: int) -> str | None:
    """The interpreter that read the version's latest extraction, or None when it has none."""
    latest = _latest(conn, version_id)
    return None if latest is None else latest["interpreter_version"]


def load_forecasts(conn: sqlite3.Connection, version_id: int) -> list[StoredTableForecast]:
    """The figures of the version's latest extraction, in printed order."""
    latest = _latest(conn, version_id)
    if latest is None:
        return []
    rows = conn.execute(
        "SELECT * FROM research_table_forecast WHERE extraction_id=? ORDER BY ordinal",
        (latest["id"],),
    ).fetchall()
    return [
        StoredTableForecast(
            r["id"],
            r["extraction_id"],
            version_id,
            latest["interpreter_version"],
            r["ordinal"],
            r["indicator"],
            r["label"],
            r["period_text"],
            r["horizon"],
            r["kind"],
            r["unit"],
            r["raw_text"],
            None if r["value"] is None else Decimal(r["value"]),
            bool(r["missing"]),
            r["author_role"],
            r["footnote"],
            r["page"],
            r["tbl"],
            r["tbl_row"],
            r["tbl_col"],
            json.loads(r["evidence"]),
        )  # fmt: skip
        for r in rows
    ]


def load_rejections(conn: sqlite3.Connection, version_id: int) -> list[Rejection]:
    latest = _latest(conn, version_id)
    if latest is None:
        return []
    return [
        Rejection(r["code"], r["page"], r["tbl"], r["tbl_row"], r["tbl_col"])
        for r in conn.execute(
            "SELECT * FROM research_table_rejection WHERE extraction_id=? ORDER BY ordinal",
            (latest["id"],),
        )
    ]
