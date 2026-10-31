"""PDF layout hazards found in Phase 4H (synthetic text in the same shapes as the real pages).

A minus sign left at a line end, table cells whose column headings are detached from the rows, and chart-axis
labels that leak into the text as runs of loose numbers.
"""

from datetime import date

import pytest

from nzstats.research.contract import ReportedFact, SectionText
from nzstats.research.verify import _Layout, _norm

from .verify_support import check, codes, forecast, ref, warning_codes

SIGN = SectionText(
    "SYNTHETIC FIXTURE. The confidence index fell 3 points over the month to -\n7%. The expectations"
    " index rose to -2% in October 2026.",
    1, 1,
)  # fmt: skip
# The shape of the Phase 4H Treasury page: a titled caption, chart-axis labels from another chart in between, the
# table's own header fragments, one row of years, labelled rows, and the column-group labels detached after the
# rows (in the real file they come out in the opposite order to the columns, so they can never be trusted).
TABLE = SectionText(
    "SYNTHETIC FIXTURE. Inflation eased in the June quarter (chart 3).\n"
    "Table 1: IMF World Economic Outlook forecasts\n"
    "Source: WEO, October 2026\n"
    "-10\n-5\n0\n5\n10 15 20\n"
    "Annual\naverage % change\nCalendar years\n"
    "2025 2026 2027 2025 2026 2027\n"
    "World 3.3 3.2 3.1 4.2 3.7 3.4\n"
    "Australia 1.4 2.2 2.3 3.2 2.9 2.5\n"
    "New Zealand 0.3 2.0 2.6 2.8 4.1 2.8\n"
    "Treasury (PEU) -- 1.9 2.8 -- 3.6 2.1\n"
    "Forecasts\n"
    "Inflation (%, annual average)Real GDP (%, annual average)\n",
    2, 2,
)  # fmt: skip
NO_HEADER = SectionText(
    "SYNTHETIC FIXTURE. Growth forecasts, annual average % change\n"
    "New Zealand 0.8 1.6 2.9\n"
    "Australia 1.4 2.2 2.3\n",
    3, 3,
)  # fmt: skip
NO_GROUPS = SectionText(
    "SYNTHETIC FIXTURE. Forecasts, annual average % change\n"
    "2025 2026 2027 2025 2026 2027\n"
    "New Zealand 0.8 1.6 2.9 2.7 2.4 2.0\n",
    4, 4,
)  # fmt: skip
ONE_GROUP = SectionText(
    "SYNTHETIC FIXTURE. GDP forecasts, annual average % change\n"
    "2025 2026 2027\n"
    "New Zealand 0.8 1.6 2.9\n",
    5, 5,
)  # fmt: skip
AXIS = SectionText(
    "SYNTHETIC FIXTURE. Figure 2: Confidence indices\n"
    "Source: Example survey, October 2026\n"
    "-40\n-20\n0\n20\n40 60 80\n"
    "Confidence fell to 40 in October 2026, its lowest level this year.\n",
    6, 6,
)  # fmt: skip
SECTIONS = {1: SIGN, 2: TABLE, 3: NO_HEADER, 4: NO_GROUPS, 5: ONE_GROUP, 6: AXIS}
OUTLOOK = ref(6, "Confidence fell to 40 in October 2026")


def run(**items):
    return check(SECTIONS, outlook_ref=OUTLOOK, **items)


def fact(ordinal: int, quote: str, **kw) -> ReportedFact:
    base = dict(text="The index fell.", source="Example survey", value=None, unit=None,
                period="October 2026", evidence=[ref(ordinal, quote, ordinal)])  # fmt: skip
    base.update(kw)
    return ReportedFact(**base)


# --- a minus sign split from its number by a line break -----------------------------------------
def test_the_layout_view_is_the_normalised_text():
    raw = "a  b\n\nc\x1fd e\r\nf -\n7% g\t\n"
    assert _Layout(raw).text == _norm(raw) == "a b c d e f -7% g"


def test_a_sign_left_at_a_line_end_belongs_to_the_number_on_the_next_line():
    assert _norm("fell to -\n7%") == "fell to -7%"
    assert (
        _norm("over 2026-\n27 the deficit") == "over 2026- 27 the deficit"
    )  # a hyphen, not a sign
    assert _norm("a\n-\n  12") == "a -12"


@pytest.mark.parametrize(
    "quote", ["fell 3 points over the month to -\n7%", "over the month to - 7%"]
)
def test_a_negative_value_split_across_lines_keeps_its_sign(quote):
    good = fact(1, quote, value=-7, unit="percent")
    assert codes(run(facts=[good])) == set()
    lost = fact(1, quote, value=7, unit="percent")  # the sign dropped
    assert "value_not_in_evidence" in codes(run(facts=[lost]))


