"""The ANZ forecasts workbook mapping (Phase 4AP). Fictional workbooks shaped like the masked
Phase 4AO structure: dates in column A from row 3, titles merged over blocks in row 1, unit headers in row 2, a bold
forecast tail, a legend note and an "as at" note below the table. Every figure is invented."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from nzstats.research.table_context import stored_context_rejection
from nzstats.research.xlsx_anz import INTERPRETER_VERSION, interpret_anz_workbook
from nzstats.research.xlsx_cells import read_cells

from .xlsx_support import C, Sheet, build

PUBLISHER = ("Fictional Bank",)
TITLE = "Fictional Bank Forecasts"
SHA = "c" * 64
QUARTERS = [
    date(2025 + (m - 1) // 12, (m - 1) % 12 + 1, 1) for m in range(3, 27, 3)
]  # Mar 2025 .. Dec 2026
FIRST_BOLD = 5  # index into QUARTERS: Jun 2026 onwards is the forecast tail
LEGEND = "Figures in bold are Fictional Bank forecasts"
AS_AT = "Data as at 5 November 2026"


def series(values, *, first_bold=FIRST_BOLD, fmt="0.0", bold_rows=None) -> dict[int, C]:
    """Column cells keyed by date index; `bold_rows` overrides the contiguous tail."""
    bold = set(range(first_bold, len(QUARTERS))) if bold_rows is None else set(bold_rows)
    return {i: C(v, bold=i in bold, fmt=fmt) for i, v in enumerate(values) if v is not None}


def data_sheet(
    name, blocks, *, notes=(LEGEND, AS_AT), dates=QUARTERS, state=None, date_fmt="d/mm/yyyy"
):
    """`blocks`: [(title, [(header, {date index: C})...])...], starting in column B."""
    cells: dict[tuple[int, int], C] = {}
    merges = []
    col = 2
    for title, columns in blocks:
        cells[(1, col)] = C(title)
        if len(columns) > 1:
            merges.append(f"{chr(64 + col)}1:{chr(64 + col + len(columns) - 1)}1")
        for header, column_cells in columns:
            if header is not None:
                cells[(2, col)] = C(header)
            for i, cell in column_cells.items():
                cells[(3 + i, col)] = cell
            col += 1
    for i, d in enumerate(dates):
        cells[(3 + i, 1)] = C(d, fmt=date_fmt)
    for j, note in enumerate(notes):
        cells[(3 + len(dates) + 2 + j, 1)] = C(note)
    return Sheet(name, cells, merges=tuple(merges), state=state)


GDP_QQ = [0.5, 0.4, 0.3, 0.6, 0.2, 0.1, 0.7, 0.8]
GDP_AA = [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.4, 2.5]
CPI_AA = [2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9]
UNEMP = [4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8]


def standard(**kw) -> list[Sheet]:
    growth = kw.pop(
        "growth",
        [("GDP", [("% q/q", series(GDP_QQ)), ("Annual % change", series(GDP_AA))])],
    )
    prices = kw.pop(
        "prices",
        [
            ("CPI inflation", [("Annual % change", series(CPI_AA))]),
            ("Unemployment rate", [("%", series(UNEMP))]),
        ],
    )
    return [
        Sheet("Cover"),
        data_sheet("Growth", growth, **kw.pop("growth_kw", {})),
        data_sheet("Prices", prices, **kw.pop("prices_kw", {})),
        *kw.pop("extra", []),
    ]


def run(sheets: list[Sheet], *, publisher=PUBLISHER):
    wb = read_cells(build(sheets, drawing_paragraphs=(("Fictional Bank",),)), isolate=False)
    return interpret_anz_workbook(
        wb, publisher_names=publisher, document_title=TITLE, workbook_sha256=SHA
    )


def codes(rejections) -> list[str]:
    return [r.code for r in rejections]


def test_the_interpreter_version_is_pinned():
    assert INTERPRETER_VERSION == "xlsx-anz-3"


def test_the_bold_tail_gives_forecasts_with_exact_evidence():
    forecasts, rejections = run(standard())
    assert rejections == ()
    qq = [f for f in forecasts if f.label == "GDP: % q/q"]
    assert [f.horizon for f in qq] == [
        "June 2026 quarter",
        "September 2026 quarter",
        "December 2026 quarter",
    ]
    assert [f.value for f in qq] == [Decimal("0.1"), Decimal("0.7"), Decimal("0.8")]
    first = qq[0]
    assert (first.indicator, first.kind, first.unit, first.author_role, first.missing) == (
        "gdp",
        "forecast",
        "percent",
        "author",
        False,
    )
    assert (first.page, first.table, first.row, first.col, first.raw_text, first.footnote) == (
        2,
        1,
        8,
        2,
        "0.1",
        None,
    )
    assert first.period_text == "2026-06-01"
    assert first.evidence == {
        "page": 2,
        "table": 1,
        "row": 8,
        "col": 2,
        "bbox": None,
        "absent": False,
        "sheet_position": 2,
        "cell": "B8",
        "cell_text": "0.1",
        "stored_text": "0.1",
        "number_format": "0.0",
        "bold": True,
        "workbook_sha256": SHA,
        "caption": "Growth",
        "row_label": "GDP: % q/q",
        "block_title": "GDP",
        "unit_header": "% q/q",
        "header_texts": ["2026-06-01"],
        "unit_texts": ["% q/q"],
        "notes": [],
        "boundary_note": LEGEND,
        "vintage_note": AS_AT,
        "boundary_row": 8,
        "document_title": TITLE,
        "publisher_names": list(PUBLISHER),
    }


def test_historical_cells_are_never_emitted():
    forecasts, _ = run(standard())
    historical = {(2, 3 + i) for i in range(FIRST_BOLD)} | {(3, 3 + i) for i in range(FIRST_BOLD)}
    assert all((f.page, f.row) not in historical for f in forecasts)
    assert all(f.evidence["bold"] for f in forecasts)
    assert {f.kind for f in forecasts} == {"forecast"}
    assert len(forecasts) == 4 * (len(QUARTERS) - FIRST_BOLD)


def test_horizons_follow_each_columns_basis():
    forecasts, _ = run(standard())
    by_label = {}
    for f in forecasts:
        by_label.setdefault(f.label, []).append(f.horizon)
    assert by_label["GDP: Annual % change"][0] == "year to June 2026"
    assert by_label["CPI inflation: Annual % change"][0] == "year to June 2026"
    assert by_label["Unemployment rate: %"] == [
        "June 2026 quarter",
        "September 2026 quarter",
        "December 2026 quarter",
    ]
    assert {f.indicator for f in forecasts} == {"gdp", "cpi_inflation", "unemployment"}


def test_a_level_column_is_refused_as_an_unsupported_unit():
    growth = [("GDP", [("% q/q", series(GDP_QQ)), ("$m", series([100.0] * 8))])]
    forecasts, rejections = run(standard(growth=growth))
    assert codes(rejections) == ["unsupported_unit"]
    assert (rejections[0].page, rejections[0].table, rejections[0].col) == (2, 1, 3)
    assert {f.col for f in forecasts if f.page == 2} == {2}


@pytest.mark.parametrize("header", ["Rate", "p.a.", "per annum"])
def test_ocr_without_a_stated_unit_is_refused(header):
    """An annual basis qualifier is not a unit (Phase 4AO §1.2)."""
    prices = [("OCR", [(header, series([3.0] * 8))])]
    forecasts, rejections = run(standard(prices=prices))
    assert codes(rejections) == ["unit_unstated"]
    assert not [f for f in forecasts if f.indicator == "ocr"]


def test_a_monthly_sheet_is_an_unsupported_period():
    months = [date(2026, m, 1) for m in range(1, 13)]
    monthly = data_sheet(
        "Rates",
        [("OCR", [("%", {i: C(3.0, bold=i > 8, fmt="0.00") for i in range(12)})])],
        dates=months,
    )
    forecasts, rejections = run(standard(extra=[monthly]))
    assert codes(rejections) == ["unsupported_period"]
    assert (rejections[0].page, rejections[0].table, rejections[0].col) == (4, None, None)
    assert not [f for f in forecasts if f.page == 4]


@pytest.mark.parametrize(
    "dates",
    [
        [date(2025, 3, 2), *QUARTERS[1:]],  # not the 1st
        [*QUARTERS[:3], *QUARTERS[4:], date(2027, 3, 1)],  # a gap of six months
        [QUARTERS[1], QUARTERS[0], *QUARTERS[2:]],  # not increasing
        [
            date(2025, 2, 1),
            *[date(d.year, d.month - 1, 1) for d in QUARTERS[1:]],
        ],  # Feb/May/Aug/Nov
    ],
)
def test_dates_must_be_quarter_months_three_apart(dates):
    _, rejections = run(standard(growth_kw={"dates": dates}))
    assert "unsupported_period" in codes(rejections)


def test_a_text_date_column_is_an_unsupported_period():
    _, rejections = run(
        standard(growth_kw={"dates": [d.isoformat() for d in QUARTERS], "date_fmt": "General"})
    )
    assert codes(rejections) == ["unsupported_period"]


@pytest.mark.parametrize(
    "notes",
    [(AS_AT,), ("Figures in bold are not forecasts", AS_AT), (LEGEND, "Forecasts in bold", AS_AT)],
)
def test_without_exactly_one_legend_the_marker_is_missing(notes):
    forecasts, rejections = run(standard(growth_kw={"notes": notes}))
    assert codes(rejections) == ["forecast_marker_missing"]
    assert not [f for f in forecasts if f.page == 2]


@pytest.mark.parametrize(
    "bold_rows",
    [
        [6, 7, 3],  # a bold cell inside the historical block
        [5, 7],  # a non-bold cell inside the forecast block
        [],  # no forecast at all
    ],
)
def test_an_unclear_boundary_refuses_the_whole_column(bold_rows):
    growth = [
        (
            "GDP",
            [("% q/q", series(GDP_QQ, bold_rows=bold_rows)), ("Annual % change", series(GDP_AA))],
        )
    ]
    forecasts, rejections = run(standard(growth=growth))
    assert codes(rejections) == ["forecast_boundary_unclear"]
    assert (rejections[0].page, rejections[0].col) == (2, 2)
    assert not [f for f in forecasts if f.page == 2 and f.col == 2]


def test_a_gap_inside_the_forecast_block_is_unclear_but_a_short_tail_is_not():
    gap = series(GDP_QQ)
    del gap[6]  # bold, absent, bold
    short = series([*GDP_QQ[:7], None])
    growth = [("GDP", [("% q/q", gap), ("Annual % change", short)])]
    forecasts, rejections = run(standard(growth=growth))
    assert codes(rejections) == ["forecast_boundary_unclear"]
    assert [f.horizon for f in forecasts if f.label == "GDP: Annual % change"] == [
        "year to June 2026",
        "year to September 2026",
    ]


def test_a_formula_in_the_tail_is_refused_and_not_evaluated():
    cells = series(GDP_QQ)
    cells[7] = C(0.8, bold=True, fmt="0.0", kind="formula")
    forecasts, rejections = run(standard(growth=[("GDP", [("% q/q", cells)])]))
    assert codes(rejections) == ["formula_cell"]
    assert (rejections[0].row, rejections[0].col) == (10, 2)
    assert [f.row for f in forecasts if f.page == 2] == [8, 9]


def test_a_float_artefact_gives_the_printed_figure():
    cells = series(GDP_QQ)
    cells[6] = C("2.0999999999999996", bold=True, fmt="0.0", kind="number")
    cells[7] = C("-0.15000000000000002", bold=True, fmt="0.00", kind="number")
    forecasts, _ = run(standard(growth=[("GDP", [("% q/q", cells)])]))
    got = {f.row: f for f in forecasts if f.page == 2}
    assert (got[9].value, got[9].raw_text, got[9].evidence["stored_text"]) == (
        Decimal("2.1"),
        "2.1",
        "2.0999999999999996",
    )
    assert (got[10].value, got[10].raw_text) == (Decimal("-0.15"), "-0.15")


@pytest.mark.parametrize(
    ("stored", "fmt", "shown"),
    [
        ("0.25", "0.0", "0.3"),
        ("0.14999999999999999", "0.0", "0.2"),  # Excel rounds to 15 significant digits first
        ("-0.25", "0.0", "-0.3"),
        ("1234.5", "#,##0.0", "1,234.5"),
        ("3", "0", "3"),
        ("2.5", "General", "2.5"),
        ("1.5", "0.0;-0.0", "1.5"),
    ],
)
def test_printed_precision_follows_the_number_format(stored, fmt, shown):
    cells = series(GDP_QQ)
    cells[7] = C(stored, bold=True, fmt=fmt, kind="number")
    forecasts, rejections = run(standard(growth=[("GDP", [("% q/q", cells)])]))
    assert rejections == ()
    assert [f.raw_text for f in forecasts if f.row == 10 and f.page == 2] == [shown]


@pytest.mark.parametrize(
    ("stored", "fmt"),
    [
        ("0.021", "0.0%"),
        ("1.5", "0.0_);(0.0)"),
        ("2.0999999999999996", "General"),
        ("46082", "d/mm/yyyy"),
    ],
)
def test_unsupported_number_formats_are_refused(stored, fmt):
    cells = series(GDP_QQ)
    cells[7] = C(stored, bold=True, fmt=fmt, kind="number")
    _, rejections = run(standard(growth=[("GDP", [("% q/q", cells)])]))
    assert codes(rejections) == ["unsupported_number_format"]


def test_a_text_or_bool_in_the_tail_is_refused_never_guessed():
    cells = series(GDP_QQ)
    cells[6] = C("about 1", bold=True)
    cells[7] = C(True, bold=True)
    _, rejections = run(standard(growth=[("GDP", [("% q/q", cells)])]))
    assert codes(rejections) == ["unrecognised_suffix", "unsupported_number_format"]


@pytest.mark.parametrize(
    ("source", "role"),
    [
        ("RBNZ", "third_party"),
        ("Independent Analytics", "third_party"),
        ("Independent\nAnalytics", "third_party"),
        ("Fictional Bank", "author"),
        ("Fictional\nBank", "author"),
    ],
)
def test_a_source_note_determines_authorship_even_for_an_unknown_forecaster(source, role):
    forecasts, rejections = run(standard(growth_kw={"notes": (LEGEND, AS_AT, f"Source: {source}")}))
    growth = [f for f in forecasts if f.page == 2]
    assert not rejections and len(growth) == 6
    assert {f.author_role for f in growth} == {role}
    assert {f.author_role for f in forecasts if f.page == 3} == {"author"}


@pytest.mark.parametrize("forecaster", ["Treasury", "World\nBank"])
def test_a_legend_naming_another_forecaster_makes_the_figures_third_party(forecaster):
    forecasts, _ = run(
        standard(growth_kw={"notes": (f"Figures in bold are {forecaster} forecasts", AS_AT)})
    )
    assert {f.author_role for f in forecasts if f.page == 2} == {"third_party"}


@pytest.mark.parametrize(
    ("legend", "as_at"),
    [
        (LEGEND, AS_AT),
        ("Figures in bold are Fictional\nBank forecasts", AS_AT),
        ("Baseline forecasts are shown in bold", "Updated: 2026-11-05"),
        ("Bold font denotes Fictional Bank central projections", "Last updated on 05/11/2026"),
        (
            "Figures in bold are Fictional Bank's forecasts",
            "Fictional Bank data as at 5th November 2026",
        ),
        (f"  {LEGEND}  ", f"  {AS_AT}  "),
    ],
)
def test_structural_notes_accept_baseline_markers_authors_and_dates(legend, as_at):
    forecasts, rejections = run(standard(growth_kw={"notes": (legend, as_at)}))
    assert not rejections
    growth = [f for f in forecasts if f.page == 2]
    assert len(growth) == 6
    for f in growth:
        assert f.author_role == "author"
        assert (f.evidence["boundary_note"], f.evidence["vintage_note"]) == (legend, as_at)
        assert stored_context_rejection(f.label, f.evidence) is None


@pytest.mark.parametrize(
    ("legend", "as_at", "expected"),
    [
        ("Figures in bold are ANZ downside scenario forecasts", AS_AT, "scenario_context"),
        ("Figures in bold are Australian forecasts", AS_AT, "unsupported_geography"),
        ("Figures in bold are forecasts for the world", AS_AT, "unsupported_geography"),
        (LEGEND, f"{AS_AT} (alternative stress case)", "scenario_context"),
        (LEGEND, f"{AS_AT} – for China", "unsupported_geography"),
        (LEGEND, f"{AS_AT} – for youth", "unsupported_scope"),
        (LEGEND, f"{AS_AT} – for the urban population", "unsupported_context"),
        (LEGEND, f"{AS_AT} – upside", "scenario_context"),
        (LEGEND, f"{AS_AT}. Source: unknown restricted population", "unsupported_context"),
        ("Figures in bold are forecasts in basis points", AS_AT, "contradictory_unit"),
    ],
)
def test_structural_qualifiers_are_refused_in_both_consumers(legend, as_at, expected):
    baseline, _ = run(standard())
    forecasts, rejections = run(standard(growth_kw={"notes": (legend, as_at)}))
    assert not [f for f in forecasts if f.page == 2]
    assert [(r.page, r.code) for r in rejections] == [(2, expected), (2, expected)]
    for f in baseline:
        if f.page == 2:
            prior_evidence = {**f.evidence, "boundary_note": legend, "vintage_note": as_at}
            assert stored_context_rejection(f.label, prior_evidence) == expected


def test_stored_vintage_qualifiers_are_checked_without_a_boundary_note():
    evidence = {"vintage_note": f"{AS_AT} – downside scenario"}
    assert stored_context_rejection("GDP: % q/q", evidence) == "scenario_context"


def test_a_hidden_sheet_is_refused():
    forecasts, rejections = run(standard(growth_kw={"state": "hidden"}))
    assert codes(rejections) == ["hidden_sheet"]
    assert (rejections[0].page, rejections[0].table) == (2, None)
    assert not [f for f in forecasts if f.page == 2]


@pytest.mark.parametrize(
    ("title", "code"),
    [("Fictional exports", "unmapped_row"), ("GDP and CPI", "ambiguous_indicator")],
)
def test_unmapped_and_ambiguous_blocks_are_refused_once_per_column(title, code):
    growth = [(title, [("% q/q", series(GDP_QQ)), ("Annual % change", series(GDP_AA))])]
    forecasts, rejections = run(standard(growth=growth))
    assert codes(rejections) == [code, code]
    assert not [f for f in forecasts if f.page == 2]


def test_two_distinct_blocks_naming_one_indicator_are_both_refused_as_ambiguous():
    """Phase 4AP pilot: the real workbook holds several distinct series that each name GDP (or CPI). Only one can be
    the headline measure and the mapping cannot tell which, so every such column is refused, never picked."""
    growth = [
        ("Fictional GDP", [("% q/q", series(GDP_QQ)), ("Annual % change", series(GDP_AA))]),
        ("Fictional GDP subset", [("% q/q", series(GDP_QQ))]),
    ]
    forecasts, rejections = run(standard(growth=growth))
    assert codes(rejections) == ["ambiguous_indicator"] * 3
    assert {f.indicator for f in forecasts} == {"cpi_inflation", "unemployment"}


def test_the_same_indicator_on_two_sheets_under_distinct_titles_is_ambiguous():
    extra = data_sheet(
        "Inflation", [("Fictional CPI variant", [("Annual % change", series(CPI_AA))])]
    )
    forecasts, rejections = run(standard(extra=[extra]))
    assert codes(rejections) == ["ambiguous_indicator"] * 2
    assert {f.indicator for f in forecasts} == {"gdp", "unemployment"}


def test_one_block_title_repeated_over_its_columns_is_not_ambiguous():
    forecasts, rejections = run(standard())
    assert rejections == () and {f.indicator for f in forecasts} == {
        "gdp",
        "cpi_inflation",
        "unemployment",
    }


def test_a_number_column_outside_any_block_is_unmapped():
    sheets = standard()
    sheets[1].cells.update(
        {(3 + i, 4): C(1.0, bold=i >= FIRST_BOLD, fmt="0.0") for i in range(len(QUARTERS))}
    )
    _, rejections = run(sheets)
    assert [(r.code, r.col) for r in rejections] == [("unmapped_row", 4)]


def test_unknown_context_is_refused_not_dropped():
    forecasts, rejections = run(
        standard(growth_kw={"notes": (LEGEND, AS_AT, "Mystery adjustment applied")})
    )
    assert set(codes(rejections)) == {"unsupported_context"}
    assert not [f for f in forecasts if f.page == 2]


def test_a_sheet_without_a_column_a_date_run_is_an_unsupported_period():
    odd = Sheet("Notes", {(1, 1): C("Fictional text"), (5, 2): C(1.0)})
    _, rejections = run(standard(extra=[odd]))
    assert [(r.code, r.page) for r in rejections] == [("unsupported_period", 4)]


def test_an_empty_sheet_produces_nothing():
    forecasts, rejections = run([Sheet("Cover")])
    assert forecasts == () and rejections == ()


@pytest.mark.parametrize(
    ("stored", "fmt"),
    [("1E+999999", "General"), ("1E+999999", "0.0"), ("1E+30", "0.0"), ("1E-999999", "0.00")],
)
def test_extreme_exponents_are_refused_without_expanding_them(stored, fmt):
    cells = series(GDP_QQ)
    cells[7] = C(stored, bold=True, fmt=fmt, kind="number")
    _, rejections = run(standard(growth=[("GDP", [("% q/q", cells)])]))
    assert codes(rejections) == ["unsupported_number_format"]


def test_a_title_merge_wider_than_the_data_only_covers_occupied_columns():
    sheets = standard(growth=[("GDP", [("% q/q", series(GDP_QQ))])])
    sheets[1].merges = ("B1:XFD1",)
    forecasts, rejections = run(sheets)
    assert rejections == ()
    assert {f.col for f in forecasts if f.page == 2} == {2}
