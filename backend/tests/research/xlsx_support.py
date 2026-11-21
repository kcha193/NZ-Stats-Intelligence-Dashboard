"""Synthetic OOXML workbooks for the Phase 4AP tests, written part by part with `zipfile` (no openpyxl).

Every name and figure here is invented. Nothing is copied from any bank's workbook.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date
from xml.sax.saxutils import escape, quoteattr

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAW = "http://schemas.openxmlformats.org/drawingml/2006/main"
XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
SHEET_TYPE = REL + "/worksheet"
WORKBOOK_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
MACRO_CT = "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
BUILTIN = {"General": 0, "0": 1, "0.00": 2, "#,##0": 3, "#,##0.00": 4, "0%": 9}


@dataclass(frozen=True)
class C:
    """One cell. `value`: number, text, date or bool. `kind` forces a type ('number' keeps a raw stored text)."""

    value: object
    bold: bool = False
    fmt: str | int = "General"
    kind: str | None = None  # number | text | inline | bool | error | formula
    formula: str = "SUM(B1:B2)"


@dataclass
class Sheet:
    name: str
    cells: dict[tuple[int, int], C] = field(default_factory=dict)
    merges: tuple[str, ...] = ()
    state: str | None = None  # None (visible), "hidden" or "veryHidden"


def col_letters(col: int) -> str:
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def a1(row: int, col: int) -> str:
    return f"{col_letters(col)}{row}"


def serial(d: date, date1904: bool = False) -> int:
    return (d - (date(1904, 1, 1) if date1904 else date(1899, 12, 30))).days


def build(
    sheets: list[Sheet],
    *,
    date1904: bool = False,
    drawing_paragraphs: tuple[tuple[str, ...], ...] = (),
    extra: dict[str, bytes] | None = None,
    content_type: str = WORKBOOK_CT,
    drop: tuple[str, ...] = (),
) -> bytes:
    """A workbook of `sheets`. `drawing_paragraphs` (runs per paragraph) go on a drawing of the first sheet."""
    strings: list[str] = []
    xfs: list[tuple[int, int]] = [(0, 0)]
    custom: dict[str, int] = {}

    def style(cell: C) -> int:
        if isinstance(cell.fmt, int):
            num = cell.fmt
        elif cell.fmt in BUILTIN:
            num = BUILTIN[cell.fmt]
        else:
            num = custom.setdefault(cell.fmt, 164 + len(custom))
        key = (num, 1 if cell.bold else 0)
        if key not in xfs:
            xfs.append(key)
        return xfs.index(key)

    parts: dict[str, bytes] = {}
    for index, sheet in enumerate(sheets, start=1):
        rows: dict[int, list[str]] = {}
        for (r, c), cell in sorted(sheet.cells.items()):
            ref, s = a1(r, c), style(cell)
            kind, value = cell.kind, cell.value
            if kind is None:
                if isinstance(value, bool):
                    kind = "bool"
                elif isinstance(value, date):
                    kind, value = "number", serial(value, date1904)
                elif isinstance(value, int | float):
                    kind = "number"
                else:
                    kind = "text"
            if kind == "number":
                xml = f'<c r="{ref}" s="{s}"><v>{value}</v></c>'
            elif kind == "text":
                strings.append(str(value))
                xml = f'<c r="{ref}" s="{s}" t="s"><v>{len(strings) - 1}</v></c>'
            elif kind == "inline":
                xml = f'<c r="{ref}" s="{s}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            elif kind == "bool":
                xml = f'<c r="{ref}" s="{s}" t="b"><v>{int(bool(value))}</v></c>'
            elif kind == "error":
                xml = f'<c r="{ref}" s="{s}" t="e"><v>{escape(str(value))}</v></c>'
            elif kind == "formula":
                xml = f'<c r="{ref}" s="{s}"><f>{escape(cell.formula)}</f><v>{value}</v></c>'
            else:
                raise ValueError(kind)
            rows.setdefault(r, []).append(xml)
        body = "".join(f'<row r="{r}">{"".join(cs)}</row>' for r, cs in sorted(rows.items()))
        merges = ""
        if sheet.merges:
            merges = f'<mergeCells count="{len(sheet.merges)}">' + "".join(
                f'<mergeCell ref="{m}"/>' for m in sheet.merges
            ) + "</mergeCells>"  # fmt: skip
        drawing = '<drawing r:id="rId1"/>' if index == 1 and drawing_paragraphs else ""
        parts[f"xl/worksheets/sheet{index}.xml"] = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{MAIN}" xmlns:r="{REL}"><sheetData>{body}</sheetData>{merges}{drawing}</worksheet>'
        ).encode()
    if drawing_paragraphs:
        paragraphs = "".join(
            "<a:p>" + "".join(f"<a:r><a:t>{escape(t)}</a:t></a:r>" for t in runs) + "</a:p>"
            for runs in drawing_paragraphs
        )
        parts["xl/drawings/drawing1.xml"] = (
            f'<xdr:wsDr xmlns:xdr="{XDR}" xmlns:a="{DRAW}"><xdr:twoCellAnchor><xdr:sp><xdr:txBody>'
            f"{paragraphs}</xdr:txBody></xdr:sp></xdr:twoCellAnchor></xdr:wsDr>"
        ).encode()
        parts["xl/worksheets/_rels/sheet1.xml.rels"] = (
            f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{REL}/drawing"'
            ' Target="../drawings/drawing1.xml"/></Relationships>'
        ).encode()
    states = {i: f' state="{s.state}"' if s.state else "" for i, s in enumerate(sheets, start=1)}
    flag = ' date1904="1"' if date1904 else ""
    parts["xl/workbook.xml"] = (
        f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><workbookPr{flag}/><sheets>'
        + "".join(
            f'<sheet name={quoteattr(s.name)} sheetId="{i}" r:id="rId{i}"{states[i]}/>'
            for i, s in enumerate(sheets, start=1)
        )
        + "</sheets></workbook>"
    ).encode()
    n = len(sheets)
    parts["xl/_rels/workbook.xml.rels"] = (
        f'<Relationships xmlns="{PKG}">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="{SHEET_TYPE}" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, n + 1)
        )
        + f'<Relationship Id="rId{n + 1}" Type="{REL}/styles" Target="styles.xml"/>'
        + f'<Relationship Id="rId{n + 2}" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>'
        + "</Relationships>"
    ).encode()
    parts["xl/sharedStrings.xml"] = (
        f'<sst xmlns="{MAIN}" count="{len(strings)}">'
        + "".join(f'<si><t xml:space="preserve">{escape(t)}</t></si>' for t in strings)
        + "</sst>"
    ).encode()
    num_fmts = "".join(
        f'<numFmt numFmtId="{i}" formatCode={quoteattr(code)}/>' for code, i in custom.items()
    )
    parts["xl/styles.xml"] = (
        f'<styleSheet xmlns="{MAIN}">'
        + (f'<numFmts count="{len(custom)}">{num_fmts}</numFmts>' if custom else "")
        + '<fonts count="2"><font><sz val="11"/></font><font><b/><sz val="11"/></font></fonts>'
        + f'<cellXfs count="{len(xfs)}">'
        + "".join(f'<xf numFmtId="{num}" fontId="{font}" applyFont="1"/>' for num, font in xfs)
        + "</cellXfs></styleSheet>"
    ).encode()
    parts["_rels/.rels"] = (
        f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{REL}/officeDocument"'
        ' Target="xl/workbook.xml"/></Relationships>'
    ).encode()
    sheet_types = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml"'
        ' ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, n + 1)
    )
    parts["[Content_Types].xml"] = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/xl/workbook.xml" ContentType="{content_type}"/>{sheet_types}</Types>'
    ).encode()
    parts.update(extra or {})
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            if name not in drop:
                z.writestr(name, data)
    return out.getvalue()
