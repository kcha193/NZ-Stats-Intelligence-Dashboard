"""Explicit reference-period components belong to the cited value, not a neighboring figure."""

import pytest

from nzstats.research.contract import ReportedFact, SectionText

from .verify_support import check, codes, forecast, ref


def period_report(kind, local_period, neighbor_period, claimed, *, reverse=False, heading=None):
    lead = "We forecast GDP growth" if kind == "forecast" else "GDP grew"
    primary = f"{lead} 2.5%" + (f" in {local_period}" if local_period else "") + "."
    neighbor = f"{lead} 1.0% in {neighbor_period}."
    text = f"{primary} {neighbor}" if reverse else f"{neighbor} {primary}"
    quote = f"{lead} 2.5%"  # reference period is outside the quote but inside its stored clause
    return scoped_report(kind, text, quote, claimed, heading=heading)


def scoped_report(kind, text, quote, claimed, *, heading=None):
    if kind == "forecast":
        items = {"forecasts": [forecast(0, quote, value=2.5, unit="percent", horizon=claimed)]}
    else:
        items = {
            "facts": [
                ReportedFact(
                    text=quote,
                    source="Stats NZ",
                    value=2.5,
                    unit="percent",
                    period=claimed,
                    evidence=[ref(0, quote)],
                )
            ]
        }
    return check({0: SectionText(text, heading=heading)}, outlook_ref=ref(0, quote), **items)


