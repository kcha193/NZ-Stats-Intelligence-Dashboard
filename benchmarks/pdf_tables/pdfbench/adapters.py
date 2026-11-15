"""Adapt each parser's output to `BenchTable`. Every run happens in a child process with a timeout, so one parser that
crashes or hangs on one input is recorded as `error` or `timeout` and the benchmark continues.

Camelot's `ml` flavor (a Table Transformer neural model) is excluded: the brief bars local AI models on the document.
"""

from __future__ import annotations

import io
import multiprocessing
import time
from collections.abc import Callable
from queue import Empty

from pdfbench.model import BBox, BenchTable

Parser = Callable[[bytes, list[int]], list[BenchTable]]


def _clean(cell: object) -> str:
    return " ".join(str(cell).split()) if cell is not None else ""


def _existing(pdf: bytes, pages: list[int]) -> list[BenchTable]:
    from nzstats.research.table_grid import find_tables
    from nzstats.research.table_words import extract_words

    words = [w for w in extract_words(pdf, isolate=False) if w.page in pages]
    tables, _ = find_tables(words)
    out = []
    for t in tables:
        header = ["", *(" ".join(c.headers) for c in t.columns)]
        body = []
        for row in t.body_rows:
            line = [""] * (len(t.columns) + 1)
            for cell in row:
                line[cell.col + 1] = _clean(cell.text)
            body.append(line)
        cells = [c for row in t.body_rows for c in row] + [c for row in t.header_rows for c in row]
        bbox: BBox = (
            min(c.x0 for c in cells),
            min(c.y for c in cells),
            max(c.x1 for c in cells),
            max(c.y for c in cells),
        )
        out.append(BenchTable(t.page_start, bbox, [header, *body], header_rows=1, notes=[_clean(n) for n in t.notes]))
    return out


def _plumber(settings: dict | None) -> Parser:
    def parse(pdf: bytes, pages: list[int]) -> list[BenchTable]:
        import pdfplumber

        out = []
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            for number in pages:
                page = doc.pages[number - 1]
                for table in page.find_tables(settings or {}):
                    x0, top, x1, bottom = table.bbox
                    grid = [[_clean(c) for c in row] for row in table.extract()]
                    out.append(BenchTable(number, (x0, page.height - bottom, x1, page.height - top), grid))
        return out

    return parse


def _camelot(flavor: str) -> Parser:
    def parse(pdf: bytes, pages: list[int]) -> list[BenchTable]:
        import camelot

        tables = camelot.read_pdf(pdf, pages=",".join(map(str, pages)), flavor=flavor, suppress_stdout=True)
        out = []
        for t in tables:
            grid = [[_clean(c) for c in row] for row in t.df.values.tolist()]
            out.append(BenchTable(int(t.page), tuple(float(v) for v in t._bbox), grid))
        return out

    return parse


# Settings named in the PDF skill's REFERENCE.md ("Advanced Table Extraction with Custom Settings").
_SKILL_LINES = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "intersection_tolerance": 15,
}
_TEXT = {"vertical_strategy": "text", "horizontal_strategy": "text"}  # beyond the skill: pdfplumber's borderless mode

PARSERS: dict[str, Parser] = {
    "existing": _existing,
    "plumber_default": _plumber(None),
    "plumber_lines": _plumber(_SKILL_LINES),
    "plumber_text": _plumber(_TEXT),
    "camelot_lattice": _camelot("lattice"),
    "camelot_stream": _camelot("stream"),
    "camelot_network": _camelot("network"),
    "camelot_hybrid": _camelot("hybrid"),
}


def _child(name: str, pdf: bytes, pages: list[int], queue) -> None:
    import warnings

    warnings.simplefilter("ignore")
    start = time.perf_counter()
    try:
        tables = PARSERS[name](pdf, pages)
    except Exception:  # noqa: BLE001 - any parser failure is a benchmark result, recorded as a fixed code
        queue.put((None, "error", time.perf_counter() - start))
        return
    queue.put((tables, None, time.perf_counter() - start))


def run(
    parser: str, pdf: bytes, pages: list[int], timeout: float = 60
) -> tuple[list[BenchTable] | None, str | None, float]:
    """(tables, error code or None, parse seconds). The parse time excludes process start and imports."""
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    proc = ctx.Process(target=_child, args=(parser, pdf, pages, queue))
    proc.start()
    try:
        result = queue.get(timeout=timeout)
    except Empty:
        proc.kill()
        proc.join()
        return None, "timeout", float(timeout)
    proc.join()
    return result
