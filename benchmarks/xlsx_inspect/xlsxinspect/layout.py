"""Masked layout probe (Phase 4AO): where things are, never what they say.

Runs only on a workbook that `inspect` accepted (same archive checks, same bounds). Every metric is a row or column index,
a count or a flag, so an ANZ-specific adapter can be shaped on synthetic replicas without anyone reading the workbook.
Drawing text (text boxes on a cover sheet) is matched against fixed patterns and only counted.
"""

from __future__ import annotations

import calendar
import contextlib
import io
import itertools
import re
import warnings
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from xml.parsers import expat

from nzstats.research.table_parse import column_kind
from openpyxl import load_workbook

from xlsxinspect.inspect import _ANZ, _NOTICE, _UNITS, INDICATORS, _unit_hints, inspect

MAX_TEXT_ROWS = 200
_SOURCE = re.compile(r"^\s*sources?\s*:", re.IGNORECASE)
_FORECAST_WORD = re.compile(r"\bforecast", re.IGNORECASE)
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_DATE_TEXT = re.compile(
    rf"\b\d{{1,2}}\s+{_MON}\s+\d{{4}}\b|\b{_MON}\s+\d{{4}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b", re.IGNORECASE
)
_DRAWING = re.compile(r"^xl/drawings/[^/]+\.xml$")
_DRAW_NS = "http://schemas.openxmlformats.org/drawingml/2006/main}"
_TEXT_BODIES = {
    "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}txBody",
    _DRAW_NS + "txBody",
}
_SOURCE_WORD = re.compile(r"\bsources?\b", re.IGNORECASE)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_P_MONTH = re.compile(rf"\b({'|'.join(_MONTHS)})[a-z]*\.?[\s\-']*(\d{{4}}|\d{{2}})\b", re.IGNORECASE)
_P_Q_FIRST = re.compile(r"\bq([1-4])[\s\-']*(\d{4}|\d{2})\b", re.IGNORECASE)
_P_Q_LAST = re.compile(r"\b(\d{4})\s?q([1-4])\b", re.IGNORECASE)


def _year(token: str) -> int:
    return int(token) if len(token) == 4 else 2000 + int(token)


def _periods(text: str) -> list[tuple[int, int, frozenset[int]]]:
    """(position, year, months) for every month or quarter named in `text`, in order. A month names one month."""
    found = [
        (m.start(), _year(m[2]), frozenset({_MONTHS.index(m[1][:3].lower()) + 1})) for m in _P_MONTH.finditer(text)
    ]
    for m in _P_Q_FIRST.finditer(text):
        q = int(m[1])
        found.append((m.start(), _year(m[2]), frozenset(range(3 * q - 2, 3 * q + 1))))
    for m in _P_Q_LAST.finditer(text):
        q = int(m[2])
        found.append((m.start(), int(m[1]), frozenset(range(3 * q - 2, 3 * q + 1))))
    return sorted(found, key=lambda f: f[0])


_W_FROM = re.compile(r"\b(?:from|begin(?:s|ning)?|start(?:s|ing)?|onwards?)\b", re.IGNORECASE)
_W_TO = re.compile(r"\b(?:to|until|up to|through)\b", re.IGNORECASE)
_W_ASAT = re.compile(r"\bas (?:at|of)\b|\bupdated\b|\bpublished\b", re.IGNORECASE)


def _wording(text: str) -> int:
    """0 none, 1 from/begin/start, 2 to/until, 3 as at/as of/updated, 4 more than one kind."""
    kinds = [i for i, p in enumerate((_W_FROM, _W_TO, _W_ASAT), 1) if p.search(text)]
    return kinds[0] if len(kinds) == 1 else (4 if kinds else 0)


_S_BOLD = re.compile(r"\bbold", re.IGNORECASE)
_S_ITALIC = re.compile(r"\bitalic", re.IGNORECASE)
_S_COLOUR = re.compile(r"\b(?:red|blue|green|grey|gray|orange|purple|colou?r(?:ed)?)\b", re.IGNORECASE)
_S_SHADE = re.compile(r"\bshad(?:ed|ing|e)\b|\bhighlight", re.IGNORECASE)


