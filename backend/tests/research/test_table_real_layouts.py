"""Phase 4AG: tables drawn the way real reports are drawn (SYNTHETIC FIXTURE text only).

Every baseline is ONE `BT..ET`; labels use kerned `TJ` arrays; fonts are scaled through the matrix; footnote markers are raised;
numbers are drawn in pieces; some pages set prose beside a table. Each case states what must be read and what must be refused.
"""

from decimal import Decimal

from nzstats.research.extract import ExtractionLimits
from nzstats.research.table_forecast import interpret
from nzstats.research.table_grid import find_tables
from nzstats.research.table_words import extract_words

from .pdf_stream_support import raw_pdf, row

COLS = [250, 310, 370, 430]
HEAD = ["Dec-25", "Mar-26", "Jun-26", "Sep-26"]
NAMES = ("Example Bank",)


def read(*pages: str, names=NAMES):
    words = extract_words(raw_pdf(list(pages)), ExtractionLimits(), isolate=False)
    tables, grid_rejections = find_tables(words)
    forecasts, rejections = interpret(tables, publisher_names=names)
    return forecasts, tuple(r.code for r in (*grid_rejections, *rejections))


def table(rows: list[str], *, groups=None, head=HEAD, cols=COLS, caption: str | None = None) -> str:
    out = [row(740, [(72, caption)])] if caption else []
    groups = [(cols[0], "Actual"), (cols[2], "Forecast")] if groups is None else groups
    if groups:
        out.append(row(714, groups))
    out.append(row(700, list(zip(cols, head, strict=True))))
    return "\n".join([*out, *rows])


def data(y: float, label: str, values: list[str | None], cols=COLS) -> str:
    cells = [(72, label)] + [(x, v) for x, v in zip(cols, values, strict=True) if v is not None]
    return row(y, cells)


def figures(forecasts):
    return {(f.indicator, f.horizon, f.kind): (f.raw_text, f.value) for f in forecasts}


def test_a_real_style_outlook_page_reads_exactly_and_marks_actuals():
    rows = [
        data(686, "OCR (%)", ["4.25", "3.75", "3.25", "3.00"]),
        # label kerned inside a TJ array, as typesetters write it
        "BT /F1 10 Tf 72 672 Td [(Annual CP)-30(I inflation \\(%\\))] TJ ET "
        + row(672, [(x, v) for x, v in zip(COLS, ["4.0", "3.1", "2.6", "2.2"], strict=True)]),
        data(658, "Quarterly GDP growth (%)", ["0.2", "-0.1", "0.0", "0.6"]),
        data(644, "Unemployment rate (%)", ["4.8", "5.0", "–", "5.0"]),
    ]
    forecasts, codes = read(table(rows, caption="Table 1: Key economic forecasts"))
    assert codes == ()
    got = figures(forecasts)
    assert got[("ocr", "June 2026 quarter", "forecast")] == ("3.25", Decimal("3.25"))
    assert got[("ocr", "December 2025 quarter", "actual")] == ("4.25", Decimal("4.25"))
    assert got[("cpi_inflation", "year to September 2026", "forecast")] == ("2.2", Decimal("2.2"))
    assert got[("gdp", "March 2026 quarter", "actual")] == ("-0.1", Decimal("-0.1"))
    assert got[("gdp", "June 2026 quarter", "forecast")] == ("0.0", Decimal("0.0"))
    missing = [f for f in forecasts if f.missing]
    assert [(f.indicator, f.horizon) for f in missing] == [("unemployment", "June 2026 quarter")]
    assert all(f.value is None for f in missing)


def test_a_figure_drawn_in_two_pieces_is_one_figure():
    rows = [
        "BT /F1 10 Tf 72 686 Td (OCR \\(%\\)) Tj ET "
        + " ".join(
            f"BT /F1 10 Tf {x} 686 Td ({a}) Tj ({b}) Tj ET"
            for x, (a, b) in zip(
                COLS, [("4.", "25"), ("3.", "75"), ("3.", "25"), ("3.", "00")], strict=True
            )
        )
    ]
    forecasts, codes = read(table(rows))
    assert codes == ()
    assert figures(forecasts)[("ocr", "June 2026 quarter", "forecast")] == ("3.25", Decimal("3.25"))


