"""Rows, columns and headers from positioned words (Phase 4AF). Geometry only: no meaning is attached here.

A table is a run of *body lines* (a text label followed by value-like or unit-like cells) with the header lines
directly above it. Columns come from the lowest header line; a group header ("Actual", "Forecast") covers the columns
from where it starts to where the next group starts. A value belongs to a column only when it overlaps exactly one
column by at least half its width. Anything else (a value straddling two columns, beyond the last column, a group
header that starts in a gap) makes the **whole table** ambiguous and it is rejected rather than repaired. A table that
continues on the next page is joined only when the next page repeats the same header, or has no header and the table
had no notes, and in either case carries no caption of its own (or one that says "continued"); a continuation that does not
fit is refused, never guessed.

Known limit: a whole row shifted by exactly one column is geometrically identical to a row with a missing first cell,
so it cannot be detected here (the period and value checks downstream still apply). All text is untrusted data.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from nzstats.research.table_words import Word

_MINUS = "−–"
_VALUE = re.compile(
    rf"^(?:[-{_MINUS}(]?\d[\d,]*(?:\.\d+)?\)?[*†‡¹²³⁴⁵⁶⁷⁸⁹]*%?|[-–—]|n/?a|\.{{2,}})$",
    re.IGNORECASE,
)
_UNIT = re.compile(r"^(?:%|ppt?s?|bps|% ?pa|% ?y/y|% ?q/q|index)$", re.IGNORECASE)
_NOTE = re.compile(r"^(?:sources?\b|notes?\b|[*†‡¹²³⁴⁵⁶⁷⁸⁹]|\(\d\))", re.IGNORECASE)
_CAPTION = re.compile(r"^(?:table|figure|chart|exhibit)\b", re.IGNORECASE)
_SCENARIO = re.compile(
    r"\b(?:scenarios?|downside|upside|alternative|stress(?:ed)?|sensitivity|illustrative|what[- ]if|risk case)\b",
    re.IGNORECASE,
)
_SCENARIO_HEADING = re.compile(
    r"^(?:scenarios?|downside|upside|alternative|stress(?:ed)?|sensitivity|illustrative|what[- ]if|risk case)\b",
    re.IGNORECASE,
)


def _caption(text: str) -> bool:
    return bool(_CAPTION.match(text) or _SCENARIO_HEADING.match(text))


_UNIT_HEADER = re.compile(r"^units?$", re.IGNORECASE)
_CONTINUED = re.compile(r"\bcont(?:inued|'d|\.)", re.IGNORECASE)
_HEADER_HEAD = re.compile(
    r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*$|^q[1-4]$", re.IGNORECASE
)
_YEAR_TAIL = re.compile(r"^(?:\d{4}|\d{2})[a-z]?$", re.IGNORECASE)

Role = Literal["value", "unit"]


@dataclass(frozen=True)
class Cell:
    page: int
    row: int  # body row index within the table (header cells use their header line index)
    col: int  # column index; -1 for a row label
    text: str
    x0: float
    x1: float
    y: float


@dataclass(frozen=True)
class Column:
    index: int
    x0: float
    x1: float
    role: Role
    headers: tuple[str, ...]  # group headers first, the column's own header last


@dataclass(frozen=True)
class GridTable:
    index: int
    page_start: int
    page_end: int
    caption: str | None
    header_rows: tuple[tuple[Cell, ...], ...]
    columns: tuple[Column, ...]
    body_rows: tuple[tuple[Cell, ...], ...]  # each row: the label cell, then its value cells
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Rejection:
    code: str
    page: int | None = None
    table: int | None = None
    row: int | None = None
    col: int | None = None


@dataclass(frozen=True)
class _Chunk:
    page: int
    x0: float
    x1: float
    y: float
    size: float
    text: str


def _lines(words: Sequence[Word]) -> list[list[_Chunk]]:
    """Words grouped by page and baseline, merged where two pieces of one label touch, left to right."""
    by_page: dict[int, list[Word]] = {}
    for w in words:
        by_page.setdefault(w.page, []).append(w)
    out: list[list[_Chunk]] = []
    for page in sorted(by_page):
        current: list[Word] = []
        for w in sorted(by_page[page], key=lambda w: (-w.y, w.x0)):
            if current and abs(w.y - current[0].y) > 0.4 * current[0].size:
                out.append(_merge(sorted(current, key=lambda c: c.x0)))
                current = []
            current.append(w)
        if current:
            out.append(_merge(sorted(current, key=lambda c: c.x0)))
    return out


def _merge(words: list[Word]) -> list[_Chunk]:
    chunks: list[_Chunk] = []
    for w in words:
        prev = chunks[-1] if chunks else None
        touching = prev is not None and w.x0 - prev.x1 < 0.8 * prev.size
        # A period drawn in two pieces ("Dec" then "2026", "Q4" then "2026") is one header.
        split_period = bool(prev and _HEADER_HEAD.match(prev.text) and _YEAR_TAIL.match(w.text))
        if (
            prev
            and touching
            and (split_period or not (_VALUE.match(prev.text) or _VALUE.match(w.text)))
        ):
            chunks[-1] = _Chunk(
                prev.page, prev.x0, w.x1, prev.y, prev.size, f"{prev.text} {w.text}"
            )
        else:
            chunks.append(_Chunk(w.page, w.x0, w.x1, w.y, w.size, w.text))
    return chunks


def _is_body(line: list[_Chunk]) -> bool:
    if len(line) < 2:
        return False
    label, rest = line[0], line[1:]
    if _VALUE.match(label.text) or not re.search(r"[A-Za-z]", label.text):
        return False
    return all(_VALUE.match(c.text) or _UNIT.match(c.text) for c in rest) and any(
        _VALUE.match(c.text) for c in rest
    )


@dataclass
class _Candidate:
    page: int
    caption: str | None
    header: list[list[_Chunk]]  # top to bottom
    body: list[list[_Chunk]]
    notes: list[str]


def _gap(upper: list[_Chunk], lower: list[_Chunk]) -> float:
    return upper[0].y - lower[0].y


def _candidates(lines: list[list[_Chunk]]) -> list[_Candidate]:
    out: list[_Candidate] = []
    i = 0
    while i < len(lines):
        if not _is_body(lines[i]):
            i += 1
            continue
        end = i
        while (
            end + 1 < len(lines)
            and _is_body(lines[end + 1])
            and lines[end + 1][0].page == lines[i][0].page
            and _gap(lines[end], lines[end + 1]) <= 3 * lines[end][0].size
        ):
            end += 1
        body = lines[i : end + 1]
        page = body[0][0].page
        # Header cells to the right of every row label are columns. (The leftmost *value* is not the edge: a row may
        # have no figure in its first column.)
        edge = max(row[0].x1 for row in body)
        header: list[list[_Chunk]] = []
        j = i - 1
        while (
            j >= 0
            and lines[j][0].page == page
            and not _is_body(lines[j])
            and _gap(lines[j], lines[j + 1]) <= 3 * lines[j][0].size
            and not _caption(lines[j][0].text)
            and any(c.x0 >= edge for c in lines[j])
        ):
            header.insert(0, [c for c in lines[j] if c.x0 >= edge])
            j -= 1
        caption = None
        if (
            j >= 0
            and lines[j][0].page == page
            and _caption(lines[j][0].text)
            and _gap(lines[j], lines[j + 1]) <= 5 * lines[j][0].size
        ):
            caption = " ".join(c.text for c in lines[j])
        notes: list[str] = []
        k = end + 1
        while (
            k < len(lines)
            and lines[k][0].page == page
            and not _is_body(lines[k])
            and _NOTE.match(lines[k][0].text)
            and _gap(lines[k - 1], lines[k]) <= 3 * lines[k][0].size
        ):
            notes.append(" ".join(c.text for c in lines[k]))
            k += 1
        out.append(_Candidate(page, caption, header, body, notes))
        i = k
    return out


def _columns(header: list[list[_Chunk]]) -> tuple[Column, ...] | None:
    """Columns from the lowest header line, with group headers above; None when they cannot be told apart."""
    base = header[-1]
    tol = base[0].size
    spans = [(c.x0, c.x1, "unit" if _UNIT_HEADER.match(c.text) else "value", c.text) for c in base]
    if any(b[0] < a[1] for a, b in zip(spans, spans[1:], strict=False)):
        return None  # header cells overlap
    groups: list[list[str]] = [[] for _ in spans]
    for group_line in header[:-1]:
        starts: list[tuple[int, str]] = []
        for g in group_line:
            start = next((n for n, s in enumerate(spans) if s[1] >= g.x0), None)
            if start is None or not (spans[start][0] - tol <= g.x0 <= spans[start][1]):
                return None  # a group header that starts in a gap: centred or misplaced
            starts.append((start, g.text))
        for n, (start, text) in enumerate(starts):
            stop = starts[n + 1][0] if n + 1 < len(starts) else len(spans)
            for col in range(start, stop):
                groups[col].append(text)
    return tuple(
        Column(n, s[0], s[1], s[2], (*groups[n], s[3]))  # type: ignore[arg-type]
        for n, s in enumerate(spans)
    )


def _place(chunk: _Chunk, columns: tuple[Column, ...]) -> int | None:
    width = max(chunk.x1 - chunk.x0, 1e-6)
    overlaps = [max(0.0, min(chunk.x1, c.x1) - max(chunk.x0, c.x0)) for c in columns]
    hit = [n for n, o in enumerate(overlaps) if o > 0]
    if len(hit) != 1 or overlaps[hit[0]] < 0.5 * width:
        return None
    return hit[0]


class _Builder:
    def __init__(self, index: int, cand: _Candidate, columns: tuple[Column, ...]):
        self.index, self.caption, self.columns = index, cand.caption, columns
        self.page_start = self.page_end = cand.page
        self.header_rows = tuple(
            tuple(Cell(cand.page, n, -1, c.text, c.x0, c.x1, c.y) for c in row)
            for n, row in enumerate(cand.header)
        )
        self.rows: list[tuple[Cell, ...]] = []
        self.notes: list[str] = []
        self.closed = False
        self.dead = False

    def add(self, cand: _Candidate) -> Rejection | None:
        for line in cand.body:
            row = len(self.rows)
            cells = [Cell(cand.page, row, -1, line[0].text, line[0].x0, line[0].x1, line[0].y)]
            seen: set[int] = set()
            for chunk in line[1:]:
                col = _place(chunk, self.columns)
                if col is None or col in seen:
                    self.dead = True
                    return Rejection("ambiguous_columns", cand.page, self.index, row)
                seen.add(col)
                cells.append(Cell(cand.page, row, col, chunk.text, chunk.x0, chunk.x1, chunk.y))
            self.rows.append(tuple(cells))
        self.page_end = cand.page
        self.notes.extend(cand.notes)
        self.closed = bool(cand.notes)
        return None

    def build(self) -> GridTable:
        return GridTable(
            self.index, self.page_start, self.page_end, self.caption, self.header_rows,
            self.columns, tuple(self.rows), tuple(self.notes),
        )  # fmt: skip


def _same_columns(a: tuple[Column, ...], b: tuple[Column, ...], tol: float) -> bool:
    return len(a) == len(b) and all(
        x.headers == y.headers and x.role == y.role and abs(x.x0 - y.x0) <= tol
        for x, y in zip(a, b, strict=True)
    )


def _may_continue(cand: _Candidate) -> bool:
    """A captioned block starts a new table unless its caption says it continues the last one."""
    return cand.caption is None or bool(
        _CONTINUED.search(cand.caption) and not _SCENARIO.search(cand.caption)
    )


def find_tables(words: Sequence[Word]) -> tuple[tuple[GridTable, ...], tuple[Rejection, ...]]:
    builders: list[_Builder] = []
    rejections: list[Rejection] = []
    current: _Builder | None = None
    count = 0
    for cand in _candidates(_lines(words)):
        if cand.header:
            columns = _columns(cand.header)
            if columns is None:
                rejections.append(Rejection("ambiguous_columns", cand.page, count))
                count += 1
                current = None
                continue
            tol = cand.header[-1][0].size
            if (
                current is not None
                and not current.closed
                and cand.page == current.page_end + 1
                and _may_continue(cand)
                and _same_columns(current.columns, columns, tol)
            ):
                target = current
            else:
                target = current = _Builder(count, cand, columns)
                builders.append(target)
                count += 1
        elif (
            current is not None
            and not current.closed
            and cand.page == current.page_end + 1
            and _may_continue(cand)
        ):
            target = current
        else:
            rejections.append(Rejection("no_header", cand.page))
            continue
        if target.dead:
            continue
        if (rejection := target.add(cand)) is not None:
            rejections.append(rejection)
    return tuple(b.build() for b in builders if not b.dead), tuple(rejections)
