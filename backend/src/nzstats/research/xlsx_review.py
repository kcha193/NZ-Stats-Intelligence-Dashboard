"""The owner's series review of the forecasts workbook (Phase 4AQ): which block is which series, never a value.

For the owner's own terminal only (the command refuses a pipe or a tool session): it prints the workbook's sheet names,
block titles, unit headers and notes, which are ANZ text. It prints no cell value. Each column shows how the current
interpreter reads it (indicator, unit, period basis, bold forecast boundary) and its result (a candidate count or the
fixed rejection code), so the owner can name the headline series against the original workbook. All text is untrusted
and is printed JSON-quoted, so a control character is shown escaped and never reaches the terminal raw.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Sequence

from nzstats.research.table_forecast import _horizon, _indicator
from nzstats.research.table_parse import Period, unit_of_text
from nzstats.research.xlsx_anz import (
    _a1,
    _blocks,
    _date_rows,
    _forecast_rows,
    _header,
    _notes,
    interpret_anz_workbook,
)
from nzstats.research.xlsx_cells import WorkbookCells


def _q(text: str) -> str:
    return json.dumps(text, ensure_ascii=True)


def _col(col: int) -> str:
    return _a1(1, col)[:-1]


def review_lines(
    wb: WorkbookCells, *, publisher_names: Sequence[str], document_title: str, workbook_sha256: str
) -> list[str]:
    forecasts, rejections = interpret_anz_workbook(
        wb,
        publisher_names=publisher_names,
        document_title=document_title,
        workbook_sha256=workbook_sha256,
    )
    candidates = Counter((f.page, f.col) for f in forecasts)
    codes: dict[tuple[int, int | None], set[str]] = defaultdict(set)
    for r in rejections:
        codes[(r.page, r.col)].add(r.code)
    lines = [f"workbook sha256 {workbook_sha256}"]
    for sheet in wb.sheets:
        head = f"sheet {sheet.position} {_q(sheet.name)}"
        if sheet.state != "visible":
            lines.append(f"{head}: hidden_sheet ({sheet.state})")
            continue
        if not sheet.cells:
            lines.append(f"{head}: no cells")
            continue
        rows = _date_rows(sheet, wb.date1904)
        if rows is None:
            lines.append(f"{head}: unsupported_period")
        else:
            lines.append(f"{head}: quarterly {rows[0][1]} to {rows[-1][1]} ({len(rows)} dates)")
            notes = _notes(sheet, rows[-1][0])
            if notes is None:
                lines.append("  forecast_marker_missing (no single plain bold-forecast legend)")
            else:
                legend, vintage, others = notes
                lines.append(f"  legend: {_q(legend)}")
                lines.append(f"  as at: {_q(vintage) if vintage is not None else '(none)'}")
                lines.extend(f"  note: {_q(text)}" for text in others)
        blocks, unmapped = _blocks(sheet)
        by_block: dict[int, list[int]] = defaultdict(list)
        for col, (number, _title) in blocks.items():
            by_block[number].append(col)
        for number, cols in sorted(by_block.items()):
            cols.sort()
            title = blocks[cols[0]][1]
            lines.append(
                f"  block {number} {_q(title)} (columns {_col(cols[0])} to {_col(cols[-1])})"
            )
            for col in cols:
                lines.append(f"    {_column_line(sheet, col, title, rows, candidates, codes)}")
        for col in sorted(unmapped):
            lines.append(f"  column {_col(col)}: no block title (unmapped_row)")
    return lines


def _column_line(sheet, col, title, rows, candidates, codes) -> str:
    header = _header(sheet, col)
    label = f"{title}: {header}"
    found = sorted(_indicator(label))
    unit, unit_code = unit_of_text(title, header, sheet.name)
    parts = [
        f"column {_col(col)} unit {_q(header)}: indicator {'/'.join(found) or 'none'}",
        f"unit {unit or unit_code or 'unit_unstated'}",
    ]
    if rows is not None:
        tail = _forecast_rows(sheet, col, rows)
        if tail is None:
            parts.append("forecast_boundary_unclear")
        else:
            parts.append(f"forecast boundary {tail[0][1]} to {tail[-1][1]} ({len(tail)} bold)")
            if len(found) == 1:
                day = tail[0][1]
                basis, basis_code = _horizon(
                    Period("month_end", day.year, day.month), label, found[0]
                )
                parts.append(f"first horizon {basis or basis_code}")
    count = candidates.get((sheet.position, col), 0)
    found_codes = sorted(
        codes.get((sheet.position, col), set()) | codes.get((sheet.position, None), set())
    )
    if count:
        result = f"{count} candidates" + (f" + {', '.join(found_codes)}" if found_codes else "")
    else:
        result = ", ".join(found_codes) or "nothing"
    parts.append(f"result {result}")
    return ", ".join(parts)
