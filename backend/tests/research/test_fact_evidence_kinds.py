"""Evidence identity takes precedence over the age of a table's reference period."""

from datetime import date

import pytest

from nzstats.research.contract import ReportedFact, SectionText

from .verify_support import check, codes, forecast, ref


def table_report(
    caption,
    *,
    row="GDP growth",
    years="2024 2025",
    value=2.2,
    period="2025",
    heading=None,
    labels="",
    following="",
    published=date(2026, 10, 15),
):
    quote = f"{row} 1.1 2.2"
    text = f"Table 1: {caption}\n{years}\n{labels}\n{quote}\n{following}"
    item = ReportedFact(
        text=f"GDP growth was {value}%.",
        source="Stats NZ",
        value=value,
        unit="percent",
        period=period,
        evidence=[ref(0, quote)],
    )
    return check(
        {0: SectionText(text, heading=heading)},
        outlook_ref=ref(0, quote),
        facts=[item],
        published_on=published,
    )


@pytest.mark.parametrize(
    "caption",
    [
        "Previous GDP forecasts (percent)",
        "Historical GDP projections (percent)",
        "Revisions to previous GDP forecasts (percent)",
        "GDP assumptions (percent)",
        "GDP scenario (percent)",
    ],
)
@pytest.mark.parametrize("published", [date(2026, 10, 15), None])
def test_explicit_non_actual_table_evidence_is_never_a_reported_fact(caption, published):
    assert "forecast_as_fact" in codes(table_report(caption, published=published))


@pytest.mark.parametrize(
    ("row", "rejected"),
    [
        ("Previous GDP forecast", True),
        ("Revised GDP projection", True),
        ("GDP actual outturn", False),
        ("Revised GDP actual", False),
        ("GDP growth", True),
    ],
)
def test_row_identity_scopes_mixed_actual_and_forecast_tables(row, rejected):
    report = table_report("GDP actuals and forecasts (percent)", row=row)
    assert ("forecast_as_fact" in codes(report)) == rejected
    if not rejected:
        assert codes(report) == set()


@pytest.mark.parametrize(
    ("years", "value", "period", "rejected"),
    [
        ("2024a 2025f", 2.2, "2025", True),
        ("2024f 2025a", 2.2, "2025", False),
        ("2024a 2025p", 2.2, "2025", False),
    ],
)
def test_year_column_markers_identify_actual_forecast_and_provisional(
    years, value, period, rejected
):
    report = table_report(
        "GDP actuals and forecasts (percent)", years=years, value=value, period=period
    )
    assert ("forecast_as_fact" in codes(report)) == rejected
    if not rejected:
        assert codes(report) == set()


@pytest.mark.parametrize(
    ("labels", "rejected"), [("Actual Forecast", True), ("Forecast Actual", False)]
)
def test_aligned_column_labels_identify_the_selected_cell(labels, rejected):
    report = table_report("GDP actuals and forecasts (percent)", labels=labels)
    assert ("forecast_as_fact" in codes(report)) == rejected
    if not rejected:
        assert codes(report) == set()


def test_actual_outturn_does_not_inherit_the_sections_forecast_heading():
    assert (
        codes(table_report("Historical GDP actual outturns (percent)", heading="GDP forecasts"))
        == set()
    )


def test_following_table_does_not_reclassify_an_actual_cell():
    report = table_report(
        "GDP actual outturns (percent)",
        years="2025 2026",
        period="June 2026 year",
        following="Table 2: GDP forecasts (percent)",
        heading="June year results",
    )
    assert codes(report) == set()


@pytest.mark.parametrize(
    ("period", "caption", "rejected"),
    [
        ("2025/26", "June year actual GDP outturns (percent)", False),
        ("June 2026 year", "June year actual GDP outturns (percent)", False),
        ("2025/26", "Previous GDP forecasts (percent)", True),
    ],
)
def test_completed_fiscal_pairs_keep_their_period_and_evidence_identity(period, caption, rejected):
    report = table_report(caption, years="2024/25 2025/26", period=period)
    assert ("forecast_as_fact" in codes(report)) == rejected
    assert "table_column_mismatch" not in codes(report)


def test_current_fiscal_year_without_a_stated_end_month_remains_ambiguous():
    report = table_report(
        "Fiscal GDP actual outturns (percent)", years="2024/25 2025/26", period="2025/26"
    )
    assert "forecast_as_fact" in codes(report)


@pytest.mark.parametrize(
    ("caption", "period"),
    [
        ("June year historical GDP outturns (percent)", "calendar year 2025"),
        ("Calendar year historical GDP outturns (percent)", "June 2025 year"),
    ],
)
def test_table_fact_year_basis_must_match_the_caption(caption, period):
    assert "fiscal_calendar_mismatch" in codes(table_report(caption, period=period))


@pytest.mark.parametrize(
    ("sentence", "value", "rejected"),
    [
        (
            "GDP growth was forecast at 1.1% in 2025, but the actual outturn was 2.2% in 2025.",
            1.1,
            True,
        ),
        (
            "GDP growth was forecast at 1.1% in 2025, but the actual outturn was 2.2% in 2025.",
            2.2,
            False,
        ),
        ("GDP growth was 2.2% in 2025, compared with the previous forecast of 1.1%.", 2.2, False),
    ],
)
def test_actuals_alongside_previous_forecasts_are_scoped_to_the_figure(sentence, value, rejected):
    item = ReportedFact(
        text=f"GDP growth was {value}%.",
        source="Stats NZ",
        value=value,
        unit="percent",
        period="2025",
        evidence=[ref(0, sentence)],
    )
    report = check({0: SectionText(sentence)}, outlook_ref=ref(0, sentence), facts=[item])
    assert ("forecast_as_fact" in codes(report)) == rejected
    if not rejected:
        assert codes(report) == set()


@pytest.mark.parametrize(
    ("row", "year", "expected"),
    [
        ("GDP actual outturn", "2026", "historical_not_forecast"),
        ("Previous GDP forecast", "2027", "superseded_value"),
        ("Revised GDP projection", "2027", None),
    ],
)
def test_forecasts_use_the_same_scoped_table_identity(row, year, expected):
    quote = f"{row} 1.1 2.2"
    section = SectionText(f"Table 1: GDP actuals and forecasts (percent)\n2025 {year}\n{quote}")
    claim = forecast(0, quote, value=2.2, unit="percent", horizon=year)
    errors = codes(check({0: section}, outlook_ref=ref(0, quote), forecasts=[claim]))
    assert (expected in errors) if expected else not errors


@pytest.mark.parametrize("caption", ["GDP outlook", "GDP expected growth"])
def test_table_forecast_retains_forward_wording_without_an_explicit_type_label(caption):
    quote = "GDP growth 1.1 2.2"
    section = SectionText(f"Table 1: {caption} (percent)\n2026 2027\n{quote}")
    claim = forecast(0, quote, value=2.2, unit="percent", horizon="2027")
    assert codes(check({0: section}, outlook_ref=ref(0, quote), forecasts=[claim])) == set()
