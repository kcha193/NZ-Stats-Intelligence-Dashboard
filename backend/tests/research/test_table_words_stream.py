"""Phase 4AG: positioned words from real-world-like content streams (SYNTHETIC FIXTURE text only).

Real reports draw a whole row in one `BT..ET`, kern with `TJ`, position with `Tm`, scale fonts through the matrix and raise
footnote markers. The reader must give every cell its own word and position, never glue two cells, and never lose a marker.
"""

import pytest

from nzstats.domain import IngestError
from nzstats.research import table_words
from nzstats.research.extract import ExtractionLimits
from nzstats.research.table_words import extract_words

from .pdf_stream_support import page, raw_pdf, row

LIMITS = ExtractionLimits()


def words_of(*contents: str, **kw):
    return extract_words(raw_pdf(list(contents), **kw), LIMITS, isolate=False)


def texts(words):
    return [w.text for w in words]


def test_cells_drawn_in_one_block_are_separate_words_with_their_own_positions():
    words = words_of(row(700, [(72, "OCR"), (252, "3.25"), (312, "3.00")]))
    assert texts(words) == ["OCR", "3.25", "3.00"]
    assert [round(w.x0) for w in words] == [72, 252, 312]
    assert {round(w.y) for w in words} == {700}


def test_the_right_edge_is_the_real_glyph_edge_not_an_estimate():
    (w,) = words_of(row(700, [(100, "3.25")]))
    assert w.x1 - w.x0 == pytest.approx(
        19.46, abs=0.05
    )  # Helvetica: 3 digits at 556 and a point at 278, 10 pt


def test_kerning_inside_a_tj_array_does_not_split_a_number():
    (w,) = words_of("BT /F1 10 Tf 72 700 Td [(3.)-20(2)-15(5)] TJ ET")
    assert w.text == "3.25"


def test_a_number_drawn_in_two_adjacent_pieces_is_one_word():
    (w,) = words_of("BT /F1 10 Tf 72 700 Td (3.) Tj (25) Tj ET")
    assert w.text == "3.25"


def test_two_numbers_in_one_string_stay_two_words():
    assert texts(words_of("BT /F1 10 Tf 72 700 Td (3.25 3.00) Tj ET")) == ["3.25", "3.00"]


def test_two_numbers_a_third_of_an_em_apart_stay_two_words():
    # 3.25 ends 19.46 points after its start; 3.0 points further on is 0.3 em at 10 pt.
    words = words_of(row(700, [(72, "3.25"), (72 + 19.46 + 3.0, "3.00")]))
    assert texts(words) == ["3.25", "3.00"]


def test_a_label_with_spaces_is_one_phrase():
    assert texts(words_of(row(700, [(72, "Real GDP growth (annual average % change)")]))) == [
        "Real GDP growth (annual average % change)"
    ]


def test_a_label_spaced_by_positioning_alone_is_one_phrase():
    # "Real" is 20.56 points wide at 10 pt; a 3 point gap is a word space made by positioning, not a column gap.
    (w,) = words_of(row(700, [(72, "Real"), (72 + 20.56 + 3.0, "GDP")]))
    assert w.text == "Real GDP"


def test_a_gap_wider_than_half_an_em_separates_cells():
    assert texts(words_of(row(700, [(72, "Real"), (72 + 20.56 + 7.0, "GDP")]))) == ["Real", "GDP"]


def test_a_raised_small_marker_touching_a_figure_is_kept_as_a_marker_not_glued_as_a_digit():
    stream = "BT /F1 10 Tf 72 700 Td (3.25) Tj ET BT /F1 6 Tf 1 0 0 1 91.7 704 Tm (1) Tj ET"
    (w,) = words_of(stream)
    assert w.text == "3.25¹"  # a superscript one, never "3.251"


def test_text_rise_marker_is_also_kept_as_a_marker():
    (w,) = words_of("BT /F1 10 Tf 72 700 Td (3.25) Tj 4 Ts /F1 6 Tf (2) Tj ET")
    assert w.text == "3.25²"


