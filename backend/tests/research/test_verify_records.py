"""Contract v2 records (Phase 4I): policy decisions, reported facts and their definitions, guidance, assumptions."""

from datetime import date

import pytest

from nzstats.research.contract import (
    Assumption,
    Guidance,
    PolicyDecision,
    ReportedFact,
    SectionText,
)

from .verify_support import check, codes, forecast, ref, warning_codes

RELEASE = SectionText(
    "SYNTHETIC FIXTURE. OCR held at 2.75 percent\nThe Monetary Policy Committee today voted 4–3 to hold"
    " the Official Cash Rate at 2.75 percent. The Committee agreed to hold the OCR at 2.75 percent and"
    " expects it to remain there until mid-2027.",
    None, None, "News release",
)  # fmt: skip
RECORD = SectionText(
    "SYNTHETIC FIXTURE. Members discussed the outlook. Four members preferred to hold the OCR, while"
    " three members preferred a 25 basis point cut. The Committee expects to lower the OCR further if"
    " inflation eases as projected. On 21 October 2026 the Committee agreed to hold the OCR at 3.0"
    " percent.",
)  # fmt: skip
PROJECTIONS = SectionText(
    "SYNTHETIC FIXTURE. The Committee agreed to hold the OCR at 2.75 percent.",
    None, None, "Monetary Policy Statement projections",
)  # fmt: skip
FACTS = SectionText(
    "SYNTHETIC FIXTURE. Stats NZ data show unemployment was 5.1% in the June 2026 quarter (seasonally"
    " adjusted). Annual CPI inflation was 3.7% in the September 2026 quarter. Net migration was 3,190 in July 2026 and 1,530 in"
    " August 2026. Unemployment is forecast to rise to 5.4% in 2027. In the downside scenario, export"
    " prices fall 10% in 2027.",
    1, 1,
)  # fmt: skip
SECTIONS = {0: RELEASE, 1: FACTS, 2: RECORD, 3: PROJECTIONS}
OUTLOOK = ref(2, "Members discussed the outlook")
VOTE = "today voted 4–3 to hold the Official Cash Rate at 2.75 percent"


def run(published_on=date(2026, 10, 28), institution="rbnz", **items):
    return check(SECTIONS, outlook_ref=OUTLOOK, published_on=published_on,
                 institution=institution, **items)  # fmt: skip


def decision(quote: str = VOTE, ordinal: int = 0, **kw) -> PolicyDecision:
    base = dict(action="hold", rate=2.75, decided_on="2026-10-28", vote_for=4, vote_against=3,
                decision_maker="Monetary Policy Committee", evidence=[ref(ordinal, quote)])  # fmt: skip
    base.update(kw)
    return PolicyDecision(**base)


# --- monetary policy decisions ----------------------------------------------------------------------
def test_a_faithful_decision_with_rate_date_and_vote_passes():
    assert codes(run(decisions=[decision()])) == set()


def test_a_vote_stated_as_member_counts_supports_the_decision():
    d = decision(evidence=[ref(0, VOTE), ref(2, "Four members preferred to hold the OCR")])
    assert codes(run(decisions=[d])) == set()


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"vote_for": 5, "vote_against": 2}, "vote_not_in_evidence"),
        ({"vote_for": None, "vote_against": None}, "vote_not_captured"),
        ({"action": "decrease"}, "decision_action_contradiction"),
        ({"rate": 2.5}, "value_not_in_evidence"),
        ({"decided_on": "2026-10-21"}, "decision_date_not_supported"),
    ],
)
def test_a_decision_must_match_its_evidence(change, code):
    assert code in codes(run(decisions=[decision(**change)]))


def test_a_decision_date_stated_in_the_evidence_is_accepted():
    d = decision("On 21 October 2026 the Committee agreed to hold the OCR at 3.0 percent", 2,
                 rate=3.0, decided_on="2026-10-21", vote_for=None, vote_against=None)  # fmt: skip
    assert codes(run(decisions=[d])) == set()


