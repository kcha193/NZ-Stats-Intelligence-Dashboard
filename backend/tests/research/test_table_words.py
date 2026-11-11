"""Positioned words from a PDF (Phase 4AF): where each piece of text sits, so tables can be read geometrically."""

import pytest

from nzstats.domain import IngestError
from nzstats.research.extract import ExtractionLimits
from nzstats.research.table_words import Word, extract_words

from .pdf_support import encrypted_pdf
from .pdf_table_support import table_pdf

LIMITS = ExtractionLimits()


def simple() -> bytes:
    return table_pdf([[(72, 700, "Table 1"), (72, 680, "OCR"), (300, 680, "3.25")]])


def test_words_have_positions_in_reading_order():
    words = extract_words(simple(), LIMITS, isolate=False)
    assert [w.text for w in words] == ["Table 1", "OCR", "3.25"]
    last = words[-1]
    assert last.page == 1
    assert last.x0 == pytest.approx(300, abs=0.5)
    assert last.y == pytest.approx(680, abs=0.5)
    assert last.x1 > last.x0


def test_adjacent_cells_do_not_overlap():
    pdf = table_pdf([[(72, 700, "Dec-26"), (140, 700, "Mar-27"), (200, 700, "Jun-27")]])
    a, b, c = extract_words(pdf, LIMITS, isolate=False)
    assert a.x1 < b.x0 and b.x1 < c.x0


def test_page_numbers_follow_the_document():
    pdf = table_pdf([[(72, 700, "one")], [(72, 700, "two")]])
    assert [(w.page, w.text) for w in extract_words(pdf, LIMITS, isolate=False)] == [
        (1, "one"),
        (2, "two"),
    ]


def test_isolated_child_gives_the_same_words():
    assert extract_words(simple(), LIMITS, isolate=True) == extract_words(
        simple(), LIMITS, isolate=False
    )


def test_not_a_pdf_and_encrypted_are_refused():
    with pytest.raises(IngestError):
        extract_words(b"<html></html>", LIMITS, isolate=False)
    with pytest.raises(IngestError):
        extract_words(encrypted_pdf([["secret"]]), LIMITS, isolate=False)


def test_a_page_without_text_is_no_text_layer():
    with pytest.raises(IngestError, match="no_text_layer"):
        extract_words(table_pdf([[]]), LIMITS, isolate=False)


def test_word_is_a_frozen_value():
    w = Word(1, 0.0, 1.0, 2.0, 10.0, "x")
    with pytest.raises(AttributeError):
        w.text = "y"  # type: ignore[misc]


def test_a_word_with_a_non_finite_position_is_dropped_not_sorted():
    from nzstats.research.table_words import make_word

    ident = [1, 0, 0, 1, 0, 0]
    assert make_word(1, "ok", ident, ident, 10.0) is not None
    nan, inf = float("nan"), float("inf")
    assert make_word(1, "x", ident, [1, 0, 0, 1, nan, 0], 10.0) is None
    assert make_word(1, "x", ident, [1, 0, 0, 1, 0, inf], 10.0) is None
    assert make_word(1, "x", ident, ident, nan) is None
    assert make_word(1, "   ", ident, ident, 10.0) is None


def test_text_drawn_as_one_block_yields_no_table_rather_than_a_wrong_one():
    """pypdf hands back a whole baseline drawn inside one BT..ET as one string, so positions inside it are unknown.
    That fails safe: no cell boundaries, no table. (Documented limit; the pilot's dry run shows it.)"""
    from nzstats.research.table_grid import find_tables

    stream = (
        "BT /F1 10 Tf 72 700 Td (Dec-26) Tj 180 0 Td (Mar-27) Tj ET "
        "BT /F1 10 Tf 72 686 Td (OCR) Tj 180 0 Td (3.25) Tj 60 0 Td (3.00) Tj ET"
    )
    pdf = table_pdf([[]]).replace(b"q Q", stream.encode())
    assert find_tables(extract_words(pdf, LIMITS, isolate=False)) == ((), ())
