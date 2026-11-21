"""Bounded stdlib reader for the cells of one manually imported workbook (Phase 4AP).

The workbook is hostile input. It is read in a resource-limited child process (the same helpers as the PDF readers) with
`zipfile` and `xml.parsers.expat` only: no macro runs, no formula is evaluated (a formula cell is reported as kind
`formula`, with its cached text), no relationship is followed outside the archive, and any DTD or entity declaration, in
any encoding, refuses the whole file. Every refusal is fixed wording; no workbook text or exception message is raised or
logged. The archive limits are the CPI reader's; the cell budget is the Phase 4AN inspector's.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import logging
import math
import posixpath
import re
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path, PurePosixPath
from typing import Literal
from xml.parsers import expat

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import ExtractionLimits
from nzstats.research.extract_pdf import PDF_TIMEOUT_SECONDS, _apply_child_limits, _child_env

log = logging.getLogger(__name__)

MAX_ARCHIVE = 16 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024
MAX_MEMBERS = 200
MAX_RATIO = 250
MAX_CELLS = 100_000
MAX_MERGES = 1_000
MAX_TEXT_CHARS = (
    1_000_000  # all stored cell and drawing text; keeps the child's JSON reply under its file limit
)
MAX_XML_ELEMENTS = 1_000_000
MAX_XML_DEPTH = 64
_LIMITS = (
    ExtractionLimits()
)  # the child's resource limits; its reply file limit is 8 * max_chars + 1 MiB
_REPLY_CAP = 8 * _LIMITS.max_chars + 1024 * 1024

Kind = Literal["number", "text", "bool", "error", "formula"]
State = Literal["visible", "hidden", "very_hidden"]

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships}"
_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types}"
_DRAW = "http://schemas.openxmlformats.org/drawingml/2006/main}"
_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_STATES: dict[str, State] = {"visible": "visible", "hidden": "hidden", "veryHidden": "very_hidden"}
_DECLARATIONS = tuple(
    marker.encode(enc)
    for marker in ("<!DOCTYPE", "<!ENTITY")
    for enc in ("utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be")
)
_ACTIVE = re.compile(
    r"vbaproject|^xl/externallinks/|^xl/activex/|^xl/embeddings/|^xl/connections\.xml$|^customui",
    re.IGNORECASE,
)
_ACTIVE_TYPE = re.compile(r"macroenabled|vbaproject|activex|oleobject", re.IGNORECASE)
_CELL_REF = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
# Built-in number formats (ECMA-376 §18.8.30). Ids not listed here are kept as `[builtin N]`.
_BUILTIN_FORMATS = {
    0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 10: "0.00%", 11: "0.00E+00",
    12: "# ?/?", 13: "# ??/??", 14: "mm-dd-yy", 15: "d-mmm-yy", 16: "d-mmm", 17: "mmm-yy", 18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM", 20: "h:mm", 21: "h:mm:ss", 22: "m/d/yy h:mm", 37: "#,##0 ;(#,##0)",
    38: "#,##0 ;[Red](#,##0)", 39: "#,##0.00;(#,##0.00)", 40: "#,##0.00;[Red](#,##0.00)", 45: "mm:ss",
    46: "[h]:mm:ss", 47: "mmss.0", 48: "##0.0E+0", 49: "@",
}  # fmt: skip
_LOCALE_DATE_IDS = frozenset(range(27, 37)) | frozenset(range(50, 59))
_FORMAT_LITERALS = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]|_.|\*.')


@dataclass(frozen=True)
class XCell:
    row: int
    col: int
    kind: Kind
    text: str  # the stored `<v>` text (or shared or inline string); a formula's cached text, never evaluated
    bold: bool
    number_format: str
    is_date: bool


@dataclass(frozen=True)
class XSheet:
    position: int  # 1-based order in the workbook
    name: str
    state: State
    cells: Mapping[tuple[int, int], XCell]
    merges: tuple[tuple[int, int, int, int], ...]  # (first row, first col, last row, last col)


@dataclass(frozen=True)
class WorkbookCells:
    sheets: tuple[XSheet, ...]
    drawing_texts: tuple[
        str, ...
    ]  # one entry per non-empty DrawingML paragraph, runs joined in order
    date1904: bool


class _Refused(Exception):
    """Internal: carries a fixed message only."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _refuse(message: str) -> _Refused:
    return _Refused(message)


def read_cells(body: bytes, *, isolate: bool | None = None) -> WorkbookCells:
    """The workbook's cells, styles and drawing text. Raises `IngestError` with fixed text on any refusal."""
    if len(body) > MAX_ARCHIVE:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "workbook too large")
    if isolate if isolate is not None else True:
        return _read_isolated(body)
    return _read(body)


