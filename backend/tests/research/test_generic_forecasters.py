"""Phase 4R: an unnamed group of forecasters, or a named one that only 'said', is not the author (SYNTHETIC FIXTURE: invented text).

Phase 4Q left a gap: only named organisations and 'markets' could block an author label. "Analysts expect growth of 3% in 2029",
labelled as the document's own forecast, passed. The new wording only ever adds a rejection, and it never credits the author.
Economists, staff and officials are not in the list: a document's own economists can be the author, which lexical checks cannot tell.
"""

import pytest

from .test_verify_attribution import authors, codes

BLOCKED = [
    "Analysts expect growth of 3% in 2029.",
    "Forecasters predict growth of 3% in 2029.",
    "Bank economists forecast growth of 3% in 2029.",
    "Market economists expect growth of 3% in 2029.",
    "Investors anticipate growth of 3% in 2029.",
    "Private-sector forecasters project growth of 3% in 2029.",
    "Rating agencies expect growth of 3% in 2029.",
    "Survey respondents expect growth of 3% in 2029.",
    "Commentators see growth of 3% in 2029.",
    "The banks expect growth of 3% in 2029.",
    "According to analysts, growth will be 3% in 2029.",
    "Growth of 3% in 2029 is expected by analysts.",
    'The IMF said "growth will be 3% in 2029".',
    "The OECD says growth will be 3% in 2029.",
    "The Reserve Bank noted that growth will be 3% in 2029.",
]


@pytest.mark.parametrize("sentence", BLOCKED)
def test_a_group_or_a_reporter_cannot_be_labelled_the_author(sentence):
    assert "issuer_mismatch" in codes(authors(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "We expect growth of 3% in 2029.",
        "Treasury forecasters expect growth of 3% in 2029.",
        "Our analysts expect growth of 3% in 2029.",
        "Analysts will welcome the update. We expect growth of 3% in 2029.",
        "We expect growth of 3% in 2029, as analysts expect.",
        "Growth of 3% in 2029 is above what analysts expect.",
        "The housing market expects little, and growth will reach 3% in 2029.",
        "Banks expected to lift rates, and growth will reach 3% in 2029.",
    ],
)
def test_the_authors_own_forecast_is_not_blocked_by_a_group_beside_it(sentence):
    assert "issuer_mismatch" not in codes(authors(sentence))


def test_the_group_itself_is_accepted_as_the_issuer():
    report = authors("Analysts expect growth of 3% in 2029.", "third_party", "Analysts")
    assert not codes(report) & {"issuer_mismatch", "issuer_not_in_evidence"}


def test_the_reporter_itself_is_accepted_as_the_issuer():
    report = authors(
        'The IMF said "growth will be 3% in 2029".', "third_party", "International Monetary Fund"
    )
    assert not codes(report) & {"issuer_mismatch", "issuer_not_in_evidence"}


def test_a_group_does_not_become_the_authors_view_by_label():
    # The label names the wrong third party: still an error, as before.
    report = authors(
        "Analysts expect growth of 3% in 2029.", "third_party", "International Monetary Fund"
    )
    assert codes(report) & {"issuer_mismatch", "issuer_not_in_evidence"}


# Independent review, round 1: the new wording may only add a rejection, for every label, and may never waive one.
@pytest.mark.parametrize(
    ("sentence", "issuer"),
    [
        (
            "The MPC said it expected growth of 3% in 2029 and the IMF noted risks.",
            "International Monetary Fund",
        ),
        ("Westpac said it expected growth of 3% in 2029 and ASB noted risks.", "ASB"),
        (
            "Markets expect growth of 3% in 2029 and the Reserve Bank noted risks.",
            "The Reserve Bank",
        ),
        (
            "Analysts expect growth of 3% in 2029, while the IMF said it expected a slowdown.",
            "Analysts",
        ),
        ("The IMF expected by investors to cut said growth would be 3% in 2029.", "Analysts"),
    ],
)
def test_the_new_wording_never_waives_a_rejection_for_a_third_party_label(sentence, issuer):
    assert "issuer_mismatch" in codes(authors(sentence, "third_party", issuer))


