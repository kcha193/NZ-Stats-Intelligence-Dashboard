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


def drawing(*shapes: str) -> bytes:
    bodies = "".join(f"<xdr:sp><xdr:txBody>{shape}</xdr:txBody></xdr:sp>" for shape in shapes)
    return (
        '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
        f'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{bodies}</xdr:wsDr>'
    ).encode()


def vertical_book() -> Workbook:
    """Fictional vertical time series: dates down column A, one block of three series, a forecast marker merged down the
    forecast rows, shading from the first forecast row and a source note. Every label and figure is invented."""
    from openpyxl.styles import PatternFill

    wb = Workbook()
    wb.active.title = "cover"
    ws = wb.create_sheet("Fictional data")
    ws.merge_cells("A1:D1")
    ws["A1"] = "Fictional outlook data"
    ws["B2"] = "GDP (production), real"
    ws["C2"] = "Quarterly % change"
    ws["D2"] = "Annual % change"
    shade = PatternFill("solid", fgColor="DDDDDD")
    for i in range(12):  # quarter ends from March 2024
        row = 3 + i
        year, q = 2024 + i // 4, i % 4
        month = 3 * (q + 1)
        day = 31 if month in (3, 12) else 30
        ws.cell(row=row, column=1, value=datetime(year, month, day))
        for col in (2, 3, 4):
            cell = ws.cell(row=row, column=col, value=100.0 + i + col / 10)
            if row >= 11:
                cell.fill = shade
    ws.merge_cells("E11:E14")
    ws["E11"] = "Forecast"
    ws["F5"] = SECRET_LABEL
    ws["G5"] = SECRET_VALUE
    ws["A16"] = "Source: Fictional Stats, Fictional Bank"
    return wb
