"""Score parsed tables against ground truth. Counts only; structure, not extraction volume.

- A value is *present* when a cell on its page reads exactly its text (or its text plus a separable footnote marker).
  Duplicate texts need one cell each.
- A value is *aligned* when, in addition, its grid row holds the row label left of it, and the cells above it in its
  grid column hold every header fragment of its own column and none of another column's.
- A *numeric false positive* is a numeric-looking cell that is neither a truth value, a header fragment nor a marker:
  a fused footnote digit ("2.5" + "1" read as "2.51"), two figures in one cell, or a chart tick read as a table.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from pdfbench.model import BenchTable, TruthTable

_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_UNSUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_TOKEN = r"[-−–+(]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)%?\)?"  # ".25": a figure split from its leading digits
_NUMERIC = re.compile(rf"{_TOKEN}(?:\s+{_TOKEN})*")


@dataclass(frozen=True)
class Score:
    tables_truth: int = 0
    tables_found: int = 0
    tables_extra: int = 0
    tables_merged: int = 0
    values_truth: int = 0
    values_present: int = 0
    values_aligned: int = 0
    stacked_truth: int = 0
    stacked_joined: int = 0
    markers_truth: int = 0
    markers_kept: int = 0
    notes_truth: int = 0
    notes_kept: int = 0
    numeric_false_positive: int = 0


def _norm(text: str) -> str:
    return " ".join(text.split())


def _marked(value: str, marker: str) -> set[str]:
    sup = marker.translate(_SUP)
    return {value + sup, f"{value} {marker}", f"{value} {sup}"}


def numeric(cell: str) -> bool:
    return bool(_NUMERIC.fullmatch(_norm(cell.translate(_UNSUP))))


def _accepts(truth: TruthTable, key: tuple[int, int]) -> set[str]:
    value = truth.values[key]
    marker = truth.value_markers.get(key)
    return {value} | (_marked(value, marker) if marker else set())


def _matches(table: BenchTable, truth: TruthTable) -> bool:
    if table.page != truth.page:
        return False
    text = [_norm(c) for row in table.grid for c in row]
    hits = sum(any(label in c for c in text) for label in truth.row_labels)
    return hits >= 1 and 2 * hits >= len(truth.row_labels)


def _aligned(table: BenchTable, truth: TruthTable, key: tuple[int, int], accept: set[str]) -> str | None:
    """The matching cell's text when the value at `key` sits under its own column header and on its row label."""
    r, c = key
    label = truth.row_labels[r]
    own = truth.col_headers[c]
    foreign = {f for i, h in enumerate(truth.col_headers) if i != c for f in h if f not in own}
    for i, row in enumerate(table.grid):
        for j, cell in enumerate(row):
            if _norm(cell) not in accept:
                continue
            if not any(label in _norm(x) for x in row[:j]):
                continue
            above = " ".join(_norm(table.grid[k][j]) for k in range(i) if j < len(table.grid[k]))
            if all(f in above for f in own) and not any(f in above for f in foreign):
                return _norm(cell)
    return None


def _label_marker_kept(tables: list[BenchTable], label: str, marker: str) -> bool:
    forms = _marked(label, marker)
    for t in tables:
        for row in t.grid:
            cells = [_norm(c) for c in row]
            for j, cell in enumerate(cells):
                if cell in forms:
                    return True
                if label in cell and j + 1 < len(cells) and cells[j + 1] in {marker, marker.translate(_SUP)}:
                    return True
    return False


def score(truth: list[TruthTable], got: list[BenchTable]) -> Score:
    found = sum(any(_matches(t, u) for t in got) for u in truth)
    match_counts = [sum(_matches(t, u) for u in truth) for t in got]
    values_truth = present = aligned = stacked_truth = joined = markers_truth = kept = notes_truth = notes_kept = 0
    allowed: dict[int, set[str]] = {}
    marks: dict[int, set[str]] = {}  # footnote digits: not a figure only in the label column
    for u in truth:
        on_page = [t for t in got if t.page == u.page]
        cells = Counter(_norm(c) for t in on_page for row in t.grid for c in row)
        page_allowed = allowed.setdefault(u.page, set())
        page_allowed |= {f for h in u.col_headers for f in h} | set(u.row_labels)
        digits = {m for _, m in u.markers} | set(u.value_markers.values())
        marks.setdefault(u.page, set()).update(digits | {m.translate(_SUP) for m in digits})
        # Present: each truth cell consumes one parsed cell with an accepted text.
        for key in sorted(u.values):
            accept = _accepts(u, key)
            page_allowed |= accept
            values_truth += 1
            for text in sorted(accept):
                if cells[text] > 0:
                    cells[text] -= 1
                    present += 1
                    break
        # Aligned, stacked, value markers.
        aligned_cols: set[int] = set()
        for key in sorted(u.values):
            hit = next((h for t in on_page if (h := _aligned(t, u, key, _accepts(u, key)))), None)
            if hit is None:
                continue
            aligned += 1
            aligned_cols.add(key[1])
            if key in u.value_markers and hit != u.values[key]:
                kept += 1
        stacked_truth += len(u.stacked)
        joined += sum(c in aligned_cols for c in u.stacked)
        markers_truth += len(u.markers) + len(u.value_markers)
        kept += sum(_label_marker_kept(on_page, u.row_labels[r], m) for r, m in u.markers)
        notes_truth += len(u.notes)
        blob = " ".join(
            [_norm(c) for t in on_page for row in t.grid for c in row] + [_norm(n) for t in on_page for n in t.notes]
        )
        notes_kept += sum(_norm(n) in blob for n in u.notes)
    fp = sum(
        numeric(c)
        and _norm(c) not in allowed.get(t.page, set())
        and not (j == 0 and _norm(c) in marks.get(t.page, set()))
        for t in got
        for row in t.grid
        for j, c in enumerate(row)
        if c.strip()
    )
    return Score(
        tables_truth=len(truth),
        tables_found=found,
        tables_extra=sum(n == 0 for n in match_counts),
        tables_merged=sum(n > 1 for n in match_counts),
        values_truth=values_truth,
        values_present=present,
        values_aligned=aligned,
        stacked_truth=stacked_truth,
        stacked_joined=joined,
        markers_truth=markers_truth,
        markers_kept=kept,
        notes_truth=notes_truth,
        notes_kept=notes_kept,
        numeric_false_positive=fp,
    )