@pytest.mark.parametrize(
    "sentence",
    [
        "Our economists and forecasters expect growth of 3% in 2029.",
        "Our forecasters and analysts expect growth of 3% in 2029.",
        "Treasury analysts and forecasters expect growth of 3% in 2029.",
        "The Treasury's economists and analysts expect growth of 3% in 2029.",
        "Our staff, analysts and forecasters expect growth of 3% in 2029.",
        "Treasury forecasts growth of 3% in 2029, which analysts expect to be a testing year.",
    ],
)
def test_the_authors_own_people_are_not_outside_groups(sentence):
    assert "issuer_mismatch" not in codes(authors(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "Currently analysts expect growth of 3% in 2029.",
        "Meanwhile analysts expect growth of 3% in 2029.",
        "Most analysts expect growth of 3% in 2029.",
        "The four major banks expect growth of 3% in 2029.",
        "Analysts at ANZ expect growth of 3% in 2029.",
        "Analysts are expecting growth of 3% in 2029.",
        "Analysts say growth will be 3% in 2029.",
        "Growth of 3% in 2029 is forecast by analysts.",
        "According to a survey of analysts, growth will be 3% in 2029.",
        "IMF staff said growth will be 3% in 2029.",
        "The IMF has said growth will be 3% in 2029.",
    ],
)
def test_common_ways_of_reporting_an_outside_forecast_cannot_be_the_authors(sentence):
    assert "issuer_mismatch" in codes(authors(sentence))


# Automated security review, round 1.
def test_a_group_name_is_no_exemption_for_a_claim_labelled_as_the_author():
    assert "issuer_mismatch" in codes(
        authors("Analysts expect growth of 3% in 2029.", "author", "Analysts")
    )


@pytest.mark.parametrize(
    "sentence",
    [
        "Our investors and banks expect growth of 3% in 2029.",
        "Treasury analysts at ANZ expect growth of 3% in 2029.",
        "Unlike us, analysts expect growth of 3% in 2029.",
    ],
)
def test_only_the_authors_own_kind_of_people_are_skipped(sentence):
    assert "issuer_mismatch" in codes(authors(sentence))


@pytest.mark.parametrize(
    ("sentence", "issuer"),
    [
        (
            "The RBNZ expected by analysts to cut the OCR to 3% in 2029.",
            "Reserve Bank of New Zealand",
        ),
        ("The IMF expected by investors growth of 3% in 2029.", "International Monetary Fund"),
    ],
)
def test_the_new_wording_is_not_waived_by_the_claimed_issuers_own_credit(sentence, issuer):
    assert "issuer_mismatch" in codes(authors(sentence, "third_party", issuer))


# Review of PR 46 (Codex, P2): a modifier on the author's own kind of people ("our market analysts") is still the author speaking.
@pytest.mark.parametrize(
    "sentence",
    [
        "Our market analysts expect growth of 3% in 2029.",
        "Our bank economists expect growth of 3% in 2029.",
        "Our independent forecasters expect growth of 3% in 2029.",
        "Our private-sector economists forecast growth of 3% in 2029.",
        "Our sell-side analysts predict growth of 3% in 2029.",
        "Our independent market analysts expect growth of 3% in 2029.",
        "Our market analysts and independent forecasters expect growth of 3% in 2029.",
        "Our staff, bank economists and market analysts expect growth of 3% in 2029.",
        "Treasury market analysts expect growth of 3% in 2029.",
        "The Treasury's bank economists expect growth of 3% in 2029.",
    ],
)
def test_the_authors_own_people_keep_their_modifiers(sentence):
    assert "issuer_mismatch" not in codes(authors(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        # The same wording without a self-reference is still an outside group.
        "Market analysts expect growth of 3% in 2029.",
        "Independent forecasters expect growth of 3% in 2029.",
        "Bank economists expect growth of 3% in 2029.",
        # Another organisation, or a different group, attached to the people.
        "Our market analysts at ANZ expect growth of 3% in 2029.",
        "Our bank economists from Westpac expect growth of 3% in 2029.",
        "Our market analysts and investors expect growth of 3% in 2029.",
        "Our market analysts and the banks expect growth of 3% in 2029.",
        # A self-reference in a comparison, or an unrelated opening, does not hand the next words to the author.
        "Unlike us, market analysts expect growth of 3% in 2029.",
        "Treasury and market analysts expect growth of 3% in 2029.",
        "Our forecast is 2%, but market analysts expect growth of 3% in 2029.",
        "We said so, and independent forecasters now expect growth of 3% in 2029.",
        # A modifier does not excuse a reporter.
        "According to market analysts, growth will be 3% in 2029.",
    ],
)
def test_a_modifier_does_not_turn_an_outside_group_into_the_authors_people(sentence):
    assert "issuer_mismatch" in codes(authors(sentence))