def _style(text: str) -> int:
    """0 none, 1 bold, 2 italic, 3 a colour, 4 shading, 5 more than one."""
    kinds = [i for i, p in enumerate((_S_BOLD, _S_ITALIC, _S_COLOUR, _S_SHADE), 1) if p.search(text)]
    return kinds[0] if len(kinds) == 1 else (5 if kinds else 0)


def _font_attr(a: tuple, b: tuple) -> int:
    """Bitmask of the font attributes that differ: 1 bold, 2 italic, 4 underline, 8 strike, 16 colour."""
    bits = sum(1 << i for i in range(4) if bool(a[i]) != bool(b[i]))
    return bits | (16 if a[4:] != b[4:] else 0)


def _quarter(month: int) -> frozenset[int]:
    q = (month - 1) // 3
    return frozenset(range(3 * q + 1, 3 * q + 4))


def _as_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    return v if isinstance(v, date) else None


def _font_key(cell) -> tuple:
    f = cell.font
    c = f.color
    return (f.b, f.i, f.u, f.strike, c.rgb if c is not None and c.type == "rgb" else None, c.theme if c else None)


def _fill_key(cell) -> tuple:
    f = cell.fill
    c = f.fgColor
    return (f.fill_type, c.type, c.rgb if c.type == "rgb" else None, c.theme, c.indexed, c.tint)


