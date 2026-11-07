"""Phase 4T: automatic internal drafts, with no per-summary list entry and no human gold (SYNTHETIC FIXTURE).

Auto display is a separate, opt-in mode of the one draft gate. It never weakens what a draft must be: complete,
schema-valid output from a reviewed route, on a current, held, quotable document, not rejected or withdrawn, with
every failed claim marked. Nothing here reaches the public or private gates.
"""

import hashlib
import json

import pytest

from nzstats.research import drafts
from nzstats.research import summary_store as ss
from nzstats.research.contract import ModelProvenance, assemble, parse_draft
from nzstats.research.drafts import (
    DraftAllowlist,
    DraftAllowlistError,
    draft_summaries,
    load_allowlist,
    stored_reports,
    why_not_draft,
)
from nzstats.research.private import private_summaries
from nzstats.research.public import public_summaries
from nzstats.research.registry import ContentPolicy
from nzstats.research.summarise import load_sections
from nzstats.research.verify import VERIFIER_VERSION, Problem, VerificationReport, verify
from nzstats.store.db import transaction

from .llm_support import NOW, draft, seed_version
from .public_support import registry, store_summary
from .support import institution

RAW = "RAW HOSTED MODEL OUTPUT (private)"
ROUTE_PARAMETERS = {
    "experiment": "phase-4s-treasury-v3", "max_tokens": 12000, "timeout_seconds": 300.0,
    "provider_only": "google-vertex/europe", "zdr": True, "data_collection": "deny",
    "allow_fallbacks": False, "require_parameters": True, "response_format": "json_object",
    "reasoning_effort": "low", "input_usd_per_mtok": 4.4, "output_usd_per_mtok": 22.0,
    "serving_provider": "Google", "response_id": "gen-synthetic-private-1", "finish_reason": "stop",
}  # fmt: skip
AUTO = {
    "enabled": True,
    "enabled_by": "Test Owner",
    "enabled_on": "2026-11-07",
    "note": "synthetic",
}


def auto(*withdrawn: int) -> DraftAllowlist:
    return DraftAllowlist.model_validate({
        "auto_display": AUTO,
        "withdrawn": [{"summary_id": s, "withdrawn_by": "Test Owner", "withdrawn_on": "2026-11-07",
                       "note": "synthetic"} for s in withdrawn],
    })  # fmt: skip


def store_hosted(
    conn,
    version_id,
    *,
    output=None,
    parameters=None,
    model="anthropic/claude-opus-5.5",
    provider="openrouter",
    hosted=True,
    usage="ok",
    status=None,
    raw=RAW,
    review=None,
):
    """A summary stored as the OpenRouter pipeline stores one, from a mocked response."""
    data = output if output is not None else draft(version_id)
    params = dict(ROUTE_PARAMETERS if parameters is None else parameters)
    provenance = ModelProvenance(provider=provider, model=model, prompt_version="outlook-v5",
                                 processing_version="3b-1", parameters=params, input_text_sha256="b" * 64,
                                 created_at=NOW)  # fmt: skip
    summary = assemble(parse_draft(json.dumps(data)), version_id=version_id, provenance=provenance)
    report = verify(summary, load_sections(conn, version_id))
    stored = status or ("verified" if report.passed else "failed_verification")
    usable = stored in ("verified", "failed_verification")
    key = ss.SummaryKey(version_id, provider, model, "outlook-v5", "3b-1", "b" * 64)
    run = ss.start_run(conn, provider=provider, model=model, hosted=hosted, prompt_version="outlook-v5",
                       processing_version="3b-1", limits={}, dry_run=False, now=NOW)  # fmt: skip
    with transaction(conn):
        sid = ss.insert_summary(
            conn, key, run_id=run, attempt=ss.next_attempt(conn, key), hosted=hosted,
            verifier_version=VERIFIER_VERSION, parameters=params, raw_output=raw if usable else None,
            output_json=summary.model_dump_json() if usable else None, status=stored,
            error_class=None if usable else "route_unverified",
            verification=report.to_json() if usable else None, now=NOW,
        )  # fmt: skip
        if usage is not None:
            ss.record_usage(conn, run_id=run, version_id=version_id, summary_id=sid, call_no=1,
                            provider=provider, model=model, input_tokens=100, output_tokens=20,
                            usage_estimated=False, latency_ms=1, cost_usd=0.001, outcome=usage,
                            error_class=None, now=NOW)  # fmt: skip
    if review:
        ss.review(conn, sid, decision=review, reviewer="Private Reviewer",
                  note="PRIVATE NOTE" if review == "rejected" else None, now=NOW)  # fmt: skip
    return sid


