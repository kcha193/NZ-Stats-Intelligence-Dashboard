"""Phase 3E: research pipeline health, staleness, review backlog and revocation detection. SYNTHETIC FIXTURE only."""

from __future__ import annotations

import json
import socket
from datetime import timedelta

from nzstats.research import store
from nzstats.research import summary_store as ss
from nzstats.research.contract import LlmLimits
from nzstats.research.health import research_health
from nzstats.store.db import transaction

from .llm_support import NOW, seed_version
from .public_support import displayable, registry, store_summary
from .support import institution

UNREVIEWED = {"review_status": "needs_review", "terms_evidence": "search", "approved_by": None,
              "approved_on": None, "approval_note": None}  # fmt: skip


def codes(report, key=None):
    findings = report.findings if key is None else report.source(key).findings
    return {f.code for f in findings}


def test_a_registry_with_nothing_permitted_reports_every_source_as_gated_and_needs_no_attention(
    conn,
):
    reg = {"treasury": institution("treasury", **UNREVIEWED)}
    report = research_health(conn, reg, now=NOW, limits=LlmLimits(), env={})
    assert report.source("treasury").permitted is False
    assert codes(report, "treasury") == {"gated"}
    assert not report.needs_attention


def test_a_permitted_source_with_nothing_stored_needs_attention(conn):
    report = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={})
    assert "no_publications" in codes(report, "example")
    assert report.needs_attention


def test_a_blocked_or_repeatedly_failing_crawler_needs_attention(conn):
    seed_version(conn)
    inst_id = conn.execute("SELECT id FROM research_institution WHERE key='example'").fetchone()[0]
    with transaction(conn):
        for _ in range(3):
            store.set_health(
                conn, inst_id, state="blocked", now=NOW, success=False, detail="blocked"
            )
    report = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={})
    assert {"crawler_blocked", "repeated_failures"} <= codes(report, "example")


def test_staleness_uses_the_registry_cadence_and_the_newest_publication(conn):
    seed_version(conn, published_on="2026-05-20")
    reg = {"example": displayable(expected_publication_days=120)}
    fresh = research_health(conn, reg, now=NOW - timedelta(days=100), limits=LlmLimits(), env={})
    assert "stale" not in codes(fresh, "example")
    stale = research_health(conn, reg, now=NOW, limits=LlmLimits(), env={})
    finding = next(f for f in stale.source("example").findings if f.code == "stale")
    assert "2026-05-20" in finding.message and "120" in finding.message
    no_cadence = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={})
    assert "stale" not in codes(no_cadence, "example")


def test_backlog_review_and_publication_queues_are_counted(conn):
    seed_version(conn, doc="a")
    b = seed_version(conn, doc="b")
    c = seed_version(conn, doc="c")
    store_summary(conn, b, review=None, publish=False)  # verified, awaiting review
    store_summary(conn, c, publish=False)  # approved, no publication decision
    src = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={}).source("example")
    assert (src.unsummarised, src.awaiting_review, src.awaiting_publication, src.public) == (
        1,
        1,
        1,
        0,
    )


def test_a_published_summary_withheld_after_a_permission_is_revoked_needs_attention(conn):
    version = seed_version(conn)
    sid = store_summary(conn, version)
    shown = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={})
    assert shown.source("example").public == 1 and "published_but_withheld" not in codes(
        shown, "example"
    )
    revoked = registry(displayable(public_display="none", public_display_approved_by=None,
                                   public_display_approved_on=None, public_display_note=None))  # fmt: skip
    report = research_health(conn, revoked, now=NOW, limits=LlmLimits(), env={})
    finding = next(
        f for f in report.source("example").findings if f.code == "published_but_withheld"
    )
    assert f"summary {sid}" in finding.message and report.needs_attention


def test_a_poor_extraction_needs_attention(conn):
    seed_version(conn, sections=["�" * 400 + " synthetic"])
    report = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={})
    assert "poor_extraction" in codes(report, "example")


def test_spend_near_the_rolling_cap_needs_attention(conn):
    version = seed_version(conn)
    run = conn.execute("INSERT INTO research_llm_run(provider, model, hosted, prompt_version, processing_version,"
                       " started_at) VALUES ('fake','m',0,'p','3b-1','t')").lastrowid  # fmt: skip
    conn.execute("INSERT INTO research_llm_usage(run_id, version_id, call_no, provider, model, latency_ms,"
                 " cost_usd, outcome, created_at) VALUES (?, ?, 1, 'fake', 'm', 5, 8.5, 'ok', ?)",
                 (run, version, "2026-10-20T00:00:00Z"))  # fmt: skip
    report = research_health(
        conn, registry(), now=NOW, limits=LlmLimits(max_period_usd=10.0), env={}
    )
    assert report.spent_period_usd == 8.5 and "budget_near_cap" in codes(report)
    later = research_health(
        conn, registry(), now=NOW + timedelta(days=40), limits=LlmLimits(), env={}
    )
    assert later.spent_period_usd == 0 and "budget_near_cap" not in codes(later)


