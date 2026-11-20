"""Synthetic workbooks for the inspector tests. Every label and figure here is invented; nothing comes from a bank."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment

SECRET_LABEL = "ZEBRA-SECRET-LABEL"
SECRET_VALUE = 987.654321


def forecast_book() -> Workbook:
    """One visible sheet: a period header row, two indicator rows with a hidden helper sheet beside it."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Synthetic forecasts"
    ws["A1"] = "Fictional Bank forecasts"
    ws["A2"] = "Indicator"
    ws["B2"] = "Actual"
    ws.merge_cells("C2:D2")
    ws["C2"] = "Forecast"
    ws["A3"] = "Quarter"
    for col, head in zip("BCD", ("Sep-26", "Dec-26f", "Mar-27f")):
        ws[f"{col}3"] = head
    ws["A4"] = "OCR (%)"
    ws["A5"] = "CPI inflation, annual % change"
    for row, values in ((4, (2.5, 2.25, 2.0)), (5, (0.031, 0.028, 0.025))):
        for col, value in zip("BCD", values):
            ws[f"{col}{row}"] = value
    for col in "BCD":
        ws[f"{col}5"].number_format = "0.0%"
    ws["A6"] = SECRET_LABEL
    ws["B6"] = SECRET_VALUE
    ws["A8"] = "Source: Fictional Bank, ANZ"
    ws["A9"] = "Copyright 2026. Important notice: all rights reserved."
    ws["B4"].comment = Comment("synthetic note", "tester")
    ws.cell(row=10, column=1, value=datetime(2026, 9, 30))
    helper = wb.create_sheet("helper")
    helper.sheet_state = "hidden"
    helper["A1"] = 2026
    secret = wb.create_sheet("vh")
    secret.sheet_state = "veryHidden"
    return wb


def save(wb: Workbook, path: Path) -> Path:
    wb.save(path)
    return path


def rewrite(path: Path, edits: dict[str, bytes | None], add: dict[str, bytes] | None = None) -> Path:
    """Copy the archive, replacing (bytes), dropping (None) or adding members. Used to build what openpyxl won't write."""
    src = path.read_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(src)) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename in edits:
                if edits[item.filename] is not None:
                    zout.writestr(item.filename, edits[item.filename])
                continue
            zout.writestr(item, zin.read(item.filename))
        for name, data in (add or {}).items():
            zout.writestr(name, data)
    path.write_bytes(out.getvalue())
    return path


def with_cached_formula(path: Path, cell: str, cached: str) -> Path:
    """Give one formula cell of sheet 1 a cached value, as a spreadsheet program would on save."""
    name = "xl/worksheets/sheet1.xml"
    with zipfile.ZipFile(path) as z:
        xml = z.read(name).decode()
    pattern = re.compile(rf'(<c r="{cell}"[^>]*>)(<f>[^<]*</f>)(<v\s*/>|<v></v>)?')
    xml, n = pattern.subn(lambda m: f"{m[1]}{m[2]}<v>{cached}</v>", xml)
    assert n == 1, "formula cell not found"
    return rewrite(path, {name: xml.encode()})


def sheet1(path: Path) -> bytes:
    with zipfile.ZipFile(path) as z:
        return z.read("xl/worksheets/sheet1.xml")
