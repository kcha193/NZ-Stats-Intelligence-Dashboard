"""SYNTHETIC fixtures: presentation partitions never confer economic accuracy."""

import sqlite3
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nzstats.research.assessment import assess, classify_claims
from nzstats.research.contract import OutlookSummary
from nzstats.research.drafts import draft_summaries
from nzstats.research.verify import Problem, VerificationReport

from .public_support import registry
from .support import institution
from .test_drafts import allow, failing
from .truth_corpus import CORPUS, PUBLISHED
from .verify_support import PROV, ref


def summary():
    return OutlookSummary(
        version_id=7,
        provenance=PROV,
        outlook={"text": "Synthetic outlook", "evidence": [ref(0, "Synthetic outlook")]},
        drivers=[{"text": "Synthetic driver", "evidence": [ref(0, "Synthetic driver")]}],
    )


def test_nested_evidence_errors_exclude_the_containing_claim_and_keep_warnings():
    report = VerificationReport(
        errors=(Problem("quote_not_found", "outlook.evidence[0]", "Synthetic failure"),),
        warnings=(Problem("weak_lexical_support", "drivers[0]", "Synthetic warning", "warning"),),
    )
    claims = classify_claims(summary(), report)
    assert [(c.path, c.status) for c in claims] == [
        ("outlook", "failed"),
        ("drivers[0]", "warning"),
    ]
    assert claims[0].problems == report.errors
    assert claims[1].problems == report.warnings


def test_unscoped_or_unknown_error_paths_fail_closed_for_every_claim():
    for path in ("section[0]", "unknown", "drivers[10].evidence[0]"):
        problem = Problem("unsafe_evidence", path, "Synthetic failure")
        claims = classify_claims(summary(), VerificationReport((problem,), ()))
        assert all(c.status == "failed" and problem in c.problems for c in claims)


def test_clean_claims_stay_clean_and_section_warnings_remain_visible():
    assert all(c.status == "clean" for c in classify_claims(summary(), VerificationReport((), ())))
    warning = Problem("extraction_warning", "section[0]", "Synthetic warning", "warning")
    assert all(
        c.status == "warning"
        for c in classify_claims(summary(), VerificationReport((), (warning,)))
    )


@pytest.mark.parametrize("example", CORPUS, ids=lambda e: e.id)
def test_presentation_does_not_promote_unsupported_ambiguous_or_inexpressible_claims(example):
    from nzstats.research.contract import PolicyDecision, SectionText
    from nzstats.research.verify import VerificationContext, verify

    quote = example.sentence.rstrip(".")
    claim = example.claim(quote)
    field = "decisions" if isinstance(claim, PolicyDecision) else "facts"
    s = summary().model_copy(update={field: (claim,)})
    report = verify(
        s,
        {0: SectionText(f"Synthetic outlook. Synthetic driver. {example.sentence}")},
        VerificationContext(
            published_on=PUBLISHED[example.institution], institution=example.institution
        ),
        version="verify-5",
    )
    assessed = next(c for c in classify_claims(s, report) if c.path == f"{field}[0]")
    if example.truth in ("unsupported", "ambiguous", "inexpressible"):
        assert assessed.status == "failed"
    assert tuple(p for p in assessed.problems if p.severity == "error") == tuple(
        p for p in report.errors if p.path.startswith(f"{field}[0]")
    )


def test_reassessment_works_with_database_writes_denied_and_keeps_original_claims(conn):
    sid = failing(conn)
    (original,) = draft_summaries(conn, registry(institution()), allow(conn, sid))
    before = list(conn.iterdump())
    writes = {
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_TABLE,
    }
    conn.set_authorizer(
        lambda op, *args: sqlite3.SQLITE_DENY if op in writes else sqlite3.SQLITE_OK
    )
    result = assess(conn, original)
    assert result is not None and result.draft is not original
    assert original.claims[1].status == "failed"
    assert list(conn.iterdump()) == before
    changed = replace(original, row={**original.row, "published_on": "2026-08-14"})
    assert assess(conn, changed).id != result.id


def test_damaged_original_hash_cannot_produce_an_executive_assessment(conn):
    sid = failing(conn)
    (original,) = draft_summaries(conn, registry(institution()), allow(conn, sid))
    damaged_read = Mock()
    damaged_read.execute.return_value.fetchone.return_value = ("Synthetic changed output", "0" * 64)
    assert assess(damaged_read, original) is None