def test_a_quote_that_starts_after_the_split_sign_is_truncated():
    report = run(facts=[fact(1, "7%. The expectations index", value=7, unit="percent")])
    assert "quote_truncated" in codes(report)


def test_a_forecast_value_keeps_its_split_sign_too():
    claim = forecast(1, "fell 3 points over the month to -\n7%", 1, value=7, unit="percent")
    assert "value_not_in_evidence" in codes(run(forecasts=[claim]))


# --- table cells and their column headings ------------------------------------------------------
def table_claim(value: float, horizon: str, indicator: str = "gdp", **kw):
    label = {"gdp": "Real GDP", "cpi_inflation": "CPI inflation"}[indicator]
    return forecast(2, "Treasury (PEU) -- 1.9 2.8 -- 3.6 2.1", 2, value=value, unit="percent",
                    horizon=horizon, indicator=indicator, indicator_label=label, **kw)  # fmt: skip


@pytest.mark.parametrize(
    ("value", "horizon", "indicator"),
    [(1.9, "2026", "gdp"), (2.8, "2027", "gdp"), (3.6, "2026", "cpi_inflation"),
     (2.1, "2027", "cpi_inflation"), (1.9, "2026", "cpi_inflation")],
)  # fmt: skip
def test_a_cell_under_repeated_year_columns_is_refused_even_when_right(value, horizon, indicator):
    """The year row is reliable; which group (GDP or inflation) a column belongs to is not."""
    report = run(forecasts=[table_claim(value, horizon, indicator)])
    assert "table_column_unverified" in codes(report)
    assert "table_column_mismatch" not in codes(report)


@pytest.mark.parametrize(("value", "horizon"), [(1.9, "2027"), (2.8, "2026"), (3.6, "2025")])
def test_a_table_cell_read_under_the_wrong_year_is_an_error(value, horizon):
    assert "table_column_mismatch" in codes(run(forecasts=[table_claim(value, horizon)]))


def test_a_row_without_a_matching_header_row_cannot_be_assigned_a_column():
    claim = forecast(3, "New Zealand 0.8 1.6 2.9", 3, value=1.6, unit="percent", horizon="2026")
    assert "table_column_unverified" in codes(run(forecasts=[claim]))


def test_repeated_year_columns_without_group_headings_cannot_be_assigned():
    claim = forecast(4, "New Zealand 0.8 1.6 2.9 2.7 2.4 2.0", 4, value=1.6, unit="percent",
                     horizon="2026")  # fmt: skip
    assert "table_column_unverified" in codes(run(forecasts=[claim]))


def test_a_single_group_table_checks_the_year_and_asks_the_reviewer_for_the_heading():
    claim = forecast(5, "New Zealand 0.8 1.6 2.9", 5, value=1.6, unit="percent", horizon="2026")
    report = run(forecasts=[claim])
    assert codes(report) == set() and "table_heading_unverified" in warning_codes(report)
    wrong_year = forecast(5, "New Zealand 0.8 1.6 2.9", 5, value=1.6, unit="percent",
                          horizon="2027")  # fmt: skip
    assert "table_column_mismatch" in codes(run(forecasts=[wrong_year]))


def test_table_cell_can_supply_its_own_percent_unit():
    section = SectionText("Table 1: GDP forecasts\n2026 2027\nGDP growth 1.0% 2.0%", 1, 1)
    claim = forecast(1, "GDP growth 1.0% 2.0%", 1, value=2.0, unit="percent", horizon="2027")
    report = check({1: section}, outlook_ref=ref(1, "GDP growth 1.0% 2.0%", 1), forecasts=[claim])
    assert "unit_mismatch" not in codes(report)


def test_a_reported_fact_from_a_table_row_is_checked_the_same_way():
    # Reported facts need actual evidence; a historical forecast remains a forecast.
    sections = {
        **SECTIONS,
        5: SectionText(ONE_GROUP.text.replace("GDP forecasts", "Historical GDP actuals"), 5, 5),
    }
    good = fact(5, "New Zealand 0.8 1.6 2.9", value=0.8, unit="percent", period="2025",
                text="GDP grew 0.8% in 2025")  # fmt: skip
    report = check(sections, outlook_ref=OUTLOOK, facts=[good])
    assert codes(report) == set() and "table_heading_unverified" in warning_codes(report)
    wrong = good.model_copy(update={"period": "2027"})
    assert "table_column_mismatch" in codes(check(sections, outlook_ref=OUTLOOK, facts=[wrong]))