def _read(body: bytes) -> WorkbookCells:
    try:
        try:
            archive = zipfile.ZipFile(io.BytesIO(body))
        except (zipfile.BadZipFile, ValueError, OSError, EOFError):
            raise _refuse("workbook archive refused") from None
        with archive:
            parts = _checked_members(archive)
            return _workbook(parts)
    except _Refused as refused:
        message = refused.message
    except Exception as exc:  # noqa: BLE001 - hostile input: whatever fails is one fixed refusal, its text never kept
        log.warning("workbook unreadable (%s)", type(exc).__name__)
        message = "workbook cannot be read"
    error_class = (
        ErrorClass.LAYOUT_CHANGED
        if message == "workbook cannot be read"
        else ErrorClass.VALIDATION_FAILED
    )
    raise IngestError(error_class, message)


def _checked_members(z: zipfile.ZipFile) -> dict[str, bytes]:
    members = z.infolist()
    if (
        len(members) > MAX_MEMBERS
        or sum(m.file_size for m in members) > MAX_UNPACKED
        or any(m.file_size / max(m.compress_size, 1) > MAX_RATIO for m in members)
    ):
        raise _refuse("workbook archive refused")
    names = [m.filename for m in members]
    for m in members:
        path = PurePosixPath(m.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in m.filename or m.flag_bits & 1:
            raise _refuse("workbook archive refused")
    if len(set(names)) != len(names) or "[Content_Types].xml" not in names:
        raise _refuse("workbook archive refused")
    if any(_ACTIVE.search(name) for name in names):
        raise _refuse("workbook content refused")
    parts: dict[str, bytes] = {}
    for m in members:
        data = z.read(
            m
        )  # bounded: zipfile stops at the declared size, which the limits above already checked
        if any(d in data for d in _DECLARATIONS):
            raise _refuse("workbook content refused")
        parts[m.filename] = data
    return parts


class _Node:
    __slots__ = ("attrs", "children", "parts", "tag")

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        self.tag, self.attrs = tag, attrs
        self.children: list[_Node] = []
        self.parts: list[str] = []

    @property
    def text(self) -> str:
        return "".join(self.parts)

    def iter(self, tag: str, *, skip: str | None = None) -> Iterator[_Node]:
        stack = [self]
        while stack:
            node = stack.pop()
            if skip is not None and node.tag == skip:
                continue
            if node.tag == tag:
                yield node
            stack.extend(reversed(node.children))

    def find(self, tag: str) -> _Node | None:
        return next((c for c in self.children if c.tag == tag), None)


def _parse(data: bytes, budget: list[int]) -> _Node:
    """Well-formed XML into a small tree. No DTD, entity or external resource; depth and element count bounded."""
    parser = expat.ParserCreate(namespace_separator="}")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    stack: list[_Node] = []
    roots: list[_Node] = []

    def declaration(*_args: object) -> None:
        raise _refuse("workbook content refused")

    def start(tag: str, attrs: dict[str, str]) -> None:
        budget[0] += 1
        if budget[0] > MAX_XML_ELEMENTS:
            raise _refuse("workbook over cell budget")
        if len(stack) >= MAX_XML_DEPTH:
            raise ValueError("too deep")
        node = _Node(tag, attrs)
        (stack[-1].children if stack else roots).append(node)
        stack.append(node)

    def end(_tag: str) -> None:
        stack.pop()

    def chars(text: str) -> None:
        if stack:
            stack[-1].parts.append(text)

    parser.StartDoctypeDeclHandler = declaration
    parser.EntityDeclHandler = declaration
    parser.ExternalEntityRefHandler = declaration
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    parser.Parse(data, True)
    if len(roots) != 1:
        raise ValueError("no root")
    return roots[0]


def _rels_path(part: str) -> str:
    return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")


def _relationships(trees: dict[str, _Node], part: str) -> dict[str, tuple[str, str, bool]]:
    """`{id: (type, resolved part name, external)}` for `part`'s relationships (none when it has no .rels)."""
    tree = trees.get(_rels_path(part))
    if tree is None:
        return {}
    if tree.tag != _PKG_REL + "Relationships":
        raise ValueError("bad relationships")
    out: dict[str, tuple[str, str, bool]] = {}
    base = posixpath.dirname(part)
    for rel in tree.iter(_PKG_REL + "Relationship"):
        target = rel.attrs.get("Target", "")
        external = rel.attrs.get("TargetMode") == "External"
        if external:
            resolved = ""
        elif target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join(base, target))
        if resolved.startswith(".."):
            raise ValueError("relationship escapes the archive")
        out[rel.attrs.get("Id", "")] = (rel.attrs.get("Type", ""), resolved, external)
    return out


