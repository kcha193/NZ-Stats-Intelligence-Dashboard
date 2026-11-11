"""Phase 4AE review round 3: an identical repeat of a claim (prose and table) is the same claim, so whatever excludes
or hides one of them excludes or hides all of them (SYNTHETIC FIXTURE)."""

from nzstats.research.bank_analytics import bank_comparison, bank_consensus

from .bank_support import nf, unusable, view_of


def _peers():
    return [
        nf("bank_b", summary_id=7, value=3.9, published_on="2026-05-13"),
        nf("bank_c", summary_id=8, value=3.7, published_on="2026-05-14"),
    ]


def _a_excluded(out):
    return sorted(
        (e.summary_id, e.claim_path, e.code) for e in out.excluded if e.institution_key == "bank_a"
    )


def test_every_copy_of_a_repeated_claim_is_excluded_when_another_document_conflicts_with_it():
    view = view_of(
        nf("bank_a", summary_id=2, value=2.0, published_on="2026-05-12", claim_path="forecasts[0]"),
        nf("bank_a", summary_id=2, value=2.0, published_on="2026-05-12", claim_path="forecasts[1]"),
        nf("bank_a", summary_id=5, value=3.0, published_on="2026-05-12", claim_path="forecasts[0]"),
        *_peers(),
    )
    out = bank_consensus(view)
    assert [c.key for c in out.groups[0].contributors] == ["bank_b", "bank_c"]
    assert _a_excluded(out) == [
        (2, "forecasts[0]", "conflicting_forecasts"),
        (2, "forecasts[1]", "conflicting_forecasts"),
        (5, "forecasts[0]", "conflicting_forecasts"),
    ]
    ((_, comparison),) = bank_comparison(view)
    assert {r.forecast.institution.key for r in comparison.groups[0].rows} == {"bank_b", "bank_c"}


def test_every_copy_of_an_older_repeated_claim_is_hidden_by_a_newer_unusable_claim():
    view = view_of(
        nf("bank_a", summary_id=1, value=3.8, published_on="2026-02-10", claim_path="forecasts[0]"),
        nf("bank_a", summary_id=1, value=3.8, published_on="2026-02-10", claim_path="forecasts[1]"),
        *_peers(),
        excluded=[unusable("bank_a", summary_id=2, value=9.9, published_on="2026-05-12")],
    )
    out = bank_consensus(view)
    assert [c.key for c in out.groups[0].contributors] == ["bank_b", "bank_c"]
    assert _a_excluded(out) == [
        (1, "forecasts[0]", "newer_claim_unusable"),
        (1, "forecasts[1]", "newer_claim_unusable"),
    ]


def test_an_unconflicted_repeat_is_still_one_vintage():
    view = view_of(
        nf("bank_a", summary_id=2, value=2.0, published_on="2026-05-12", claim_path="forecasts[0]"),
        nf("bank_a", summary_id=2, value=2.0, published_on="2026-05-12", claim_path="forecasts[1]"),
        *_peers(),
    )
    out = bank_consensus(view)
    assert {c.key: c.value for c in out.groups[0].contributors} == {
        "bank_a": 2.0,
        "bank_b": 3.9,
        "bank_c": 3.7,
    }
    assert out.excluded == []
