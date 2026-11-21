"""ANZ's forecasts workbook as table forecasts (Phase 4AP): fixed rules, no guessing.

Shaped by the masked Phase 4AO structure (docs/phase-4ao-anz-workbook.md §1): one vertical time series per sheet, dates
in column A from row 3, series titles in row 1 (merged over blocks of columns), unit headers in row 2, and below the table
one note saying that figures in bold are forecasts plus one dated "as at" note. A date on the 1st of March, June,
September or December stands for that calendar quarter (the GDP boundary one quarter before CPI and labour fits the
release calendar on the workbook's date).

Only bold cells are forecasts, and only when the column turns bold once and stays bold: anything else refuses the whole
column, never splits it. Non-bold (historical) cells are neither emitted nor stored; workbook actuals are never official
data. A unit, period, indicator or author is never inferred; each refusal is a fixed code, recorded once per sheet or
column where it applies to the whole of it. The figure is the text Excel prints under the cell's number format; the
stored text stays in the evidence. A formula is never evaluated. All workbook text is untrusted data.

The block title and unit header form the label (the identity, as a PDF row label does). The context includes the
sheet name, notes, period and unit header. The legend and the "as at" note are kept under their own evidence keys
and checked for qualifiers as well as authorship.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation

from nzstats.research.table_context import stored_context_rejection
from nzstats.research.table_forecast import (
    TableForecast,
    _horizon,
    _indicator,
    _source_names_other_forecaster,
    _third_party,
)
from nzstats.research.table_grid import Rejection
from nzstats.research.table_parse import Period, parse_value, unit_of_text
from nzstats.research.xlsx_cells import WorkbookCells, XCell, XSheet, serial_date

INTERPRETER_VERSION = "xlsx-anz-3"

_TITLE_ROW, _HEADER_ROW, _FIRST_DATE_ROW, _DATE_COL = 1, 2, 3, 1
_QUARTER_MONTHS = frozenset({3, 6, 9, 12})
_LEGEND_FORECAST = re.compile(r"\b(?:forecasts?|projections?|projected)\b", re.IGNORECASE)
_LEGEND_BOLD = re.compile(r"\bbold\b", re.IGNORECASE)
# A legend that negates, excepts or names another style is not the plain "bold = forecast" statement.
_LEGEND_REFUSED = re.compile(
    r"\b(?:not|non|except|excluding|unless|italics?|underlined?|shaded|shading|colou?red|actuals?|historical)\b",
    re.IGNORECASE,
)
_AS_AT = re.compile(r"\bas\s+at\b|\bupdated\b", re.IGNORECASE)
# General, 0, 0.0..., #,##0 and #,##0.0..., with an optional negative section of the same shape and precision.
_NUMBER_FORMAT = re.compile(
    r"(?P<pos>(?:#,##)?0(?:\.0+)?)(?:;(?:-|\\-)(?P<neg>(?:#,##)?0(?:\.0+)?))?"
)
_GENERAL_DIGITS = (
    10  # beyond this many significant digits Excel's General rendering is not the stored text
)
_EXCEL_DIGITS = Context(prec=15, rounding=ROUND_HALF_UP)  # Excel keeps 15 significant digits
_MIN_EXPONENT, _MAX_EXPONENT = (
    -30,
    15,
)  # a rate or growth figure is never outside this (a computed zero may be ~1e-17)


def _a1(row: int, col: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def _display(cell: XCell) -> tuple[str | None, str | None]:
    """(printed text, None) or (None, refusal code) for a cell in a forecast block."""
    if cell.kind == "formula":
        return None, "formula_cell"
    if cell.kind in ("text", "error"):
        return cell.text, None  # parse_value decides: a dash is missing, anything else is refused
    if cell.kind != "number" or cell.is_date:
        return None, "unsupported_number_format"
    try:
        stored = Decimal(cell.text)
    except InvalidOperation:
        return None, "unsupported_number_format"
    # Bounded before any rendering: a hostile exponent must not expand into a huge string or overflow the context.
    if not stored.is_finite() or not _MIN_EXPONENT <= stored.adjusted() <= _MAX_EXPONENT:
        return None, "unsupported_number_format"
    if cell.number_format == "General":
        if len(stored.normalize().as_tuple().digits) > _GENERAL_DIGITS:
            return None, "unsupported_number_format"
        return format(stored.normalize(), "f"), None
    match = _NUMBER_FORMAT.fullmatch(cell.number_format)
    if match is None or (match["neg"] is not None and match["neg"] != match["pos"]):
        return None, "unsupported_number_format"
    places = len(match["pos"].partition(".")[2])
    try:
        value = _EXCEL_DIGITS.plus(stored).quantize(
            Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP
        )
    except InvalidOperation:
        return None, "unsupported_number_format"
    if value == 0:
        value = abs(value)  # Excel prints 0.0, never -0.0
    return format(value, ",f" if match["pos"].startswith("#") else "f"), None


def _date_rows(sheet: XSheet, date1904: bool) -> list[tuple[int, date]] | None:
    """Column A's dates from row 3, when they are consecutive calendar quarters (1st of Mar/Jun/Sep/Dec); else None."""
    rows: list[tuple[int, date]] = []
    row = _FIRST_DATE_ROW
    while (
        (cell := sheet.cells.get((row, _DATE_COL))) is not None
        and cell.kind == "number"
        and cell.is_date
    ):
        d = serial_date(cell.text, date1904)
        if d is None:
            return None
        rows.append((row, d))
        row += 1
    later = [
        c
        for (r, col), c in sheet.cells.items()
        if col == _DATE_COL and r >= row and c.kind == "number" and c.is_date
    ]
    if len(rows) < 2 or later:
        return None
    for (_, a), (_, b) in zip(rows, rows[1:], strict=False):
        if (b.year * 12 + b.month) - (a.year * 12 + a.month) != 3:
            return None
    if any(d.day != 1 or d.month not in _QUARTER_MONTHS for _, d in rows):
        return None
    return rows