def test_a_small_word_far_from_a_figure_is_not_attached_to_it():
    stream = "BT /F1 10 Tf 72 700 Td (3.25) Tj ET BT /F1 6 Tf 1 0 0 1 140 704 Tm (note) Tj ET"
    assert sorted(texts(words_of(stream))) == ["3.25", "note"]


def test_rotated_text_is_dropped_and_upright_text_kept():
    stream = "BT /F1 10 Tf 0 1 -1 0 40 300 Tm (Forecast) Tj ET " + row(700, [(72, "OCR")])
    assert texts(words_of(stream)) == ["OCR"]


def test_text_drawn_twice_in_the_same_place_is_read_once():
    stream = row(700, [(72, "3.25")]) + " " + row(700, [(72, "3.25")])
    assert texts(words_of(stream)) == ["3.25"]


def test_a_scaled_font_gives_the_true_size_and_width():
    (w,) = words_of("BT /F1 20 Tf 0.5 0 0 0.5 72 700 Tm (3.25) Tj ET")
    assert w.size == pytest.approx(10, abs=0.2)
    assert w.x1 - w.x0 == pytest.approx(19.46, abs=0.1)


def test_a_minus_sign_glyph_stays_with_its_figure():
    (w,) = words_of("BT /F1 10 Tf 72 700 Td [(−) 10 (0.3)] TJ ET".replace("−", "-"))
    assert w.text == "-0.3"


def test_upright_content_on_a_page_rotated_for_display_is_displayed_sideways_and_not_read():
    with pytest.raises(IngestError, match="rotated_text_only"):
        words_of(row(700, [(72, "OCR"), (252, "3.25")]), rotate=90)


def test_a_landscape_page_stored_rotated_but_displayed_upright_is_read():
    stream = (
        "BT /F1 10 Tf 0 1 -1 0 100 72 Tm (OCR) Tj ET BT /F1 10 Tf 0 1 -1 0 100 252 Tm (3.25) Tj ET"
    )
    assert texts(words_of(stream, rotate=90)) == ["OCR", "3.25"]


# A composite font with no Unicode map: a reader can only name its glyphs by number.
UNMAPPED = (
    b"<< /Type /Font /Subtype /Type0 /BaseFont /Arial /Encoding /Identity-H /DescendantFonts [<< /Type /Font"
    b" /Subtype /CIDFontType2 /BaseFont /Arial /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >>"
    b" /DW 556 >>] >>"
)


def test_an_unmapped_glyph_keeps_a_visible_marker_so_the_value_cannot_parse():
    (w,) = words_of("BT /F3 10 Tf 72 700 Td <00330034> Tj ET", font_objects={"F3": UNMAPPED})
    assert "(cid:" in w.text


def test_the_word_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(table_words, "_MAX_WORDS", 3)
    cells = [(72 + 40 * i, str(i)) for i in range(6)]
    with pytest.raises(IngestError, match="pdf_extraction_limit"):
        words_of(row(700, cells))


def test_the_isolated_child_gives_the_same_words_as_the_parent():
    pdf = raw_pdf(
        [page(row(700, [(72, "OCR"), (252, "3.25")]), row(686, [(72, "CPI"), (252, "2.1")]))]
    )
    assert extract_words(pdf, LIMITS, isolate=True) == extract_words(pdf, LIMITS, isolate=False)


def test_neighbouring_period_headers_are_separate_cells_even_when_the_gutter_is_narrow():
    # "Mar-26" is 31.7 points wide at 10 pt; a 4.3 point gutter is 0.43 em, inside the phrase limit.
    words = words_of(row(700, [(150, "Mar-26"), (186, "Jun-26"), (222, "Sep-26")]))
    assert texts(words) == ["Mar-26", "Jun-26", "Sep-26"]


def test_headers_made_of_a_month_and_a_year_do_not_run_into_the_next_header():
    words = words_of(row(700, [(150, "Dec 2026"), (150 + 42.7 + 3, "Mar 2027")]))
    assert texts(words) == ["Dec 2026", "Mar 2027"]


def test_a_month_and_a_year_drawn_apart_still_form_one_header():
    assert texts(words_of(row(700, [(150, "Dec"), (150 + 17.8 + 3, "2026")]))) == ["Dec 2026"]
