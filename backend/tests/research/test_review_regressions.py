"""Regressions for the Phase 4I independent review."""

from datetime import date

from nzstats.research.contract import PolicyDecision, ReportedFact, SectionText
from nzstats.research.evaluate import GoldClaim, extraction_counts

from .test_evaluate import fc, own
from .verify_support import check, codes, forecast, ref


def test_two_column_table_rejects_wrong_year():
    text = "GDP forecasts (percent)\n2026 2027\nGDP growth 1.0% 2.0%"
    section = {0: SectionText(text, heading="GDP forecasts")}
    claim = forecast(0, "GDP growth 1.0% 2.0%", horizon="2027", value=1.0, unit="percent")
    report = check(section, outlook_ref=ref(0, "GDP forecasts"), forecasts=[claim])
    assert "table_column_mismatch" in codes(report)


def test_later_two_column_table_row_rejects_wrong_year():
    text = "GDP forecasts (percent)\n2026 2027\nGDP growth 1.0% 2.0%\nInflation 3.0% 4.0%"
    section = {0: SectionText(text, heading="Inflation forecasts")}
    claim = forecast(0, "Inflation 3.0% 4.0%", indicator="cpi_inflation", indicator_label="Inflation",
                     horizon="2027", value=3.0, unit="percent")  # fmt: skip
    report = check(section, outlook_ref=ref(0, "GDP forecasts"), forecasts=[claim])
    assert "table_column_mismatch" in codes(report)


def test_explicit_quarterly_change_is_not_erased_by_quarter_period():
    text = "Annual CPI inflation is projected at 4.4 percent in the December quarter."
    section = {0: SectionText(text)}
    claim = forecast(0, text, indicator="cpi_inflation", indicator_label="CPI inflation",
                     horizon="quarterly change in December quarter", value=4.4, unit="percent",
                     issuer="RBNZ")  # fmt: skip
    report = check(section, outlook_ref=ref(0, text), forecasts=[claim], institution="rbnz")
    assert "period_basis_mismatch" in codes(report)


def test_expected_inflation_is_not_a_survey_outturn():
    text = "Respondents expect inflation to be 3% in 2027."
    fact = ReportedFact(text="Inflation will be 3% in 2027", source="Survey", value=3,
                        unit="percent", period="2027", evidence=[ref(0, text)])  # fmt: skip
    report = check({0: SectionText(text)}, outlook_ref=ref(0, text), facts=[fact])
    assert "forecast_as_fact" in codes(report)


def test_survey_share_does_not_excuse_identical_forecast_value():
    text = "40% of respondents expect inflation to reach 40% in 2027."
    fact = ReportedFact(text="Inflation will be 40% in 2027", source="Survey", value=40,
                        unit="percent", period="2027", evidence=[ref(0, text)])  # fmt: skip
    report = check({0: SectionText(text)}, outlook_ref=ref(0, text), facts=[fact])
    assert "forecast_as_fact" in codes(report)


def test_spaced_fiscal_year_is_not_calendar_year():
    text = "We forecast GDP growth of 2.0% in 2026 - 27."
    claim = forecast(0, text, horizon="2026", value=2, unit="percent")
    report = check({0: SectionText(text)}, outlook_ref=ref(0, text), forecasts=[claim])
    assert "fiscal_calendar_mismatch" in codes(report)


def test_chart_axis_after_a_year_does_not_change_quarterly_basis():
    text = (
        "Source: October 2026\n-10\n-5\n0\nGDP is projected to grow 0.8% in the December quarter."
    )
    claim = forecast(0, "GDP is projected to grow 0.8% in the December quarter",
                     horizon="December quarter", value=0.8, unit="percent",
                     indicator_label="Quarterly GDP growth")  # fmt: skip
    report = check(
        {0: SectionText(text)}, outlook_ref=ref(0, "GDP is projected"), forecasts=[claim]
    )
    assert "period_basis_mismatch" not in codes(report)


def test_same_line_axis_values_do_not_form_a_fiscal_year():
    text = "GDP is projected to grow 0.8% in 2026 -10 -5 0."
    claim = forecast(0, text, horizon="2026", value=0.8, unit="percent")
    report = check({0: SectionText(text)}, outlook_ref=ref(0, text), forecasts=[claim])
    assert "fiscal_calendar_mismatch" not in codes(report)


def test_decision_date_must_match_explicit_year():
    text = "On 28 October 2026 the committee voted 4–3 to hold the OCR at 2.75 percent."
    decision = PolicyDecision(action="hold", rate=2.75, decided_on="2025-10-28", vote_for=4,
                              vote_against=3, decision_maker="RBNZ", evidence=[ref(0, text)])  # fmt: skip
    report = check({0: SectionText(text)}, outlook_ref=ref(0, text), decisions=[decision],
                   institution="rbnz")  # fmt: skip
    assert "decision_date_not_supported" in codes(report)


def test_publication_date_does_not_override_explicit_decision_year():
    text = "On 2026-10-28 the committee voted 4–3 to hold the OCR at 2.75 percent."
    decision = PolicyDecision(action="hold", rate=2.75, decided_on="2025-10-28", vote_for=4,
                              vote_against=3, decision_maker="RBNZ", evidence=[ref(0, text)])  # fmt: skip
    report = check({0: SectionText(text)}, outlook_ref=ref(0, text), decisions=[decision],
                   institution="rbnz", published_on=date(2025, 10, 28))  # fmt: skip
    assert "decision_date_not_supported" in codes(report)


def test_publication_date_does_not_override_explicit_different_day():
    text = "On 29 October 2026 the committee voted 4–3 to hold the OCR at 2.75 percent."
    decision = PolicyDecision(action="hold", rate=2.75, decided_on="2026-10-28", vote_for=4,
                              vote_against=3, decision_maker="RBNZ", evidence=[ref(0, text)])  # fmt: skip
    report = check({0: SectionText(text)}, outlook_ref=ref(0, text), decisions=[decision],
                   institution="rbnz", published_on=date(2026, 10, 28))  # fmt: skip
    assert "decision_date_not_supported" in codes(report)


def test_author_forecast_mislabelled_as_third_party_is_scored():
    gold = [GoldClaim("gdp", "2027", 1.8, "percent", None, "author")]
    counts = extraction_counts([own(fc("gdp", "2027", 1.8), "third_party")], gold)
    assert (counts["predicted"], counts["issuer_scored"], counts["issuer_correct"]) == (1, 1, 0)
