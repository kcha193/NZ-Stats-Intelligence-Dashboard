"""Values, periods and units as printed in a forecast table (Phase 4AF): parse exactly, or say why not."""

from decimal import Decimal

import pytest

from nzstats.research.table_parse import (
    Period,
    column_kind,
    parse_value,
    period_of,
    unit_of_text,
)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("3.25", "3.25"),
        ("-0.3", "-0.3"),
        ("−0.3", "-0.3"),
        ("–0.3", "-0.3"),
        ("+1.2", "1.2"),
        ("0", "0"),
        ("0.0", "0.0"),
        ("-0.0", "0.0"),
        ("1,234", "1234"),
        ("3.25%", "3.25"),
    ],
)
def test_numbers_keep_sign_and_zero(text, value):
    p = parse_value(text)
    assert (p.kind, p.value, p.raw) == ("number", Decimal(value), text)
    assert p.code is None


@pytest.mark.parametrize("text", ["", " ", "-", "–", "—", "n/a", "N/A", "..", "…"])
def test_dashes_and_markers_are_missing_never_zero(text):
    p = parse_value(text)
    assert (p.kind, p.value) == ("missing", None)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("(0.3)", "bracketed_value"),
        ("4.1x", "unrecognised_suffix"),
        ("1,23", "unrecognised_suffix"),
        ("1.2.3", "unrecognised_suffix"),
        ("three", "unrecognised_suffix"),
        ("--1", "unrecognised_suffix"),
    ],
)
def test_ambiguous_or_unknown_text_is_rejected(text, code):
    p = parse_value(text)
    assert (p.kind, p.value, p.code) == ("reject", None, code)


@pytest.mark.parametrize(("text", "mark"), [("4.1*", "*"), ("4.1¹", "¹"), ("-4.1†", "†")])
def test_a_footnote_marker_is_recorded_not_applied(text, mark):
    p = parse_value(text)
    assert p.kind == "number" and p.footnote == mark and abs(p.value) == Decimal("4.1")


@pytest.mark.parametrize(
    ("headers", "kind", "year", "month"),
    [
        (("Forecast", "Dec-26"), "month_end", 2026, 12),
        (("Dec 2026",), "month_end", 2026, 12),
        (("Mar-27 yr",), "year_to", 2027, 3),
        (("Year to March 2027",), "year_to", 2027, 3),
        (("Q4 2026",), "quarter", 2026, 12),
        (("2026 Q1",), "quarter", 2026, 3),
        (("Q2-27",), "quarter", 2027, 6),
        (("2026",), "calendar", 2026, None),
        (("2027f",), "calendar", 2027, None),
        (("Dec-27 (f)",), "month_end", 2027, 12),
    ],
)
def test_periods_are_read_as_printed(headers, kind, year, month):
    period, code = period_of(headers)
    assert code is None
    assert period == Period(kind, year, month)


def test_a_period_renders_in_the_forms_the_comparison_reads():
    assert Period("month_end", 2026, 12).render("quarter") == "December 2026 quarter"
    assert Period("month_end", 2027, 3).render("year_to") == "year to March 2027"
    assert Period("calendar", 2026, None).render("calendar") == "calendar year 2026"
    assert Period("month_end", 2026, 11).render("month") == "November 2026"
    assert Period("month_end", 2026, 11).render("quarter") is None  # not a quarter end


@pytest.mark.parametrize(
    "headers",
    [
        ("Year to Dec", "Mar 2026"),
        ("2026", "Mar-27"),
        ("Forecast", "next year"),
        ("Dec-26", "Dec-26x"),
    ],
)
def test_contradictory_or_unreadable_periods_are_refused(headers):
    period, code = period_of(headers)
    assert period is None and code in ("contradictory_period", "unparsed_period")


def test_contradiction_and_unreadable_have_their_own_codes():
    assert period_of(("Year to Dec", "Mar 2026"))[1] == "contradictory_period"
    assert period_of(("Forecast", "next year"))[1] == "unparsed_period"


@pytest.mark.parametrize(
    ("headers", "kind"),
    [
        (("Actual", "Dec-25"), "actual"),
        (("Forecast", "Dec-26"), "forecast"),
        (("Projections", "Dec-26"), "forecast"),
        (("2027f",), "forecast"),
        (("Dec-27 (f)",), "forecast"),
        (("Dec-26",), "unknown"),
        (("2026p",), "unknown"),
        (("2026e",), "unknown"),
        (("Actual", "2026f"), "unknown"),
    ],
)
def test_actual_or_forecast_needs_an_explicit_marker(headers, kind):
    assert column_kind(headers) == kind


@pytest.mark.parametrize(
    ("texts", "unit", "code"),
    [
        (("OCR (%)",), "percent", None),
        (("Annual CPI inflation, % y/y",), "percent", None),
        (("GDP growth % pa",), "percent", None),
        (("Cash rate in percentage points",), "percentage_points", None),
        (("Change, ppt",), "percentage_points", None),
        (("Spread, bps",), "basis_points", None),
        (("Debt, % of GDP",), "percent_of_gdp", None),
        (("Unemployment rate", "Table 1: Forecasts"), None, None),
        (
            ("Unemployment rate (%)", "Table: figures are percentage points"),
            None,
            "contradictory_unit",
        ),
        (("Rate (%)", "Caption (%)"), "percent", None),
    ],
)
def test_units_are_read_from_wording_and_conflicts_are_refused(texts, unit, code):
    assert unit_of_text(*texts) == (unit, code)


@pytest.mark.parametrize(
    "texts",
    [
        ("Unemployment (000s)", "(%)"),
        ("Debt, NZ$ million",),
        ("Index, 2010=1000", "%"),
        ("Persons employed",),
        ("Rate ($)",),
    ],
)
def test_a_unit_this_phase_does_not_read_is_refused_rather_than_taken_as_a_percentage(texts):
    assert unit_of_text(*texts) == (None, "unsupported_unit")


@pytest.mark.parametrize("text", ["1" + "0" * 400, "1234567", "9" * 13])
def test_an_absurd_magnitude_is_refused_so_nothing_overflows(text):
    p = parse_value(text)
    assert (p.kind, p.value, p.code) == ("reject", None, "value_out_of_range")
