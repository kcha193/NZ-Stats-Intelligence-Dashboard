"""Repository for the `research_*` tables. Callers own the transaction."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import to_utc_iso


@dataclass(frozen=True)
class SectionRow:
    ordinal: int
    heading: str | None
    text: str
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int


def upsert_institution(
    conn: sqlite3.Connection,
    *,
    key: str,
    name: str,
    review_status: str,
    content_policy: str,
    now: datetime,
) -> int:
    conn.execute(
        "INSERT INTO research_institution(key, name, review_status, content_policy, synced_at)"
        " VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET name=excluded.name,"
        " review_status=excluded.review_status, content_policy=excluded.content_policy,"
        " synced_at=excluded.synced_at",
        (key, name, review_status, content_policy, to_utc_iso(now)),
    )
    return int(
        conn.execute("SELECT id FROM research_institution WHERE key=?", (key,)).fetchone()[0]
    )


def upsert_publication(
    conn: sqlite3.Connection,
    institution_id: int,
    *,
    doc_key: str,
    url: str,
    title: str,
    series: str | None,
    categories: Sequence[str],
    published_on: str | None,
    published_at: str | None,
    precision: str | None,
    content_status: str,
    now: datetime,
) -> tuple[int, bool]:
    """Insert or refresh a publication; returns (id, created). `first_seen_at` never changes."""
    stamp = to_utc_iso(now)
    existing = conn.execute(
        "SELECT id FROM research_publication WHERE doc_key=?", (doc_key,)
    ).fetchone()
    if existing is None:
        cur = conn.execute(
            "INSERT INTO research_publication(institution_id, doc_key, canonical_url, title, series,"
            " categories, published_on, published_at, published_precision, content_status,"
            " first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (institution_id, doc_key, url, title, series, json.dumps(list(categories)), published_on,
             published_at, precision, content_status, stamp, stamp),
        )  # fmt: skip
        return int(cur.lastrowid), True
    conn.execute(
        "UPDATE research_publication SET canonical_url=?, title=?, series=?, categories=?,"
        " last_seen_at=? WHERE id=?",
        (url, title, series, json.dumps(list(categories)), stamp, existing["id"]),
    )
    if published_on is not None:
        # The three date columns describe one stated date, so they change together: a replacement
        # overwrites all of them (clearing a timestamp the new source does not state). With no
        # replacement date the existing group is kept untouched.
        conn.execute(
            "UPDATE research_publication SET published_on=?, published_at=?, published_precision=?"
            " WHERE id=?",
            (published_on, published_at, precision, existing["id"]),
        )
    return int(existing["id"]), False


def current_version(conn: sqlite3.Connection, publication_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT v.* FROM research_document_version v JOIN research_publication p"
        " ON p.current_version_id = v.id WHERE p.id=?",
        (publication_id,),
    ).fetchone()


def version_text_length(conn: sqlite3.Connection, version_id: int) -> int:
    return int(conn.execute("SELECT char_count FROM research_document_version WHERE id=?",
                            (version_id,)).fetchone()[0])  # fmt: skip


def add_version(
    conn: sqlite3.Connection,
    publication_id: int,
    *,
    content_sha256: str,
    text_sha256: str,
    fmt: str,
    fetched_at: datetime,
    extractor_version: str,
    raw_artifact_id: int | None,
    title: str,
    sections: Sequence[SectionRow],
    page_count: int | None,
    licence_snapshot: str,
    now: datetime,
) -> tuple[int, str]:
    """Make this text the publication's current version: `new`, `reactivated` (a revert) or `unchanged`."""
    stamp = to_utc_iso(now)
    current = current_version(conn, publication_id)
    same = conn.execute(
        "SELECT id FROM research_document_version WHERE publication_id=? AND text_sha256=?",
        (publication_id, text_sha256),
    ).fetchone()
    if same is not None:
        if current is not None and current["id"] == same["id"]:
            return int(same["id"]), "unchanged"
        _supersede(conn, current, stamp)
        conn.execute(
            "UPDATE research_document_version SET superseded_at=NULL WHERE id=?", (same["id"],)
        )
        _point(conn, publication_id, same["id"])
        return int(same["id"]), "reactivated"
    _supersede(conn, current, stamp)
    version_no = conn.execute(
        "SELECT COALESCE(MAX(version_no), 0) + 1 FROM research_document_version WHERE publication_id=?",
        (publication_id,),
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO research_document_version(publication_id, version_no, content_sha256, text_sha256,"
        " format, fetched_at, extracted_at, extractor_version, raw_artifact_id, title, page_count,"
        " char_count, licence_snapshot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (publication_id, version_no, content_sha256, text_sha256, fmt, to_utc_iso(fetched_at), stamp,
         extractor_version, raw_artifact_id, title, page_count, sum(len(s.text) for s in sections),
         licence_snapshot),
    )  # fmt: skip
    version_id = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO research_section(version_id, ordinal, heading, text, page_start, page_end,"
        " char_start, char_end) VALUES (?,?,?,?,?,?,?,?)",
        [(version_id, s.ordinal, s.heading, s.text, s.page_start, s.page_end, s.char_start, s.char_end)
         for s in sections],
    )  # fmt: skip
    _point(conn, publication_id, version_id)
    return version_id, "new"


