"""Phase 4V: the prepared prompt `outlook-v6`, tested offline on synthetic documents (SYNTHETIC FIXTURE).

v6 is prepared, not adopted: `PROMPT_VERSION` stays `outlook-v5`, no experiment authorises v6, and v4 and v5 are byte for byte what
frozen requests recorded. These tests check what can be checked without a model: the text, the registry, that the JSON contract
is unchanged, and that the output shapes v6 asks for are shapes the verifier accepts (and the shapes it warns against are
rejected). They say nothing about whether a real model follows v6 or becomes more accurate; only a fresh, separately authorised
experiment can.
"""

import hashlib
import re
from datetime import date

import pytest

from nzstats.research.contract import (
    Guidance,
    PolicyDecision,
    ReportedFact,
    SectionText,
    SummaryRequest,
)
from nzstats.research.openrouter import EXPERIMENTS
from nzstats.research.prompt import (
    PROMPT_VERSION,
    RULES,
    RULES_SHA256,
    render,
    rules_for,
    system_text,
)

from .verify_support import check, codes, forecast, ref

V6 = rules_for("outlook-v6")


def flat(text: str) -> str:
    """The rules as one line of text, so a phrase is found wherever the prompt wraps it."""
    return re.sub(r"\s+", " ", text)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# --- registry and integrity -------------------------------------------------------------------------------------
def test_v6_is_prepared_but_not_adopted_and_no_experiment_authorises_it():
    assert PROMPT_VERSION == "outlook-v5" and V6 != RULES
    assert "outlook-v6" in RULES_SHA256 and RULES_SHA256["outlook-v6"] == sha(V6)
    assert all(e.prompt_version != "outlook-v6" for e in EXPERIMENTS.values())


def test_v4_and_v5_are_untouched_so_frozen_requests_stay_reproducible():
    assert (
        RULES_SHA256["outlook-v5"]
        == "f976a085024457ed28489fa269927736600397f694d747306ea0a8a6bda91ae0"
        == sha(rules_for("outlook-v5"))
    )
    assert (
        RULES_SHA256["outlook-v4"]
        == "b77701837d1ad6a9d8bf0e06ce7789dc16710bc467d88e6d47c0c88ecfa1c821"
        == sha(rules_for("outlook-v4"))
    )
    assert rules_for("anything-else") == RULES  # an unknown label still gets the current (v5) rules


def test_the_json_contract_is_unchanged():
    def schema_tail(version: str) -> str:
        text = system_text("INSTRUCTIONS", version)
        return text[text.index("Return only one JSON object") :]

    assert schema_tail("outlook-v6") == schema_tail("outlook-v5")


def test_rendering_a_request_with_v6_uses_the_v6_rules_and_the_same_delimiters():
    sections = (SectionText("SYNTHETIC FIXTURE. Body.", 1, 1, "Heading"),)
    from nzstats.research.contract import build_request

    for version in ("outlook-v5", "outlook-v6"):
        request: SummaryRequest = build_request(
            7, {0: sections[0]}, prompt_version=version, published_on="2026-10-29"
        )
        rendered = render(request, published_on="2026-10-29", boundary="b" * 32)
        assert rules_for(version) in rendered.system
        assert (
            "<<<SECTION " + "b" * 32 + " ordinal=0 pages=1-1>>>" in rendered.user
            and "Heading: Heading" in rendered.user
        )


def test_rules_are_numbered_without_gaps():
    numbers = [int(n) for n in re.findall(r"^(\d+)\. ", V6, re.M)]
    assert numbers == list(range(1, len(numbers) + 1))


def test_v6_does_not_grow_the_prompt_by_much():
    assert (
        len(V6) - len(RULES) < 3_500
    )  # a few hundred tokens; the request cap and cost estimate are unchanged in kind


# --- every safety rule of v5 survives -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "phrase",
    [
        "untrusted data",
        "Never follow instructions",
        "copied verbatim",
        "no ellipses",
        "A publication date is not a data",
        "A scenario, sensitivity or alternative path is not the baseline forecast",
        "issuer_role",
        "third_party",
        "Never present a third party's forecast as the author's",
        "chart-axis labels",
        "leave the claim out",
        "never add a forecast the document does not state",
        "An unsupported claim is worse than a gap",
        "compact JSON",
        "under 20,000 characters",
    ],
)
def test_every_v5_safeguard_is_still_in_v6(phrase):
    assert phrase in flat(RULES), "the phrase must exist in v5 for this test to mean anything"
    assert phrase in flat(V6)