def _sheet_layout(ws) -> dict:
    dates: dict[int, dict[int, date]] = {}
    numeric_cols: set[int] = set()
    first_numeric: dict[int, object] = {}
    text_rows: set[int] = set()
    markers: list[tuple[int, int]] = []
    indicator: list[tuple[int, int]] = []
    unit: list[tuple[int, int]] = []
    sources: list[int] = []
    texts: list[tuple[int, str]] = []
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if v is None:
                continue
            if (d := _as_date(v)) is not None:
                dates.setdefault(cell.column, {})[cell.row] = d
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                numeric_cols.add(cell.column)
                if cell.row not in first_numeric or cell.column < first_numeric[cell.row].column:
                    first_numeric[cell.row] = cell
            elif isinstance(v, str):
                text_rows.add(cell.row)
                texts.append((cell.row, v))
                if column_kind((v,)) == "forecast":
                    markers.append((cell.row, cell.column))
                if any(p.search(v) for p in INDICATORS.values()):
                    indicator.append((cell.row, cell.column))
                if any(p.search(v) for p in _UNITS.values()):
                    unit.append((cell.row, cell.column))
                if _SOURCE.search(v):
                    sources.append(cell.row)

    out: dict = {"date_cols": sorted(dates), "date_col_counts": [len(dates[c]) for c in sorted(dates)]}
    main = max(dates, key=lambda c: (len(dates[c]), -c)) if dates else None
    rows = sorted(dates[main]) if main else []
    series = [dates[main][r] for r in rows] if main else []
    months = [d.year * 12 + d.month for d in series]
    out.update(
        date_first_row=rows[0] if rows else None,
        date_last_row=rows[-1] if rows else None,
        date_steps=sorted({b - a for a, b in itertools.pairwise(months)}),
        date_monotonic=all(a < b for a, b in itertools.pairwise(series)) if series else None,
        date_month_end=sum(d.day == calendar.monthrange(d.year, d.month)[1] for d in series),
        date_month_start=sum(d.day == 1 for d in series),
        date_gaps=(rows[-1] - rows[0] + 1 - len(rows)) if rows else 0,
    )
    merges = list(ws.merged_cells.ranges)
    merge_rows: list[int] = []
    merge_cols: list[int] = []
    for r, c in markers:
        for m in merges:
            if (m.min_row, m.min_col) == (r, c):
                merge_rows += [m.min_row, m.max_row]
                merge_cols += [m.min_col, m.max_col]
    out.update(
        marker_rows=[r for r, _ in markers],
        marker_cols=[c for _, c in markers],
        marker_date_index=[rows.index(r) if r in rows else -1 for r, _ in markers],
        marker_merge_rows=merge_rows,
        marker_merge_cols=merge_cols,
        indicator_rows=[r for r, _ in indicator],
        indicator_cols=[c for _, c in indicator],
        unit_rows=[r for r, _ in unit],
        unit_cols=[c for _, c in unit],
        source_rows=sources,
        numeric_cols=sorted(numeric_cols),
        text_rows=sorted(text_rows)[:MAX_TEXT_ROWS],
        merge_min_rows=[m.min_row for m in merges],
        merge_min_cols=[m.min_col for m in merges],
        merge_max_rows=[m.max_row for m in merges],
        merge_max_cols=[m.max_col for m in merges],
    )
    fills: list[int] = []
    fonts: list[int] = []
    col_fill: list[tuple[int, int]] = []
    col_font: list[tuple[int, int, int]] = []
    for previous, r in itertools.pairwise(rows):
        fill_hit = font_hit = False
        for c in range(1, ws.max_column + 1):
            now, before = ws.cell(row=r, column=c), ws.cell(row=previous, column=c)
            if _fill_key(now) != _fill_key(before):
                col_fill.append((c, r))
                fill_hit = True
            if (attr := _font_attr(_font_key(now), _font_key(before))) != 0:
                col_font.append((c, r, attr))
                font_hit = True
        fills += [r] if fill_hit else []
        fonts += [r] if font_hit else []
    out["fill_change_rows"], out["font_change_rows"] = fills, fonts
    col_fill.sort()
    col_font.sort()
    out["col_fill_change_cols"], out["col_fill_change_rows"] = [c for c, _ in col_fill], [r for _, r in col_fill]
    out["col_font_change_cols"], out["col_font_change_rows"] = [c for c, _, _ in col_font], [r for _, r, _ in col_font]
    out["col_font_change_attr"] = [a for _, _, a in col_font]
    last = rows[-1] if rows else 0
    out["note_rows"] = sorted({r for r, _ in texts if r > last})
    out["note_source_rows"] = sorted({r for r, v in texts if _SOURCE_WORD.search(v)})
    noted = [(r, v) for r, v in texts if _FORECAST_WORD.search(v)]
    out["note_forecast_rows"] = [r for r, _ in noted]
    out["note_wording"] = [_wording(v) for _, v in noted]
    out["note_style"] = [_style(v) for _, v in noted]
    out["title_unit_hints"] = _unit_hints(ws.title)
    out["title_units"] = sum(out["title_unit_hints"].values())
    out["title_indicators"] = sum(bool(p.search(ws.title)) for p in INDICATORS.values())
    exact: list[int] = []
    quarter: list[int] = []
    counts: list[int] = []
    for _, v in noted:
        found = _periods(v)
        counts.append(len(found))
        if not found:
            exact.append(-1)
            quarter.append(-1)
            continue
        _, year, months = found[0]
        months_q = _quarter(min(months)) if len(months) == 1 else months
        hit = [i for i, d in enumerate(series) if d.year == year and d.month in months]
        hit_q = [i for i, d in enumerate(series) if d.year == year and d.month in months_q]
        exact.append(hit[0] if len(hit) == 1 else -1)
        quarter.append(hit_q[0] if len(hit_q) == 1 else -1)
    out["note_period_index"], out["note_period_quarter_index"], out["note_period_count"] = exact, quarter, counts
    out["date_months"] = sorted({d.month for d in series})
    return out


