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

Phase 4AR (`xlsx-anz-4`): with the owner's reviewed mapping (`xlsx_mapping`), only the listed columns may stand for
their indicator; every other column naming a mapped indicator is `not_canonical_series`, never a second copy. A listed
column must still match its recorded structure exactly and pass every rule above. The mapping never supplies a word the
workbook does not print: its basis must equal the basis the column states, an unemployment unit comes only from a
verified note on the same sheet, and a sheet name reviewed as editorial is dropped from the context rule for that
exact sheet only. Without a mapping, the result is exactly `xlsx-anz-3`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from typing import Any

from nzstats.research.compare import _ANNUAL, _ANNUAL_AVERAGE, _QUARTERLY, _THROUGH_YEAR
from nzstats.research.table_context import stored_context_rejection
from nzstats.research.table_forecast import (
    _RATE_INDICATORS,
    TableForecast,
    _horizon,
    _indicator,
    _source_names_other_forecaster,
    _third_party,
)
from nzstats.research.table_grid import Rejection
from nzstats.research.table_parse import Period, parse_value, unit_of_text
from nzstats.research.xlsx_cells import WorkbookCells, XCell, XSheet, serial_date
from nzstats.research.xlsx_mapping import (
    SCHEMA,
    AnzMapping,
    MappingEntry,
    MappingRefused,
    UnitEvidence,
    cell_position,
    column_number,
    parse_mapping,
)

INTERPRETER_VERSION = "xlsx-anz-3"  # no mapping
MAPPED_INTERPRETER_VERSION = "xlsx-anz-4"  # with the owner's reviewed mapping

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


def _norm(text: str) -> str:
    return " ".join(text.split())


def _sheet_at(wb: WorkbookCells, position: int) -> XSheet | None:
    return next((s for s in wb.sheets if s.position == position), None)


def _text_at(wb: WorkbookCells, position: int, a1: str) -> str | None:
    """The exact text of a text cell, or None when there is no such sheet, cell or text."""
    sheet, at = _sheet_at(wb, position), cell_position(a1)
    cell = None if sheet is None or at is None else sheet.cells.get(at)
    return cell.text if cell is not None and cell.kind == "text" and cell.text.strip() else None


def mapping_refusal(mapping: AnzMapping, wb: WorkbookCells, workbook_sha256: str) -> str | None:
    """A fixed code when the whole mapping does not belong to this workbook; None when it does."""
    if mapping.workbook_sha256 != workbook_sha256:
        return "mapping_hash_mismatch"
    published = mapping.published_on
    if published is not None:
        text = _text_at(wb, published["sheet"], published["cell"])
        if text is None or _norm(text) != _norm(published["text"]):
            return "mapping_structure_mismatch"
    return None


def _stated_basis(label: str, indicator: str) -> str | None:
    """The growth basis the column's own title and header state, as `_horizon` reads it; None when unclear."""
    average = bool(_ANNUAL_AVERAGE.search(label))
    annual = bool(_ANNUAL.search(label) or _THROUGH_YEAR.search(label))
    quarterly = bool(_QUARTERLY.search(label))
    if quarterly and (annual or average):
        return None
    if average:
        return "annual_average"
    if annual:
        return "annual"
    if quarterly:
        return "quarterly"
    return (
        "quarterly" if indicator in _RATE_INDICATORS else None
    )  # `_horizon` reads a rate by its quarter


def _entry_matches(
    entry: MappingEntry, sheet: XSheet, blocks: dict[int, tuple[int, str]], col: int
) -> bool:
    """The listed column is where, and what, the owner reviewed: whitespace is the only allowed difference."""
    return (
        _norm(sheet.name) == _norm(entry.sheet_name)
        and col in blocks
        and blocks[col][0] == entry.block
        and _norm(blocks[col][1]) == _norm(entry.block_title)
        and _norm(_header(sheet, col)) == _norm(entry.unit_header)
    )


def _evidence_unit(sheet: XSheet, evidence: UnitEvidence, last_row: int) -> str | None:
    """`percent` when the cited cell is a note below the table on this sheet (so the context rule reads it too), says
    exactly what was reviewed, and names percent alone."""
    at = cell_position(evidence.cell)
    below = at is not None and at[0] > last_row
    cell = None if not below or evidence.sheet != sheet.position else sheet.cells.get(at)
    if cell is None or cell.kind != "text" or _norm(cell.text) != _norm(evidence.text):
        return None
    return "percent" if unit_of_text(cell.text) == ("percent", None) else None