@pytest.mark.parametrize("issuer", ["Analysts", "Market analysts", "ANZ"])
def test_our_market_analysts_are_not_credited_to_another_label(issuer):
    # A third-party label on the author's own people's forecast stays an error, as before the fix.
    report = authors("Our market analysts expect growth of 3% in 2029.", "third_party", issuer)
    assert codes(report) & {"issuer_mismatch", "issuer_not_in_evidence"}


# Review of PR 46 (Codex, P2, round 2): a group after the figure that is only the other side of a comparison is no forecaster.
@pytest.mark.parametrize(
    "sentence",
    [
        "We expect growth of 3% in 2029, higher than forecast by analysts.",
        "We expect growth of 3% in 2029, above what is expected by analysts.",
        "We expect growth of 3% in 2029, unlike growth forecast by analysts.",
        "We expect growth of 3% in 2029, compared with growth expected by analysts.",
        "We expect growth of 3% in 2029, versus 2% according to analysts.",
        "We expect growth of 3% in 2029, as strong as forecast by analysts.",
        "We expect growth of 3% in 2029, exceeding the rate forecast by analysts.",
        "We expect growth of 3% in 2029, relative to growth projected by investors.",
    ],
)
def test_a_group_on_the_other_side_of_a_comparison_after_the_figure_is_not_the_forecaster(sentence):
    assert "issuer_mismatch" not in codes(authors(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "Growth of 3% in 2029 is expected by analysts.",
        "We expect growth of 3% in 2029, forecast by analysts.",
        "We expect growth of 3% in 2029, according to analysts.",
        # "As forecast by analysts" gives the figure to analysts. It is no comparison, and "as" alone must not excuse it.
        "We expect growth of 3% in 2029, as forecast by analysts.",
        "Growth will be 3% in 2029, as expected by investors.",
        # The comparison ends before the group: a comma, a semicolon or distance separates them.
        "We expect growth of 3% in 2029, higher than 2%, forecast by analysts.",
        "We expect growth of 3% in 2029, higher than the RBNZ; this is forecast by analysts.",
        "We expect growth of 3% in 2029, higher than the rate we had last year, as forecast by analysts.",
    ],
)
def test_a_group_after_the_figure_without_a_comparison_still_blocks(sentence):
    assert "issuer_mismatch" in codes(authors(sentence))


def test_a_comparison_after_the_figure_does_not_excuse_a_third_party_label_for_a_group():
    report = authors(
        "The IMF forecasts growth of 3% in 2029, as forecast by analysts.",
        "third_party",
        "International Monetary Fund",
    )
    assert "issuer_mismatch" in codes(report)