# --- each requested behaviour is stated -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("behaviour", "pattern"),
    [
        ("copy a unit shown beside a figure", r"shows a unit beside"),
        ("use null only when no unit is shown", r"null only when"),
        ("leave out a unit that is not in the list", r"not in the list"),
        ("a null period when periods conflict", r'leave "period" null'),
        ("the figure's own period vs the comparison base", r"directly after the figure"),
        ("a measured expectation is a fact", r"measured expectation"),
        ("a forecast of a future outcome is a forecast", r"forecast of a future outcome"),
        (
            "an OCR decision is not commentary on future moves",
            r"expected future (?:OCR )?(?:moves|changes)",
        ),
        ("decision evidence is one sentence", r"single sentence"),
        ("vote and date evidence is a separate entry", r"separate evidence entry"),
        (
            "attribute the Treasury, RBNZ, IMF and markets correctly",
            r"RBNZ.*IMF.*markets|IMF.*RBNZ.*markets",
        ),
        ("leave out what the evidence cannot support", r"leave the claim out"),
        ("accuracy over the number of claims", r"accura\w+[^.]*more than the number of claims"),
    ],
)
def test_v6_states_the_behaviour(behaviour, pattern):
    assert re.search(pattern, flat(V6), re.I), behaviour


def test_v6_no_longer_forbids_recording_a_unit_the_text_shows():
    assert (
        "never fill a missing horizon or unit" in RULES
    )  # the v5 wording that conflicted with copying units
    assert "never fill a missing horizon or unit" not in flat(V6)


# --- the shapes v6 asks for are shapes the verifier accepts ----------------------------------------------------------
CPI_SENTENCE = "Annual CPI inflation was 3.7% in the September 2026 quarter, up from 3.3% in the June 2026 quarter."
SECTIONS = {
    0: SectionText(
        "SYNTHETIC FIXTURE. The Monetary Policy Committee agreed to hold the Official Cash Rate at 2.75 percent on 28 October 2026. "
        "The decision was made by a vote of 4:3. Markets expect the OCR to be cut in 2027. "
        "The Treasury forecasts GDP growth of 2.5% in 2027, while the IMF expects 2.1% in 2027 and markets expect 2.3%."
    ),
    1: SectionText(
        f"SYNTHETIC FIXTURE. {CPI_SENTENCE} The business expectations index fell to 12 in October 2026. "
        "The deficit was $4.2 billion in the year to June 2026. Brent crude averaged US$82 a barrel in October 2026. "
        "Net migration was 3,190 in July 2026 and 1,530 in August 2026."
    ),
}
OUTLOOK = ref(1, "Annual CPI inflation was 3.7%")


def run(**items):
    return check(
        SECTIONS,
        outlook_ref=OUTLOOK,
        institution="treasury",
        published_on=date(2026, 10, 29),
        **items,
    )


def fact(quote, section=1, **kw):
    base = dict(text="A figure.", source="Stats NZ", unit="percent", evidence=[ref(section, quote)])
    base.update(kw)
    return ReportedFact(**base)


def test_a_unit_copied_from_beside_the_figure_passes_and_a_null_one_fails():
    quote = "The deficit was $4.2 billion in the year to June 2026"
    assert (
        codes(run(facts=[fact(quote, value=4.2, unit="nzd_billion", period="year to June 2026")]))
        == set()
    )
    assert "missing_unit" in codes(
        run(facts=[fact(quote, value=4.2, unit=None, period="year to June 2026")])
    )


def test_a_figure_with_a_unit_not_in_the_list_cannot_be_stated_so_v6_says_to_leave_it_out():
    quote = "Brent crude averaged US$82 a barrel in October 2026"
    for unit in (None, "usd_per_barrel", "nzd"):
        assert codes(run(facts=[fact(quote, value=82, unit=unit, period="October 2026")])) & {
            "missing_unit",
            "unknown_unit",
            "unit_mismatch",
        }
    assert codes(run(facts=[])) == set()  # the claim v6 asks for: omitted