def _workbook(parts: dict[str, bytes]) -> WorkbookCells:
    budget = [0]
    trees = {
        name: _parse(data, budget)
        for name, data in parts.items()
        if name.lower().endswith((".xml", ".rels"))
        or data.lstrip(b"\xef\xbb\xbf\xff\xfe\x00 \t\r\n").startswith(b"<")
    }
    types = trees["[Content_Types].xml"]
    if types.tag != _TYPES + "Types":
        raise ValueError("bad content types")
    if any(_ACTIVE_TYPE.search(node.attrs.get("ContentType", "")) for node in types.children):
        raise _refuse("workbook content refused")
    office = [
        (target, external)
        for rel_type, target, external in _relationships(trees, "").values()
        if rel_type == _REL_TYPE + "officeDocument"
    ]
    if len(office) != 1 or office[0][1] or office[0][0] not in trees:
        raise ValueError("no workbook part")
    workbook_part = office[0][0]
    workbook = trees[workbook_part]
    if workbook.tag != _MAIN + "workbook":
        raise ValueError("not a spreadsheet")
    pr = workbook.find(_MAIN + "workbookPr")
    date1904 = pr is not None and pr.attrs.get("date1904", "0") in ("1", "true")
    rels = _relationships(trees, workbook_part)

    def related(kind: str) -> _Node | None:
        found = [
            target for rel_type, target, external in rels.values() if rel_type == _REL_TYPE + kind
        ]
        if len(found) > 1 or any(t not in trees for t in found):
            raise ValueError("ambiguous part")
        return trees[found[0]] if found else None

    strings = _shared_strings(related("sharedStrings"))
    formats = _styles(related("styles"))
    sheets_node = workbook.find(_MAIN + "sheets")
    if sheets_node is None:
        raise ValueError("no sheets")
    sheets: list[XSheet] = []
    seen_targets: set[str] = set()
    counters = [0, 0]  # cells, text characters
    for position, sheet in enumerate(sheets_node.iter(_MAIN + "sheet"), start=1):
        rel = rels.get(sheet.attrs.get(_DOC_REL + "id", ""))
        if rel is None or rel[2] or rel[1] not in trees or rel[1] in seen_targets:
            raise ValueError("missing sheet target")
        seen_targets.add(rel[1])
        state = _STATES.get(sheet.attrs.get("state", "visible"))
        name = sheet.attrs.get("name", "")
        if state is None or not name:
            raise ValueError("bad sheet")
        counters[1] += len(name)
        if rel[0] == _REL_TYPE + "chartsheet":
            sheets.append(XSheet(position, name, state, {}, ()))
            continue
        if rel[0] != _REL_TYPE + "worksheet":
            raise ValueError("unsupported sheet type")
        cells, merges = _sheet_cells(trees[rel[1]], strings, formats, counters)
        sheets.append(XSheet(position, name, state, cells, merges))
    drawing_texts = _drawing_texts(trees, counters)
    if counters[1] > MAX_TEXT_CHARS:
        raise _refuse("workbook over cell budget")
    return WorkbookCells(tuple(sheets), drawing_texts, date1904)


def _shared_strings(tree: _Node | None) -> list[str]:
    if tree is None:
        return []
    return [
        "".join(t.text for t in si.iter(_MAIN + "t", skip=_MAIN + "rPh"))
        for si in tree.iter(_MAIN + "si")
    ]


def _bold(font: _Node) -> bool:
    b = font.find(_MAIN + "b")
    return b is not None and b.attrs.get("val", "1") not in ("0", "false")


def _styles(tree: _Node | None) -> list[tuple[str, bool, bool]]:
    """Per cell style index: (number format code, bold, is_date)."""
    if tree is None:
        return [("General", False, False)]
    custom: dict[int, str] = {}
    num_fmts = tree.find(_MAIN + "numFmts")
    for fmt in num_fmts.children if num_fmts is not None else ():
        custom[int(fmt.attrs["numFmtId"])] = fmt.attrs.get("formatCode", "")
    fonts_node = tree.find(_MAIN + "fonts")
    fonts = [_bold(f) for f in (fonts_node.children if fonts_node is not None else ())]
    xfs = tree.find(_MAIN + "cellXfs")
    out: list[tuple[str, bool, bool]] = []
    for xf in xfs.children if xfs is not None else ():
        num_id, font_id = int(xf.attrs.get("numFmtId", "0")), int(xf.attrs.get("fontId", "0"))
        code = custom.get(num_id, _BUILTIN_FORMATS.get(num_id, f"[builtin {num_id}]"))
        is_date = (
            _date_format(code)
            if num_id in custom or num_id in _BUILTIN_FORMATS
            else num_id in _LOCALE_DATE_IDS
        )
        bold = fonts[font_id] if 0 <= font_id < len(fonts) else False
        out.append((code, bold, is_date))
    return out or [("General", False, False)]


