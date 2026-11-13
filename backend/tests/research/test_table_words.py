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


def test_a_glyph_with_a_non_finite_position_is_dropped_not_sorted():
    from nzstats.research.table_words import _finite

    assert _finite(1.0, 2.0, 3.0)
    assert not _finite(1.0, float("nan"))
    assert not _finite(float("inf"), 1.0)


def test_text_drawn_as_one_block_now_gives_each_cell_its_own_word():
    """Phase 4AF documented that `pypdf` returned a whole baseline drawn in one BT..ET as one string. The Phase 4AG reader
    follows each glyph, so the same stream yields separate cells at their own positions."""
    stream = (
        "BT /F1 10 Tf 72 700 Td (Dec-26) Tj 180 0 Td (Mar-27) Tj ET "
        "BT /F1 10 Tf 72 686 Td (OCR) Tj 180 0 Td (3.25) Tj 60 0 Td (3.00) Tj ET"
    )
    pdf = table_pdf([[]]).replace(b"q Q", stream.encode())
    words = extract_words(pdf, LIMITS, isolate=False)
    assert [(w.text, round(w.x0)) for w in words] == [
        ("Dec-26", 72),
        ("Mar-27", 252),
        ("OCR", 72),
        ("3.25", 252),
        ("3.00", 312),
    ]
