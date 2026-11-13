"""Table rows as forecasts (Phase 4AF): what a row means, and the cases where it is refused rather than guessed."""

from decimal import Decimal

import pytest

from nzstats.research.compare import horizon_of
from nzstats.research.extract import ExtractionLimits
from nzstats.research.table_forecast import INTERPRETER_VERSION, interpret
from nzstats.research.table_grid import find_tables
from nzstats.research.table_words import extract_words

from .pdf_table_support import Item, table_pdf
from .test_table_grid import line

PUBLISHER = ("Example Bank",)
GROUPS: list[Item] = [(250, 714, "Actual"), (370, 714, "Forecast")]
HEAD = ["Dec-25", "Mar-26", "Jun-26", "Sep-26"]


def run(*pages: list[Item], publisher=PUBLISHER):
    words = extract_words(table_pdf(list(pages)), ExtractionLimits(), isolate=False)
    tables, grid_rejections = find_tables(words)
    forecasts, rejections = interpret(tables, publisher_names=publisher)
    return forecasts, (*grid_rejections, *rejections)


def page(rows: list[Item], *, groups=GROUPS, head=HEAD, extra: list[Item] = ()) -> list[Item]:
    return [*groups, *(line(700, "", head) if head else []), *rows, *extra]


def by(forecasts, **kw):
    return [f for f in forecasts if all(getattr(f, k) == v for k, v in kw.items())]


def test_the_four_priority_indicators_map_with_their_horizons_and_units():
    rows = [
        *line(686, "OCR (%)", ["4.25", "3.75", "3.25", "3.00"]),
        *line(672, "Annual CPI inflation (%)", ["4.0", "3.1", "2.6", "2.2"]),
        *line(658, "Quarterly GDP growth (%)", ["0.2", "-0.1", "0.4", "0.6"]),
        *line(644, "Unemployment rate (%)", ["4.8", "5.0", "5.1", "5.0"]),
    ]
    forecasts, rejections = run(page(rows))
    assert rejections == ()
    assert INTERPRETER_VERSION == "tables-12"
    got = {
        (f.indicator, f.horizon): (f.value, f.unit, f.raw_text)
        for f in forecasts
        if f.kind == "forecast"
    }
    assert got == {
        ("ocr", "June 2026 quarter"): (Decimal("3.25"), "percent", "3.25"),
        ("ocr", "September 2026 quarter"): (Decimal("3.00"), "percent", "3.00"),
        ("cpi_inflation", "year to June 2026"): (Decimal("2.6"), "percent", "2.6"),
        ("cpi_inflation", "year to September 2026"): (Decimal("2.2"), "percent", "2.2"),
        ("gdp", "June 2026 quarter"): (Decimal("0.4"), "percent", "0.4"),
        ("gdp", "September 2026 quarter"): (Decimal("0.6"), "percent", "0.6"),
        ("unemployment", "June 2026 quarter"): (Decimal("5.1"), "percent", "5.1"),
        ("unemployment", "September 2026 quarter"): (Decimal("5.0"), "percent", "5.0"),
    }
    assert all(horizon_of(f.horizon) for f in forecasts)


def test_actual_columns_are_actuals_and_never_forecasts():
    forecasts, _ = run(page(line(686, "OCR (%)", ["4.25", "3.75", "3.25", "3.00"])))
    assert {(f.horizon, f.kind) for f in forecasts} == {
        ("December 2025 quarter", "actual"),
        ("March 2026 quarter", "actual"),
        ("June 2026 quarter", "forecast"),
        ("September 2026 quarter", "forecast"),
    }


def test_negative_zero_and_original_text_are_preserved():
    rows = line(686, "Quarterly GDP growth (%)", ["0.2", "–0.1", "0.0", "-0.4"])
    forecasts, _ = run(page(rows))
    assert [(f.raw_text, f.value) for f in forecasts] == [
        ("0.2", Decimal("0.2")),
        ("–0.1", Decimal("-0.1")),
        ("0.0", Decimal("0.0")),
        ("-0.4", Decimal("-0.4")),
    ]