def _date_format(code: str) -> bool:
    if code == "General":
        return False
    section = _FORMAT_LITERALS.sub("", code).split(";")[0]
    return bool(re.search(r"[dmyhs]", section, re.IGNORECASE))


def _coordinate(ref: str) -> tuple[int, int]:
    match = _CELL_REF.fullmatch(ref)
    if match is None:
        raise ValueError("bad reference")
    col = 0
    for letter in match[1]:
        col = col * 26 + ord(letter) - 64
    row = int(match[2])
    if row > 1_048_576 or col > 16_384:
        raise ValueError("bad reference")
    return row, col


def _sheet_cells(
    tree: _Node, strings: list[str], formats: list[tuple[str, bool, bool]], counters: list[int]
) -> tuple[dict[tuple[int, int], XCell], tuple[tuple[int, int, int, int], ...]]:
    if tree.tag != _MAIN + "worksheet":
        raise ValueError("not a worksheet")
    cells: dict[tuple[int, int], XCell] = {}
    data = tree.find(_MAIN + "sheetData")
    last_row = 0
    for row in data.iter(_MAIN + "row") if data is not None else ():
        row_no = int(row.attrs["r"]) if "r" in row.attrs else last_row + 1
        if row_no <= last_row:
            raise ValueError("rows out of order")
        last_row, last_col = row_no, 0
        for c in row.children:
            if c.tag != _MAIN + "c":
                continue
            r, col = _coordinate(c.attrs["r"]) if "r" in c.attrs else (row_no, last_col + 1)
            if r != row_no or col <= last_col:
                raise ValueError("cells out of order")
            last_col = col
            cell = _cell(c, r, col, strings, formats)
            if cell is None:
                continue
            counters[0] += 1
            counters[1] += len(cell.text)
            if counters[0] > MAX_CELLS or counters[1] > MAX_TEXT_CHARS:
                raise _refuse("workbook over cell budget")
            cells[(r, col)] = cell
    merges: list[tuple[int, int, int, int]] = []
    merge_node = tree.find(_MAIN + "mergeCells")
    for m in merge_node.iter(_MAIN + "mergeCell") if merge_node is not None else ():
        first, _, last = m.attrs.get("ref", "").partition(":")
        (r1, c1), (r2, c2) = _coordinate(first), _coordinate(last or first)
        if r2 < r1 or c2 < c1:
            raise ValueError("bad merge")
        merges.append((r1, c1, r2, c2))
        if len(merges) > MAX_MERGES:
            raise _refuse("workbook over cell budget")
    return cells, tuple(merges)


def _cell(
    c: _Node, row: int, col: int, strings: list[str], formats: list[tuple[str, bool, bool]]
) -> XCell | None:
    style = int(c.attrs.get("s", "0"))
    if not 0 <= style < len(formats):
        raise ValueError("bad style")
    number_format, bold, is_date = formats[style]
    v, f, inline = c.find(_MAIN + "v"), c.find(_MAIN + "f"), c.find(_MAIN + "is")
    t = c.attrs.get("t", "n")
    kind: Kind
    if f is not None:
        kind, text = "formula", v.text if v is not None else ""
    elif t == "inlineStr":
        if inline is None:
            return None
        kind, text = "text", "".join(x.text for x in inline.iter(_MAIN + "t", skip=_MAIN + "rPh"))
    elif v is None:
        return None  # a styled empty cell holds no value
    elif t == "s":
        kind, text = "text", strings[int(v.text)]
    elif t in ("str", "d"):
        kind, text = "text", v.text
    elif t == "b":
        kind, text = "bool", v.text
    elif t == "e":
        kind, text = "error", v.text
    elif t == "n":
        kind, text = "number", v.text.strip()
    else:
        raise ValueError("unknown cell type")
    return XCell(row, col, kind, text, bold, number_format, is_date)


