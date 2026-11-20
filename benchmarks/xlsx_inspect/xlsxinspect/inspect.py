"""Masked structural inspection of one spreadsheet that no model may read (Phase 4AN).

The archive is checked with the standard library first (sizes, member names, encryption, XML declarations). Only an archive
that passes is opened with openpyxl, twice: once for formulas and once for the cached values a spreadsheet program saved.
Links are not loaded, macros are not kept and nothing is evaluated. Every metric is a count, a flag or a cell index.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import re
import warnings
import zipfile
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path, PurePosixPath

from nzstats.research.table_parse import column_kind, period_of
from openpyxl import load_workbook
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula

# The same limits as the CPI workbook reader (backend/src/nzstats/adapters/cpi/workbook.py).
MAX_ARCHIVE = 16 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024
MAX_MEMBERS = 200
MAX_RATIO = 250

# Copied from backend/src/nzstats/research/table_forecast.py; tests/test_inspect.py fails if the two drift.
INDICATORS: dict[str, re.Pattern[str]] = {
    "ocr": re.compile(r"\bocr\b|official cash rate", re.IGNORECASE),
    "cpi_inflation": re.compile(r"\bcpi\b|consumers?'? price|\binflation\b", re.IGNORECASE),
    "gdp": re.compile(r"\bgdp\b|gross domestic product", re.IGNORECASE),
    "unemployment": re.compile(r"unemployment", re.IGNORECASE),
}
OTHER_FORECASTERS = (
    "treasury", "rbnz", "reserve bank", "imf", "oecd", "world bank", "consensus", "bloomberg", "reuters",
    "market pricing", "stats nz", "statistics new zealand",
    "anz", "asb", "bnz", "westpac", "kiwibank",
)  # fmt: skip
_ANZ = re.compile(r"\banz\b", re.IGNORECASE)
_OTHERS = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in OTHER_FORECASTERS if n != "anz") + r")\b", re.IGNORECASE)
_NOTICE = re.compile(r"copyright|disclaimer|©|important notice|all rights reserved", re.IGNORECASE)
_UNITS = {
    "percent": re.compile(r"%|per ?cent\b|\bpercent\b", re.IGNORECASE),
    "annual": re.compile(r"\bannual\b|\by\s*/\s*y\b|year on year|\byoy\b|\bannual average\b", re.IGNORECASE),
    "quarterly": re.compile(r"\bq\s*/\s*q\b|\bquarterly\b|quarter on quarter", re.IGNORECASE),
    "seasonal": re.compile(r"seasonally adjusted|\bs\.a\.", re.IGNORECASE),
}
_EXTERNAL_REF = re.compile(r"\[\d+\]")
_COUNTS = (
    "numeric", "text", "booleans", "dates", "percent_format", "literal_percent_format", "year_like_numbers", "formulas",
    "formulas_cached", "formulas_uncached", "formulas_external", "comments", "period_headers",
    "forecast_markers", "actual_markers", "anz_mentions", "other_forecaster_mentions", "notice_cells",
)  # fmt: skip
_STATES = {"visible": "visible", "hidden": "hidden", "veryHidden": "very_hidden"}


# A DOCTYPE or ENTITY in any encoding expat accepts (UTF-8, Latin-1 and ASCII share these bytes; UTF-16 both ways).
_DECLARATIONS = tuple(
    marker.encode(enc)
    for marker in ("<!DOCTYPE", "<!ENTITY")
    for enc in ("utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be")
)
_ACTIVE = re.compile(r"^xl/(?:connections\.xml$|embeddings/|activex/)|^customui/", re.IGNORECASE)
_EXTERNAL_TARGET = re.compile(rb"TargetMode\s*=\s*[\"']External[\"']")


def _archive(raw: bytes) -> dict:
    """Stdlib checks before any XML parser runs. A check not reached is None, never False."""
    a = {
        "bytes": len(raw), "members": 0, "unpacked_bytes": 0, "max_ratio": 0.0, "encrypted": False,
        "unsafe_path": False, "vba_part": False, "external_link_parts": 0, "active_content_parts": 0,
        "external_targets": None, "xml_declarations": None, "macro_content_type": None,
        "over_limit": len(raw) > MAX_ARCHIVE, "not_zip": False, "unreadable": False,
    }  # fmt: skip
    if a["over_limit"]:
        return a
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        a["not_zip"] = True
        return a
    try:
        with z:
            _members(z, a)
    except Exception:  # noqa: BLE001 - a corrupt member (bad CRC, zlib error) is a fixed flag; its message may name parts
        a["unreadable"] = True
    return a


def _members(z: zipfile.ZipFile, a: dict) -> None:
    members = z.infolist()
    a["members"] = len(members)
    a["unpacked_bytes"] = sum(m.file_size for m in members)
    for m in members:
        path = PurePosixPath(m.filename)
        lowered = m.filename.lower()
        a["max_ratio"] = max(a["max_ratio"], round(m.file_size / max(m.compress_size, 1), 1))
        a["encrypted"] |= bool(m.flag_bits & 1)
        a["unsafe_path"] |= path.is_absolute() or ".." in path.parts or "\\" in m.filename
        a["vba_part"] |= "vbaproject" in lowered
        a["active_content_parts"] += bool(_ACTIVE.search(m.filename))
        if lowered.startswith("xl/externallinks/") and lowered.endswith(".xml"):
            a["external_link_parts"] += 1
    a["over_limit"] = a["members"] > MAX_MEMBERS or a["unpacked_bytes"] > MAX_UNPACKED or a["max_ratio"] > MAX_RATIO
    if a["over_limit"] or a["encrypted"] or a["unsafe_path"]:
        return
    declarations = external = 0
    macro = False
    for m in members:  # every member, whatever its name: a part's extension does not decide how openpyxl parses it
        data = z.read(m)
        declarations += any(d in data for d in _DECLARATIONS)
        if m.filename.lower().endswith(".rels"):
            external += len(_EXTERNAL_TARGET.findall(data))
        if m.filename == "[Content_Types].xml":
            macro = b"macroEnabled" in data
    a["xml_declarations"] = declarations > 0
    a["external_targets"] = external
    a["macro_content_type"] = macro


def _refused(a: dict) -> bool:
    return any(a[k] for k in ("over_limit", "not_zip", "encrypted", "unsafe_path", "xml_declarations", "unreadable"))


def _formula_text(cell) -> str | None:
    """Only a cell stored as a formula; text that merely starts with "=" is text."""
    if cell.data_type != "f":
        return None
    value = cell.value
    if isinstance(value, ArrayFormula):
        return value.text or ""
    if isinstance(value, DataTableFormula):
        return ""
    return str(value)


_QUOTED = re.compile(r'"[^"]*"|\\.')


def _percent_kind(number_format: str | None) -> str | None:
    """`scaled` when the format multiplies by 100 (stored 0.025 shows 2.5%); `literal` when "%" is only printed text."""
    fmt = number_format or ""
    if "%" not in fmt:
        return None
    return "scaled" if "%" in _QUOTED.sub("", fmt) else "literal"


def _sheet(fws, vws) -> dict:
    s = Counter()
    indicators = Counter({k: 0 for k in INDICATORS})
    kinds = Counter({k: 0 for k in ("quarter", "month_end", "year_to", "calendar")})
    units = Counter({k: 0 for k in _UNITS})
    label_cols: set[int] = set()
    period_rows: set[int] = set()
    period_cols: set[int] = set()
    for row in fws.iter_rows():
        for cell in row:
            formula = _formula_text(cell)
            if formula is None:
                continue
            s["formulas"] += 1
            cached = vws.cell(row=cell.row, column=cell.column).value is not None
            s["formulas_cached" if cached else "formulas_uncached"] += 1
            s["formulas_external"] += bool(_EXTERNAL_REF.search(formula))
    for row in vws.iter_rows():
        for cell in row:
            v = cell.value
            if cell.comment is not None:
                s["comments"] += 1
            if v is None:
                continue
            if isinstance(v, bool):
                s["booleans"] += 1
            elif isinstance(v, (int, float)):
                s["numeric"] += 1
                kind = _percent_kind(cell.number_format)
                s["percent_format"] += kind == "scaled"
                s["literal_percent_format"] += kind == "literal"
                s["year_like_numbers"] += float(v).is_integer() and 1990 <= v <= 2100
            elif isinstance(v, (datetime, date, time, timedelta)):
                s["dates"] += 1
            elif isinstance(v, str):
                s["text"] += 1
                _text(v, cell, s, indicators, kinds, units, label_cols, period_rows, period_cols)
    return {
        "state": _STATES.get(vws.sheet_state, "hidden"),
        "rows": vws.max_row,
        "cols": vws.max_column,
        **{k: s[k] for k in _COUNTS},
        "merged": len(vws.merged_cells.ranges),
        **_merged_periods(vws),
        "indicator_labels": dict(indicators),
        "label_columns": sorted(label_cols),
        "period_header_rows": len(period_rows),
        "period_header_cols": len(period_cols),
        "period_kinds": dict(kinds),
        "unit_hints": dict(units),
    }


def _merged_periods(ws) -> dict:
    """Merged ranges whose top-left cell is a period header, and the columns they span (a group header over a block)."""
    count = cols = 0
    for rng in ws.merged_cells.ranges:
        top_left = ws.cell(row=rng.min_row, column=rng.min_col).value
        text = str(top_left) if isinstance(top_left, (str, int)) and not isinstance(top_left, bool) else None
        if text is not None and period_of((text,))[0] is not None:
            count += 1
            cols += rng.max_col - rng.min_col + 1
    return {"merged_period_headers": count, "merged_period_header_cols": cols}


def _text(v, cell, s, indicators, kinds, units, label_cols, period_rows, period_cols) -> None:
    hit = False
    for name, pattern in INDICATORS.items():
        if pattern.search(v):
            indicators[name] += 1
            hit = True
    if hit:
        label_cols.add(cell.column)
    period, _ = period_of((v,))
    if period is not None:
        s["period_headers"] += 1
        kinds[period.kind] += 1
        period_rows.add(cell.row)
        period_cols.add(cell.column)
    kind = column_kind((v,))
    s["forecast_markers"] += kind == "forecast"
    s["actual_markers"] += kind == "actual"
    s["anz_mentions"] += bool(_ANZ.search(v))
    s["other_forecaster_mentions"] += bool(_OTHERS.search(v))
    s["notice_cells"] += bool(_NOTICE.search(v))
    for name, pattern in _UNITS.items():
        units[name] += bool(pattern.search(v))


def inspect(path: Path, raw: bytes | None = None) -> dict:
    """Inspect `raw` when given (the bytes whose hash was checked), else the file at `path`."""
    raw = Path(path).read_bytes() if raw is None else raw
    out: dict = {"sha256": hashlib.sha256(raw).hexdigest(), "status": "refused", "archive": _archive(raw)}
    if _refused(out["archive"]):
        return out
    sink = io.StringIO()
    try:
        with (
            warnings.catch_warnings(record=True) as caught,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            warnings.simplefilter("always")
            formulas = load_workbook(io.BytesIO(raw), data_only=False, keep_links=False, keep_vba=False)
            values = load_workbook(io.BytesIO(raw), data_only=True, keep_links=False, keep_vba=False)
            sheets = [_sheet(f, v) for f, v in zip(formulas.worksheets, values.worksheets, strict=True)]
        props = values.properties
        modified = props.modified
        out["workbook"] = {
            "sheets": len(values.worksheets),
            "chartsheets": len(values.chartsheets),
            "defined_names": len(values.defined_names),
            "has_created": props.created is not None,
            "has_modified": modified is not None,
            "modified_ymd": [modified.year, modified.month, modified.day] if modified else None,
            "warnings": len(caught),
        }
        out["sheets"] = sheets
        out["status"] = "ok"
    except Exception:  # noqa: BLE001 - untrusted input: the reason may quote the document, so only a fixed code leaves
        out = {"sha256": out["sha256"], "status": "error", "archive": out["archive"]}
    return out
