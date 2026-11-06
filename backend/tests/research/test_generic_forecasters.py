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