def _supersede(conn: sqlite3.Connection, current: sqlite3.Row | None, stamp: str) -> None:
    if current is not None:
        conn.execute("UPDATE research_document_version SET superseded_at=? WHERE id=?",
                     (stamp, current["id"]))  # fmt: skip


def _point(conn: sqlite3.Connection, publication_id: int, version_id: int) -> None:
    # A publication with its own current version is independent: drop any earlier duplicate attribution.
    conn.execute("UPDATE research_publication SET current_version_id=?, content_status='extracted',"
                 " duplicate_of_id=NULL WHERE id=?", (version_id, publication_id))  # fmt: skip


def mark_duplicate(conn: sqlite3.Connection, publication_id: int, original_id: int) -> None:
    conn.execute("UPDATE research_publication SET duplicate_of_id=? WHERE id=?",
                 (original_id, publication_id))  # fmt: skip


def find_text_elsewhere(
    conn: sqlite3.Connection, text_sha256: str, *, exclude_publication_id: int
) -> int | None:
    """The publication that already holds this exact text under a different identity, if any."""
    row = conn.execute(
        "SELECT publication_id FROM research_document_version WHERE text_sha256=?"
        " AND publication_id != ? ORDER BY id LIMIT 1",
        (text_sha256, exclude_publication_id),
    ).fetchone()
    return int(row[0]) if row else None


def record_run(
    conn: sqlite3.Connection,
    institution_id: int,
    *,
    started_at: datetime,
    finished_at: datetime,
    outcome: str,
    dry_run: bool,
    counts: dict[str, int],
    error_class: str | None,
    detail: str | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO research_run(institution_id, started_at, finished_at, outcome, dry_run, counts,"
        " error_class, detail) VALUES (?,?,?,?,?,?,?,?)",
        (institution_id, to_utc_iso(started_at), to_utc_iso(finished_at), outcome, int(dry_run),
         json.dumps(counts, sort_keys=True), error_class, detail),
    )  # fmt: skip
    return int(cur.lastrowid)


def last_attempt_runs(conn: sqlite3.Connection, institution_id: int) -> dict[str, int]:
    """URL -> id of the latest recorded (non-dry) run of this institution that attempted it.

    Run ids only grow, so this orders attempts without depending on the clock.
    """
    return {
        row["url"]: int(row["last_run"])
        for row in conn.execute(
            "SELECT i.url AS url, MAX(i.run_id) AS last_run FROM research_run_item i"
            " JOIN research_run r ON r.id = i.run_id"
            " WHERE r.institution_id=? AND r.dry_run=0 GROUP BY i.url",
            (institution_id,),
        )
    }


def record_item(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    url: str,
    outcome: str,
    error_class: str | None,
    detail: str | None,
    publication_id: int | None,
    version_id: int | None,
) -> None:
    conn.execute(
        "INSERT INTO research_run_item(run_id, url, publication_id, version_id, outcome, error_class,"
        " detail) VALUES (?,?,?,?,?,?,?)",
        (run_id, url, publication_id, version_id, outcome, error_class, detail),
    )


def set_health(
    conn: sqlite3.Connection,
    institution_id: int,
    *,
    state: str,
    now: datetime,
    success: bool,
    detail: str | None,
) -> None:
    stamp = to_utc_iso(now)
    conn.execute(
        "INSERT INTO research_source_health(institution_id, state, last_checked_at, last_success_at,"
        " consecutive_failures, detail) VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(institution_id) DO UPDATE SET state=excluded.state,"
        " last_checked_at=excluded.last_checked_at,"
        " last_success_at=COALESCE(excluded.last_success_at, last_success_at),"
        " consecutive_failures=CASE WHEN ? THEN 0 ELSE consecutive_failures + 1 END,"
        " detail=excluded.detail",
        (institution_id, state, stamp, stamp if success else None, 0 if success else 1, detail,
         int(success)),
    )  # fmt: skip
