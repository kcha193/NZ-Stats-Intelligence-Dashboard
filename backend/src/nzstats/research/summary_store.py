"""Repository for the Phase 3B summary tables (migration 006). Callers own the transaction.

Rows are append-only: triggers refuse changes to stored content, deletions, approval of anything
that did not pass verification, and reversal of a rejection. `review` also checks these rules first
so the CLI can explain a refusal in plain words.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nzstats.clock import to_utc_iso
from nzstats.research.contract import ForecastClaim
from nzstats.store.db import transaction

_SUMMARY_COLUMNS = (
    "s.*, v.version_no, v.title AS document_title, v.superseded_at, p.canonical_url, p.published_on,"
    " i.key AS institution"
)
_SUMMARY_JOIN = (
    " FROM research_summary s JOIN research_document_version v ON v.id = s.version_id"
    " JOIN research_publication p ON p.id = v.publication_id"
    " JOIN research_institution i ON i.id = p.institution_id"
)


class ReviewError(ValueError):
    pass


class PublicationError(ValueError):
    pass


@dataclass(frozen=True)
class SummaryKey:
    """What makes a summary the same piece of work: re-running it is idempotent."""

    version_id: int
    provider: str
    model: str
    prompt_version: str
    processing_version: str
    input_sha256: str

    def where(self) -> tuple[str, tuple[Any, ...]]:
        return (
            "version_id=? AND provider=? AND model=? AND prompt_version=? AND processing_version=?"
            " AND input_sha256=?",
            (self.version_id, self.provider, self.model, self.prompt_version,
             self.processing_version, self.input_sha256),
        )  # fmt: skip


def start_run(
    conn: sqlite3.Connection,
    *,
    provider: str,
    model: str,
    hosted: bool,
    prompt_version: str,
    processing_version: str,
    limits: Mapping[str, Any],
    dry_run: bool,
    now: datetime,
) -> int:
    cur = conn.execute(
        "INSERT INTO research_llm_run(provider, model, hosted, prompt_version, processing_version,"
        " limits, dry_run, started_at) VALUES (?,?,?,?,?,?,?,?)",
        (provider, model, int(hosted), prompt_version, processing_version,
         json.dumps(dict(limits), sort_keys=True), int(dry_run), to_utc_iso(now)),
    )  # fmt: skip
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    outcome: str,
    counts: Mapping[str, int],
    spent_usd: float,
    now: datetime,
) -> None:
    conn.execute(
        "UPDATE research_llm_run SET finished_at=?, outcome=?, counts=?, spent_usd=? WHERE id=?",
        (to_utc_iso(now), outcome, json.dumps(dict(counts), sort_keys=True), spent_usd, run_id),
    )


def completed_summary(conn: sqlite3.Connection, key: SummaryKey) -> sqlite3.Row | None:
    """The finished summary for this key. A provider error does not count, so it can be retried, and
    neither does a rejected summary: summarising again adds a new attempt and keeps the rejected row."""
    where, params = key.where()
    return conn.execute(
        f"SELECT * FROM research_summary WHERE {where} AND status != 'provider_error'"
        " AND review_status != 'rejected' ORDER BY attempt DESC LIMIT 1",
        params,
    ).fetchone()


def next_attempt(conn: sqlite3.Connection, key: SummaryKey) -> int:
    where, params = key.where()
    row = conn.execute(
        f"SELECT MAX(attempt) FROM research_summary WHERE {where}", params
    ).fetchone()
    return int(row[0] or 0) + 1


def insert_summary(
    conn: sqlite3.Connection,
    key: SummaryKey,
    *,
    run_id: int,
    attempt: int,
    hosted: bool,
    verifier_version: str,
    parameters: Mapping[str, Any],
    raw_output: str | None,
    output_json: str | None,
    status: str,
    error_class: str | None,
    verification: Mapping[str, Any] | None,
    now: datetime,
) -> int:
    digest = (
        hashlib.sha256(raw_output.encode("utf-8")).hexdigest() if raw_output is not None else None
    )
    cur = conn.execute(
        "INSERT INTO research_summary(version_id, run_id, attempt, provider, model, hosted,"
        " prompt_version, processing_version, verifier_version, parameters, input_sha256,"
        " output_sha256, raw_output, output_json, status, error_class, verification, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (key.version_id, run_id, attempt, key.provider, key.model, int(hosted), key.prompt_version,
         key.processing_version, verifier_version, json.dumps(dict(parameters), sort_keys=True),
         key.input_sha256, digest, raw_output, output_json, status, error_class,
         json.dumps(verification, sort_keys=True) if verification is not None else None,
         to_utc_iso(now)),
    )  # fmt: skip
    return int(cur.lastrowid)


def insert_claims(
    conn: sqlite3.Connection, summary_id: int, claims: Sequence[ForecastClaim]
) -> None:
    conn.executemany(
        "INSERT INTO research_forecast_claim(summary_id, ordinal, indicator, indicator_label, horizon,"
        " value, unit, direction, scenario, qualification, evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(summary_id, i, c.indicator.value, c.indicator_label, c.horizon, c.value, c.unit,
          c.direction.value, c.scenario, c.qualification,
          json.dumps([e.model_dump(mode="json") for e in c.evidence]))
         for i, c in enumerate(claims)],
    )  # fmt: skip


def record_usage(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    version_id: int,
    summary_id: int | None,
    call_no: int,
    provider: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    usage_estimated: bool,
    latency_ms: int,
    cost_usd: float,
    outcome: str,
    error_class: str | None,
    now: datetime,
) -> None:
    conn.execute(
        "INSERT INTO research_llm_usage(run_id, version_id, summary_id, call_no, provider, model,"
        " input_tokens, output_tokens, usage_estimated, latency_ms, cost_usd, outcome, error_class,"
        " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, version_id, summary_id, call_no, provider, model, input_tokens, output_tokens,
         int(usage_estimated), latency_ms, cost_usd, outcome, error_class, to_utc_iso(now)),
    )  # fmt: skip


def review(
    conn: sqlite3.Connection,
    summary_id: int,
    *,
    decision: str,
    reviewer: str,
    note: str | None,
    now: datetime,
) -> None:
    """Record a human decision. Approval needs a verified summary; a rejection needs a note."""
    if decision not in ("approved", "rejected"):
        raise ReviewError("decision must be approved or rejected")
    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise ReviewError("a reviewer name is required")
    if decision == "rejected" and not (note or "").strip():
        raise ReviewError("a rejection needs a note saying why")
    row = conn.execute(
        "SELECT status, review_status FROM research_summary WHERE id=?", (summary_id,)
    ).fetchone()
    if row is None:
        raise ReviewError(f"no summary {summary_id}")
    if decision == "approved" and row["status"] != "verified":
        raise ReviewError(f"only verified summaries can be approved (this one is {row['status']})")
    if row["review_status"] == "rejected":
        raise ReviewError("this summary was rejected; summarise again to replace it")
    stamp = to_utc_iso(now)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO research_summary_review(summary_id, decision, reviewer, note, decided_at)"
            " VALUES (?,?,?,?,?)",
            (summary_id, decision, reviewer, note, stamp),
        )
        conn.execute(
            "UPDATE research_summary SET review_status=?, reviewed_by=?, reviewed_at=?, review_note=?"
            " WHERE id=?",
            (decision, reviewer, stamp, note, summary_id),
        )
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def record_publication(
    conn: sqlite3.Connection,
    summary_id: int,
    *,
    decision: str,
    approver: str,
    note: str,
    now: datetime,
) -> None:
    """Record a publication decision. Publishing needs an approved, verified summary; both need a note."""
    if decision not in ("publish", "withdraw"):
        raise PublicationError("decision must be publish or withdraw")
    approver, note = (approver or "").strip(), (note or "").strip()
    if not approver:
        raise PublicationError("an approver name is required")
    if not note:
        raise PublicationError("a publication decision needs a note saying why")
    row = conn.execute(
        "SELECT status, review_status FROM research_summary WHERE id=?", (summary_id,)
    ).fetchone()
    if row is None:
        raise PublicationError(f"no summary {summary_id}")
    if decision == "publish" and (row["status"], row["review_status"]) != ("verified", "approved"):
        raise PublicationError(
            "only an approved, verified summary can be published"
            f" (this one is {row['status']}, {row['review_status']})"
        )
    with transaction(conn):
        conn.execute(
            "INSERT INTO research_summary_publication(summary_id, decision, approver, note, decided_at)"
            " VALUES (?,?,?,?,?)",
            (summary_id, decision, approver, note, to_utc_iso(now)),
        )


def publication_state(conn: sqlite3.Connection, summary_id: int) -> sqlite3.Row | None:
    """The latest publication decision for a summary, or None if there has been none."""
    return conn.execute(
        "SELECT decision, approver, decided_at FROM research_summary_publication"
        " WHERE summary_id=? ORDER BY id DESC LIMIT 1",
        (summary_id,),
    ).fetchone()


def list_summaries(
    conn: sqlite3.Connection, *, status: str | None = None, review_status: str | None = None
) -> list[sqlite3.Row]:
    clauses, params = [], []
    if status:
        clauses.append("s.status=?")
        params.append(status)
    if review_status:
        clauses.append("s.review_status=?")
        params.append(review_status)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(
        f"SELECT {_SUMMARY_COLUMNS}{_SUMMARY_JOIN}{where} ORDER BY s.id", params
    ).fetchall()


def get_summary(conn: sqlite3.Connection, summary_id: int) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT {_SUMMARY_COLUMNS}{_SUMMARY_JOIN} WHERE s.id=?", (summary_id,)
    ).fetchone()


def claims_for(conn: sqlite3.Connection, summary_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM research_forecast_claim WHERE summary_id=? ORDER BY ordinal", (summary_id,)
    ).fetchall()


def usage_for(conn: sqlite3.Connection, summary_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM research_llm_usage WHERE summary_id=? ORDER BY call_no", (summary_id,)
    ).fetchall()


def list_forecast_claims(
    conn: sqlite3.Connection, *, indicator: str | None = None, approved_only: bool = True
) -> list[sqlite3.Row]:
    """Forecast claims with their institution, publication date and exact document version."""
    clauses, params = ["s.status = 'verified'"], []
    if approved_only:
        clauses.append("s.review_status = 'approved'")
    else:
        clauses.append("s.review_status != 'rejected'")
    if indicator:
        clauses.append("c.indicator = ?")
        params.append(indicator)
    return conn.execute(
        "SELECT c.*, s.version_id, s.review_status, s.prompt_version, s.model, v.version_no,"
        " p.published_on, p.canonical_url, i.key AS institution FROM research_forecast_claim c"
        " JOIN research_summary s ON s.id = c.summary_id"
        " JOIN research_document_version v ON v.id = s.version_id"
        " JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id"
        f" WHERE {' AND '.join(clauses)} ORDER BY p.published_on, c.summary_id, c.ordinal",
        params,
    ).fetchall()
