"""The private-preview gate (Phase 4I): separate from public display in both directions (SYNTHETIC FIXTURE)."""

from nzstats.research import summary_store as ss
from nzstats.research.private import private_summaries, why_not_private
from nzstats.research.public import public_summaries

from .llm_support import NOW, draft, seed_version
from .public_support import displayable, registry, store_summary
from .support import institution

PRIVATE = {
    "private_display": "summary",
    "private_display_approved_by": "Test Owner",
    "private_display_approved_on": "2026-11-03",
    "private_display_note": "synthetic test source: private preview permitted",
}


def previewable(key: str = "example", **overrides):
    raw = {
        "llm_processing": "local_only",
        "llm_processing_note": "synthetic",
        **PRIVATE,
        **overrides,
    }
    return institution(key, **raw)


def ids(conn, reg):
    return [p.id for p in private_summaries(conn, reg)]


def test_an_approved_verified_summary_is_previewed_without_any_publication_decision(conn):
    sid = store_summary(conn, seed_version(conn), publish=False)
    reg = registry(previewable())
    assert ids(conn, reg) == [sid] and why_not_private(conn, reg, sid) is None
    assert public_summaries(conn, reg) == []  # private display never makes anything public


def test_public_display_never_grants_private_display(conn):
    sid = store_summary(conn, seed_version(conn))  # reviewed and publication-approved
    reg = registry(displayable(level="excerpt"))
    assert [p.id for p in public_summaries(conn, reg)] == [sid]
    assert ids(conn, reg) == []
    assert "private_display" in why_not_private(conn, reg, sid)


def test_unreviewed_and_rejected_summaries_are_never_previewed(conn):
    v = seed_version(conn)
    unreviewed = store_summary(conn, v, review=None, publish=False)
    reg = registry(previewable())
    assert ids(conn, reg) == []
    assert why_not_private(conn, reg, unreviewed) == "not approved by a reviewer (unreviewed)"
    rejected = store_summary(conn, seed_version(conn, doc="b"), review="rejected", publish=False)
    assert why_not_private(conn, reg, rejected) == "not approved by a reviewer (rejected)"


def test_a_summary_failing_verification_is_never_previewed(conn):
    v = seed_version(conn)
    out = draft(v)
    out["forecasts"][0]["value"] = 9.9  # not in the evidence
    sid = store_summary(conn, v, output=out, review=None, publish=False)
    reg = registry(previewable())
    assert ids(conn, reg) == [] and why_not_private(conn, reg, sid).startswith("not verified")


def test_only_the_newest_approved_summary_of_a_version_is_previewed(conn):
    v = seed_version(conn)
    older = store_summary(conn, v, publish=False)
    newer = store_summary(conn, v, publish=False, model="fake-2")
    reg = registry(previewable())
    assert ids(conn, reg) == [newer]
    assert why_not_private(conn, reg, older).startswith("superseded by summary")


def test_revoking_llm_processing_or_access_withdraws_the_preview(conn):
    sid = store_summary(conn, seed_version(conn), publish=False)
    denied = registry(previewable(llm_processing="denied"))
    assert ids(conn, denied) == [] and "private_display" in why_not_private(conn, denied, sid)
    assert ids(conn, {}) == [] and why_not_private(conn, {}, sid) == (
        "the institution is not in the research registry"
    )


def test_a_newer_document_version_withdraws_the_preview_of_the_older_one(conn):
    v = seed_version(conn)
    sid = store_summary(conn, v, publish=False)
    conn.execute(
        "UPDATE research_document_version SET superseded_at = ? WHERE id = ?", (NOW.isoformat(), v)
    )
    reason = why_not_private(conn, registry(previewable()), sid)
    assert reason == "the document has a newer version; summarise it again"


def test_a_later_rejection_withdraws_the_preview(conn):
    sid = store_summary(conn, seed_version(conn), publish=False)
    reg = registry(previewable())
    assert ids(conn, reg) == [sid]
    ss.review(conn, sid, decision="rejected", reviewer="Owner", note="wrong horizon", now=NOW)
    assert ids(conn, reg) == []
