"""Masked structural inspection of one spreadsheet that no model may read (Phase 4AN).

The archive is checked with the standard library first (sizes, member names, encryption, XML declarations). Only an archive
that passes is opened with openpyxl, twice: once for formulas and once for the cached values a spreadsheet program saved.
Links are not loaded, macros are not kept and nothing is evaluated. Every metric is a count, a flag or a cell index.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import posixpath
import re
import warnings
import zipfile
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path, PurePosixPath
from xml.parsers import expat

from nzstats.research.table_parse import column_kind, period_of
from openpyxl import load_workbook
from openpyxl.utils.escape import unescape
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula
from openpyxl.xml.constants import ARC_WORKBOOK, XLSM, XLSX, XLTM, XLTX

# The same limits as the CPI workbook reader (backend/src/nzstats/adapters/cpi/workbook.py).
MAX_ARCHIVE = 16 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024
MAX_MEMBERS = 200
MAX_RATIO = 250
# Diagnostic workbooks must fit these allocation/work budgets before openpyxl runs.
MAX_WORKBOOK_CELLS = 100_000
MAX_MERGED_CELLS = 100_000
MAX_MERGES = 1_000
MAX_XML_ELEMENTS = 200_000
MAX_XML_DEPTH = 64

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
    "percent": re.compile(r"%|(?<![^\W\d])per[^\S\r\n]*cent\b", re.IGNORECASE),
    "annual": re.compile(
        r"\bannual\b|\by\s*/\s*y\b|year on year|\byoy\b|"
        r"(?<![^\W\d])(?:p\.[^\S\r\n]*a\.(?!\w)|per[^\S\r\n]+annum\b)",
        re.IGNORECASE,
    ),
    "quarterly": re.compile(r"\bq\s*/\s*q\b|\bquarterly\b|quarter on quarter", re.IGNORECASE),
    "seasonal": re.compile(r"seasonally adjusted|\bs\.a\.", re.IGNORECASE),
}
_WORKBOOK_REF = re.compile(r"\[[^\[\]]+\]")
_OPERAND_DELIMITERS = frozenset("=+-*/^&<>(){},;:%@ \t\r\n")
_QUALIFIER_DELIMITERS = (_OPERAND_DELIMITERS - {":"}) | frozenset("[]\"'")
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
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships}"
_TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types}"
_DOCUMENT_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_WORKBOOK_TYPES = (XLTM, XLTX, XLSM, XLSX)  # same override priority as the pinned openpyxl reader
_CELL_REF = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})")
_PRINT_TEXT = {
    _SHEET_NS + page + kind.capitalize(): kind for page in ("odd", "even", "first") for kind in ("header", "footer")
}
_PRINT_CONTROL = re.compile(
    r'&&|(?P<style>&"[^"\r\n]*"|&K(?:[0-9A-Fa-f]{2}[+-][0-9]{3}|[0-9A-Fa-f]{6})|&[0-9]+ ?|&[BEHIOUSXY])'
    r"|&\[(?:Tab|Pages?|Date|Path|Time|File|Picture)\]|&[A-Z]"
)


class _ExpansionLimit(ValueError):
    """A fixed refusal; never include input in the exception."""


def _coordinate(ref: str) -> tuple[int, int]:
    match = _CELL_REF.fullmatch(ref)
    if match is None:
        raise ValueError("invalid coordinate")
    col = 0
    for letter in match[1].upper():
        col = col * 26 + ord(letter) - ord("A") + 1
    row = int(match[2])
    if row > 1_048_576 or col > 16_384:
        raise _ExpansionLimit()
    return row, col


def _unit_hints(text: str) -> dict[str, int]:
    return {kind: int(bool(pattern.search(text))) for kind, pattern in _UNITS.items()}


def _print_text_hints(text: str, counts: Counter) -> None:
    """Read literal print text, keeping page sections, dynamic fields and line breaks separate."""

    def control(match: re.Match[str]) -> str:
        if match["style"]:
            return ""
        return "&" if match[0] == "&&" else "\n"

    for line in _PRINT_CONTROL.sub(control, unescape(text)).splitlines():
        counts.update(_unit_hints(line))


def _rels_path(name: str) -> str:
    source = PurePosixPath(name)
    return str(source.parent / "_rels" / (source.name + ".rels"))


def _xml(
    data: bytes,
    name: str,
    budget: Counter,
    targets: dict,
    sheet_refs: dict[tuple[str, str | None], bool],
    print_units: dict[str, Counter[str]],
    workbook_parts: dict[str | None, str],
) -> tuple[int, bool]:
    """Streaming, encoding-aware inspection. No tree, DTD, entity or external resource is loaded."""
    parser = expat.ParserCreate(namespace_separator="}")
    depth = external = rows = cols = row = col = row_depth = 0
    root = None
    macro = False
    parents: list[str] = []
    print_text: list[str] = []
    sequence_children = {
        "row": "c",
        "mergeCells": "mergeCell",
        "hyperlinks": "hyperlink",
        "commentList": "comment",
        "sheets": "sheet",
    }
    rels = name.lower().endswith(".rels")
    types = name == "[Content_Types].xml"

    def reject_declaration(*args):
        raise ValueError("XML declaration refused")

    def start(tag, attrs):
        nonlocal depth, root, external, macro, rows, cols, row, col, row_depth
        depth += 1
        budget["elements"] += 1
        if depth > MAX_XML_DEPTH or budget["elements"] > MAX_XML_ELEMENTS:
            raise _ExpansionLimit()
        if root is None:
            root = tag
            if (rels and root != _REL_NS + "Relationships") or (types and root != _TYPE_NS + "Types"):
                raise ValueError("invalid metadata root")
        if parser.CharacterDataHandler is not None:
            raise ValueError("invalid header or footer text")
        if depth == 3 and parents == [_SHEET_NS + "worksheet", _SHEET_NS + "headerFooter"] and tag in _PRINT_TEXT:
            parser.CharacterDataHandler = print_text.append
        if rels and depth == 2:
            if tag != _REL_NS + "Relationship" or not all(attrs.get(k) for k in ("Id", "Type", "Target")):
                raise ValueError("invalid relationship")
            mode = attrs.get("TargetMode", "Internal")
            if mode not in {"Internal", "External"}:
                raise ValueError("invalid relationship mode")
            external += mode == "External"
            budget[(name, "relationship", attrs["Id"])] += 1
            if budget[(name, "relationship", attrs["Id"])] > 1:
                raise ValueError("duplicate relationship")
            if mode == "Internal":
                target = attrs["Target"]
                base = str(PurePosixPath(name).parent.parent)
                target = posixpath.normpath("/" + posixpath.join(base, target).lstrip("/"))
                budget[("target", target)] += 1
                targets[(name, attrs["Id"])] = target
                # Shared images are valid; reused comments multiply cell allocation during loading.
                if attrs["Type"].rsplit("/", 1)[-1] == "comments" and budget[("target", target)] > 1:
                    raise ValueError("repeated internal target")
        if types and depth == 2:
            if tag not in {_TYPE_NS + "Default", _TYPE_NS + "Override"} or not attrs.get("ContentType"):
                raise ValueError("invalid content type")
            content_type = attrs["ContentType"]
            macro |= any(marker in content_type.lower() for marker in ("macroenabled", "vbaproject", "macrosheet"))
            if content_type in _WORKBOOK_TYPES:
                if tag == _TYPE_NS + "Override":
                    workbook_parts.setdefault(content_type, attrs["PartName"][1:])
                else:
                    workbook_parts.setdefault(None, ARC_WORKBOOK)
        local = tag.rsplit("}", 1)[-1]
        parent = parents[-1] if parents else ""
        parent_local = parent.removeprefix(_SHEET_NS)
        if (
            parent.startswith(_SHEET_NS)
            and parent_local in sequence_children
            and tag != _SHEET_NS + sequence_children[parent_local]
        ):
            raise ValueError("invalid sequence child")
        parents.append(tag)
        if not tag.startswith(_SHEET_NS):
            if root.rsplit("}", 1)[-1] in {"worksheet", "comments", "workbook"} and local in {
                "dimension",
                "mergeCell",
                "hyperlink",
                "comment",
                "row",
                "c",
                "sheet",
                *sequence_children,
            }:
                raise ValueError("invalid spreadsheet namespace")
            return
        if local == "sheet":
            sheet_id = attrs.get(_DOCUMENT_REL_NS + "id")
            budget[(name, "sheet", sheet_id)] += 1
            if budget[(name, "sheet", sheet_id)] > 1:
                raise ValueError("repeated worksheet relationship")
            sheet_refs[(_rels_path(name), sheet_id)] = parents == [_SHEET_NS + "workbook", _SHEET_NS + "sheets", tag]
        # openpyxl dispatches worksheet tags regardless of the document root. Refuse ambiguous structures.
        if local in {"dimension", "mergeCell", "hyperlink", "comment", "row", "c"}:
            expected_root = "comments" if local == "comment" else "worksheet"
            if root.rsplit("}", 1)[-1] != expected_root:
                raise ValueError("invalid worksheet structure")
        if row_depth and depth == row_depth + 1 and local != "c":
            raise ValueError("invalid row child")
        if local in {"dimension", "mergeCell", "hyperlink", "comment"}:
            bounds = attrs["ref"].split(":")
            if len(bounds) not in {1, 2}:
                raise ValueError("invalid range")
            first = _coordinate(bounds[0])
            last = _coordinate(bounds[-1])
            if first[0] > last[0] or first[1] > last[1]:
                raise ValueError("reversed range")
            rows, cols = max(rows, last[0]), max(cols, last[1])
            if local != "dimension":
                budget["merges"] += local == "mergeCell"
                budget["merged"] += (last[0] - first[0] + 1) * (last[1] - first[1] + 1)
                if budget["merged"] > MAX_MERGED_CELLS or budget["merges"] > MAX_MERGES:
                    raise _ExpansionLimit()
        elif local == "row":
            if row_depth:
                raise ValueError("nested row")
            row_depth = depth
            row, col = int(attrs.get("r", row + 1)), 0
            if not 1 <= row <= 1_048_576:
                raise _ExpansionLimit()
            rows = max(rows, row)
        elif local == "c":
            if "r" in attrs:
                cell_row, col = _coordinate(attrs["r"])
            else:
                cell_row, col = row, col + 1
            rows, cols = max(rows, cell_row), max(cols, col)
        if rows * max(cols, 1) > MAX_WORKBOOK_CELLS or cols > 16_384:
            raise _ExpansionLimit()

    def end(tag):
        nonlocal depth, row_depth
        if parser.CharacterDataHandler is not None:
            parser.CharacterDataHandler = None
            _print_text_hints("".join(print_text), print_units.setdefault(_PRINT_TEXT[tag], Counter()))
            print_text.clear()
        parents.pop()
        if depth == row_depth:
            row_depth = 0
        depth -= 1

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    # Feed bounded chunks; Expat handles UTF-8 and UTF-16 LE/BE and rejects unknown/broken encodings.
    for offset in range(0, len(data), 64 * 1024):
        parser.Parse(data[offset : offset + 64 * 1024], False)
    parser.Parse(b"", True)
    budget["area"] += rows * max(cols, 1)
    if budget["area"] > MAX_WORKBOOK_CELLS:
        raise _ExpansionLimit()
    return external, macro


def _archive(raw: bytes, print_units: dict[str, Counter[str]]) -> dict:
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
            _members(z, a, print_units)
    except _ExpansionLimit:
        a["over_limit"] = True
    except Exception:  # noqa: BLE001 - a corrupt member (bad CRC, zlib error) is a fixed flag; its message may name parts
        a["unreadable"] = True
    return a


def _members(z: zipfile.ZipFile, a: dict, print_units: dict[str, Counter[str]]) -> None:
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
    names = [m.filename for m in members]
    if len(set(names)) != len(names) or "[Content_Types].xml" not in names:
        raise ValueError("ambiguous or missing metadata")
    declarations = external = 0
    macro = False
    budget = Counter()
    targets: dict[tuple[str, str], str] = {}
    sheet_refs: dict[tuple[str, str | None], bool] = {}
    worksheet_print_units: dict[str, dict[str, Counter[str]]] = {}
    workbook_parts: dict[str | None, str] = {}
    for m in members:  # every member, whatever its name: a part's extension does not decide how openpyxl parses it
        data = z.read(m)
        declarations += any(d in data for d in _DECLARATIONS)
        if declarations:
            a["xml_declarations"] = True
            return
        if m.filename.lower().endswith((".xml", ".rels")) or data.lstrip(b"\xef\xbb\xbf\xff\xfe\x00 \t\r\n").startswith(
            b"<"
        ):
            part_print_units: dict[str, Counter[str]] = {}
            count, has_macro = _xml(data, m.filename, budget, targets, sheet_refs, part_print_units, workbook_parts)
            if part_print_units:
                worksheet_print_units[m.filename] = part_print_units
            external += count
            macro |= has_macro
    # The reader treats workbook sheet references as worksheets even when a relationship's Type says otherwise.
    resolved = [targets[ref] for ref in sheet_refs]
    if len(set(resolved)) != len(resolved):
        raise ValueError("repeated worksheet target")
    if any(target.lstrip("/") not in names for target in resolved):
        raise ValueError("missing worksheet target")
    workbook_part = next((workbook_parts[k] for k in _WORKBOOK_TYPES if k in workbook_parts), workbook_parts.get(None))
    if workbook_part is not None:
        workbook_rels = _rels_path(workbook_part)
        for ref, direct_sheet in sheet_refs.items():
            if direct_sheet and ref[0] == workbook_rels:
                for kind, counts in worksheet_print_units.get(targets[ref].lstrip("/"), {}).items():
                    print_units[kind].update(counts)
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


def _external_formula(formula: str) -> bool:
    """Recognise workbook-qualified operands in one pass, skipping text and structured references. Never evaluate."""
    i, size = 0, len(formula)
    while i < size:
        char = formula[i]
        if char in {'"', "'"}:
            start = i + 1
            i += 1
            while i < size:
                if formula[i] == char:
                    if i + 1 < size and formula[i + 1] == char:
                        i += 2
                        continue
                    break
                i += 1
            if i == size:
                raise ValueError("unterminated formula quote")
            end = i
            i += 1
            if char == "'" and i < size and formula[i] == "!" and _WORKBOOK_REF.search(formula, start, end):
                return True
        elif char == "[":
            start, depth = i, 1
            i += 1
            while i < size and depth:
                # Apostrophes escape special characters within structured column names.
                if formula[i] == "'" and i + 1 < size and formula[i + 1] in "[]'#@":
                    i += 2
                    continue
                depth += (formula[i] == "[") - (formula[i] == "]")
                i += 1
            if depth:
                raise ValueError("unterminated formula bracket")
            if start == 0 or formula[start - 1] in _OPERAND_DELIMITERS:
                end = i
                while end < size and formula[end] not in _QUALIFIER_DELIMITERS:
                    if formula[end] == "!":
                        return True
                    end += 1
        else:
            i += 1
    return False


_QUOTED = re.compile(r'"[^"]*"|\\.')


def _percent_kind(number_format: str | None) -> str | None:
    """`scaled` when the format multiplies by 100 (stored 0.025 shows 2.5%); `literal` when "%" is only printed text."""
    fmt = number_format or ""
    if "%" not in fmt:
        return None
    return "scaled" if "%" in _QUOTED.sub("", fmt) else "literal"


def _sheet(fws, vws) -> dict:
    # Comments can create additional cells during loading; check the resulting bounds as well.
    if any(ws.max_row * ws.max_column > MAX_WORKBOOK_CELLS for ws in (fws, vws)):
        raise _ExpansionLimit()
    s = Counter()
    indicators = Counter({k: 0 for k in INDICATORS})
    kinds = Counter({k: 0 for k in ("quarter", "month_end", "year_to", "calendar")})
    units = Counter(_unit_hints(""))
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
            s["formulas_external"] += _external_formula(formula)
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
    units.update(_unit_hints(v))


def inspect(path: Path, raw: bytes | None = None) -> dict:
    """Inspect `raw` when given (the bytes whose hash was checked), else the file at `path`."""
    raw = Path(path).read_bytes() if raw is None else raw
    print_units = {kind: Counter(_unit_hints("")) for kind in ("header", "footer")}
    out: dict = {"sha256": hashlib.sha256(raw).hexdigest(), "status": "refused", "archive": _archive(raw, print_units)}
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
        out.update({f"{kind}_unit_hints": dict(counts) for kind, counts in print_units.items()})
        out["status"] = "ok"
    except Exception:  # noqa: BLE001 - untrusted input: the reason may quote the document, so only a fixed code leaves
        out = {"sha256": out["sha256"], "status": "error", "archive": out["archive"]}
    return out