def test_table_caption_supports_statistical_definition():
    section = SectionText(
        "Table 1: Historical GDP growth (seasonally adjusted, percent).\n"
        "2024 2025\nGDP growth 1.0 2.0",
        1,
        1,
    )
    item = fact(
        1,
        "GDP growth 1.0 2.0",
        value=2.0,
        unit="percent",
        period="2025",
        definition={"adjustment": "seasonally_adjusted"},
    )
    errors = codes(check({1: section}, outlook_ref=ref(1, "GDP growth 1.0 2.0", 1), facts=[item]))
    assert "definition_not_in_evidence" not in errors


@pytest.mark.parametrize(
    ("heading", "period", "published", "rejected"),
    [
        ("June year actual outturns", "June 2026 year", date(2026, 10, 15), False),
        ("June year historical results", "June 2026 year", date(2026, 10, 15), False),
        ("September quarter actual outturns", "September 2026 quarter", date(2026, 10, 15), False),
        ("Calendar year actual outturns", "calendar year 2026", date(2027, 1, 15), False),
        ("Calendar year forecasts", "calendar year 2026", date(2026, 10, 15), True),
        ("June year forecasts", "June 2026 year", date(2026, 5, 15), True),
        ("December quarter actual outturns", "December 2026 quarter", date(2026, 10, 15), True),
        ("GDP figures", "2026", date(2026, 10, 15), True),
        ("June year forecasts", "June 2026 year", date(2026, 10, 15), True),
    ],
)
def test_table_fact_current_year_requires_completed_historical_period(
    heading, period, published, rejected
):
    section = SectionText(f"Table 1: {heading} (percent)\n2025 2026 2027\nGDP 1.1 2.2 3.3", 1, 1)
    item = fact(1, "GDP 1.1 2.2 3.3", value=2.2, unit="percent", period=period)
    errors = codes(
        check(
            {1: section},
            outlook_ref=ref(1, "GDP 1.1 2.2 3.3", 1),
            published_on=published,
            facts=[item],
        )
    )
    assert ("forecast_as_fact" in errors) == rejected


# --- chart-axis residue ---------------------------------------------------------------------------
def test_a_number_from_chart_axis_labels_is_not_an_observation():
    axis = fact(6, "-40 -20 0 20 40 60 80", value=60, unit="index", text="The index was 60.")
    assert "axis_residue" in codes(run(facts=[axis]))
    prose = fact(6, "Confidence fell to 40 in October 2026", value=40, unit="index",
                 text="Confidence fell to 40.")  # fmt: skip
    assert codes(run(facts=[prose])) == set()


def test_a_statement_number_supported_only_by_axis_labels_is_an_error():
    statement = {"text": "The index reached 80.", "evidence": [ref(6, "-20 0 20 40 60 80", 6)]}
    assert "axis_residue" in codes(run(drivers=[statement]))


def test_a_forecast_value_from_axis_labels_is_an_error():
    claim = forecast(6, "-20 0 20 40 60 80", 6, value=60, unit="index", horizon="2027")
    assert "axis_residue" in codes(run(forecasts=[claim]))


def test_a_year_followed_by_chart_axis_labels_is_not_a_fiscal_year():
    """ "Source: WEO, October 2026" then an axis label "-10" read as "2026-10", a fiscal year, in Phase 4H."""
    sections = {7: SectionText(
        "SYNTHETIC FIXTURE. Table 2: GDP forecasts\nSource: WEO, October 2026\n-10\n-5\n0\n5\n10 15 20\n"
        "Annual average % change\n2025 2026 2027\nExample 0.8 1.6 2.9\n", 7, 7)}  # fmt: skip
    claim = forecast(7, "Example 0.8 1.6 2.9", 7, value=1.6, unit="percent", horizon="2026")
    report = check(sections, outlook_ref=ref(7, "Table 2: GDP forecasts"), forecasts=[claim])
    assert "fiscal_calendar_mismatch" not in codes(report)
    fiscal = SectionText(
        "SYNTHETIC FIXTURE. Debt is forecast to reach 43.1% of GDP in 2026-27.", 8, 8
    )
    debt = forecast(8, "forecast to reach 43.1% of GDP in 2026-27", 8, value=43.1, unit="percent_of_gdp",
                    horizon="2027", indicator="government_debt", indicator_label="Net debt")  # fmt: skip
    assert "fiscal_calendar_mismatch" in codes(check({8: fiscal}, outlook_ref=ref(8, "Debt is forecast"),
                                                     forecasts=[debt]))  # fmt: skip