def _drawing_texts(trees: dict[str, _Node], counters: list[int]) -> tuple[str, ...]:
    out: list[str] = []
    for name in sorted(trees):
        if not re.fullmatch(r"xl/drawings/[^/]+\.xml", name):
            continue
        for paragraph in trees[name].iter(_DRAW + "p"):
            text = "".join(t.text for t in paragraph.iter(_DRAW + "t"))
            if text.strip():
                counters[1] += len(text)
                out.append(text)
    return tuple(out)


def serial_date(text: str, date1904: bool) -> date | None:
    """The calendar date of a whole-day serial number, else None (a time of day, an invalid or pre-March-1900 value)."""
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value) or value != int(value):
        return None
    serial = int(value)
    if date1904:
        if not 0 <= serial <= 2_957_003:
            return None
        return date(1904, 1, 1) + timedelta(days=serial)
    if (
        not 61 <= serial <= 2_958_465
    ):  # serials below 61 straddle the 1900 system's phantom 29 February
        return None
    return date(1899, 12, 30) + timedelta(days=serial)


def _canonical(wb: WorkbookCells) -> dict:
    return {
        "date1904": wb.date1904,
        "drawing_texts": list(wb.drawing_texts),
        "sheets": [
            {
                "position": s.position,
                "name": s.name,
                "state": s.state,
                "merges": [list(m) for m in s.merges],
                "cells": [list(dataclasses.astuple(c)) for _, c in sorted(s.cells.items())],
            }
            for s in wb.sheets
        ],
    }


def _from_canonical(data: dict) -> WorkbookCells:
    sheets = tuple(
        XSheet(
            s["position"],
            s["name"],
            s["state"],
            {(c[0], c[1]): XCell(*c) for c in s["cells"]},
            tuple(tuple(m) for m in s["merges"]),
        )
        for s in data["sheets"]
    )
    return WorkbookCells(sheets, tuple(data["drawing_texts"]), bool(data["date1904"]))


def cells_sha256(wb: WorkbookCells) -> str:
    """Change-detection key over every cell (with its style), merge, sheet state and drawing paragraph."""
    canonical = json.dumps(
        _canonical(wb), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def render_sheet(sheet: XSheet) -> str:
    """One tab-separated line per row of a sheet's cell texts (stored text; a formula's cached text)."""
    rows: dict[int, list[str]] = {}
    for (r, _c), cell in sorted(sheet.cells.items()):
        rows.setdefault(r, []).append(cell.text)
    return "\n".join("\t".join(texts) for _, texts in sorted(rows.items()))


def render_text(wb: WorkbookCells) -> str:
    """The workbook as text: each sheet's name, then its rows (see `render_sheet`)."""
    return "\n".join(
        part for sheet in wb.sheets for part in (sheet.name, render_sheet(sheet)) if part
    )


def _limit_error() -> IngestError:
    return IngestError(ErrorClass.VALIDATION_FAILED, "workbook reader limit (time or memory)")


_CHILD_SNIPPET = (
    "import sys; r = sys.argv[1];"
    " sys.path.insert(0, r) if 'site-packages' not in r else None; sys.argv[1:] = sys.argv[2:];"
    " from nzstats.research.xlsx_cells import _child_main; raise SystemExit(_child_main())"
)


def _read_isolated(body: bytes, timeout: float = PDF_TIMEOUT_SECONDS) -> WorkbookCells:
    # `-I` ignores PYTHONPATH, so the child is told which source tree to load: the one this process runs from.
    root = str(Path(__file__).resolve().parents[2])
    command = [sys.executable, "-I", "-c", _CHILD_SNIPPET, root]
    with tempfile.TemporaryFile() as out:
        try:
            done = subprocess.run(
                command, input=body, stdout=out, stderr=subprocess.DEVNULL, timeout=timeout,
                check=False, env=_child_env(),
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            raise _limit_error() from None
        if out.seek(0, 2) > _REPLY_CAP:
            raise _limit_error()
        out.seek(0)
        raw = out.read()
    try:
        reply = json.loads(raw)
    except ValueError:
        log.warning("workbook reader child exited %s without a result", done.returncode)
        raise _limit_error() from None
    if "error" in reply:
        error_class, message = reply["error"]
        raise IngestError(ErrorClass(error_class), str(message))
    return _from_canonical(reply["ok"])


def _child_main() -> int:
    _apply_child_limits(_LIMITS)
    try:
        result: dict = {"ok": _canonical(_read(sys.stdin.buffer.read()))}
    except IngestError as exc:
        result = {"error": [exc.error_class.value, str(exc)]}
    except MemoryError:
        result = {"error": [ErrorClass.VALIDATION_FAILED.value, str(_limit_error())]}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0