@pytest.mark.parametrize("kind", ["fact", "forecast"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("facet", ["year", "month", "quarter"])
@pytest.mark.parametrize("wrong", [False, True])
def test_local_period_components_override_neighboring_figures(kind, reverse, facet, wrong):
    year = 2025 if kind == "fact" else 2028
    local, neighbor = {
        "year": (str(year), str(year - 1)),
        "month": (f"June {year}", f"March {year}"),
        "quarter": (f"Q2 {year}", f"Q1 {year}"),
    }[facet]
    report = period_report(kind, local, neighbor, neighbor if wrong else local, reverse=reverse)
    expected = "period_not_supported" if kind == "fact" else "horizon_not_supported"
    assert (expected in codes(report)) == wrong
    if not wrong:
        assert codes(report) == set()


@pytest.mark.parametrize("kind", ["fact", "forecast"])
@pytest.mark.parametrize("local_part", ["June", "year", "none"])
def test_heading_can_supply_only_period_components_missing_from_the_local_clause(kind, local_part):
    year = "2025" if kind == "fact" else "2028"
    local = {"June": "June", "year": year, "none": ""}[local_part]
    report = period_report(kind, local, "2020", f"June {year}", heading=f"June {year} GDP figures")
    assert codes(report) == set()


@pytest.mark.parametrize("kind", ["fact", "forecast"])
@pytest.mark.parametrize("separator", [". ", "; ", ", while "])
def test_a_wide_quote_does_not_join_the_periods_of_separate_figures(kind, separator):
    lead = "We forecast GDP growth" if kind == "forecast" else "GDP grew"
    year = 2028 if kind == "forecast" else 2025
    text = f"{lead} 1.0% in {year - 1}{separator}{lead} 2.5% in {year}."
    report = scoped_report(kind, text, text, str(year - 1))
    assert {"period_not_supported", "horizon_not_supported"} & codes(report)
    assert codes(scoped_report(kind, text, text, str(year))) == set()


@pytest.mark.parametrize("kind", ["fact", "forecast"])
@pytest.mark.parametrize("reverse", [False, True])
def test_an_independent_adjacent_figure_cannot_supply_an_unstated_period(kind, reverse):
    report = period_report(
        kind,
        "",
        "2028" if kind == "forecast" else "2025",
        "2028" if kind == "forecast" else "2025",
        reverse=reverse,
    )
    assert {"period_not_supported", "horizon_not_supported"} & codes(report)


@pytest.mark.parametrize("kind", ["fact", "forecast"])
@pytest.mark.parametrize(
    "context,claimed,ok",
    [
        ("All figures refer to June 2025.", "June 2025", True),
        (
            "All figures refer to June 2025. {figure}. These figures refer to March 2024.",
            "June 2025",
            False,
        ),
        ("All figures refer to June 2025 or March 2024.", "June 2025", False),
    ],
)
def test_only_unambiguous_period_context_is_inherited(kind, context, claimed, ok):
    if kind == "forecast":
        context, claimed = context.replace("2025", "2028"), claimed.replace("2025", "2028")
    quote = "We forecast GDP growth 2.5%" if kind == "forecast" else "GDP grew 2.5%"
    text = context.format(figure=quote) if "{figure}" in context else f"{context} {quote}."
    report = scoped_report(kind, text, quote, claimed)
    assert not bool({"period_not_supported", "horizon_not_supported"} & codes(report)) == ok


@pytest.mark.parametrize("kind", ["fact", "forecast"])
@pytest.mark.parametrize(
    "local,claimed",
    [
        ("the year to June 2025", "calendar year 2025"),
        ("calendar year 2025", "June 2025 year"),
    ],
)
def test_adjacent_periods_cannot_override_the_selected_figures_year_basis(kind, local, claimed):
    if kind == "forecast":
        local, claimed = local.replace("2025", "2028"), claimed.replace("2025", "2028")
    report = period_report(kind, local, claimed, claimed)
    assert {"period_not_supported", "horizon_not_supported", "fiscal_calendar_mismatch"} & codes(
        report
    )


@pytest.mark.parametrize("kind", ["fact", "forecast"])
def test_inherited_fiscal_context_cannot_be_labelled_as_calendar(kind):
    year = "2028" if kind == "forecast" else "2025"
    quote = "We forecast GDP growth 2.5%" if kind == "forecast" else "GDP grew 2.5%"
    text = f"All figures refer to the year to June {year}. {quote}."
    wrong = scoped_report(kind, text, quote, f"calendar year {year}")
    assert {"period_not_supported", "horizon_not_supported", "fiscal_calendar_mismatch"} & codes(
        wrong
    )
    assert codes(scoped_report(kind, text, quote, f"June {year} year")) == set()


@pytest.mark.parametrize("kind", ["fact", "forecast"])
def test_a_partial_period_cannot_borrow_a_month_from_another_year(kind):
    year = "2028" if kind == "forecast" else "2025"
    report = period_report(kind, year, "June 2024", f"June {year}")
    assert {"period_not_supported", "horizon_not_supported"} & codes(report)


@pytest.mark.parametrize("kind", ["fact", "forecast"])
def test_heading_supplies_an_unstated_year_basis_even_when_the_year_is_local(kind):
    year = "2028" if kind == "forecast" else "2025"
    report = period_report(
        kind, year, "2020", f"calendar year {year}", heading=f"Fiscal year {year} figures"
    )
    assert {"period_not_supported", "horizon_not_supported", "fiscal_calendar_mismatch"} & codes(
        report
    )


@pytest.mark.parametrize("kind", ["fact", "forecast"])
def test_fiscal_pair_heading_can_qualify_its_explicit_local_end_year(kind):
    year = 2028 if kind == "forecast" else 2025
    report = period_report(
        kind,
        str(year),
        "2020",
        f"June {year} year",
        heading=f"June year {year - 1}/{year % 100:02d} figures",
    )
    assert codes(report) == set()


@pytest.mark.parametrize("kind", ["fact", "forecast"])
@pytest.mark.parametrize("source_after", [False, True])
@pytest.mark.parametrize("wrong", [False, True])
def test_table_source_date_cannot_replace_or_conflict_with_the_selected_column(
    kind, source_after, wrong
):
    year = 2028 if kind == "forecast" else 2025
    caption = "forecasts" if kind == "forecast" else "historical results"
    source = "Source: Treasury, October 2026"
    row = "GDP growth 1.0 2.5"
    text = f"Table 1: GDP {caption} (percent)\n"
    if not source_after:
        text += source + "\n"
    text += f"{year - 1} {year}\n{row}"
    if source_after:
        text += "\n" + source
    report = scoped_report(kind, text, row, "2026" if wrong else str(year))
    if wrong:
        assert {"period_not_supported", "horizon_not_supported", "table_column_mismatch"} & codes(
            report
        )
    else:
        assert codes(report) == set()


@pytest.mark.parametrize("kind", ["fact", "forecast"])
@pytest.mark.parametrize("period", ["2025", "June 2025", "Q2 2025"])
@pytest.mark.parametrize("local_override", [False, True])
def test_coordinated_assertions_inherit_only_a_shared_temporal_prefix(kind, period, local_override):
    year = 2028 if kind == "forecast" else 2025
    period = period.replace("2025", str(year))
    first = "We forecast CPI inflation 1.0%" if kind == "forecast" else "GDP grew 1.0%"
    quote = "we forecast GDP growth 2.5%" if kind == "forecast" else "CPI inflation was 2.5%"
    suffix = f" in {year - 1}" if local_override else ""
    text = f"In {period}, {first} and {quote}{suffix}."
    correct = str(year - 1) if local_override else period
    wrong = period if local_override else str(year - 1)
    assert codes(scoped_report(kind, text, quote, correct)) == set()
    assert {"period_not_supported", "horizon_not_supported"} & codes(
        scoped_report(kind, text, quote, wrong)
    )
