"""Each parser adapter returns neutral tables for the requested pages, and a failing parser never stops the run."""

import pytest

from pdfbench import synth
from pdfbench.adapters import PARSERS, run
from pdfbench.model import BenchTable
from pdfbench.synth import cases

BY_NAME = {c.name: c for c in cases()}
NAMES = sorted(PARSERS)
LINE_BASED = ["plumber_default", "plumber_lines", "camelot_lattice"]


def _ruled_then_blank() -> bytes:
    """Page 1: the ruled control table. Page 2: nothing. (A document with no text at all is refused by `existing`.)"""
    (pages, _) = synth._ruled()
    return synth._render([*pages, synth._Page()], "ruled then blank")


def test_parser_set_covers_the_brief():
    assert set(NAMES) == {
        "existing",
        "plumber_default",
        "plumber_lines",
        "plumber_text",
        "camelot_lattice",
        "camelot_stream",
        "camelot_network",
        "camelot_hybrid",
    }


@pytest.mark.parametrize("name", LINE_BASED)
def test_line_based_parsers_find_the_ruled_control(name):
    tables, error, seconds = run(name, BY_NAME["ruled_control"].pdf, [1])
    assert error is None and seconds >= 0
    assert len(tables) >= 1
    assert all(isinstance(t, BenchTable) and t.page == 1 for t in tables)
    assert any("1.5" in cell for t in tables for row in t.grid for cell in row)


@pytest.mark.parametrize("name", NAMES)
def test_blank_page_gives_no_tables(name):
    tables, error, _ = run(name, _ruled_then_blank(), [2])
    assert error is None
    assert tables == []


@pytest.mark.parametrize("name", LINE_BASED)
def test_only_requested_pages_are_read(name):
    tables, error, _ = run(name, _ruled_then_blank(), [1])
    assert error is None and tables and all(t.page == 1 for t in tables)


@pytest.mark.parametrize("name", NAMES)
def test_unreadable_input_is_an_error_not_a_crash(name):
    tables, error, seconds = run(name, b"%PDF-1.4\nnot really a pdf", [1])
    assert tables is None and error == "error" and seconds >= 0


def test_cells_are_strings_without_newlines():
    for name in NAMES:
        tables, _, _ = run(name, BY_NAME["p8_stacked"].pdf, [1])
        for t in tables or []:
            assert all(isinstance(c, str) and "\n" not in c for row in t.grid for c in row)


@pytest.mark.parametrize("module", ["torch", "transformers", "timm", "onnxruntime", "pytesseract"])
def test_no_model_or_ocr_package_is_installed(module):
    """Camelot's `ml` flavor and OCR need these; the brief bars models and OCR on the document."""
    import importlib.util

    assert importlib.util.find_spec(module) is None


def test_a_slow_parser_is_a_timeout():
    tables, error, seconds = run("camelot_lattice", BY_NAME["p5_annual"].pdf, [1], timeout=0.01)
    assert (tables, error, seconds) == (None, "timeout", 0.01)


def test_a_child_that_dies_without_reporting_is_an_error_not_a_timeout():
    from tests.crash_helper import die

    tables, error, seconds = run("existing", BY_NAME["p5_annual"].pdf, [1], timeout=30, target=die)
    assert (tables, error) == (None, "error")
    assert seconds < 30


def test_a_table_continued_across_pages_keeps_each_row_on_its_own_page():
    from nzstats.research.table_grid import Cell, Column, GridTable

    from pdfbench.adapters import _bench_tables

    head = (Cell(5, 0, 0, "2026f", 50.0, 60.0, 700.0),)
    first = (Cell(5, 0, -1, "Prices", 10.0, 40.0, 680.0), Cell(5, 0, 0, "2.5", 50.0, 60.0, 680.0))
    second = (Cell(6, 1, -1, "Jobless rate", 10.0, 40.0, 700.0), Cell(6, 1, 0, "4.9", 50.0, 60.0, 700.0))
    joined = GridTable(
        0, 5, 6, None, (head,), (Column(0, 50.0, 60.0, "value", ("2026f",)),), (first, second), ("Note",)
    )
    tables = _bench_tables(joined)
    assert [(t.page, t.grid) for t in tables] == [
        (5, [["", "2026f"], ["Prices", "2.5"]]),
        (6, [["", "2026f"], ["Jobless rate", "4.9"]]),
    ]
    assert [t.notes for t in tables] == [[], ["Note"]]
    assert tables[1].bbox == (10.0, 700.0, 60.0, 700.0)