# Review of PR 46 (Codex, P2, round 3, finding 1): the claimed issuer's own "said" ends an earlier reporter's reach, as its forecast does.
@pytest.mark.parametrize(
    "sentence",
    [
        "The OECD said growth would be 2% in 2029, but the IMF said growth would be 3% in 2029.",
        "The OECD says growth will be 2% in 2029, while the IMF says growth will be 3% in 2029.",
        "The OECD noted growth of 2% in 2029; IMF staff said growth would be 3% in 2029.",
        "The OECD said growth would be 2% in 2029, but the IMF has said growth would be 3% in 2029.",
    ],
)
def test_the_claimed_reporters_own_words_end_an_earlier_reporters_reach(sentence):
    report = authors(sentence, "third_party", "International Monetary Fund")
    assert "issuer_mismatch" not in codes(report)


IMF = "International Monetary Fund"


@pytest.mark.parametrize(
    ("sentence", "role", "issuer"),
    [
        # The other reporter is the one who gives the figure.
        (
            "The IMF said growth would be 2% in 2029, but the OECD said growth would be 3% in 2029.",
            "third_party",
            IMF,
        ),
        # A bare mention is no credit: the OECD's wording still leads to the figure.
        (
            "The OECD said growth would be 2% in 2029, but the IMF has a view and growth would be 3% in 2029.",
            "third_party",
            IMF,
        ),
        # Under the author label, a named reporter who gives the figure is still no author.
        (
            "The OECD said growth would be 2% in 2029, but the IMF said growth would be 3% in 2029.",
            "author",
            "The Treasury",
        ),
    ],
)
def test_an_earlier_or_other_reporter_is_still_a_mismatch(sentence, role, issuer):
    assert "issuer_mismatch" in codes(authors(sentence, role, issuer))


# Round 3, finding 2: a named reporter who only comments on the year in a "which" clause is not the forecaster.
@pytest.mark.parametrize(
    "sentence",
    [
        "We expect growth of 3% in 2029, which the IMF says will be a challenging year.",
        "We expect growth of 3% in 2029, which the IMF said would be too optimistic.",
        "We expect growth of 3% in 2029, which the OECD notes will be a difficult year.",
        "We expect growth of 3% in 2029, which the Reserve Bank has said will be a testing year.",
    ],
)
def test_a_named_reporter_commenting_on_the_year_is_not_the_forecaster(sentence):
    assert "issuer_mismatch" not in codes(authors(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "We expect growth of 3% in 2029, which the IMF says will be 3%.",
        "We expect growth of 3% in 2029, which the IMF said would be higher.",
        "We expect growth of 3% in 2029, which the IMF says is the right figure.",
        "We expect growth of 3% in 2029, which the OECD noted will be a challenging year and growth would be 3%.",
        "We expect growth of 3% in 2029, which the IMF says.",
        # Outside the closed list of comments: it may be the forecast itself.
        "We expect growth of 3% in 2029, which the IMF said would stay unchanged.",
    ],
)
def test_a_named_reporter_in_a_which_clause_that_is_not_a_comment_still_blocks(sentence):
    assert "issuer_mismatch" in codes(authors(sentence))