def test_a_raised_footnote_marker_refuses_that_figure_and_only_that_figure():
    base = data(686, "OCR (%)", ["4.25", "3.75", "3.25", "3.00"])
    marker = (
        "BT /F1 6 Tf 1 0 0 1 389.5 690 Tm (1) Tj ET"  # raised, small, touching the Jun-26 figure
    )
    forecasts, codes = read(table([base + "\n" + marker]))
    assert codes == ("footnote_unresolved",)
    got = figures(forecasts)
    assert ("ocr", "June 2026 quarter", "forecast") not in got
    assert got[("ocr", "September 2026 quarter", "forecast")] == ("3.00", Decimal("3.00"))


def test_a_scaled_font_reads_the_same_as_plain_text():
    def scaled(y, cells):  # one unit font, a ten times matrix
        return "BT /F1 1 Tf " + " ".join(f"10 0 0 10 {x} {y} Tm ({t}) Tj" for x, t in cells) + " ET"

    rows = [
        scaled(686, [(72, "OCR (%)"), *zip(COLS, ["4.25", "3.75", "3.25", "3.00"], strict=True)])
    ]
    head = scaled(700, list(zip(COLS, HEAD, strict=True)))
    groups = scaled(714, [(250, "Actual"), (370, "Forecast")])
    forecasts, codes = read("\n".join([groups, head, *rows]))
    assert codes == ()
    assert figures(forecasts)[("ocr", "September 2026 quarter", "forecast")] == (
        "3.00",
        Decimal("3.00"),
    )


def test_prose_set_beside_table_rows_is_reported_not_silently_dropped():
    rows = [
        data(686, "OCR (%)", ["4.25", "3.75", "3.25", "3.00"])
        + "\n"
        + row(686, [(500, "Inflation is")]),
        data(672, "Annual CPI inflation (%)", ["4.0", "3.1", "2.6", "2.2"])
        + "\n"
        + row(672, [(500, "expected to ease")]),
    ]
    forecasts, codes = read(table(rows))
    assert not forecasts
    assert codes.count("mixed_layout") == 2


def test_a_wide_table_keeps_every_figure_in_its_own_column():
    cols = [150 + 36 * i for i in range(12)]
    head = [f"{('Mar', 'Jun', 'Sep', 'Dec')[i % 4]}-{26 + i // 4}" for i in range(12)]
    values = [f"{1 + i / 10:.1f}" for i in range(12)]
    rows = [data(686, "OCR (%)", values, cols)]
    forecasts, codes = read(table(rows, groups=[(cols[0], "Forecast")], head=head, cols=cols))
    ocr = sorted(f.raw_text for f in forecasts if f.indicator == "ocr")
    assert codes == ()
    assert ocr == sorted(values)


def test_a_scenario_column_is_refused_and_the_central_columns_survive():
    cols = [250, 310, 370, 430]
    groups = row(714, [(250, "Actual"), (370, "Forecast"), (430, "Downside")])
    head = row(700, list(zip(cols, HEAD, strict=True)))
    rows = [data(686, "OCR (%)", ["4.25", "3.75", "3.25", "2.50"])]
    forecasts, codes = read("\n".join([groups, head, *rows]))
    assert "scenario_column" in codes
    assert ("ocr", "September 2026 quarter", "forecast") not in figures(forecasts)


def test_a_caption_naming_another_forecaster_makes_the_figures_third_party():
    rows = [data(686, "OCR (%)", ["4.25", "3.75", "3.25", "3.00"])]
    forecasts, _ = read(table(rows, caption="Table 2: Treasury forecasts"))
    assert forecasts and {f.author_role for f in forecasts} == {"third_party"}