@pytest.mark.parametrize(
    ("sentence", "action", "expected"),
    [
        ("The Committee agreed to hold the OCR at 2.75 percent today.", "hold", None),
        (
            "The Committee agreed to hold the OCR at 2.75 percent today.",
            "increase",
            "decision_action_contradiction",
        ),
        ("The Committee agreed to raise the OCR at 2.75 percent today.", "increase", None),
        ("The Committee agreed to reduce the OCR at 2.75 percent today.", "decrease", None),
        (
            "The Committee agreed not to raise the OCR at 2.75 percent today.",
            "increase",
            "decision_action_not_supported",
        ),
        (
            "The Committee agreed to not raise the OCR at 2.75 percent today.",
            "increase",
            "decision_action_not_supported",
        ),
        (
            "The Committee decided the OCR at 2.75 percent today.",
            "hold",
            "decision_action_not_supported",
        ),
    ],
)
def test_short_decision_quote_requires_supported_action(sentence, action, expected):
    sections = {0: SectionText(sentence)}
    quote = "OCR at 2.75 percent"
    d = decision(quote, action=action, vote_for=None, vote_against=None)
    errors = codes(
        check(
            sections,
            outlook_ref=ref(0, quote),
            published_on=date(2026, 10, 28),
            institution="rbnz",
            decisions=[d],
        )
    )
    assert (expected in errors) if expected else not errors


def test_forward_guidance_is_not_a_decision():
    d = decision("The Committee expects to lower the OCR further if inflation eases", 2,
                 vote_for=None, vote_against=None)  # fmt: skip
    assert "decision_not_in_evidence" in codes(run(decisions=[d]))


@pytest.mark.parametrize(
    ("ordinal", "quote", "horizon"),
    [
        (3, "The Committee agreed to hold the OCR at 2.75 percent", "2027"),  # forward heading only
        (0, "The Committee agreed to hold the OCR at 2.75 percent and expects it to remain there until"
            " mid-2027", "mid-2027"),
    ],
)  # fmt: skip
def test_a_policy_decision_reported_as_a_forecast_is_an_error(ordinal, quote, horizon):
    claim = forecast(ordinal, quote, indicator="ocr", indicator_label="OCR", horizon=horizon,
                     value=2.75, unit="percent", issuer="Reserve Bank", issuer_role="author")  # fmt: skip
    assert "decision_as_forecast" in codes(run(forecasts=[claim]))


def test_a_forecast_of_a_future_cut_is_not_a_decision():
    sections = {0: SectionText("SYNTHETIC FIXTURE. We expect the RBNZ to have cut the OCR to 2.25% by"
                               " February 2027.", 1, 1)}  # fmt: skip
    claim = forecast(0, "We expect the RBNZ to have cut the OCR to 2.25% by February 2027", 1,
                     indicator="ocr", indicator_label="OCR", horizon="February 2027", value=2.25,
                     unit="percent", direction="down", issuer="ANZ", issuer_role="author")  # fmt: skip
    report = check(sections, outlook_ref=ref(0, "We expect the RBNZ"), institution="anz",
                   forecasts=[claim])  # fmt: skip
    assert codes(report) == set()


# --- reported facts and statistical definitions -----------------------------------------------------
def fact(quote: str, **kw) -> ReportedFact:
    base = dict(text="Unemployment was 5.1%.", source="Stats NZ", value=5.1, unit="percent",
                period="June 2026 quarter", definition={"adjustment": "seasonally_adjusted"},
                evidence=[ref(1, quote, 1)])  # fmt: skip
    base.update(kw)
    return ReportedFact(**base)


SA = "unemployment was 5.1% in the June 2026 quarter (seasonally adjusted)"
CPI = "Annual CPI inflation was 3.7% in the September 2026 quarter"
MIGRATION = "Net migration was 3,190 in July 2026"


def test_a_fact_with_its_stated_definition_passes():
    report = run(
        facts=[fact(SA, definition={"measure": "rate", "adjustment": "seasonally_adjusted"})]
    )
    assert codes(report) == set() and warning_codes(report) == set()


@pytest.mark.parametrize(
    ("quote", "change"),
    [
        (CPI, {"value": 3.7, "period": "September 2026 quarter", "definition": {"adjustment": "seasonally_adjusted"}}),
        (MIGRATION, {"value": 3190, "unit": "persons", "period": "July 2026", "definition": {"adjustment": "seasonally_adjusted"}}),
        (CPI, {"value": 3.7, "period": "September 2026 quarter", "definition": {"measure": "annual average % change"}}),
    ],
)  # fmt: skip
def test_a_definition_the_evidence_does_not_state_is_an_error(quote, change):
    assert "definition_not_in_evidence" in codes(run(facts=[fact(quote, **change)]))


def test_an_unstated_adjustment_basis_is_reported_explicitly():
    monthly = fact(MIGRATION, text="Net migration was 3,190.", value=3190, unit="persons",
                   period="July 2026", definition={"adjustment": "not_stated"})  # fmt: skip
    report = run(facts=[monthly])
    assert codes(report) == set()
    (warning,) = [p for p in report.warnings if p.code == "definition_not_stated"]
    assert "adjustment" in warning.message and "official series" in warning.message