# Review of PR 46 (Codex, P2, round 4): a group that is the agent of ANOTHER indicator's own passive is not the claimed figure's source.
@pytest.mark.parametrize(
    "sentence",
    [
        "We expect growth of 3% in 2029, and inflation of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, and inflation of 2% in 2030 is expected by investors.",
        "We expect growth of 3% in 2029 and the unemployment rate of 4% was projected by market economists.",
        "We expect growth of 3% in 2029, and the cash rate of 3.5% will be forecast by the banks.",
        "We expect growth of 3% in 2029, and wage growth of 2% has been predicted by independent forecasters.",
        # Other ways to open that clause.
        "We expect growth of 3% in 2029 (inflation of 2% is forecast by analysts).",
        "We expect growth of 3% in 2029 - inflation of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029 \u2014 inflation of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, as inflation of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, because inflation of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, although inflation of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, inflation of 2% is forecast by analysts.",
    ],
)
def test_another_indicators_own_passive_does_not_make_its_group_the_source_of_the_claimed_figure(
    sentence,
):
    assert "issuer_mismatch" not in codes(authors(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        # Several figures under one attribution: no clause of its own for the second figure.
        "We expect growth of 3% in 2029 and 4% in 2030, which is forecast by analysts.",
        "We expect growth of 3% in 2029 and 4% in 2030 are forecast by analysts.",
        # Detached attribution may cover both figures.
        "We expect growth of 3% in 2029, and inflation of 2%, as forecast by analysts.",
        "We expect growth of 3% in 2029, with inflation at 2% as forecast by analysts.",
        "We expect growth of 3% in 2029, with inflation at 2% now forecast by analysts.",
        "We expect growth of 3% in 2029, and inflation of 2% forecast by analysts.",
        "We expect growth of 3% in 2029, and inflation of 2% according to analysts.",
        # No second figure at all, or the passive belongs to the claimed figure.
        "We expect growth of 3% in 2029, and it is forecast by analysts.",
        "We expect growth of 3% in 2029, and that is expected by investors.",
        "We expect growth of 3% in 2029, and inflation is forecast by analysts.",
        # The group comes before the second clause.
        "Growth of 3% in 2029 is forecast by analysts, and inflation of 2% is ours.",
        # A second figure without a subject of its own, or a passive that is not finite, may still be about the claimed figure.
        "We expect growth of 3% in 2029, inflation of 2% and 4% in 2030 are forecast by analysts.",
        "We expect growth of 3% in 2029 (and 4% in 2030 are forecast by analysts).",
        # A pronoun or a bare connective is no subject of its own: "that of 2%" and "and of 2%" point back at the claimed figure.
        "We expect growth of 3% in 2029, and that of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, and it at 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, and of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, this of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, with inflation of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029, without inflation of 2% is forecast by analysts.",
        "We expect growth of 3% in 2029 and also of 2% is forecast by analysts.",
        # The second clause is not a subject with a figure of its own.
        "We expect growth of 3% in 2029, and over 2030 it is forecast by analysts.",
    ],
)
def test_a_group_that_may_still_be_the_source_of_the_claimed_figure_still_blocks(sentence):
    assert "issuer_mismatch" in codes(authors(sentence))


def test_a_second_indicators_passive_does_not_excuse_a_group_that_wrote_the_claimed_figure():
    report = authors(
        "Analysts expect growth of 3% in 2029, and inflation of 2% is forecast by the IMF.",
        "author",
        "The Treasury",
    )
    assert "issuer_mismatch" in codes(report)


# Review of PR 46 (Codex, P2, round 6, finding 1): a third party's label may carry the same modifiers the evidence's group does.
@pytest.mark.parametrize(
    ("sentence", "issuer"),
    [
        ("The major banks expect growth of 3% in 2029.", "Major banks"),
        ("The major banks expect growth of 3% in 2029.", "The major banks"),
        ("Most analysts expect growth of 3% in 2029.", "Most analysts"),
        ("The four major banks expect growth of 3% in 2029.", "The four major banks"),
        ("Leading forecasters predict growth of 3% in 2029.", "Leading forecasters"),
        ("Australian banks expect growth of 3% in 2029.", "Australian banks"),
        ("Some market economists forecast growth of 3% in 2029.", "Some market economists"),
    ],
)
def test_a_group_label_with_the_evidences_modifiers_is_accepted_for_a_third_party(sentence, issuer):
    report = authors(sentence, "third_party", issuer)
    assert not codes(report) & {"issuer_mismatch", "issuer_not_in_evidence"}


@pytest.mark.parametrize(
    ("sentence", "role", "issuer"),
    [
        # A group is never the author, whatever its label.
        ("The major banks expect growth of 3% in 2029.", "author", "Major banks"),
        # The label must be in the evidence and be a closed-list group, not any longer name.
        ("Analysts expect growth of 3% in 2029.", "third_party", "Major banks"),
        ("The major banks expect growth of 3% in 2029.", "third_party", "Major banks of Asia"),
        ("The major banks expect growth of 3% in 2029.", "third_party", "Westpac"),
        ("The IMF said growth will be 3% in 2029.", "third_party", "Most analysts"),
        ("Most analysts expect growth of 3% in 2029.", "third_party", "The Treasury"),
    ],
)
def test_a_group_label_is_still_refused_when_it_is_not_what_the_evidence_names(
    sentence, role, issuer
):
    assert codes(authors(sentence, role, issuer)) & {"issuer_mismatch", "issuer_not_in_evidence"}