def failing_output(v):
    out = draft(v)
    out["forecasts"][0]["value"] = 9.9  # not in the evidence
    return out


def ids(conn, reg, config):
    return [d.id for d in draft_summaries(conn, reg, config)]


REG = registry(institution())


def test_auto_display_shows_an_eligible_summary_nobody_named(conn):
    sid = store_hosted(conn, seed_version(conn))
    assert ids(conn, REG, DraftAllowlist(drafts=())) == []  # the explicit list still names nothing
    assert ids(conn, REG, auto()) == [sid]
    assert why_not_draft(conn, REG, auto(), sid) is None


def test_auto_display_is_off_unless_the_local_configuration_enables_it(conn, tmp_path):
    store_hosted(conn, seed_version(conn))
    assert load_allowlist(tmp_path / "missing.json").auto is False
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"drafts": []}))  # a Phase 4P file keeps its meaning
    assert load_allowlist(legacy).auto is False
    off = tmp_path / "off.json"
    off.write_text(json.dumps({"auto_display": {**AUTO, "enabled": False}}))
    with pytest.raises(
        DraftAllowlistError
    ):  # only an explicit true enables it; anything else shows nothing
        load_allowlist(off)
    typo = tmp_path / "typo.json"
    typo.write_text(json.dumps({"auto-display": AUTO}))
    with pytest.raises(DraftAllowlistError):
        load_allowlist(typo)


def test_failed_claims_stay_flagged_and_the_summary_is_classed_as_failed(conn):
    v = seed_version(conn)
    sid = store_hosted(conn, v, output=failing_output(v))
    (d,) = draft_summaries(conn, REG, auto())
    assert d.id == sid and d.passed is False
    assert d.category == "failed_automated_checks"
    failed = next(c for c in d.claims if c.path == "forecasts[0]")
    assert failed.status == "failed" and failed.problems
    assert all(p.message for p in failed.problems)  # the reason travels with the claim


def test_the_validation_categories_never_claim_more_than_the_checks_found(conn, monkeypatch):
    sid = store_hosted(conn, seed_version(conn))
    (d,) = draft_summaries(conn, REG, auto())
    assert d.id == sid and d.category == "no_automated_issue"
    warning = Problem("horizon_without_period", "forecasts[0]", "names no period", "warning")
    monkeypatch.setattr(drafts, "verify", lambda *a, **k: VerificationReport((), (warning,)))
    (d,) = draft_summaries(conn, REG, auto())
    assert d.passed and d.category == "automated_warning"
    assert next(c for c in d.claims if c.path == "forecasts[0]").status == "warning"
    assert set(drafts.VALIDATION_CATEGORIES) == {
        "no_automated_issue", "automated_warning", "failed_automated_checks", "unusable_response",
    }  # fmt: skip
    assert not any("verified" in c for c in drafts.VALIDATION_CATEGORIES)


@pytest.mark.parametrize("status", ["provider_error", "invalid_output"])
def test_an_unusable_response_never_appears_as_commentary(conn, status):
    v = seed_version(conn)
    sid = store_hosted(conn, v, status=status)
    assert ids(conn, REG, auto()) == []
    assert why_not_draft(conn, REG, auto(), sid) == f"no usable output ({status})"
    (report,) = stored_reports(conn, REG)
    assert report.unusable_attempts == 1  # counted, never shown


def test_a_rejected_summary_stays_rejected_in_auto_mode(conn):
    sid = store_hosted(conn, seed_version(conn), review="rejected")
    assert ids(conn, REG, auto()) == []
    assert why_not_draft(conn, REG, auto(), sid) == "a reviewer rejected it"