def test_missing_and_absent_cells_are_missing_and_never_filled():
    rows = line(686, "Unemployment rate (%)", [None, "5.0", "-", None])
    forecasts, rejections = run(page(rows))
    assert rejections == ()
    assert [(f.horizon, f.missing, f.value, f.raw_text) for f in forecasts] == [
        ("December 2025 quarter", True, None, ""),
        ("March 2026 quarter", False, Decimal("5.0"), "5.0"),
        ("June 2026 quarter", True, None, "-"),
        ("September 2026 quarter", True, None, ""),
    ]


def test_evidence_names_the_cell_and_its_headers():
    forecasts, _ = run(page(line(686, "OCR (%)", ["4", "3", "2.75", "2"])))
    f = by(forecasts, horizon="June 2026 quarter")[0]
    assert (f.page, f.row, f.col) == (1, 0, 2)
    assert f.evidence["cell_text"] == "2.75"
    assert f.evidence["row_label"] == "OCR (%)"
    assert f.evidence["header_texts"] == ["Forecast", "Jun-26"]
    assert f.evidence["page"] == 1 and len(f.evidence["bbox"]) == 3


def test_the_label_is_kept_as_printed():
    rows = line(686, "Annual CPI (SA) (%)", ["4", "3", "2", "2"])
    forecasts, _ = run(page(rows))
    assert {f.label for f in forecasts} == {"Annual CPI (SA) (%)"}


def test_two_indicators_in_one_label_are_ambiguous():
    forecasts, rejections = run(page(line(686, "GDP and CPI inflation (%)", ["1", "2", "3", "4"])))
    assert forecasts == ()
    assert [(r.code, r.row) for r in rejections] == [("ambiguous_indicator", 0)]


def test_an_unknown_row_is_rejected_not_an_error():
    rows = [
        *line(686, "Current account balance (% of GDP)", ["-6", "-5", "-4", "-3"]),
        *line(672, "OCR (%)", ["4", "3", "2", "2"]),
    ]
    forecasts, rejections = run(page(rows))
    assert {f.indicator for f in forecasts} == {"ocr"}
    assert [(r.code, r.row) for r in rejections] == [("unmapped_row", 0)]


def test_a_row_without_a_unit_is_rejected():
    forecasts, rejections = run(page(line(686, "Annual CPI inflation", ["4", "3", "2", "2"])))
    assert forecasts == ()
    assert [(r.code, r.row) for r in rejections] == [("unit_unstated", 0)]


def test_a_unit_stated_by_the_caption_applies():
    caption = [(72, 745, "Table 2: Forecasts, % change")]
    forecasts, rejections = run(
        page(line(686, "Annual CPI inflation", ["4", "3", "2", "2"]), extra=caption)
    )
    assert rejections == ()
    assert {f.unit for f in forecasts} == {"percent"}


def test_a_unit_that_disagrees_with_the_caption_is_rejected():
    caption = [(72, 745, "Table 2: figures in percentage points")]
    forecasts, rejections = run(page(line(686, "OCR (%)", ["4", "3", "2", "2"]), extra=caption))
    assert forecasts == ()
    assert [r.code for r in rejections] == ["contradictory_unit"]


def test_a_unit_column_supplies_the_unit():
    xs = [200.0, 260.0, 320.0]
    rows = [
        *line(700, "", ["Unit", "Dec-26", "Mar-27"], xs),
        *line(686, "Unemployment rate", ["%", "5.0", "4.9"], xs),
    ]
    forecasts, rejections = run(page(rows, groups=[(260, 714, "Forecast")], head=[]))
    assert rejections == ()
    assert {(f.unit, f.value) for f in forecasts} == {
        ("percent", Decimal("5.0")),
        ("percent", Decimal("4.9")),
    }


def test_a_source_line_naming_someone_else_makes_it_a_third_party_forecast():
    other = page(line(686, "OCR (%)", ["4", "3", "2", "2"]), extra=[(72, 665, "Source: RBNZ")])
    own = page(
        line(686, "OCR (%)", ["4", "3", "2", "2"]),
        extra=[(72, 665, "Source: Example Bank, Stats NZ")],
    )
    none = page(line(686, "OCR (%)", ["4", "3", "2", "2"]))
    assert {f.author_role for f in run(other)[0]} == {"third_party"}
    assert {f.author_role for f in run(own)[0]} == {"author"}
    assert {f.author_role for f in run(none)[0]} == {"author"}


def test_a_footnoted_figure_is_not_used():
    rows = line(686, "Annual CPI inflation (%)", ["4", "3", "2.6*", "2"])
    forecasts, rejections = run(page(rows, extra=[(72, 665, "* Excludes petrol")]))
    assert [(r.code, r.col) for r in rejections] == [("footnote_unresolved", 2)]
    assert by(forecasts, horizon="year to June 2026") == []
    assert len(forecasts) == 3


def test_a_bracketed_value_is_rejected():
    forecasts, rejections = run(
        page(line(686, "Quarterly GDP growth (%)", ["0.2", "0.1", "(0.3)", "0.4"]))
    )
    assert [(r.code, r.row, r.col) for r in rejections] == [("bracketed_value", 0, 2)]
    assert len(forecasts) == 3


def test_two_columns_for_one_period_are_contradictory():
    forecasts, rejections = run(
        page(
            line(686, "OCR (%)", ["4", "3", "2", "2"]),
            head=["Dec-25", "Mar-26", "Jun-26", "Jun-26"],
        )
    )
    assert {r.code for r in rejections} == {"contradictory_period"}
    assert {f.horizon for f in forecasts} == {"December 2025 quarter", "March 2026 quarter"}


def test_a_table_with_no_actual_or_forecast_marker_is_unstated():
    forecasts, rejections = run(page(line(686, "OCR (%)", ["4", "3", "2", "2"]), groups=[]))
    assert forecasts == ()
    assert [(r.code, r.col) for r in rejections] == [
        ("actual_or_forecast_unstated", n) for n in range(4)
    ]


def test_a_period_whose_kind_the_row_does_not_state_is_rejected():
    forecasts, rejections = run(page(line(686, "CPI inflation (%)", ["4", "3", "2", "2"])))
    assert forecasts == ()
    assert {r.code for r in rejections} == {"period_basis_unstated"}


def test_an_annual_row_under_a_quarter_header_is_contradictory():
    forecasts, rejections = run(
        page(
            line(686, "Annual CPI inflation (%)", ["4", "3", "2", "2"]),
            head=["Q4 2025", "Q1 2026", "Q2 2026", "Q3 2026"],
        )
    )
    assert forecasts == ()
    assert {r.code for r in rejections} == {"contradictory_period"}


def test_a_scenario_table_is_never_read_as_the_central_forecast():
    caption = [(72, 745, "Table 2: Downside scenario (%)")]
    forecasts, rejections = run(
        page(line(686, "Annual CPI inflation", ["5.8", "5.4", "5.1", "5.0"]), extra=caption)
    )
    assert forecasts == ()
    assert [r.code for r in rejections] == ["scenario_table"]


@pytest.mark.parametrize(
    "heading",
    [
        "Downside scenario (%)",
        "Upside scenario (%)",
        "Alternative scenario (%)",
        "Stress scenario (%)",
        "Sensitivity analysis (%)",
        "Illustrative projections (%)",
    ],
)
def test_unnumbered_scenario_heading_is_not_lost(heading):
    forecasts, rejections = run(
        page(line(686, "OCR (%)", ["4", "3", "2", "2"]), extra=[(72, 745, heading)])
    )
    assert forecasts == ()
    assert [r.code for r in rejections] == ["scenario_table"]


def test_scenario_heading_on_continuation_cannot_inherit_central_context():
    central = page(line(686, "OCR (%)", ["4", "3", "2", "2"]))
    scenario = page(
        line(686, "OCR (%)", ["9", "9", "9", "9"]),
        extra=[(72, 745, "Downside scenario (continued)")],
    )
    forecasts, rejections = run(central, scenario)
    assert len(forecasts) == 4
    assert {f.page for f in forecasts} == {1}
    assert [r.code for r in rejections] == ["scenario_table"]


def test_explicit_continuation_after_notes_cannot_lose_attribution():
    first = page(
        line(686, "OCR (%)", ["4", "3", "2", "2"]),
        extra=[(72, 745, "Table 1: RBNZ forecasts (%)"), (72, 665, "Note: context")],
    )
    second = page(
        line(686, "OCR (%)", ["9", "9", "9", "9"]),
        extra=[(72, 745, "Table 1 (continued)")],
    )
    forecasts, rejections = run(first, second)
    assert {f.author_role for f in forecasts} == {"third_party"}
    assert {f.page for f in forecasts} == {1}
    assert [r.code for r in rejections] == ["unjoined_continuation"]