# Round 6, finding 2: a group that only comments on the year in a "which" clause is not the forecaster, in every wording the group
# attribution itself recognises.
@pytest.mark.parametrize(
    "sentence",
    [
        "We expect growth of 3% in 2029, which analysts say will be a challenging year.",
        "We expect growth of 3% in 2029, which analysts said would be too optimistic.",
        "We expect growth of 3% in 2029, which analysts are expecting to be a testing year.",
        "We expect growth of 3% in 2029, which analysts at ANZ expect to be a testing year.",
        "We expect growth of 3% in 2029, which most analysts now expect to be a difficult year.",
        "We expect growth of 3% in 2029, which market economists currently reckon will be a tough year.",
    ],
)
def test_a_group_commenting_on_the_year_in_any_of_its_wordings_is_not_the_forecaster(sentence):
    assert "issuer_mismatch" not in codes(authors(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "We expect growth of 3% in 2029, which analysts say will be 3%.",
        "We expect growth of 3% in 2029, which analysts said would be higher.",
        "We expect growth of 3% in 2029, which analysts are expecting to be 3%.",
        "We expect growth of 3% in 2029, which analysts at ANZ expect growth of 3%.",
        "We expect growth of 3% in 2029, which analysts say.",
        "We expect growth of 3% in 2029, which most analysts now expect to stay unchanged.",
    ],
)
def test_a_group_in_a_which_clause_that_is_not_a_comment_still_blocks(sentence):
    assert "issuer_mismatch" in codes(authors(sentence))


# Review of PR 46 (Codex, P2, round 7): a group said to be at ONE named organisation is that organisation's view, so that organisation's
# own third-party label answers the group block. Nothing else does.
@pytest.mark.parametrize(
    ("sentence", "issuer"),
    [
        ("Analysts at ANZ expect growth of 3% in 2029.", "ANZ"),
        ("Growth of 3% in 2029 is forecast by analysts at ANZ.", "ANZ"),
        ("Market economists at Westpac forecast growth of 3% in 2029.", "Westpac"),
        ("Analysts from the IMF expect growth of 3% in 2029.", "International Monetary Fund"),
        ("According to analysts at ASB, growth will be 3% in 2029.", "ASB"),
        ("Most analysts at BNZ now expect growth of 3% in 2029.", "BNZ"),
        ("Analysts at ANZ expect growth of 3% in 2029.", "ANZ Bank New Zealand"),
        ("Investors at Kiwibank are expecting growth of 3% in 2029.", "Kiwibank"),
    ],
)
def test_a_group_at_one_named_organisation_is_answered_by_that_organisations_label(
    sentence, issuer
):
    report = authors(sentence, "third_party", issuer)
    assert not codes(report) & {"issuer_mismatch", "issuer_not_in_evidence"}


@pytest.mark.parametrize(
    ("sentence", "role", "issuer"),
    [
        # Another organisation, even one the evidence names elsewhere.
        (
            "Analysts at ANZ expect growth of 3% in 2029, while Westpac said it was cautious.",
            "third_party",
            "Westpac",
        ),
        (
            "Analysts at ANZ expect growth of 3% in 2029.",
            "third_party",
            "International Monetary Fund",
        ),
        # An author label is never answered by a group, whichever organisation it is at.
        ("Analysts at ANZ expect growth of 3% in 2029.", "author", "The Treasury"),
        ("Growth of 3% in 2029 is forecast by analysts at ANZ.", "author", "The Treasury"),
        # More than one organisation, or none attached to the group: the label cannot tell which view it is.
        ("Analysts at ANZ and Westpac expect growth of 3% in 2029.", "third_party", "ANZ"),
        ("Analysts at ANZ and the IMF expect growth of 3% in 2029.", "third_party", "ANZ"),
        ("Analysts expect growth of 3% in 2029, as ANZ noted.", "third_party", "ANZ"),
        ("Growth of 3% in 2029 is forecast by analysts, as ANZ noted.", "third_party", "ANZ"),
    ],
)
def test_nothing_else_answers_a_group_attached_to_an_organisation(sentence, role, issuer):
    assert codes(authors(sentence, role, issuer)) & {"issuer_mismatch", "issuer_not_in_evidence"}


