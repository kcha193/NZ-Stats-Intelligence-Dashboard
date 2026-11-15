"""Truth-free structural diagnostics for a document no one may read: every metric is a count, computed in memory.

`emit` is the only way out. It refuses any key outside a fixed vocabulary and any value that is not a number, a
boolean, None or a fixed code, so a document string cannot leave this process by accident (a header used as a key,
an error message, a cell text).
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import math
import os
import re
import sys
from collections import Counter

from pdfbench.adapters import PARSERS, run
from pdfbench.metrics import numeric
from pdfbench.model import BenchTable

CODES = frozenset({"error", "timeout", "refused", "hash_mismatch", "unavailable"})
KEYS = frozenset(
    {
        "pages",
        "parsers",
        "error",
        "seconds",
        # page facts
        "lines",
        "rects",
        "curves",
        "value_marker_sites",
        "label_marker_sites",
        # per parser and page
        "tables",
        "shapes",
        "numeric_cells",
        "multi_number_cells",
        "fused_marker_cells",
        "detached_marker_cells",
        "source_lines_in_grid",
        "notes",
        "existing_value_cells",
        "agreement_with_existing",
        "tables_merged_vs_existing",
        "bbox_numeric_tokens",
        "bbox_numeric_tokens_uncovered",
        "unreproduced_existing_cells",
        "unreproduced_reasons",
        "label_mismatch",
        "header_mismatch",
        "value_missing",
    }
)
_PAGE_KEY = re.compile(r"^\d{1,4}$")
_FIGURE = set("0123456789.,%")
_SOURCE = re.compile(r"^(?:sources?|notes?)\b", re.IGNORECASE)
_MARKER_RATIO = 0.75
_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"


def _check(value: object, path: str, parent: str | None = None) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            # A number is a key only as a page number, directly under a "pages" map, never anywhere else (a year
            # header used as a metric key would otherwise pass).
            text = key if isinstance(key, str) else ""
            page = parent == "pages" and bool(_PAGE_KEY.match(text))
            if not text or not (page or (parent != "pages" and (text in KEYS or text in PARSERS))):
                raise ValueError(f"key refused at {path}")
            _check(inner, f"{path}/<key>", None if page else key)
    elif isinstance(value, list):
        for inner in value:
            _check(inner, f"{path}[]")
    elif isinstance(value, bool) or value is None or isinstance(value, int):
        return
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite value at {path}")
    elif isinstance(value, str):
        if value not in CODES:
            raise ValueError(f"string value refused at {path}")
    else:
        raise ValueError(f"type refused at {path}")


def emit(data: dict) -> str:
    _check(data, "")
    return json.dumps(data, sort_keys=True)


def _norm(text: str) -> str:
    return " ".join(text.split())


def _marker_sites(chars: list[dict]) -> tuple[list[tuple[str, str]], int]:
    """(figure text, marker digit) for each small digit set directly after a figure; and the count after a word."""
    sites, labels = [], 0
    normal = [c for c in chars if c["text"].strip()]
    for c in normal:
        if not c["text"].isdigit():
            continue
        prev = [
            p
            for p in normal
            if p is not c
            and c["size"] < _MARKER_RATIO * p["size"]
            and 0 <= c["x0"] - p["x1"] < 0.3 * p["size"]
            and c["top"] < p["bottom"]
            and c["bottom"] > p["top"]
        ]
        if not prev:
            continue
        p = max(prev, key=lambda q: q["x1"])
        if p["text"] not in _FIGURE:
            labels += 1
            continue
        line = sorted(
            (
                q
                for q in normal
                if abs(q["bottom"] - p["bottom"]) < 1 and abs(q["size"] - p["size"]) < 0.1 and q["x1"] <= p["x1"]
            ),
            key=lambda q: q["x0"],
        )
        token = [p]
        for q in reversed(line[:-1] if line and line[-1] is p else line):
            if q["text"] in _FIGURE and token[0]["x0"] - q["x1"] < 0.15 * p["size"]:
                token.insert(0, q)
            else:
                break
        sites.append(("".join(q["text"] for q in token), c["text"]))
    return sites, labels


def _cells(t: BenchTable) -> list[str]:
    return [_norm(c) for row in t.grid for c in row]


def _triple(header: list[str], row: list[str], j: int) -> tuple[str, str, str]:
    """(row label without its footnote marker, column header, value text)."""
    return _norm(row[0]).rstrip(_SUPERSCRIPTS).strip(), _norm(header[j]), _norm(row[j]).rstrip(_SUPERSCRIPTS).strip()


def _value_triples(tables: list[BenchTable]) -> list[tuple[str, str, str]]:
    return [
        _triple(t.grid[0], row, j) for t in tables for row in t.grid[1:] for j in range(1, len(row)) if numeric(row[j])
    ]


def _agrees(tables: list[BenchTable], label: str, header: str, text: str) -> bool:
    for t in tables:
        for i, row in enumerate(t.grid):
            for j, cell in enumerate(row):
                if _norm(cell).rstrip(_SUPERSCRIPTS).strip() != text or not any(
                    label and label in _norm(x) for x in row[:j]
                ):
                    continue
                above = " ".join(_norm(t.grid[k][j]) for k in range(i) if j < len(t.grid[k]))
                if all(token in above for token in header.split()):
                    return True
    return False


def _unreproduced(tables: list[BenchTable], existing: list[BenchTable]) -> list[list[int]]:
    """[table index, grid row, grid column] of each existing value cell that `tables` does not reproduce. Ints only."""
    return [
        [ti, i, j]
        for ti, e in enumerate(existing)
        for i, row in enumerate(e.grid[1:], start=1)
        for j in range(1, len(row))
        if numeric(row[j]) and not _agrees(tables, *_triple(e.grid[0], row, j))
    ]


def _reasons(tables: list[BenchTable], existing: list[BenchTable]) -> dict[str, int]:
    """Why each unreproduced existing cell failed: its value is nowhere; it sits under its header but off its label's
    row; or it is never under its own header."""
    out = {"label_mismatch": 0, "header_mismatch": 0, "value_missing": 0}
    for label, header, text in _value_triples(existing):
        if _agrees(tables, label, header, text):
            continue
        if not any(_norm(c) == text for t in tables for row in t.grid for c in row):
            out["value_missing"] += 1
        elif any(
            _agrees([BenchTable(t.page, t.bbox, [[label, *r[1:]] for r in t.grid])], label, header, text)
            for t in tables
        ):
            out["label_mismatch"] += 1
        else:
            out["header_mismatch"] += 1
    return out


def _labels(t: BenchTable) -> list[str]:
    return [_norm(r[0]) for r in t.grid[1:] if r and _norm(r[0])]


def _page_metrics(
    tables: list[BenchTable],
    existing: list[BenchTable] | None,
    sites: list[tuple[str, str]],
    words: list[dict],
    height: float,
) -> dict:
    cells = [c for t in tables for c in _cells(t)]
    nums = [c for c in cells if numeric(c)]
    fused = Counter(f + d for f, d in sites)
    have = Counter(cells)
    out = {
        "tables": len(tables),
        "shapes": [[len(t.grid), max((len(r) for r in t.grid), default=0)] for t in tables],
        "numeric_cells": len(nums),
        "multi_number_cells": sum(len(c.split()) > 1 for c in nums),
        "fused_marker_cells": sum(min(n, have[text]) for text, n in fused.items()),
        "detached_marker_cells": sum(
            1
            for t in tables
            for row in t.grid
            for j, c in enumerate(row)
            if j > 0 and re.fullmatch(r"\d{1,2}", _norm(c)) and not any(_norm(x) for k, x in enumerate(row) if k != j)
        ),
        "source_lines_in_grid": sum(bool(_SOURCE.match(c)) for c in cells),
        "notes": sum(len(t.notes) for t in tables),
    }
    if existing is None:
        out.update(
            existing_value_cells=None,
            agreement_with_existing=None,
            tables_merged_vs_existing=None,
            unreproduced_existing_cells=None,
            unreproduced_reasons=None,
        )
    else:
        triples = _value_triples(existing)
        out["existing_value_cells"] = len(triples)
        out["agreement_with_existing"] = sum(_agrees(tables, *tr) for tr in triples)
        out["unreproduced_existing_cells"] = _unreproduced(tables, existing)
        out["unreproduced_reasons"] = _reasons(tables, existing)
        out["tables_merged_vs_existing"] = sum(
            sum(
                bool(ls) and 2 * sum(any(lab in c for c in _cells(t)) for lab in ls) >= len(ls)
                for ls in (_labels(e) for e in existing)
            )
            > 1
            for t in tables
        )
    tokens = Counter(tok for c in cells for tok in c.split())
    inside = [
        w["text"]
        for w in words
        if numeric(w["text"])
        and any(
            t.bbox[0] - 2 <= w["x0"]
            and w["x1"] <= t.bbox[2] + 2
            and t.bbox[1] - 2 <= height - w["bottom"] <= t.bbox[3] + 12
            for t in tables
        )
    ]
    need = Counter(inside)
    out["bbox_numeric_tokens"] = len(inside)
    out["bbox_numeric_tokens_uncovered"] = sum(max(0, n - tokens[text]) for text, n in need.items())
    return out


@contextlib.contextmanager
def silenced():
    """Send fd 1 and 2 to /dev/null and switch logging off: library warnings and native output can quote the document."""
    logging.disable(logging.CRITICAL)
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (*saved, null):
            os.close(fd)


def safe_diagnose(pdf: bytes, pages: list[int], parsers: list[str] | None = None, timeout: float = 120) -> dict:
    """`diagnose` with every stream silenced; any failure becomes {"error": "error"} (no message, no traceback)."""
    with silenced():
        try:
            return diagnose(pdf, pages, parsers, timeout)
        except Exception:  # noqa: BLE001 - the message could quote the document; only the fixed code may leave
            return {"error": "error"}


def diagnose(pdf: bytes, pages: list[int], parsers: list[str] | None = None, timeout: float = 120) -> dict:
    import pdfplumber

    names = parsers or sorted(PARSERS)
    page_facts, sites, words, heights = {}, {}, {}, {}
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for number in pages:
            page = doc.pages[number - 1]
            found, labels = _marker_sites(page.chars)
            sites[number], words[number], heights[number] = found, page.extract_words(), float(page.height)
            page_facts[str(number)] = {
                "lines": len(page.lines),
                "rects": len(page.rects),
                "curves": len(page.curves),
                "value_marker_sites": len(found),
                "label_marker_sites": labels,
            }
    results = {name: run(name, pdf, pages, timeout) for name in names}
    existing_tables = results["existing"][0] if "existing" in results else None
    out: dict = {}
    for name, (tables, error, seconds) in results.items():
        entry: dict = {"error": error, "seconds": round(seconds, 2)}
        if tables is not None:
            entry["pages"] = {
                str(p): _page_metrics(
                    [t for t in tables if t.page == p],
                    None if existing_tables is None else [t for t in existing_tables if t.page == p],
                    sites[p],
                    words[p],
                    heights[p],
                )
                for p in pages
            }
        out[name] = entry
    return {"pages": page_facts, "parsers": out}
