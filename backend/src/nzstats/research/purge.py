"""Targeted purge of stored source content (Phase 3F), for when a permission is withdrawn or a takedown is asked.

What is removed: the extracted text (sections), the model output derived from it (raw output, the validated
summary, its verification report), the forecast claims, and the raw files, including byte-for-byte copies that no
version links. What is kept, because it is an audit fact rather than content: the version row as a tombstone (ids,
hashes, timestamps, how it was obtained), the summary row with placeholders in its content columns, and every
append-only log (manual imports, reviews, publication decisions, model usage and spend), plus one new purge record
and one record per removed artifact. Published summaries of the purged text are withdrawn in the same transaction.

Two steps, because a file cannot join a database transaction. The database step makes the content unavailable
first, atomically, and records every artifact to destroy. The file step then removes them and is resumable: a crash
between the steps leaves `research_purge_artifact` rows without `removed_at`, which `finish_pending` completes and
`research health` reports. Purged text cannot be stored again (migration 010 triggers, and `store.purged_text`).
Deleted content is overwritten (`secure_delete`) and the write-ahead log is truncated, so it is not recoverable from
the database files; copies in older backups are outside this tool's reach.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nzstats.clock import to_utc_iso
from nzstats.research import summary_store as ss
from nzstats.sources.artifacts import ArtifactStore, valid_rel
from nzstats.store.db import transaction

log = logging.getLogger(__name__)

REASONS = ("permission_withdrawn", "takedown", "other")
ACQUISITIONS = ("manual", "crawler", "all")
ORPHAN_MIN_AGE_SECONDS = (
    3600  # a younger unreferenced file may belong to an import still in progress
)


class PurgeError(ValueError):
    """A purge was refused before anything changed; the message is fixed wording, safe to print."""


@dataclass(frozen=True)
class ArtifactRef:
    id: int
    url: str
    sha256: str
    path: str


@dataclass(frozen=True)
class PurgePlan:
    institution: str
    institution_id: int
    scope: dict
    version_ids: tuple[int, ...]
    sections: int
    summaries: int
    claims: int
    published: int
    artifacts: tuple[ArtifactRef, ...]


@dataclass(frozen=True)
class PurgeResult:
    purge_id: int
    versions: int
    artifacts_removed: int
    pending: int


def _in(values: Sequence[int]) -> str:
    return ",".join("?" * len(values))


def plan_purge(
    conn: sqlite3.Connection,
    key: str,
    *,
    acquisition: str | None = None,
    version_ids: Sequence[int] = (),
) -> PurgePlan:
    """What a purge would remove, read-only. Select by acquisition (`manual`, `crawler`, `all`) or by version ids."""
    row = conn.execute("SELECT id FROM research_institution WHERE key=?", (key,)).fetchone()
    if row is None:
        raise PurgeError(f"unknown institution {key!r}: nothing is stored for it")
    if acquisition and version_ids:
        raise PurgeError("select by acquisition or by version ids, not both")
    if not acquisition and not version_ids:
        raise PurgeError(
            "select what to purge: an acquisition (manual, crawler or all) or version ids"
        )
    inst_id = int(row["id"])
    base = (
        "SELECT v.id FROM research_document_version v JOIN research_publication p ON p.id = v.publication_id"
        " WHERE p.institution_id = ? AND v.purged_at IS NULL"
    )
    if version_ids:
        ids = tuple(dict.fromkeys(int(v) for v in version_ids))
        owned = {
            r[0] for r in conn.execute(
                f"SELECT v.id FROM research_document_version v JOIN research_publication p ON p.id = v.publication_id"
                f" WHERE p.institution_id = ? AND v.id IN ({_in(ids)})", (inst_id, *ids))
        }  # fmt: skip
        foreign = [v for v in ids if v not in owned]
        if foreign:
            raise PurgeError(f"version {foreign[0]} is not a version of {key}")
        selected = [
            r[0]
            for r in conn.execute(f"{base} AND v.id IN ({_in(ids)}) ORDER BY v.id", (inst_id, *ids))
        ]
        scope = {"versions": list(ids)}
    else:
        if acquisition not in ACQUISITIONS:
            raise PurgeError(f"acquisition must be one of {', '.join(ACQUISITIONS)}")
        clause = "" if acquisition == "all" else " AND v.acquisition = ?"
        params = (inst_id,) if acquisition == "all" else (inst_id, acquisition)
        selected = [r[0] for r in conn.execute(f"{base}{clause} ORDER BY v.id", params)]
        scope = {"acquisition": acquisition}
    selected_t = tuple(selected)
    if not selected_t:
        return PurgePlan(key, inst_id, scope, (), 0, 0, 0, 0, ())
    marks = _in(selected_t)
    sections = conn.execute(
        f"SELECT COUNT(*) FROM research_section WHERE version_id IN ({marks})", selected_t
    ).fetchone()[0]
    summaries = conn.execute(
        f"SELECT COUNT(*) FROM research_summary WHERE version_id IN ({marks})", selected_t
    ).fetchone()[0]
    claims = conn.execute(
        f"SELECT COUNT(*) FROM research_forecast_claim c JOIN research_summary s ON s.id = c.summary_id"
        f" WHERE s.version_id IN ({marks})", selected_t).fetchone()[0]  # fmt: skip
    published = len(_published_summary_ids(conn, selected_t))
    return PurgePlan(key, inst_id, scope, selected_t, sections, summaries, claims, published,
                     _artifacts_for(conn, selected_t))  # fmt: skip


def _published_summary_ids(conn: sqlite3.Connection, version_ids: Sequence[int]) -> list[int]:
    return [
        r[0] for r in conn.execute(
            f"SELECT s.id FROM research_summary s WHERE s.version_id IN ({_in(version_ids)}) AND"
            " (SELECT d.decision FROM research_summary_publication d WHERE d.summary_id = s.id"
            "  ORDER BY d.id DESC LIMIT 1) = 'publish' ORDER BY s.id", tuple(version_ids))
    ]  # fmt: skip


def _artifacts_for(
    conn: sqlite3.Connection, version_ids: tuple[int, ...]
) -> tuple[ArtifactRef, ...]:
    """The raw artifacts that hold the selected versions' content and are needed by no surviving version.

    That is: the files the versions link, the files their manual-import audit rows say were supplied, and any other
    stored copy of the same document address (the crawler keeps each fetch's bytes) that no surviving version of the
    document owns.
    """
    marks = _in(version_ids)
    found: dict[int, ArtifactRef] = {}

    def add(rows) -> None:
        for r in rows:
            found.setdefault(
                int(r["id"]), ArtifactRef(int(r["id"]), r["url"], r["sha256"], r["path"])
            )

    add(conn.execute(f"SELECT a.* FROM raw_artifact a JOIN research_document_version v ON v.raw_artifact_id = a.id"
                     f" WHERE v.id IN ({marks})", version_ids))  # fmt: skip
    add(conn.execute(f"SELECT a.* FROM raw_artifact a JOIN research_manual_import m ON m.url = a.url"
                     f" AND m.content_sha256 = a.sha256 WHERE m.version_id IN ({marks})", version_ids))  # fmt: skip
    for pub_id, url in conn.execute(
        f"SELECT DISTINCT p.id, p.canonical_url FROM research_publication p JOIN research_document_version v"
        f" ON v.publication_id = p.id WHERE v.id IN ({marks})", version_ids):  # fmt: skip
        surviving = {
            r[0] for r in conn.execute(
                f"SELECT content_sha256 FROM research_document_version WHERE publication_id = ?"
                f" AND purged_at IS NULL AND id NOT IN ({marks})", (pub_id, *version_ids))
        }  # fmt: skip
        add(
            a
            for a in conn.execute("SELECT * FROM raw_artifact WHERE url = ?", (url,))
            if a["sha256"] not in surviving
        )
    in_use = {
        r[0] for r in conn.execute(
            f"SELECT raw_artifact_id FROM research_document_version WHERE raw_artifact_id IS NOT NULL"
            f" AND purged_at IS NULL AND id NOT IN ({marks})", version_ids)
    }  # fmt: skip
    return tuple(a for _, a in sorted(found.items()) if a.id not in in_use)


def apply_purge(
    conn: sqlite3.Connection,
    plan: PurgePlan,
    artifacts: ArtifactStore,
    *,
    reason: str,
    purged_by: str,
    note: str,
    now: datetime,
) -> PurgeResult:
    """Purge what `plan` selected, as it stands now. Raises `PurgeError` before changing anything if refused."""
    purged_by, note = (purged_by or "").strip(), (note or "").strip()
    if reason not in REASONS:
        raise PurgeError(f"reason must be one of {', '.join(REASONS)}")
    if not purged_by:
        raise PurgeError("a named person is required")
    if not note:
        raise PurgeError("a note is required (why, and who asked)")
    conn.execute(
        "PRAGMA secure_delete=ON"
    )  # deleted and overwritten content is zeroed, not just unlinked
    try:
        with transaction(conn):
            # Re-resolve under the write lock: the plan may be stale, and a second purge must not double-count.
            current = plan_purge(conn, plan.institution, **_selector(plan.scope))
            if not current.version_ids:
                raise PurgeError("nothing to purge: no stored version matches")
            purge_id = _record_purge(conn, current, reason, purged_by, note, now)
            _mark_versions(conn, current.version_ids, purge_id, now)
            _withdraw_published(conn, current.version_ids, purged_by, purge_id, now)
            _redact_summaries(conn, current.version_ids)
            _delete_content(conn, current.version_ids)
            for ref in current.artifacts:
                conn.execute(
                    "INSERT INTO research_purge_artifact(purge_id, raw_artifact_id, url, sha256, path)"
                    " VALUES (?,?,?,?,?)", (purge_id, ref.id, ref.url, ref.sha256, ref.path))  # fmt: skip
        removed = finish_pending(conn, artifacts, now=now)
        pending = len(pending_artifacts(conn))
        conn.execute(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        )  # drop the log pages that held the old content
    finally:
        conn.execute("PRAGMA secure_delete=OFF")
    return PurgeResult(purge_id, len(current.version_ids), removed, pending)


def _selector(scope: dict) -> dict:
    return (
        {"version_ids": tuple(scope["versions"])}
        if "versions" in scope
        else {"acquisition": scope["acquisition"]}
    )


def _record_purge(conn, plan: PurgePlan, reason: str, by: str, note: str, now: datetime) -> int:
    cur = conn.execute(
        "INSERT INTO research_purge(institution_id, reason, scope, purged_by, note, versions, sections, summaries,"
        " claims, withdrawn, artifacts, purged_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (plan.institution_id, reason, json.dumps(plan.scope, sort_keys=True), by, note, len(plan.version_ids),
         plan.sections, plan.summaries, plan.claims, plan.published, len(plan.artifacts), to_utc_iso(now)),
    )  # fmt: skip
    return int(cur.lastrowid)


def _mark_versions(conn, version_ids: Sequence[int], purge_id: int, now: datetime) -> None:
    conn.execute(f"UPDATE research_document_version SET purged_at=?, purge_id=? WHERE id IN ({_in(version_ids)})",
                 (to_utc_iso(now), purge_id, *version_ids))  # fmt: skip
    # A publication whose current text is gone is a link, not an extract.
    conn.execute(f"UPDATE research_publication SET content_status='link_only'"
                 f" WHERE current_version_id IN ({_in(version_ids)})", tuple(version_ids))  # fmt: skip


def _withdraw_published(
    conn, version_ids: Sequence[int], by: str, purge_id: int, now: datetime
) -> None:
    for sid in _published_summary_ids(conn, version_ids):
        conn.execute(
            "INSERT INTO research_summary_publication(summary_id, decision, approver, note, decided_at)"
            " VALUES (?, 'withdraw', ?, ?, ?)",
            (sid, by, f"source text purged (purge {purge_id})", to_utc_iso(now)),
        )


def _redact_summaries(conn, version_ids: Sequence[int]) -> None:
    conn.execute(
        f"UPDATE research_summary SET raw_output = NULL,"
        f" output_json = CASE WHEN output_json IS NULL THEN NULL ELSE ? END,"
        f" verification = CASE WHEN verification IS NULL THEN NULL ELSE ? END"
        f" WHERE version_id IN ({_in(version_ids)})",
        (ss.REDACTED, ss.REDACTED, *version_ids),
    )


def _delete_content(conn, version_ids: Sequence[int]) -> None:
    marks = _in(version_ids)
    conn.execute(f"DELETE FROM research_forecast_claim WHERE summary_id IN"
                 f" (SELECT id FROM research_summary WHERE version_id IN ({marks}))", tuple(version_ids))  # fmt: skip
    conn.execute(f"DELETE FROM research_section WHERE version_id IN ({marks})", tuple(version_ids))


def pending_artifacts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM research_purge_artifact WHERE removed_at IS NULL ORDER BY id"
    ).fetchall()


def finish_pending(conn: sqlite3.Connection, artifacts: ArtifactStore, *, now: datetime) -> int:
    """Remove the files (and their records) of every purge not yet finished; returns how many were finalised.

    Idempotent: a file already gone is recorded as missing, a file another record still points at is kept, a stored
    path of a shape this store never writes is never followed. A file that cannot be removed stays pending.
    """
    done = 0
    for art in pending_artifacts(conn):
        outcome = _remove_file(conn, artifacts, art)
        if outcome is None:
            continue
        with transaction(conn):
            surviving = conn.execute(
                "SELECT 1 FROM research_document_version WHERE raw_artifact_id=? AND purged_at IS NULL",
                (art["raw_artifact_id"],)).fetchone()  # fmt: skip
            conn.execute("UPDATE research_document_version SET raw_artifact_id=NULL WHERE raw_artifact_id=?"
                         " AND purged_at IS NOT NULL", (art["raw_artifact_id"],))  # fmt: skip
            if surviving is None:
                conn.execute("DELETE FROM raw_artifact WHERE id=?", (art["raw_artifact_id"],))
            conn.execute("UPDATE research_purge_artifact SET outcome=?, removed_at=? WHERE id=?",
                         (outcome, to_utc_iso(now), art["id"]))  # fmt: skip
        done += 1
    return done


def _remove_file(
    conn: sqlite3.Connection, artifacts: ArtifactStore, art: sqlite3.Row
) -> str | None:
    """The outcome of removing one file, or None when it could not be removed (try again later)."""
    if not valid_rel(art["path"]):
        log.warning(
            "purge artifact %s has an unexpected stored path; the file was not touched", art["id"]
        )
        return "unsafe_path"
    shared = conn.execute(
        "SELECT 1 FROM raw_artifact WHERE path=? AND id != ?", (art["path"], art["raw_artifact_id"])
    ).fetchone()
    if shared is not None:
        return "file_kept_shared"
    try:
        return "removed" if artifacts.remove(art["path"]) else "file_missing"
    except OSError:
        log.exception("could not remove the purged artifact %s; it stays pending", art["path"])
        return None


def integrity_problems(
    conn: sqlite3.Connection, artifacts: ArtifactStore | None = None
) -> list[str]:
    """Plain-words findings about purges and stored files; empty when consistent. Read-only."""
    problems = []
    pending = pending_artifacts(conn)
    if pending:
        problems.append(
            f"{len(pending)} purged artifact(s) still to remove; run `research purge --finish`"
        )
    for (vid,) in conn.execute(
        "SELECT v.id FROM research_document_version v WHERE v.purged_at IS NOT NULL AND EXISTS"
        " (SELECT 1 FROM research_section s WHERE s.version_id = v.id)"):  # fmt: skip
        problems.append(f"version {vid} is purged but still holds text")
    if artifacts is not None:
        for vid, rel in conn.execute(
            "SELECT v.id, a.path FROM research_document_version v JOIN raw_artifact a ON a.id = v.raw_artifact_id"
            " WHERE v.purged_at IS NULL ORDER BY v.id"):  # fmt: skip
            if not artifacts.exists(rel):
                problems.append(f"version {vid}: its raw file is missing")
    return problems


def find_orphan_files(
    conn: sqlite3.Connection,
    artifacts: ArtifactStore,
    *,
    older_than_seconds: float = ORPHAN_MIN_AGE_SECONDS,
) -> list[Path]:
    """Stored files that no `raw_artifact` row records and that are old enough not to be mid-write."""
    known = {r[0] for r in conn.execute("SELECT path FROM raw_artifact")}
    cutoff = time.time() - older_than_seconds
    out = []
    for path in artifacts.files():
        rel = f"{path.parent.name}/{path.name}"
        if rel in known:
            continue
        if path.stat().st_mtime <= cutoff:
            out.append(path)
    return out


def remove_orphan_files(
    conn: sqlite3.Connection,
    artifacts: ArtifactStore,
    *,
    older_than_seconds: float = ORPHAN_MIN_AGE_SECONDS,
) -> int:
    removed = 0
    for path in find_orphan_files(conn, artifacts, older_than_seconds=older_than_seconds):
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed
