"""Table rows as forecasts (Phase 4AF): what a row means, and the cases where it is refused rather than guessed."""

from decimal import Decimal

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
    assert INTERPRETER_VERSION == "tables-1"
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