def test_a_withdrawn_summary_is_not_shown_in_either_mode(conn):
    sid = store_summary(conn, seed_version(conn), review=None, publish=False)
    digest = conn.execute(
        "SELECT output_sha256 FROM research_summary WHERE id=?", (sid,)
    ).fetchone()[0]
    named = DraftAllowlist.model_validate({
        "drafts": [{"summary_id": sid, "output_sha256": digest, "approved_by": "Test Owner",
                    "approved_on": "2026-11-02", "note": "x"}],
        "withdrawn": [{"summary_id": sid, "withdrawn_by": "Test Owner", "withdrawn_on": "2026-11-07",
                       "note": "x"}],
    })  # fmt: skip
    assert ids(conn, REG, named) == []
    assert why_not_draft(conn, REG, named, sid) == "the owner withdrew it"
    hosted = store_hosted(conn, seed_version(conn, doc="b"))
    assert ids(conn, REG, auto(hosted)) == []


@pytest.mark.parametrize(
    "change",
    [
        {"parameters": {**ROUTE_PARAMETERS, "zdr": False}},
        {"parameters": {**ROUTE_PARAMETERS, "allow_fallbacks": True}},
        {"parameters": {**ROUTE_PARAMETERS, "data_collection": "allow"}},
        {"parameters": {**ROUTE_PARAMETERS, "provider_only": "azure/eu"}},
        {"parameters": {**ROUTE_PARAMETERS, "serving_provider": "Azure"}},
        {"parameters": {k: v for k, v in ROUTE_PARAMETERS.items() if k != "response_id"}},
        {"parameters": {k: v for k, v in ROUTE_PARAMETERS.items() if k != "serving_provider"}},
        {"model": "openai/gpt-unknown"},
        {"usage": None},
        {"usage": "provider_error"},
        {"provider": "fake", "hosted": False, "parameters": {}},
        {"provider": "anthropic", "parameters": {}},
        {"provider": "openrouter", "hosted": False},
    ],
)
def test_auto_display_needs_a_verified_provider_identity_and_request_integrity(conn, change):
    sid = store_hosted(conn, seed_version(conn), **change)
    assert ids(conn, REG, auto()) == []
    assert why_not_draft(conn, REG, auto(), sid) is not None


def test_a_stored_output_that_no_longer_matches_its_hash_is_not_shown(conn):
    sid = store_hosted(conn, seed_version(conn))
    conn.execute("DROP TRIGGER IF EXISTS research_summary_content_immutable")
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='research_summary'"
    ).fetchall():
        conn.execute(f"DROP TRIGGER {name}")
    conn.execute("UPDATE research_summary SET output_sha256=? WHERE id=?", ("0" * 64, sid))
    assert ids(conn, REG, auto()) == []
    assert (
        why_not_draft(conn, REG, auto(), sid)
        == "the stored output does not match its recorded hash"
    )


def test_source_permissions_and_injection_checks_still_apply(conn, monkeypatch):
    sid = store_hosted(conn, seed_version(conn))
    quiet = registry(institution(content_policy=ContentPolicy.METADATA_ONLY.value))
    assert ids(conn, quiet, auto()) == []
    assert ids(conn, {}, auto()) == []
    monkeypatch.setattr(drafts, "injection_findings", lambda sections: [0])
    assert ids(conn, REG, auto()) == []
    assert why_not_draft(conn, REG, auto(), sid) == "a section reads like instructions to a model"


def test_only_the_newest_usable_summary_of_a_version_is_shown(conn):
    v = seed_version(conn)
    older = store_hosted(conn, v, output=failing_output(v))
    newer = store_hosted(conn, v)
    assert ids(conn, REG, auto()) == [newer]
    assert (
        why_not_draft(conn, REG, auto(), older)
        == f"superseded by summary {newer} of the same document version"
    )


def test_an_auto_draft_never_reaches_the_public_or_private_gates(conn):
    store_hosted(conn, seed_version(conn))
    assert ids(conn, REG, auto())
    assert public_summaries(conn, REG) == []
    assert private_summaries(conn, REG) == []


