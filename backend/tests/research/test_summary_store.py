import json
import sqlite3

import pytest

from nzstats.research import summary_store as ss
from nzstats.research.contract import ForecastClaim
from nzstats.store.db import transaction

from .llm_support import NOW, draft, seed_version


def _key(version_id: int, prompt_version: str = "outlook-v1") -> ss.SummaryKey:
    return ss.SummaryKey(version_id, "fake", "fake-1", prompt_version, "3b-1", "a" * 64)


def _summary(conn, key, *, status="verified", attempt=1) -> int:
    run = ss.start_run(conn, provider="fake", model="fake-1", hosted=False, prompt_version=key.prompt_version,
                       processing_version="3b-1", limits={"max_run_usd": 1.0}, dry_run=False, now=NOW)  # fmt: skip
    with transaction(conn):
        sid = ss.insert_summary(
            conn, key, run_id=run, attempt=attempt, hosted=False, verifier_version="verify-2",
            parameters={"temperature": 0}, raw_output='{"x": 1}',
            output_json=None if status in ("provider_error", "invalid_output") else '{"ok": true}',
            status=status, error_class="timeout" if status == "provider_error" else None,
            verification={"passed": status == "verified"}, now=NOW,
        )  # fmt: skip
    return sid


def test_summaries_are_append_only_and_keep_history(conn):
    v = seed_version(conn)
    first = _summary(conn, _key(v, "outlook-v1"))
    second = _summary(conn, _key(v, "outlook-v2"))
    assert first != second
    rows = ss.list_summaries(conn)
    assert [r["prompt_version"] for r in rows] == ["outlook-v1", "outlook-v2"]
    row = ss.get_summary(conn, first)
    assert row["output_sha256"] and len(row["output_sha256"]) == 64
    assert row["institution"] == "example" and row["review_status"] == "unreviewed"
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("UPDATE research_summary SET output_json='{}' WHERE id=?", (first,))
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute("DELETE FROM research_summary WHERE id=?", (first,))


def test_completed_summary_ignores_provider_errors_and_attempts_count_up(conn):
    v = seed_version(conn)
    key = _key(v)
    assert ss.completed_summary(conn, key) is None and ss.next_attempt(conn, key) == 1
    _summary(conn, key, status="provider_error")
    assert ss.completed_summary(conn, key) is None and ss.next_attempt(conn, key) == 2
    sid = _summary(conn, key, status="failed_verification", attempt=2)
    assert ss.completed_summary(conn, key)["id"] == sid


def test_only_verified_summaries_can_be_approved(conn):
    v = seed_version(conn)
    failed = _summary(conn, _key(v), status="failed_verification")
    with pytest.raises(ss.ReviewError, match="only verified"):
        ss.review(conn, failed, decision="approved", reviewer="Kevin", note=None, now=NOW)
    with pytest.raises(sqlite3.DatabaseError, match="only verified"):
        conn.execute("UPDATE research_summary SET review_status='approved' WHERE id=?", (failed,))
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("INSERT INTO research_summary_review(summary_id, decision, reviewer, decided_at)"
                     " VALUES (?, 'approved', 'x', 't')", (failed,))  # fmt: skip


def test_review_records_an_audit_row_and_rejection_is_final(conn):
    v = seed_version(conn)
    sid = _summary(conn, _key(v))
    ss.review(conn, sid, decision="approved", reviewer="Kevin", note="checked quotes", now=NOW)
    row = ss.get_summary(conn, sid)
    assert (row["review_status"], row["reviewed_by"]) == ("approved", "Kevin")
    ss.review(conn, sid, decision="rejected", reviewer="Kevin", note="horizon misread", now=NOW)
    with pytest.raises(ss.ReviewError, match="rejected"):
        ss.review(conn, sid, decision="approved", reviewer="Kevin", note=None, now=NOW)
    log = conn.execute("SELECT decision, reviewer, note FROM research_summary_review"
                       " WHERE summary_id=? ORDER BY id", (sid,)).fetchall()  # fmt: skip
    assert [tuple(r) for r in log] == [("approved", "Kevin", "checked quotes"),
                                       ("rejected", "Kevin", "horizon misread")]  # fmt: skip
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE research_summary_review SET note='x'")