# Review of PR 46 (Codex, P2, round 8, finding 1): the document author's OWN analysts ("analysts at the Treasury") are the author speaking.
@pytest.mark.parametrize(
    "sentence",
    [
        "Growth of 3% in 2029 is forecast by analysts at the Treasury.",
        "According to analysts at the Treasury, growth will be 3% in 2029.",
        "Growth of 3% in 2029 is expected by forecasters at the Treasury.",
        "Growth of 3% in 2029 is projected by forecasters from Treasury.",
    ],
)
def test_the_authors_own_analysts_named_with_its_organisation_are_the_author(sentence):
    assert "issuer_mismatch" not in codes(authors(sentence))


@pytest.mark.parametrize(
    ("sentence", "role", "issuer"),
    [
        # Another organisation's analysts, for an author label.
        ("Growth of 3% in 2029 is forecast by analysts at ANZ.", "author", "The Treasury"),
        (
            "Growth of 3% in 2029 is forecast by analysts at ANZ and the Treasury.",
            "author",
            "The Treasury",
        ),
        # The author's analysts do not answer a THIRD PARTY's label.
        (
            "Growth of 3% in 2029 is forecast by analysts at the Treasury, while ANZ was silent.",
            "third_party",
            "ANZ",
        ),
    ],
)
def test_only_the_authors_own_organisation_is_the_author(sentence, role, issuer):
    assert "issuer_mismatch" in codes(authors(sentence, role, issuer))


# Round 8, finding 2: an earlier reporter's separate figure does not reach the claimed group's own forecast.
@pytest.mark.parametrize(
    ("sentence", "issuer"),
    [
        (
            "The IMF said growth would be 2% in 2029, but analysts expect growth of 3% in 2029.",
            "Analysts",
        ),
        (
            "The OECD says growth will be 2% in 2029; most analysts now expect growth of 3% in 2029.",
            "Most analysts",
        ),
        (
            "The IMF said growth would be 2% in 2029, but growth of 3% in 2029 is forecast by analysts.",
            "Analysts",
        ),
    ],
)
def test_an_earlier_reporters_figure_does_not_reach_the_claimed_groups_own_forecast(
    sentence, issuer
):
    report = authors(sentence, "third_party", issuer)
    assert not codes(report) & {"issuer_mismatch", "issuer_not_in_evidence"}


@pytest.mark.parametrize(
    ("sentence", "issuer"),
    [
        # The reporter gives the claimed figure, so the group label is wrong.
        (
            "Analysts expect growth of 2% in 2028, while the IMF said growth would be 3% in 2029.",
            "Analysts",
        ),
        ("The IMF said growth would be 3% in 2029, and analysts expect 2%.", "Analysts"),
        ("The IMF said growth would be 3% in 2029.", "Analysts"),
        # The group's credit belongs to another figure, not the claimed one.
        (
            "The IMF said growth would be 2% in 2028, but growth of 3% in 2029 is ours, and analysts expect 4%.",
            "Analysts",
        ),
        # A group credit that is only a comparison does not reset anything.
        ("The IMF said growth would be 3% in 2029, higher than analysts expect.", "Analysts"),
        ("The IMF said growth would be 3% in 2029, higher than forecast by analysts.", "Analysts"),
    ],
)
def test_a_reporter_who_gives_the_claimed_figure_still_blocks_a_group_label(sentence, issuer):
    assert codes(authors(sentence, "third_party", issuer)) & {
        "issuer_mismatch",
        "issuer_not_in_evidence",
    }