def test_the_output_hash_is_the_raw_outputs(conn):
    sid = store_hosted(conn, seed_version(conn))
    stored = conn.execute(
        "SELECT output_sha256 FROM research_summary WHERE id=?", (sid,)
    ).fetchone()[0]
    assert stored == hashlib.sha256(RAW.encode()).hexdigest()


# --- The routes in automatic mode -----------------------------------------------------------------------------------

LOCAL = {"host": "127.0.0.1:8000", "x-nzstats-client": "dashboard"}
FEED = "/api/internal/drafts"
NOTICE = (
    "AI-generated research draft. Automated checks may miss errors. Not independently reviewed."
)


@pytest.fixture()
def auto_client(make, tmp_path):
    from nzstats.research.drafts_api import internal_drafts_router

    build, conn = make
    v = seed_version(conn)
    sid = store_hosted(conn, v, output=failing_output(v))
    rbnz = seed_version(conn, key="example", doc="later", published_on="2026-08-20")
    store_hosted(conn, rbnz, status="provider_error")
    (tmp_path / "data" / "internal-drafts.json").write_text(
        json.dumps({"auto_display": {**AUTO, "note": "OWNER AUTO NOTE"}})
    )
    client = build(routers=[internal_drafts_router(enabled=True, registry=lambda: REG)])
    return client, sid


def test_the_automatic_feed_shows_the_draft_with_its_category_and_the_notice(auto_client):
    client, sid = auto_client
    r = client.get(FEED, headers=LOCAL)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["mode"] == "automatic" and body["notice"] == NOTICE
    (item,) = body["items"]
    assert item["id"] == sid and item["validation"] == "failed_automated_checks"
    assert item["label"].startswith(NOTICE)
    assert item["human_reviewed"] is False and item["approved_for_publication"] is False
    assert item["official_statistic"] is False
    failed = [c for c in item["claims"] if c["status"] == "failed"]
    assert failed and all(p["message"] for c in failed for p in c["problems"])
    reports = {rep["title"]: rep for rep in body["reports"]}
    assert reports["Synthetic outlook later"]["validation"] == "unusable_response"
    assert reports["Synthetic outlook later"]["draft_id"] is None
    assert reports["Synthetic outlook a"]["draft_id"] == sid


def test_the_automatic_feed_leaks_no_key_raw_output_or_processing_metadata(auto_client):
    client, sid = auto_client
    blob = client.get(FEED, headers=LOCAL).text + client.get(f"{FEED}/{sid}", headers=LOCAL).text
    for secret in (RAW, "gen-synthetic-private-1", "provider_only", "zdr", "data_collection", "response_id",
                   "raw_output", "output_sha256", "input_sha256", "cost_usd", "OWNER AUTO NOTE",
                   "Test Owner", "synthetic-secret", "route_unverified", "Private Reviewer"):  # fmt: skip
        assert secret not in blob, secret


def test_no_automatic_label_says_verified_reviewed_or_approved(auto_client):
    client, _ = auto_client
    body = client.get(FEED, headers=LOCAL).json()
    texts = (
        [body["notice"]]
        + [i["label"] for i in body["items"]]
        + [i["validation"] for i in body["items"]]
    )
    for text in texts:
        lowered = text.lower()
        assert "verified" not in lowered
        assert "human reviewed" not in lowered and "approved for publication" not in lowered


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "127.0.0.1:8000"},
        {"host": "evil.example:8000", "x-nzstats-client": "dashboard"},
        {**LOCAL, "origin": "http://evil.example"},
        {**LOCAL, "sec-fetch-site": "cross-site"},
    ],
)
def test_automatic_mode_keeps_the_local_dashboard_checks(auto_client, headers):
    client, sid = auto_client
    for route in (FEED, f"{FEED}/{sid}"):
        assert client.get(route, headers=headers).status_code == 403


def test_automatic_mode_is_read_only(auto_client):
    client, sid = auto_client
    for method in ("post", "put", "delete"):
        assert getattr(client, method)(f"{FEED}/{sid}", headers=LOCAL).status_code in (404, 405)
