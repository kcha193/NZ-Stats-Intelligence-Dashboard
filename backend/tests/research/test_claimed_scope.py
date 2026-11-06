"""`claimed_scope`: the part of a sentence that belongs to the claimed figure's own assertion (PR 46 convergence review).

SYNTHETIC FIXTURE: invented sentences. The scope is one function used by every scan of the Phase 4R wording. It is tested here on its own
so that a change to a regular expression elsewhere cannot silently change where an assertion begins and ends.
"""

import re

import pytest

from nzstats.research import issuers
from nzstats.research.issuers import _without_comments, claimed_scope

from .attribution_matrix import cases


def split(sentence: str, figure: str) -> tuple[str, str]:
    at = sentence.index(figure)
    return sentence[:at], sentence[at:]


@pytest.mark.parametrize(
    ("sentence", "figure", "lead_starts"),
    [
        # A contrast, a semicolon, ", and", ", which" and a comparator each open a new assertion once it names its forecaster.
        ("Analysts expect growth of 3%, but ANZ expects inflation of 2%.", "2%", " ANZ expects"),
        (
            "Analysts expect growth of 3%; the IMF forecasts inflation of 2%.",
            "2%",
            " the IMF forecasts",
        ),
        ("Analysts expect growth of 3%, and we expect inflation of 2%.", "2%", " we expect"),
        ("Analysts expect growth of 3%, which ANZ says will be 2%.", "2%", " ANZ says"),
        (
            "Analysts forecast 3%, compared with the OECD forecasts of 2%.",
            "2%",
            " the OECD forecasts",
        ),
        # The new side names its forecaster only after the figure.
        (
            "Analysts expect growth of 3%, while inflation of 2% is forecast by the IMF.",
            "2%",
            " inflation of ",
        ),
        (
            "Analysts expect growth of 3%, while inflation will be 2%, according to ANZ.",
            "2%",
            " inflation will be ",
        ),
    ],
)
def test_the_lead_starts_where_the_claimed_assertion_begins(sentence, figure, lead_starts):
    lead, _ = claimed_scope(*split(sentence, figure))
    assert lead.startswith(lead_starts)


@pytest.mark.parametrize(
    ("sentence", "figure"),
    [
        # Nothing on the claimed side names a forecaster, so the earlier credit may still reach the figure.
        ("Analysts expect growth of 3%, but only 2% in 2030.", "2%"),
        (
            "Analysts expect growth of 3% in 2029 but only if banks cut rates, and 2% otherwise.",
            "2%",
        ),
        ("Analysts expect growth of 3% and 4% in 2030.", "4%"),
        ("Analysts expect growth of 3%, while downside risks of 2% remain.", "2%"),
        ("Analysts expect growth of 3%, while the IMF is mentioned beside 2%.", "2%"),
        # A comparison names no forecaster of the figure.
        ("Analysts expect growth of 3%, while 2% is higher than forecast by the IMF.", "2%"),
    ],
)
def test_nothing_is_cut_when_the_claimed_side_names_no_forecaster(sentence, figure):
    before, after = split(sentence, figure)
    assert claimed_scope(before, after)[0] == before


def test_the_figures_in_a_relative_clause_belong_to_the_clause_unless_one_equals_the_claimed_figure():
    base = "We forecast growth of 3%, which the banks say will be {}."
    for tail, kept in [
        ("2%", False),
        ("2.5% in 2030", False),
        ("3%", True),
        ("3.0%", True),
        ("3 per cent", True),
        ("between 2% and 3%", True),
        ("higher", True),
        ("2 percentage points higher", True),
    ]:
        _, trail = claimed_scope(*split(base.format(tail), "3%"))
        assert ("which" in trail) is kept, tail


def test_a_comment_is_the_same_comment_on_either_side_of_the_figure():
    for clause in (
        "which analysts say will be a testing year",
        "which the IMF says will be too optimistic",
        "which analysts expect to be a challenging year",
    ):
        assert not issuers.reported_more(_without_comments(clause))
    for clause in (
        "which analysts say will be 3%",
        "which the IMF says will be higher",
        "which analysts say",
    ):
        assert issuers.reported_more(_without_comments(clause)), clause


def test_the_scope_only_ever_shrinks_what_is_read():
    """Lead is a suffix of what came before, trail is a prefix of what comes after: the scope never invents or reorders text."""
    seen = 0
    for case in cases()[::5]:
        for m in re.finditer(r"\d+%", case.sentence):
            before, after = case.sentence[: m.start()], case.sentence[m.start() :]
            lead, trail = claimed_scope(before, after)
            assert before.endswith(lead) and after.startswith(trail)
            seen += 1
    assert seen > 1000