def test_quarterly_growth_under_year_to_group_is_refused():
    forecasts, rejections = run(
        page(
            line(686, "Quarterly GDP growth (%)", ["0.2", None, None, None]),
            groups=[(250, 714, "Forecast — year to March")],
            head=["Mar-27", "Mar-28", "Mar-29", "Mar-30"],
        )
    )
    assert forecasts == ()
    assert {r.code for r in rejections} == {"contradictory_period"}


def test_quarterly_growth_under_calendar_year_is_refused():
    forecasts, rejections = run(
        page(
            line(686, "Quarterly GDP growth (%)", ["0.2", None, None, None]),
            groups=[(250, 714, "Forecast")],
            head=["2027", "2028", "2029", "2030"],
        )
    )
    assert forecasts == ()
    assert {r.code for r in rejections} == {"contradictory_period"}


@pytest.mark.parametrize("word", ["downside", "Upside", "alternative", "stress", "sensitivity"])
def test_a_scenario_row_is_refused_and_its_neighbour_is_not(word):
    rows = [
        *line(686, f"Annual CPI inflation, {word} (%)", ["5.8", "5.4", "5.1", "5.0"]),
        *line(672, "OCR (%)", ["4", "3", "2.75", "2.5"]),
    ]
    forecasts, rejections = run(page(rows))
    assert {f.indicator for f in forecasts} == {"ocr"}
    assert [(r.code, r.row) for r in rejections] == [("scenario_row", 0)]


def test_a_scenario_column_is_refused():
    groups = [(250, 714, "Actual"), (370, 714, "Forecast, downside")]
    forecasts, rejections = run(page(line(686, "OCR (%)", ["4", "3", "9", "9"]), groups=groups))
    assert {f.kind for f in forecasts} == {"actual"}
    assert {r.code for r in rejections} == {"scenario_column"}


def test_a_forecaster_in_the_column_header_is_not_attributed_to_the_publisher():
    groups = [(250, 714, "Forecast — RBNZ")]
    forecasts, _ = run(page(line(686, "OCR (%)", ["4", "3", "2", "2"]), groups=groups))
    assert forecasts
    assert {f.author_role for f in forecasts} == {"third_party"}


def test_annual_average_column_is_not_read_as_through_year():
    forecasts, rejections = run(
        page(
            line(686, "Annual CPI inflation (%)", ["4", "3", "2", "2"]),
            groups=[(250, 714, "Forecast (annual average)")],
        )
    )
    assert forecasts == ()
    assert {r.code for r in rejections} == {"period_basis_unstated"}


def test_column_unit_conflicting_with_row_is_refused():
    forecasts, rejections = run(
        page(
            line(686, "OCR (%)", ["25", "25", "25", "25"]),
            groups=[(250, 714, "Forecast (basis points)")],
        )
    )
    assert forecasts == ()
    assert {r.code for r in rejections} == {"contradictory_unit"}


def test_foreign_geography_in_column_header_is_refused():
    forecasts, rejections = run(
        page(
            line(686, "Unemployment rate (%)", ["4", "3", "2", "2"]),
            groups=[(250, 714, "Forecast (Australia)")],
        )
    )
    assert forecasts == ()
    assert {r.code for r in rejections} == {"unsupported_geography"}


def test_column_cadence_conflicting_with_row_is_refused():
    forecasts, rejections = run(
        page(
            line(686, "Quarterly real GDP growth (%)", ["5", "4", "3", "2"]),
            groups=[(250, 714, "Forecast (% y/y)")],
        )
    )
    assert forecasts == ()
    assert {r.code for r in rejections} == {"contradictory_period"}


def test_column_attribution_does_not_change_neighbouring_forecasts():
    groups = [(250, 714, "Forecast"), (370, 714, "Forecast — RBNZ")]
    forecasts, _ = run(page(line(686, "OCR (%)", ["4", "3", "2", "2"]), groups=groups))
    assert [f.author_role for f in forecasts] == ["author", "author", "third_party", "third_party"]