def _notes(sheet: XSheet, last_row: int) -> tuple[str | None, str | None, list[str]] | None:
    """(legend, "as at" note, other notes) from the text below the table; None without exactly one plain legend."""
    texts = [
        c.text
        for (r, _c), c in sorted(sheet.cells.items())
        if r > last_row and c.kind == "text" and c.text.strip()
    ]
    legends = [t for t in texts if _LEGEND_FORECAST.search(t) and _LEGEND_BOLD.search(t)]
    if len(legends) != 1 or _LEGEND_REFUSED.search(legends[0]):
        return None
    as_at = [t for t in texts if t not in legends and _AS_AT.search(t)]
    vintage = as_at[0] if len(as_at) == 1 else None
    others = [t.strip() for t in texts if t not in legends and t != vintage]
    return legends[0], vintage, others


def _blocks(sheet: XSheet) -> tuple[dict[int, tuple[int, str]], set[int]]:
    """({column: (block number, title)}, columns refused as unmapped): titles in row 1, merged or single."""
    starts: dict[int, int] = {}
    for r1, c1, r2, c2 in sheet.merges:
        if r1 == _TITLE_ROW and r2 == _TITLE_ROW:
            starts[c1] = c2
    for r, c in sorted(sheet.cells):
        if r == _TITLE_ROW and c != _DATE_COL and c not in starts:
            if not any(c1 < c <= c2 for c1, c2 in starts.items()):
                starts[c] = c
    columns: dict[int, tuple[int, str]] = {}
    unmapped: set[int] = set()
    occupied = sorted({c for (_r, c) in sheet.cells if c != _DATE_COL})
    for number, (first, last) in enumerate(sorted(starts.items()), start=1):
        title = sheet.cells.get((_TITLE_ROW, first))
        for c in (
            c for c in occupied if first <= c <= last
        ):  # a merge wider than the data adds no columns
            if title is None or title.kind != "text" or not title.text.strip():
                unmapped.add(c)
            else:
                columns[c] = (number, title.text.strip())
    return columns, unmapped


def _data_columns(sheet: XSheet, rows: list[tuple[int, date]]) -> set[int]:
    """Columns with cells inside the recognised date range, excluding the date column."""
    first, last = rows[0][0], rows[-1][0]
    return {c for r, c in sheet.cells if c != _DATE_COL and first <= r <= last}


def _header(sheet: XSheet, col: int) -> str:
    """The column's unit header (row 2), or "" when it holds no text."""
    cell = sheet.cells.get((_HEADER_ROW, col))
    return cell.text.strip() if cell is not None and cell.kind == "text" else ""


def _forecast_rows(
    sheet: XSheet, col: int, rows: list[tuple[int, date]]
) -> list[tuple[int, date, XCell]] | None:
    """The column's bold tail, or None when the bold cells are not one block that runs to the last value."""
    present = [(r, d, sheet.cells[(r, col)]) for r, d in rows if (r, col) in sheet.cells]
    first = next((i for i, (_, _, c) in enumerate(present) if c.bold), None)
    if first is None:
        return None
    tail = present[first:]
    if not all(c.bold for _, _, c in tail):
        return None  # a non-bold cell inside the forecast block, or a bold one inside the history
    index = {r: i for i, (r, _) in enumerate(rows)}
    if index[tail[-1][0]] - index[tail[0][0]] + 1 != len(tail):
        return None  # a gap inside the forecast block
    return tail


