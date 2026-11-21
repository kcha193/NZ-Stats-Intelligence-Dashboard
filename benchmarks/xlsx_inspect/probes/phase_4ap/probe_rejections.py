"""Phase 4AP masked probe: why each column of a stored ANZ workbook version is refused.

Owner's machine only. Opens data/nzstats.db read-only, checks the raw copy against the stored SHA-256, reads the
workbook with the production reader (`xlsx-cells-1`) and re-runs the production rules (`xlsx-anz-1`) part by part.
Prints only ints, booleans and production codes: never a cell text, sheet name, note or value. Writes nothing.

    # from the repository root
    PYTHONPATH=backend/src backend/.venv/bin/python benchmarks/xlsx_inspect/probes/phase_4ap/probe_rejections.py 5
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from nzstats.config import load_settings
from nzstats.research import xlsx_anz as m
from nzstats.research.table_context import _unknown_context, context_rejection
from nzstats.research.table_forecast import _indicator
from nzstats.research.table_ingest import _VERSION
from nzstats.research.table_parse import unit_of_text
from nzstats.research.xlsx_cells import read_cells

DATA = Path("data")
NAMES = ("ANZ New Zealand", "anz", "ANZ")


def main(version: int) -> dict:
    settings = load_settings({"NZSTATS_DATA_DIR": str(DATA)})
    conn = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute(_VERSION, (version,)).fetchone()
    assert row is not None and row["format"] == "xlsx", "not an xlsx version"
    body = (settings.raw_dir / row["path"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == row["raw_sha256"], "raw copy does not match"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        wb = read_cells(body)
        _, rejections = m.interpret_anz_workbook(
            wb, publisher_names=NAMES, document_title="", workbook_sha256=row["raw_sha256"]
        )
    out: dict = {"sheets": [], "codes": dict(Counter(r.code for r in rejections))}
    by_sheet: dict[int, list] = {}
    for r in rejections:
        by_sheet.setdefault(r.page, []).append(r)
    for sheet in wb.sheets:
        info: dict = {"position": sheet.position, "visible": sheet.state == "visible", "cells": len(sheet.cells)}
        rows = m._date_rows(sheet, wb.date1904) if sheet.cells else None
        info["quarterly_dates"] = rows is not None
        if rows:
            notes = m._notes(sheet, rows[-1][0])
            info["legend_found"] = notes is not None
            if notes:
                _legend, vintage, others = notes
                info["vintage_found"] = vintage is not None
                info["other_notes"] = len(others)
                info["other_notes_unknown_words"] = sum(_unknown_context(t, NAMES) for t in others)
                info["sheet_name_unknown_words"] = _unknown_context(sheet.name, NAMES)
                blocks, unmapped = m._blocks(sheet)
                cols = []
                for col, (block, title) in sorted(blocks.items()):
                    h = sheet.cells.get((m._HEADER_ROW, col))
                    header = h.text.strip() if h is not None and h.kind == "text" else ""
                    label = f"{title}: {header}"
                    found = _indicator(label)
                    c = {"col": col, "block": block, "indicator": sorted(found), "header_present": bool(header)}
                    c["unit_parts"] = [
                        unit_of_text(t)[1] or (unit_of_text(t)[0] and "ok") for t in (title, header, sheet.name)
                    ]
                    c["unit"] = list(unit_of_text(title, header, sheet.name))
                    if len(found) == 1:
                        c["boundary_ok"] = m._forecast_rows(sheet, col, rows) is not None
                        c["context_whole"] = context_rejection(
                            label, (sheet.name, *others, rows[-1][1].isoformat(), header), publisher_names=NAMES
                        )
                        c["context_without_sheet_name"] = context_rejection(
                            label, (*others, rows[-1][1].isoformat(), header), publisher_names=NAMES
                        )
                        c["context_without_notes"] = context_rejection(
                            label, (sheet.name, rows[-1][1].isoformat(), header), publisher_names=NAMES
                        )
                        c["context_without_header"] = context_rejection(
                            label, (sheet.name, *others, rows[-1][1].isoformat()), publisher_names=NAMES
                        )
                        c["context_label_only"] = context_rejection(
                            label, (rows[-1][1].isoformat(),), publisher_names=NAMES
                        )
                        c["header_unknown_words"] = _unknown_context(header, NAMES)
                    cols.append(c)
                info["columns"] = cols
                info["unmapped_columns"] = len(unmapped)
        info["rejections"] = dict(Counter(r.code for r in by_sheet.get(sheet.position, [])))
        out["sheets"].append(info)
    return out


if __name__ == "__main__":
    print(json.dumps(main(int(sys.argv[1])), indent=1, sort_keys=True))
