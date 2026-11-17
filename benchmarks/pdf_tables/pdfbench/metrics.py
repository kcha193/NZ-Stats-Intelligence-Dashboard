"""Score parsed tables against ground truth. Counts only; structure, not extraction volume.

- A value is *present* when a cell on its page reads exactly its text (or its text plus a separable footnote marker).
- A value is *aligned* when, in addition, its grid row holds the row label left of it, and the cells above it in its
  grid column hold every header fragment of its own column and none of another column's.
- One physical parsed cell (parsed table, grid row, grid column) counts for at most one truth value, across all truth
  tables of a page, for presence and for alignment alike. Cells are assigned by a maximum one-to-one matching, so a
  duplicate never takes a cell another value needed, and neither the order of the truth tables nor that of the parsed
  tables changes a count. Among the largest assignments, alignment keeps as many footnote markers as possible. Truth
  in which one value's text is another's with its footnote marker ("2.5 1" beside "2.5" marked "1") is refused: a cell
  reading it could not be attributed.
- A *numeric false positive* is a numeric-looking cell that is neither a truth value, a header fragment nor a marker:
  a fused footnote digit ("2.5" + "1" read as "2.51"), two figures in one cell, or a chart tick read as a table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdfbench.model import BenchTable, TruthTable

_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_UNSUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_TOKEN = r"[-−–+(]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)%?\)?"  # ".25": a figure split from its leading digits
_NUMERIC = re.compile(rf"{_TOKEN}(?:\s+{_TOKEN})*")

Cell = tuple[int, int, int]  # (index of the parsed table in `got`, grid row, grid column): one physical cell


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


def _aligned(table: BenchTable, truth: TruthTable, key: tuple[int, int], accept: set[str]) -> list[tuple[int, int]]:
    """Grid positions of the cells that read the value at `key` on its row label and under its own column header."""
    r, c = key
    label = truth.row_labels[r]
    own = truth.col_headers[c]
    foreign = {f for i, h in enumerate(truth.col_headers) if i != c for f in h if f not in own}
    hits = []
    for i, row in enumerate(table.grid):
        for j, cell in enumerate(row):
            if _norm(cell) not in accept:
                continue
            if not any(label in _norm(x) for x in row[:j]):
                continue
            above = " ".join(_norm(table.grid[k][j]) for k in range(i) if j < len(table.grid[k]))
            if all(f in above for f in own) and not any(f in above for f in foreign):
                hits.append((i, j))
    return hits


def _match(wants: list[list[Cell]], first: list[list[Cell]] | None = None) -> dict[int, Cell]:
    """A maximum one-to-one assignment of truth values (by index) to the parsed cells each accepts.

    Augmenting paths (Kuhn). `first[v]`, a subset of `wants[v]`, is matched as far as it can be before any other cell;
    an augmenting path never frees a matched cell, so every cell matched in that first round stays matched.
    """
    owner: dict[Cell, int] = {}

    def augment(root: int, edges: list[list[Cell]]) -> bool:
        """Depth-first search for an augmenting path from `root`, iterative so a long chain cannot overflow the stack."""
        seen: set[Cell] = set()
        stack = [(root, iter(edges[root]))]  # values on the path, each with the cells it has still to try
        path: list[Cell] = []  # path[k]: the cell stack[k] takes when the path is applied
        while stack:
            for cell in stack[-1][1]:
                if cell in seen:
                    continue
                seen.add(cell)
                path.append(cell)
                if cell not in owner:
                    for (v, _), c in zip(stack, path):
                        owner[c] = v
                    return True
                stack.append((owner[cell], iter(edges[owner[cell]])))
                break
            else:
                stack.pop()
                if path:
                    path.pop()
        return False

    matched: set[int] = set()
    for edges in [first, wants] if first is not None else [wants]:
        for v in range(len(wants)):
            if v not in matched and augment(v, edges):
                matched.add(v)
    return {v: cell for cell, v in owner.items()}


def _content(truth: TruthTable) -> str:
    """Orders truth tables by content alone. Which values win contested cells depends on the order values are tried in
    (never on the order of their candidate cells), so this keeps every count independent of the order of `truth`."""
    return repr(sorted((f, sorted(v.items()) if isinstance(v, dict) else v) for f, v in vars(truth).items()))


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
    for page in sorted({u.page for u in truth}):
        tables = [g for g, t in enumerate(got) if t.page == page]
        on_page = [got[g] for g in tables]
        texts = {(g, i, j): _norm(c) for g in tables for i, row in enumerate(got[g].grid) for j, c in enumerate(row)}
        page_allowed = allowed.setdefault(page, set())
        page_truth = sorted((n for n, u in enumerate(truth) if u.page == page), key=lambda n: (_content(truth[n]), n))
        values: list[tuple[int, tuple[int, int]]] = []  # (truth table index, value key), one per truth value
        loose: list[list[Cell]] = []  # per value: the cells reading an accepted text
        placed: list[list[Cell]] = []  # per value: those that are also aligned
        marked: list[list[Cell]] = []  # per value: aligned cells that keep its footnote marker
        plain: set[str] = set()  # the printed texts of the page's values
        forms: set[str] = set()  # the same values with their footnote markers
        for n in page_truth:
            u = truth[n]
            page_allowed |= {f for h in u.col_headers for f in h} | set(u.row_labels)
            digits = {m for _, m in u.markers} | set(u.value_markers.values())
            marks.setdefault(page, set()).update(digits | {m.translate(_SUP) for m in digits})
            for key in sorted(u.values):
                accept = _accepts(u, key)
                page_allowed |= accept
                values.append((n, key))
                loose.append([cell for cell, text in texts.items() if text in accept])
                here = [(g, i, j) for g in tables for i, j in _aligned(got[g], u, key, accept)]
                placed.append(here)
                marked.append([cell for cell in here if texts[cell] != u.values[key]])
                plain.add(u.values[key])
                forms |= accept - {u.values[key]}
            stacked_truth += len(u.stacked)
            markers_truth += len(u.markers) + len(u.value_markers)
            kept += sum(_label_marker_kept(on_page, u.row_labels[r], m) for r, m in u.markers)
            notes_truth += len(u.notes)
            blob = " ".join(
                [_norm(c) for t in on_page for row in t.grid for c in row]
                + [_norm(note) for t in on_page for note in t.notes]
            )
            notes_kept += sum(_norm(note) in blob for note in u.notes)
        if plain & forms:
            raise ValueError(f"ambiguous truth on page {page}: a value reads as another value with its footnote marker")
        values_truth += len(values)
        present += len(_match(loose))
        # No value's text is another's marked form (checked above), so a marked cell is accepted only by values printed
        # with that marker: whichever value ends up holding a cell matched in the first round keeps its marker, and the
        # count of kept markers is as large as it can be.
        hits = _match(placed, first=marked)
        aligned += len(hits)
        kept += sum(texts[cell] != truth[values[v][0]].values[values[v][1]] for v, cell in hits.items())
        aligned_cols = {(values[v][0], values[v][1][1]) for v in hits}
        joined += sum((n, c) in aligned_cols for n in page_truth for c in truth[n].stacked)
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