def test_a_forecast_reported_as_a_fact_is_an_error():
    f = fact("Unemployment is forecast to rise to 5.4% in 2027", value=5.4, period="2027",
             text="Unemployment is 5.4%.", definition={})  # fmt: skip
    assert "forecast_as_fact" in codes(run(facts=[f]))


def test_a_fact_period_must_be_stated_near_the_quote():
    assert "period_not_supported" in codes(run(facts=[fact(SA, period="March 2026 quarter")]))


def test_a_fact_value_needs_a_unit_that_the_evidence_states():
    assert "missing_unit" in codes(run(facts=[fact(SA, unit=None)]))
    assert "unit_mismatch" in codes(run(facts=[fact(SA, unit="percentage_points")]))


# --- guidance and assumptions -----------------------------------------------------------------------
def test_forward_guidance_must_be_forward_looking():
    good = Guidance(text="Further cuts are possible.", issuer="Monetary Policy Committee",
                    evidence=[ref(2, "The Committee expects to lower the OCR further")])  # fmt: skip
    assert codes(run(guidance=[good])) == set()
    past = Guidance(text="Members split.", issuer="Monetary Policy Committee",
                    evidence=[ref(2, "Four members preferred to hold the OCR")])  # fmt: skip
    assert "guidance_not_forward" in codes(run(guidance=[past]))


def test_an_assumption_names_only_a_scenario_the_document_names():
    good = Assumption(text="Export prices fall 10%.", scenario="downside",
                      evidence=[ref(1, "In the downside scenario, export prices fall 10% in 2027", 1)])  # fmt: skip
    assert codes(run(assumptions=[good])) == set()
    invented = good.model_copy(update={"scenario": "trade war"})
    assert "scenario_not_in_text" in codes(run(assumptions=[invented]))


def test_an_annual_rate_at_a_named_quarter_is_not_a_quarterly_change():
    """RBNZ, Phase 4H: "annual CPI inflation ... in the December quarter" is an annual rate for that quarter."""
    sections = {0: SectionText("SYNTHETIC FIXTURE. Annual CPI inflation is projected to peak at 4.4 percent"
                               " in the December quarter, before easing.", None, None, "Inflation outlook")}  # fmt: skip
    claim = forecast(0, "Annual CPI inflation is projected to peak at 4.4 percent in the December quarter",
                     indicator="cpi_inflation", indicator_label="Annual CPI inflation", horizon="December quarter",
                     value=4.4, unit="percent", direction="up", issuer="Reserve Bank", issuer_role="author")  # fmt: skip
    report = check(sections, outlook_ref=ref(0, "Annual CPI inflation is projected"), forecasts=[claim],
                   institution="rbnz")  # fmt: skip
    assert codes(report) == set()
    quarterly = claim.model_copy(update={"indicator_label": "Quarterly CPI inflation"})
    assert "period_basis_mismatch" in codes(check(sections, outlook_ref=ref(0, "Annual CPI inflation"),
                                                  forecasts=[quarterly], institution="rbnz"))  # fmt: skip
    inferred = claim.model_copy(
        update={"horizon": "December quarter 2026"}
    )  # the year is not stated
    assert "horizon_not_supported" in codes(check(sections, outlook_ref=ref(0, "Annual CPI inflation"),
                                                  forecasts=[inferred], institution="rbnz"))  # fmt: skip


def test_a_survey_of_expectations_is_a_reported_fact_but_an_estimate_is_not():
    """Treasury, Phase 4H: "a net 40% of respondents expected conditions to improve" is a survey outturn."""
    sections = {0: SectionText("SYNTHETIC FIXTURE. In the September quarter, a net 40% of respondents expected"
                               " general business conditions to improve. Core inflation is estimated to be 3.1"
                               " percent.", 1, 1)}  # fmt: skip
    survey = ReportedFact(text="A net 40% expected improvement.", source="Example survey", value=40,
                          unit="percent", period="September quarter",
                          evidence=[ref(0, "a net 40% of respondents expected general business conditions to improve", 1)])  # fmt: skip
    outlook = ref(0, "In the September quarter")
    assert "forecast_as_fact" not in codes(check(sections, outlook_ref=outlook, facts=[survey]))
    estimate = ReportedFact(text="Core inflation is 3.1%.", source="Example", value=3.1, unit="percent",
                            evidence=[ref(0, "Core inflation is estimated to be 3.1 percent", 1)])  # fmt: skip
    assert "forecast_as_fact" in codes(check(sections, outlook_ref=outlook, facts=[estimate]))