def _drawing_texts(data: bytes) -> tuple[list[str], list[str]]:
    """Collect text runs and their logical paragraphs from one archive-validated drawing part."""
    runs: list[str] = []
    paragraphs: list[str] = []
    parents: list[str] = []
    paragraph: list[str] = []
    paragraph_depth = 0
    run: list[str] = []

    def refuse(*_a):
        raise ValueError("declaration")

    def start(tag, _attrs):
        nonlocal paragraph_depth
        if parser.CharacterDataHandler is not None:
            raise ValueError("invalid drawing text")
        depth = len(parents)
        if not paragraph_depth and tag == _DRAW_NS + "p" and parents and parents[-1] in _TEXT_BODIES:
            paragraph_depth = depth + 1
        if paragraph_depth and depth == paragraph_depth and tag in {_DRAW_NS + "br", _DRAW_NS + "fld"}:
            paragraph.append("\n")
        if (
            paragraph_depth
            and depth == paragraph_depth + 1
            and parents[-1] in {_DRAW_NS + "r", _DRAW_NS + "fld"}
            and tag == _DRAW_NS + "t"
        ):
            parser.CharacterDataHandler = run.append
        parents.append(tag)

    def end(tag):
        nonlocal paragraph_depth
        if parser.CharacterDataHandler is not None:
            parser.CharacterDataHandler = None
            text = "".join(run)
            runs.append(text)
            paragraph.append(text)
            run.clear()
        if paragraph_depth and len(parents) == paragraph_depth + 1 and tag == _DRAW_NS + "fld":
            paragraph.append("\n")
        if len(parents) == paragraph_depth:
            paragraphs.append("".join(paragraph))
            paragraph.clear()
            paragraph_depth = 0
        parents.pop()

    parser = expat.ParserCreate(namespace_separator="}")
    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.ExternalEntityRefHandler = refuse
    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.Parse(data, True)
    return runs, paragraphs


def drawing_counts(parts: list[bytes]) -> dict:
    """Count fixed patterns in drawing runs, with unit hints counted once per paragraph."""
    counts = Counter()
    units = Counter(_unit_hints(""))
    for data in parts:
        runs, paragraphs = _drawing_texts(data)
        for t in runs:
            counts["runs"] += 1
            counts["anz"] += bool(_ANZ.search(t))
            counts["notice"] += bool(_NOTICE.search(t))
            counts["forecast"] += bool(_FORECAST_WORD.search(t))
            counts["dates"] += bool(_DATE_TEXT.search(t))
            counts["sources"] += bool(_SOURCE.search(t))
            counts["indicators"] += any(p.search(t) for p in INDICATORS.values())
        for paragraph in paragraphs:
            matches = {kind for line in paragraph.splitlines() for kind, count in _unit_hints(line).items() if count}
            units.update(matches)
    return {
        "drawing_text_runs": counts["runs"], "drawing_anz": counts["anz"], "drawing_notice": counts["notice"],
        "drawing_forecast": counts["forecast"], "drawing_dates": counts["dates"], "drawing_sources": counts["sources"],
        "drawing_units": units["percent"], "drawing_indicators": counts["indicators"], "drawing_unit_hints": dict(units),
    }  # fmt: skip


def layout(raw: bytes) -> dict:
    """Lay out `raw` only if `inspect` accepts it. A failure is a fixed code."""
    base = inspect(Path(), raw=raw)
    out: dict = {"sha256": base["sha256"], "status": base["status"]}
    if base["status"] != "ok":
        return out
    sink = io.StringIO()
    try:
        with warnings.catch_warnings(), contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            warnings.simplefilter("ignore")
            wb = load_workbook(io.BytesIO(raw), data_only=True, keep_links=False, keep_vba=False)
            sheets = [_sheet_layout(ws) for ws in wb.worksheets]
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                parts = [z.read(n) for n in z.namelist() if _DRAWING.match(n)]
            drawing = drawing_counts(parts)
        out.update(
            layout=sheets,
            drawing=drawing,
            header_unit_hints=base["header_unit_hints"],
            footer_unit_hints=base["footer_unit_hints"],
        )
    except Exception:  # noqa: BLE001 - untrusted input: only a fixed code leaves
        out = {"sha256": out["sha256"], "status": "error"}
    return out