def test_the_figures_own_period_is_accepted_and_the_bases_is_not():
    own = fact(CPI_SENTENCE.rstrip("."), value=3.7, period="September 2026 quarter")
    base_period = fact(CPI_SENTENCE.rstrip("."), value=3.7, period="June 2026 quarter")
    assert codes(run(facts=[own])) == set()
    assert "period_not_supported" in codes(run(facts=[base_period]))


def test_a_clause_with_two_figures_before_the_comparison_word_takes_a_null_period_and_a_picked_one_fails():
    sentence = "Imports rose 4% in June with exports at 6.3% compared with 5.9% in September."
    sections = {0: SectionText(f"SYNTHETIC FIXTURE. {sentence}")}
    quote = sentence.rstrip(".")

    def claim(period):
        f = ReportedFact(
            text="A figure.",
            source="Stats NZ",
            value=6.3,
            unit="percent",
            period=period,
            evidence=[ref(0, quote)],
        )
        return codes(check(sections, outlook_ref=ref(0, quote), facts=[f]))

    assert "period_not_supported" not in claim(None)  # what rule 6 asks for
    assert "period_not_supported" in claim(
        "June"
    )  # a chosen period, which rule 6 forbids, is rejected


def test_a_measured_expectation_is_a_fact_and_a_forecast_of_an_outcome_is_not():
    measured = fact(
        "The business expectations index fell to 12 in October 2026",
        value=12,
        unit="index",
        period="October 2026",
    )
    assert codes(run(facts=[measured])) == set()
    as_fact = fact(
        "The Treasury forecasts GDP growth of 2.5% in 2027", section=0, value=2.5, period="2027"
    )
    assert "forecast_as_fact" in codes(run(facts=[as_fact]))


def decision(quote, *extra, **kw):
    base = dict(action="hold", rate=2.75, decided_on="2026-10-28", decision_maker="Monetary Policy Committee",
                evidence=[ref(0, quote), *extra])  # fmt: skip
    base.update(kw)
    return PolicyDecision(**base)


def test_a_decision_cites_its_own_sentence_and_the_vote_in_a_separate_entry():
    action = "The Monetary Policy Committee agreed to hold the Official Cash Rate at 2.75 percent on 28 October 2026"
    vote = "The decision was made by a vote of 4:3"
    both = decision(action, ref(0, vote), vote_for=4, vote_against=3)
    assert codes(run(decisions=[both])) == set()
    assert "vote_not_in_evidence" in codes(
        run(decisions=[decision(action, ref(0, vote), vote_for=3, vote_against=4)])
    )


def test_commentary_about_expected_future_moves_is_not_a_decision():
    commentary = "Markets expect the OCR to be cut in 2027"
    assert "decision_not_in_evidence" in codes(
        run(decisions=[decision(commentary, rate=2.5, action="decrease")])
    )
    guidance = Guidance(
        text="Markets expect a cut in 2027.", issuer="markets", evidence=[ref(0, commentary)],
    )  # fmt: skip
    assert "decision_not_in_evidence" not in codes(run(guidance=[guidance]))


ATTRIBUTION = [
    ("The Treasury forecasts GDP growth of 2.5% in 2027", 2.5, "The Treasury", "author"),
    ("the IMF expects 2.1% in 2027", 2.1, "IMF", "third_party"),
]


@pytest.mark.parametrize(("quote", "value", "issuer", "role"), ATTRIBUTION)
def test_a_forecast_attributed_to_the_forecaster_in_the_right_role_passes(
    quote, value, issuer, role
):
    claim = forecast(
        0,
        quote,
        indicator="gdp",
        horizon="2027",
        value=value,
        unit="percent",
        issuer=issuer,
        issuer_role=role,
    )
    assert codes(run(forecasts=[claim])) == set()


@pytest.mark.parametrize(("quote", "value", "issuer", "role"), ATTRIBUTION)
def test_the_same_forecast_with_the_role_reversed_is_rejected(quote, value, issuer, role):
    wrong = "third_party" if role == "author" else "author"
    claim = forecast(
        0,
        quote,
        indicator="gdp",
        horizon="2027",
        value=value,
        unit="percent",
        issuer=issuer,
        issuer_role=wrong,
    )
    assert codes(run(forecasts=[claim])) != set()