def interpret_anz_workbook(
    wb: WorkbookCells, *, publisher_names: Sequence[str], document_title: str, workbook_sha256: str
) -> tuple[tuple[TableForecast, ...], tuple[Rejection, ...]]:
    forecasts: list[TableForecast] = []
    rejections: list[Rejection] = []
    readable = []
    for sheet in wb.sheets:
        if sheet.state != "visible":
            rejections.append(Rejection("hidden_sheet", sheet.position))
            continue
        if not sheet.cells:
            continue  # a cover or empty sheet holds no table
        rows = _date_rows(sheet, wb.date1904)
        if rows is None:
            rejections.append(Rejection("unsupported_period", sheet.position))
            continue
        notes = _notes(sheet, rows[-1][0])
        if notes is None:
            rejections.append(Rejection("forecast_marker_missing", sheet.position))
            continue
        readable.append((sheet, rows, notes, *_blocks(sheet)))
    # Distinct block titles that name one indicator (a headline series beside its components or variants): the
    # mapping cannot tell which is the headline measure, so all of them are refused, never one picked.
    titles: dict[str, set[str]] = {}
    for sheet, *_, blocks, _ in readable:
        for col, (_block, title) in blocks.items():
            found = _indicator(f"{title}: {_header(sheet, col)}")
            if len(found) == 1:
                titles.setdefault(next(iter(found)), set()).add(" ".join(title.split()).casefold())
    ambiguous = {indicator for indicator, seen in titles.items() if len(seen) > 1}
    for sheet, rows, (legend, vintage, others), blocks, unmapped in readable:
        for col in sorted(_data_columns(sheet, rows) | blocks.keys() | unmapped):
            if col not in blocks:
                rejections.append(Rejection("unmapped_row", sheet.position, None, None, col))
                continue
            block, title = blocks[col]
            if _indicator(f"{title}: {_header(sheet, col)}") & ambiguous:
                rejections.append(
                    Rejection("ambiguous_indicator", sheet.position, block, None, col)
                )
                continue
            forecasts_or_code = _column(
                sheet, col, block, title, rows, legend, vintage, others,
                publisher_names=publisher_names, document_title=document_title, workbook_sha256=workbook_sha256,
            )  # fmt: skip
            for item in forecasts_or_code:
                (forecasts if isinstance(item, TableForecast) else rejections).append(item)
    return tuple(forecasts), tuple(rejections)


def _column(
    sheet: XSheet,
    col: int,
    block: int,
    title: str,
    rows: list[tuple[int, date]],
    legend: str,
    vintage: str | None,
    others: list[str],
    *,
    publisher_names: Sequence[str],
    document_title: str,
    workbook_sha256: str,
) -> list[TableForecast | Rejection]:
    at = (sheet.position, block, None, col)
    header = _header(sheet, col)
    label = f"{title}: {header}"
    found = _indicator(label)
    if len(found) != 1:
        return [Rejection("ambiguous_indicator" if found else "unmapped_row", *at)]
    (indicator,) = found
    unit, code = unit_of_text(title, header, sheet.name)
    if unit is None:
        return [Rejection(code or "unit_unstated", *at)]
    tail = _forecast_rows(sheet, col, rows)
    if tail is None:
        return [Rejection("forecast_boundary_unclear", *at)]
    notes = (legend, vintage or "", *others)
    role_text = " ".join((label, sheet.name, document_title, *notes))
    role = (
        "third_party"
        if _source_names_other_forecaster(notes, publisher_names)
        or _third_party(" ".join(role_text.split()), publisher_names)
        else "author"
    )
    out: list[TableForecast | Rejection] = []
    for row, day, cell in tail:
        period = Period("month_end", day.year, day.month)
        horizon, code = _horizon(period, label, indicator)
        if horizon is None:
            return [Rejection(code or "unparsed_period", *at)]
        period_text = day.isoformat()
        evidence = {
            "caption": sheet.name,
            "header_texts": [period_text],
            "unit_texts": [header],
            "notes": list(others),
            "boundary_note": legend,
            "vintage_note": vintage,
            "document_title": document_title,
            "publisher_names": list(publisher_names),
        }
        if code := stored_context_rejection(label, evidence):
            return [Rejection(code, *at)]
        shown, code = _display(cell)
        if shown is None:
            out.append(
                Rejection(code or "unsupported_number_format", sheet.position, block, row, col)
            )
            continue
        parsed = parse_value(shown)
        if parsed.kind == "reject" or parsed.footnote:
            out.append(
                Rejection(parsed.code or "footnote_unresolved", sheet.position, block, row, col)
            )
            continue
        out.append(
            TableForecast(
                table=block,
                page=sheet.position,
                row=row,
                col=col,
                indicator=indicator,
                label=label,
                period_text=period_text,
                horizon=horizon,
                kind="forecast",
                unit=unit,
                raw_text=parsed.raw,
                value=parsed.value,
                missing=parsed.kind == "missing",
                author_role=role,  # type: ignore[arg-type]
                footnote=None,
                evidence={
                    **evidence,
                    "page": sheet.position,
                    "table": block,
                    "row": row,
                    "col": col,
                    "bbox": None,
                    "absent": False,
                    "sheet_position": sheet.position,
                    "cell": _a1(row, col),
                    "cell_text": shown,
                    "stored_text": cell.text,
                    "number_format": cell.number_format,
                    "bold": cell.bold,
                    "workbook_sha256": workbook_sha256,
                    "row_label": label,
                    "block_title": title,
                    "unit_header": header,
                    "boundary_row": tail[0][0],
                },
            )
        )
    return out
