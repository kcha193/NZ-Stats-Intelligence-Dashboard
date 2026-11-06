"""The attribution matrix (PR 46 convergence review), run against the verifier. SYNTHETIC FIXTURE: invented sentences.

The generator and its oracle are in `attribution_matrix.py`. Two kinds of test live here:

* Hard guarantees that hold across the whole matrix and must never weaken.
* A table of outcomes per class of sentence. It is exact on purpose: a change in either direction fails the test, and whoever
  changes the verifier must read which rows moved (the cross-revision differential is described in docs/phase-4r-acceptance.md)
  and update the table with the reason. An improvement is not a licence to trade away a safety row, so it has to be looked at.

"over_reject" is a true label refused (the summary fails, closed). "under_reject" is a wrong label accepted (a safety defect).
At the PR baseline the older wording was the only check: 4,804 true labels refused and 13,125 wrong labels accepted on this matrix.
"""

from collections import Counter

import pytest

from .attribution_matrix import (
    AUTHOR_LABEL,
    STRANGER,
    cases,
    documented_residual,
    labels_for,
    outcome,
    truth,
)
from .test_verify_attribution import authors, codes

REFUSED = {"issuer_mismatch", "issuer_not_in_evidence"}
ALL = cases()


def _refused(sentence, role, label, value):
    return bool(codes(authors(sentence, role, label, value, "2029")) & REFUSED)


def test_the_matrix_is_deterministic_and_covers_every_class():
    assert len(ALL) == len(cases())
    assert {c.cls for c in ALL} == {
        "single",
        "two_forecasts",
        "two_sentences",
        "comparison",
        "comparison_with_figure",
        "year_comment",
        "which_gives_figure",
        "reporter_then_forecaster",
        "forecaster_then_reporter",
    }
    assert len(ALL) > 7000


def test_an_outside_forecasters_figure_is_never_accepted_as_the_authors_in_any_sentence():
    """The Phase 4R guarantee, over every sentence of the matrix (the PR baseline accepted 4,715 of these)."""
    leaked = [
        (c.sentence, f.value)
        for c in ALL
        for f in c.figures
        if not truth(f, AUTHOR_LABEL) and not _refused(c.sentence, *AUTHOR_LABEL, f.value)
    ]
    assert not leaked, leaked[:5]


def test_the_authors_own_figure_is_not_refused_when_nothing_else_credits_it():
    """Every single-assertion sentence the author makes is accepted under the author's label."""
    refused = [
        c.sentence
        for c in ALL
        if c.cls == "single"
        and c.figures[0].maker in ("author", "author_group")
        and _refused(c.sentence, *AUTHOR_LABEL, c.figures[0].value)
    ]
    assert not refused, refused[:5]


def test_a_label_that_names_nobody_in_the_sentence_is_never_accepted():
    accepted = [
        (c.sentence, f.value)
        for c in ALL
        for f in c.figures
        if not _refused(c.sentence, *STRANGER, f.value)
    ]
    assert not accepted, accepted[:5]


def test_no_sentence_of_the_matrix_crashes_the_verifier():
    for c in ALL[::7]:
        for f in c.figures:
            for role, label in labels_for(c):
                authors(c.sentence, role, label, f.value, "2029")


# The outcome table, on every fourth case. Rows: (class, outcome) -> count of (case, figure, label) triples.
EXPECTED = {
    ("comparison", "correct"): 615,
    ("comparison", "over_reject"): 61,
    ("comparison", "under_reject"): 56,
    ("comparison_with_figure", "correct"): 210,
    ("comparison_with_figure", "over_reject"): 27,
    ("comparison_with_figure", "under_reject"): 7,
    ("forecaster_then_reporter", "correct"): 178,
    ("forecaster_then_reporter", "over_reject"): 18,
    ("forecaster_then_reporter", "under_reject"): 2,
    ("single", "correct"): 99,
    ("single", "under_reject"): 3,
    ("two_forecasts", "correct"): 9106,
    ("two_forecasts", "over_reject"): 951,
    ("two_forecasts", "under_reject"): 751,
    ("two_sentences", "correct"): 424,
    ("two_sentences", "over_reject"): 50,
    ("two_sentences", "under_reject"): 14,
    ("which_gives_figure", "correct"): 205,
    ("which_gives_figure", "over_reject"): 29,
    ("which_gives_figure", "under_reject"): 10,
    ("year_comment", "correct"): 2040,
    ("year_comment", "over_reject"): 75,
    ("year_comment", "under_reject"): 117,
}


def _table():
    table = Counter()
    for c in ALL[::4]:
        for f in c.figures:
            for role, label in labels_for(c):
                table[
                    (
                        c.cls,
                        outcome(
                            truth(f, (role, label)), _refused(c.sentence, role, label, f.value)
                        ),
                    )
                ] += 1
    return table


def test_the_outcome_table_is_exactly_what_was_reviewed():
    table = _table()
    assert dict(sorted(table.items())) == dict(sorted(EXPECTED.items())), dict(
        sorted(table.items())
    )


def test_every_wrong_label_accepted_is_a_documented_limit_not_a_phase_4r_wording_gap():
    """Wrong labels still accepted are third-party labels only (never the author's), and none is accepted for a stranger.

    Two documented limits explain them, both unchanged since the PR baseline (the matrix never accepts anything the baseline refused):
    a generic group label answers every group block, and the older wording lets a third party's label pass when that organisation
    is credited elsewhere in the sentence. The second is the follow-up proposed in docs/phase-4r-acceptance.md.
    """
    roles = Counter()
    for c in ALL[::4]:
        for f in c.figures:
            for role, label in labels_for(c):
                if not truth(f, (role, label)) and not _refused(c.sentence, role, label, f.value):
                    roles[
                        (role, "residual" if documented_residual((role, label)) else "older")
                    ] += 1
    assert {role for role, _ in roles} == {"third_party"}


@pytest.mark.parametrize("cls", sorted({c.cls for c in ALL}))
def test_each_class_has_cases_with_true_and_wrong_labels(cls):
    chosen = [c for c in ALL if c.cls == cls]
    assert chosen
    labels = {truth(f, label) for c in chosen[:50] for f in c.figures for label in labels_for(c)}
    assert labels == {True, False}