def test_the_report_is_json_serialisable_and_carries_no_private_fields(conn):
    version = seed_version(conn)
    store_summary(conn, version)
    report = research_health(
        conn, registry(), now=NOW, limits=LlmLimits(), env={"NZSTATS_PUBLIC_RESEARCH": "1"}
    )
    text = json.dumps(report.to_dict())
    assert report.public_switch == "on"
    for private in ("Private Reviewer Name", "PRIVATE", "Private Approver", "RAW MODEL OUTPUT"):
        assert private not in text


def _removed(conn, **kw):
    """Health over a registry that no longer lists `example`, the institution whose summaries are stored."""
    return research_health(conn, {}, now=NOW, limits=LlmLimits(), env={}, **kw)


def test_a_published_summary_of_an_institution_removed_from_the_registry_needs_attention(conn):
    sid = store_summary(conn, seed_version(conn))
    visible = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={})
    assert visible.source("example").public == 1 and "published_but_withheld" not in codes(
        visible, "example"
    )
    report = _removed(conn)
    finding = next(
        f for f in report.source("example").findings if f.code == "published_but_withheld"
    )
    assert finding.severity == "attention" and f"summary {sid}" in finding.message
    assert "registry" in finding.message and f"research withdraw {sid}" in finding.message
    assert report.source("example").public == 0 and report.needs_attention


def test_a_removed_institution_is_assessed_once_per_published_summary_across_decisions(conn):
    withdrawn = store_summary(conn, seed_version(conn, doc="a"))
    ss.record_publication(
        conn, withdrawn, decision="withdraw", approver="A", note="synthetic", now=NOW
    )
    republished = store_summary(conn, seed_version(conn, doc="b"))
    ss.record_publication(
        conn, republished, decision="withdraw", approver="A", note="synthetic", now=NOW
    )
    ss.record_publication(
        conn, republished, decision="publish", approver="A", note="synthetic", now=NOW
    )
    messages = [f.message for f in _removed(conn).source("example").findings]
    assert len(messages) == 1 and f"summary {republished}" in messages[0]  # latest decision wins


def test_a_removed_institution_whose_summaries_are_all_withdrawn_is_not_flagged(conn):
    sid = store_summary(conn, seed_version(conn))
    ss.record_publication(conn, sid, decision="withdraw", approver="A", note="synthetic", now=NOW)
    report = _removed(conn)
    assert not report.sources and not report.needs_attention


def test_superseded_summaries_raise_no_false_alarm_but_the_newest_of_a_removed_source_does(conn):
    version = seed_version(conn)
    older = store_summary(conn, version, prompt_version="outlook-v1")
    newer = store_summary(conn, version, prompt_version="outlook-v2")
    live = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={})
    assert live.source("example").public == 1 and "published_but_withheld" not in codes(
        live, "example"
    )
    findings = _removed(conn).source("example").findings
    assert [f.code for f in findings] == ["published_but_withheld"]
    assert (
        f"summary {newer}" in findings[0].message and f"summary {older}" not in findings[0].message
    )


def test_a_removed_institution_is_reported_beside_the_registered_ones_in_json(conn):
    store_summary(conn, seed_version(conn, key="gone"))
    store_summary(conn, seed_version(conn, key="example"))
    report = research_health(conn, registry(), now=NOW, limits=LlmLimits(), env={})
    data = json.loads(json.dumps(report.to_dict()))
    assert [s["key"] for s in data["sources"]] == ["example", "gone"] and data["needs_attention"]
    gone = data["sources"][1]
    assert (gone["permitted"], gone["routes"], gone["public"]) == (False, "unregistered", 0)
    assert [f["code"] for f in gone["findings"]] == ["published_but_withheld"]
    assert "published_but_withheld" not in codes(report, "example")
    for private in ("Private Reviewer Name", "PRIVATE", "Private Approver", "RAW MODEL OUTPUT"):
        assert private not in json.dumps(data)


def test_the_withholding_audit_writes_nothing_and_makes_no_network_request(conn, monkeypatch):
    store_summary(conn, seed_version(conn))

    def refuse(*args, **kwargs):
        raise AssertionError("health must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    before = conn.total_changes
    assert _removed(conn).needs_attention
    assert conn.total_changes == before and not conn.in_transaction