@pytest.mark.parametrize("marker", ["e", "p", "(e)", "(p)"])
def test_estimated_or_provisional_column_is_not_a_forecast(marker):
    forecasts, rejections = run(
        page(
            line(686, "OCR (%)", ["4", "3", "2", "2"]),
            groups=[(250, 714, "Forecast")],
            head=[f"Dec-25{marker}", "Mar-26", "Jun-26", "Sep-26"],
        )
    )
    assert all(f.period_text != f"Dec-25{marker}" for f in forecasts)
    assert ("actual_or_forecast_unstated", 0) in [(r.code, r.col) for r in rejections]


def test_a_footnote_marker_whose_note_cannot_be_found_is_refused_too():
    rows = line(686, "Annual CPI inflation (%)", ["4", "3", "2.6*", "2"])
    forecasts, rejections = run(page(rows))  # no note anywhere near the table
    assert [(r.code, r.col) for r in rejections] == [("footnote_unresolved", 2)]
    assert len(forecasts) == 3


def test_a_footnoted_row_label_is_refused():
    rows = line(686, "Unemployment rate* (%)", ["4", "3", "2", "2"])
    forecasts, rejections = run(page(rows, extra=[(72, 665, "* Youth aged 15-24 only")]))
    assert forecasts == ()
    assert [r.code for r in rejections] == ["footnote_unresolved"]


def test_unit_cadence_conflicting_with_quarterly_row_is_refused():
    xs = [230.0, 300.0, 360.0, 420.0]
    report = [
        (300, 714, "Forecast"),
        *line(700, "", ["Unit", "Dec-26", "Mar-27", "Jun-27"], xs),
        *line(686, "Quarterly real GDP growth", ["% y/y", "5.0", "4.0", "3.0"], xs),
    ]
    forecasts, rejections = run(report)
    assert forecasts == ()
    assert "contradictory_period" in {r.code for r in rejections}


@pytest.mark.parametrize(
    ("label", "unit"),
    [("Annual GDP growth", "% y/y"), ("Quarterly GDP growth", "% q/q")],
)
def test_matching_row_and_unit_cadence_is_preserved(label, unit):
    xs = [230.0, 300.0, 360.0, 420.0]
    report = [
        (300, 714, "Forecast"),
        *line(700, "", ["Unit", "Dec-26", "Mar-27", "Jun-27"], xs),
        *line(686, label, [unit, "5.0", "4.0", "3.0"], xs),
    ]
    forecasts, rejections = run(report)
    assert len(forecasts) == 3
    assert rejections == ()


def test_a_caption_naming_another_forecaster_makes_it_a_third_party_figure():
    caption = [(72, 745, "Table 3: Treasury forecasts (%)")]
    forecasts, _ = run(page(line(686, "OCR", ["4", "3", "2", "2"]), extra=caption))
    assert {f.author_role for f in forecasts} == {"third_party"}
    ours = [(72, 745, "Table 3: Example Bank forecasts, Treasury actuals (%)")]
    forecasts, rejections = run(page(line(686, "OCR", ["4", "3", "2", "2"]), extra=ours))
    assert {f.kind for f in forecasts} == {"actual"}  # forecasts need column-specific attribution
    assert {r.code for r in rejections} == {"actual_or_forecast_unstated"}


def test_a_short_bank_name_does_not_match_inside_an_unrelated_word():
    notes = [(72, 665, "Source: Manzano Research")]
    forecasts, _ = run(
        page(line(686, "OCR (%)", ["4", "3", "2", "2"]), extra=notes), publisher=("anz",)
    )
    assert {f.author_role for f in forecasts} == {"third_party"}
    named = [(72, 665, "Source: ANZ Research, Stats NZ")]
    assert {
        f.author_role
        for f in run(
            page(line(686, "OCR (%)", ["4", "3", "2", "2"]), extra=named), publisher=("anz",)
        )[0]
    } == {"author"}


def test_a_row_in_a_unit_the_phase_does_not_read_is_refused_even_under_a_percent_caption():
    caption = [(72, 745, "Table 2: Forecasts (%)")]
    rows = [
        *line(686, "Unemployment (000s)", ["150", "151", "152", "153"]),
        *line(672, "OCR", ["4", "3", "2", "2"]),
    ]
    forecasts, rejections = run(page(rows, extra=caption))
    assert {f.indicator for f in forecasts} == {"ocr"}
    assert [(r.code, r.row) for r in rejections] == [("unsupported_unit", 0)]