@pytest.mark.parametrize(
    ("decision", "reviewer", "note", "match"),
    [("approved", " ", None, "reviewer"), ("rejected", "Kevin", None, "note"),
     ("maybe", "Kevin", "n", "decision")],
)  # fmt: skip
def test_review_input_is_validated(conn, decision, reviewer, note, match):
    sid = _summary(conn, _key(seed_version(conn)))
    with pytest.raises(ss.ReviewError, match=match):
        ss.review(conn, sid, decision=decision, reviewer=reviewer, note=note, now=NOW)


def test_unknown_summary_is_a_review_error(conn):
    with pytest.raises(ss.ReviewError, match="no summary"):
        ss.review(conn, 999, decision="approved", reviewer="K", note=None, now=NOW)


def test_claims_are_stored_for_verified_summaries_only_and_queryable(conn):
    v = seed_version(conn)
    sid = _summary(conn, _key(v))
    claims = [ForecastClaim(**c) for c in draft(v)["forecasts"]]
    with transaction(conn):
        ss.insert_claims(conn, sid, claims)
    assert ss.list_forecast_claims(conn) == []  # approved only by default
    rows = ss.list_forecast_claims(conn, approved_only=False, indicator="gdp")
    assert len(rows) == 1 and rows[0]["value"] == 2.5 and rows[0]["version_id"] == v
    assert json.loads(rows[0]["evidence"])[0]["quote"].startswith("expected to grow")
    assert rows[0]["institution"] == "example" and rows[0]["published_on"] == "2026-08-13"
    failed = _summary(conn, _key(v, "outlook-v9"), status="failed_verification")
    with pytest.raises(sqlite3.DatabaseError, match="verified"):
        with transaction(conn):
            ss.insert_claims(conn, failed, claims)


def test_usage_is_recorded_per_call(conn):
    v = seed_version(conn)
    sid = _summary(conn, _key(v))
    run = conn.execute("SELECT run_id FROM research_summary WHERE id=?", (sid,)).fetchone()[0]
    with transaction(conn):
        for call_no, outcome in ((1, "provider_error"), (2, "ok")):
            ss.record_usage(conn, run_id=run, version_id=v, summary_id=sid, call_no=call_no,
                            provider="fake", model="fake-1", input_tokens=100, output_tokens=50,
                            usage_estimated=False, latency_ms=12, cost_usd=0.001, outcome=outcome,
                            error_class=None, now=NOW)  # fmt: skip
    rows = ss.usage_for(conn, sid)
    assert [r["call_no"] for r in rows] == [1, 2] and rows[1]["outcome"] == "ok"
    ss.finish_run(conn, run, outcome="ok", counts={"verified": 1}, spent_usd=0.002, now=NOW)
    run_row = conn.execute("SELECT outcome, spent_usd, counts FROM research_llm_run WHERE id=?",
                           (run,)).fetchone()  # fmt: skip
    assert run_row["outcome"] == "ok" and run_row["spent_usd"] == 0.002


def test_claims_and_usage_cannot_be_changed_or_deleted(conn):
    test_usage_is_recorded_per_call(conn)
    sid = conn.execute("SELECT id FROM research_summary").fetchone()[0]
    with transaction(conn):
        ss.insert_claims(conn, sid, [ForecastClaim(**c) for c in draft(1)["forecasts"]])
    for sql in ("DELETE FROM research_forecast_claim", "DELETE FROM research_llm_usage",
                "UPDATE research_llm_usage SET cost_usd = 0"):  # fmt: skip
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            conn.execute(sql)
