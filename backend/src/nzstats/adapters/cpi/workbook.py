"""Bounded stdlib reader for the quarterly blocks of the CPI release workbook (tables 10 and 11).

Only the "Percentage change from previous quarter" blocks are read: the annual trimmed-mean blocks
are spliced from two weight bases and are deliberately not stored.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import PurePosixPath
from typing import NoReturn

from nzstats.adapters.cpi.series import UNDERLYING
from nzstats.domain import ErrorClass, IngestError

MAX_ARCHIVE = 16 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024
MAX_MEMBERS = 200
MAX_RATIO = 250
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MONTH = {"Mar": "03", "Jun": "06", "Sep": "09", "Sept": "09", "Dec": "12"}
CELL = re.compile(r"([A-Z]+)([0-9]+)")
TABLES = ("10", "11")
EXPECTED = {ref for ref, _, _ in UNDERLYING} | {"SE9A"}


def _bad(message: str) -> NoReturn:
    raise IngestError(ErrorClass.LAYOUT_CHANGED, message)


def _xml(z: zipfile.ZipFile, name: str) -> ET.Element:
    data = z.read(name)
    if b"<!DOCTYPE" in data[:2048] or b"<!ENTITY" in data:
        _bad("CPI workbook contains unsupported XML declarations")
    return ET.fromstring(data)


def read_quarterly_tables(raw: bytes) -> dict[str, dict[str, float]]:
    """`{series reference: {YYYY-MM: quarterly % change}}` for tables 10 and 11, incl. `SE9A`."""
    if len(raw) > MAX_ARCHIVE:
        _bad("CPI workbook exceeds size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members = z.infolist()
            if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_UNPACKED:
                _bad("CPI workbook exceeds member limits")
            for m in members:
                path = PurePosixPath(m.filename)
                lowered = m.filename.lower()
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in m.filename
                    or m.flag_bits & 1
                    or "vbaproject" in lowered
                    or "externallinks" in lowered
                    or m.file_size / max(m.compress_size, 1) > MAX_RATIO
                ):
                    _bad("CPI workbook contains unsafe members")
            return _tables(z)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, RuntimeError, EOFError) as exc:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "CPI workbook cannot be read") from exc


def _tables(z: zipfile.ZipFile) -> dict[str, dict[str, float]]:
    rels = {
        r.get("Id"): r.get("Target", "")
        for r in _xml(z, "xl/_rels/workbook.xml.rels").iter(PKG + "Relationship")
    }
    sheets = _xml(z, "xl/workbook.xml").find(M + "sheets")
    if sheets is None:
        _bad("CPI workbook has no sheets")
    targets = {
        s.get("name"): "xl/" + rels[s.get(R + "id")].lstrip("/").removeprefix("xl/") for s in sheets
    }
    if not set(TABLES) <= set(targets):
        _bad("CPI workbook tables 10 and 11 are missing")
    strings = [
        "".join(t.text or "" for t in si.iter(M + "t"))
        for si in _xml(z, "xl/sharedStrings.xml").findall(M + "si")
    ]
    merged: dict[str, dict[str, float]] = {}
    for name in TABLES:
        for ref, series in _sheet(_xml(z, targets[name]), strings).items():
            if ref in merged and ref != "SE9A":
                _bad("CPI workbook repeats a series")
            if ref == "SE9A" and merged.get(ref, series) != series:
                _bad("CPI workbook all-groups columns disagree")
            merged[ref] = series
    if set(merged) != EXPECTED:
        _bad("CPI workbook series changed")
    return merged


def _sheet(root: ET.Element, strings: list[str]) -> dict[str, dict[str, float]]:
    refs: dict[str, str] = {}
    mode = False
    year: int | None = None
    out: dict[str, dict[str, float]] = {}
    for row in root.iter(M + "row"):
        cells: dict[str, str] = {}
        for c in row:
            v = c.find(M + "v")
            match = CELL.fullmatch(c.get("r", ""))
            if v is None or v.text is None or match is None:
                continue
            cells[match[1]] = strings[int(v.text)] if c.get("t") == "s" else v.text
        head = cells.get("A", "")
        if head.startswith("Series ref"):
            refs, mode = {col: val for col, val in cells.items() if col != "A"}, False
        elif head == "Percentage change from previous quarter":
            mode = True
        elif head.startswith("Percentage change from same quarter"):
            mode = False
        elif mode:
            if head.isdigit():
                year = int(head)
            month = MONTH.get(cells.get("B", ""))
            if month is None or year is None:
                continue
            for col, ref in refs.items():
                if col in cells:
                    out.setdefault(ref, {})[f"{year:04d}-{month}"] = float(cells[col])
    return out