def mapping_from_positions(
    wb: WorkbookCells,
    *,
    workbook_sha256: str,
    decided_on: str,
    series: Sequence[tuple[str, int, int, str, str]],
    unit_evidence: tuple[int, str] | None,
    sheet_context: Sequence[tuple[int, str]],
    published: tuple[str, int, str] | None,
) -> bytes:
    """The owner's mapping file, built from positions only: every text in it is copied from the workbook here.

    `series`: (indicator, sheet, block, column letters, basis). `unit_evidence`: (sheet, A1) of the unemployment
    unit note. `sheet_context`: (sheet, classification). `published`: (YYYY-MM-DD, sheet, A1) or None.
    """

    def invalid_position() -> MappingRefused:
        return MappingRefused("mapping_position_invalid")

    entries: list[dict[str, Any]] = []
    for indicator, position, block, column, basis in series:
        sheet = _sheet_at(wb, position)
        if sheet is None or not re.fullmatch(r"[A-Z]{1,3}", column):
            raise invalid_position()
        blocks, _ = _blocks(sheet)
        col = column_number(column)
        if col not in blocks or blocks[col][0] != block:
            raise invalid_position()
        entry: dict[str, Any] = {
            "indicator": indicator, "basis": basis, "sheet": position, "sheet_name": sheet.name, "block": block,
            "block_title": blocks[col][1], "column": column, "unit_header": _header(sheet, col), "unit_evidence": None,
        }  # fmt: skip
        if indicator == "unemployment" and unit_evidence is not None:
            text = _text_at(wb, *unit_evidence)
            if text is None:
                raise invalid_position()
            entry["unit_evidence"] = {
                "sheet": unit_evidence[0],
                "cell": unit_evidence[1],
                "text": text,
            }
        entries.append(entry)
    if unit_evidence is not None and not any(e["indicator"] == "unemployment" for e in entries):
        raise MappingRefused("mapping_invalid")
    context = []
    for position, classification in sheet_context:
        sheet = _sheet_at(wb, position)
        if sheet is None:
            raise invalid_position()
        context.append(
            {"sheet": position, "sheet_name": sheet.name, "classification": classification}
        )
    published_on: Any = "not_stated"
    if published is not None:
        day, position, a1 = published
        text = _text_at(wb, position, a1)
        if text is None:
            raise invalid_position()
        published_on = {"date": day, "sheet": position, "cell": a1, "text": text}
    doc = {
        "schema": SCHEMA, "workbook_sha256": workbook_sha256, "reviewer": "owner", "decided_on": decided_on,
        "published_on": published_on, "series": entries, "sheet_context": context,
    }  # fmt: skip
    raw = (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    parse_mapping(raw)  # the reader's own checks, so an invalid file is never written
    return raw


def interpret_anz_workbook(
    wb: WorkbookCells,
    *,
    publisher_names: Sequence[str],
    document_title: str,
    workbook_sha256: str,
    mapping: AnzMapping | None = None,
) -> tuple[tuple[TableForecast, ...], tuple[Rejection, ...]]:
    if mapping is not None and (code := mapping_refusal(mapping, wb, workbook_sha256)):
        raise MappingRefused(code)
    listed = {} if mapping is None else {(e.sheet, e.col): e for e in mapping.series}
    mapped = set() if mapping is None else {e.indicator for e in mapping.series}
    visited: set[tuple[int, int]] = set()
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
            entry = listed.get((sheet.position, col))
            if entry is not None and mapping is not None:
                visited.add((sheet.position, col))
                if not _entry_matches(entry, sheet, blocks, col):
                    rejections.append(
                        Rejection(
                            "mapping_structure_mismatch", sheet.position, entry.block, None, col
                        )
                    )
                    continue
                block, title = blocks[col]
                forecasts_or_code = _column(
                    sheet, col, block, title, rows, legend, vintage, others,
                    publisher_names=publisher_names, document_title=document_title, workbook_sha256=workbook_sha256,
                    reviewed=(mapping, entry),
                )  # fmt: skip
                for item in forecasts_or_code:
                    (forecasts if isinstance(item, TableForecast) else rejections).append(item)
                continue
            if col not in blocks:
                rejections.append(Rejection("unmapped_row", sheet.position, None, None, col))
                continue
            block, title = blocks[col]
            if _indicator(f"{title}: {_header(sheet, col)}") & mapped:
                # The owner named the canonical column for this indicator; this one is a variant or another basis.
                rejections.append(
                    Rejection("not_canonical_series", sheet.position, block, None, col)
                )
                continue
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
    for (position, col), entry in listed.items():
        if (position, col) not in visited:  # its sheet is unreadable, or the column is gone
            rejections.append(
                Rejection("mapping_structure_mismatch", position, entry.block, None, col)
            )
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
    reviewed: tuple[AnzMapping, MappingEntry] | None = None,
) -> list[TableForecast | Rejection]:
    at = (sheet.position, block, None, col)
    header = _header(sheet, col)
    label = f"{title}: {header}"
    found = _indicator(label)
    if len(found) != 1:
        return [Rejection("ambiguous_indicator" if found else "unmapped_row", *at)]
    (indicator,) = found
    unit, code = unit_of_text(title, header, sheet.name)
    provenance: dict[str, Any] = {}
    if reviewed is not None:
        mapping, entry = reviewed
        if indicator != entry.indicator:
            return [Rejection("mapping_indicator_mismatch", *at)]
        if _stated_basis(label, indicator) != entry.basis:
            return [Rejection("mapping_basis_mismatch", *at)]
        provenance = {
            "mapping_sha256": mapping.sha256,
            "mapping_reviewer": mapping.reviewer,
            "mapping_decided_on": mapping.decided_on,
            "mapping_entry": entry.raw,
        }
        if mapping.sheet_context.get((sheet.position, sheet.name)) == "editorial":
            provenance["caption_review"] = {
                "classification": "editorial",
                "sheet_name": sheet.name,
                "mapping_sha256": mapping.sha256,
                "decided_on": mapping.decided_on,
            }
        if entry.unit_evidence is not None and code is None:
            stated = _evidence_unit(sheet, entry.unit_evidence, rows[-1][0])
            if stated is None:
                return [
                    Rejection("unit_unstated", *at)
                ]  # never assumed: the cited note must say it
            if unit is not None and unit != stated:
                return [Rejection("contradictory_unit", *at)]
            unit = stated
            ev = entry.unit_evidence
            provenance["unit_evidence"] = {"sheet": ev.sheet, "cell": ev.cell, "text": ev.text}
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
            **provenance,
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
