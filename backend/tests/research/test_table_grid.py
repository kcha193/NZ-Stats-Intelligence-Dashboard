"""Rows and columns from positioned words (Phase 4AF): what a table is, and when to refuse to read one."""

from nzstats.research.extract import ExtractionLimits
from nzstats.research.table_grid import find_tables
from nzstats.research.table_words import extract_words, text_width

from .pdf_table_support import Item, table_pdf

COLS = [250.0, 310.0, 370.0, 430.0]
HEAD = ["Dec-26", "Mar-27", "Jun-27", "Sep-27"]


def line(y: float, label: str, values: list[str | None], xs=COLS) -> list[Item]:
    items: list[Item] = [(72, y, label)] if label else []
    items += [(x, y, v) for x, v in zip(xs, values, strict=True) if v is not None]
    return items


def header(y: float = 700, texts=HEAD, xs=COLS) -> list[Item]:
    return line(y, "", list(texts), xs)


def read(*pages: list[Item]):
    words = extract_words(table_pdf(list(pages)), ExtractionLimits(), isolate=False)
    return find_tables(words)


def simple_page() -> list[Item]:
    return [
        (72, 740, "Table 1: Forecasts (SYNTHETIC)"),
        *header(),
        *line(686, "OCR (%)", ["3.25", "3.00", "2.75", "2.75"]),
        *line(672, "Annual CPI inflation", ["2.8", "2.4", "2.1", "2.0"]),
        *line(658, "Unemployment rate", ["5.1", "5.0", "4.9", None]),
        (72, 630, "Source: Example Bank"),
    ]


def test_a_simple_table_has_columns_headers_rows_caption_and_notes():
    tables, rejections = read(simple_page())
    assert rejections == ()
    (t,) = tables
    assert t.caption == "Table 1: Forecasts (SYNTHETIC)"
    assert [c.headers for c in t.columns] == [(h,) for h in HEAD]
    assert [row[0].text for row in t.body_rows] == [
        "OCR (%)",
        "Annual CPI inflation",
        "Unemployment rate",
    ]
    assert [c.text for c in t.body_rows[0][1:]] == ["3.25", "3.00", "2.75", "2.75"]
    assert t.notes == ("Source: Example Bank",)
    assert (t.page_start, t.page_end) == (1, 1)


def test_an_incomplete_row_keeps_its_cells_in_their_own_columns():
    tables, _ = read(simple_page())
    last = tables[0].body_rows[2]
    assert [(c.col, c.text) for c in last[1:]] == [(0, "5.1"), (1, "5.0"), (2, "4.9")]


def test_merged_group_headers_apply_to_the_columns_they_start_over():
    page = [
        (250, 714, "Actual"),
        (370, 714, "Forecast"),
        *header(),
        *line(686, "OCR (%)", ["4.00", "3.50", "3.25", "3.00"]),
    ]
    (t,), rejections = read(page)
    assert rejections == ()
    assert [c.headers for c in t.columns] == [
        ("Actual", "Dec-26"),
        ("Actual", "Mar-27"),
        ("Forecast", "Jun-27"),
        ("Forecast", "Sep-27"),
    ]


def test_a_group_header_starting_in_a_gap_is_ambiguous():
    page = [(350, 714, "Forecast"), *header(), *line(686, "OCR (%)", ["4", "3", "2", "1"])]
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_right_aligned_numbers_land_in_their_header_columns():
    right = [x + text_width(h, 10) for x, h in zip(COLS, HEAD, strict=True)]
    values = ["3.25", "3.00", "2.75", "2.75"]
    xs = [r - text_width(v, 10) for r, v in zip(right, values, strict=True)]
    page = [*header(), *line(686, "OCR (%)", values, xs)]
    (t,), _ = read(page)
    assert [(c.col, c.text) for c in t.body_rows[0][1:]] == list(enumerate(values))


def test_a_row_straddling_two_columns_rejects_the_whole_table():
    shifted = [x + 30 for x in COLS]
    page = [
        *header(),
        *line(686, "OCR (%)", ["3.25", "3.00", "2.75", "2.75"]),
        *line(672, "Annual CPI inflation", ["2.8", "2.4", "2.1", "2.0"], shifted),
    ]
    tables, rejections = read(page)
    assert tables == ()
    assert [(r.code, r.page, r.row) for r in rejections] == [("ambiguous_columns", 1, 1)]


def test_a_value_beyond_the_last_column_is_ambiguous():
    page = [*header(), *line(686, "OCR (%)", ["1", "2", "3", "4"]), (560, 686, "9.9")]
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_a_table_continued_with_a_repeated_header_is_one_table():
    p1 = [*header(), *line(686, "OCR (%)", ["3", "3", "3", "3"])]
    p2 = [*header(), *line(686, "Annual CPI inflation", ["2", "2", "2", "2"])]
    (t,), rejections = read(p1, p2)
    assert rejections == ()
    assert (t.page_start, t.page_end) == (1, 2)
    assert len(t.header_rows) == 1
    assert [row[0].text for row in t.body_rows] == ["OCR (%)", "Annual CPI inflation"]
    assert [row[0].row for row in t.body_rows] == [0, 1]
    assert [row[0].page for row in t.body_rows] == [1, 2]


def test_a_table_continued_without_a_header_is_one_table():
    p1 = [*header(), *line(686, "OCR (%)", ["3", "3", "3", "3"])]
    p2 = [*line(700, "Annual CPI inflation", ["2", "2", "2", "2"])]
    (t,), _ = read(p1, p2)
    assert len(t.body_rows) == 2 and t.page_end == 2


def test_a_different_header_on_the_next_page_is_a_new_table():
    p1 = [*header(), *line(686, "OCR (%)", ["3", "3", "3", "3"])]
    p2 = [*header(texts=["2026", "2027", "2028", "2029"]), *line(686, "GDP", ["1", "2", "3", "4"])]
    tables, _ = read(p1, p2)
    assert len(tables) == 2
    assert [c.headers for c in tables[1].columns] == [("2026",), ("2027",), ("2028",), ("2029",)]


def test_rows_without_any_header_and_nothing_to_continue_are_refused():
    tables, rejections = read([*line(700, "OCR (%)", ["3", "3", "3", "3"])])
    assert tables == ()
    assert [r.code for r in rejections] == ["no_header"]


def test_a_continuation_after_notes_is_not_joined():
    p1 = [*header(), *line(686, "OCR (%)", ["3", "3", "3", "3"]), (72, 660, "Source: Example Bank")]
    p2 = [*line(700, "Annual CPI inflation", ["2", "2", "2", "2"])]
    tables, rejections = read(p1, p2)
    assert len(tables) == 1 and len(tables[0].body_rows) == 1
    assert [r.code for r in rejections] == ["no_header"]


def test_prose_is_not_a_table():
    page = [(72, 700, "The economy is expected to grow slowly."), (72, 686, "Inflation will ease.")]
    assert read(page) == ((), ())


def test_missing_markers_are_cells_not_gaps():
    page = [*header(), *line(686, "Unemployment rate", ["5.1", "-", "n/a", "4.9"])]
    (t,), _ = read(page)
    assert [c.text for c in t.body_rows[0][1:]] == ["5.1", "-", "n/a", "4.9"]


def test_a_unit_column_is_a_column_with_its_own_role():
    xs = [200.0, 260.0, 320.0]
    page = [
        *line(700, "", ["Unit", "Dec-26", "Mar-27"], xs),
        *line(686, "OCR", ["%", "3.25", "3.00"], xs),
    ]
    (t,), _ = read(page)
    assert [c.role for c in t.columns] == ["unit", "value", "value"]
    assert t.body_rows[0][1].text == "%"


def test_a_row_with_no_figure_in_the_first_column_keeps_that_column():
    page = [*header(), *line(686, "Unemployment rate", [None, "5.0", "4.9", None])]
    (t,), _ = read(page)
    assert len(t.columns) == 4
    assert [(c.col, c.text) for c in t.body_rows[0][1:]] == [(1, "5.0"), (2, "4.9")]


def test_a_captioned_table_on_the_next_page_is_a_new_table_even_with_the_same_header():
    p1 = [
        (72, 745, "Table 1: Central forecasts"),
        *header(),
        *line(686, "OCR (%)", ["3", "3", "3", "3"]),
    ]
    p2 = [
        (72, 745, "Table 2: Downside scenario"),
        *header(),
        *line(686, "OCR (%)", ["9", "9", "9", "9"]),
    ]
    tables, _ = read(p1, p2)
    assert [(t.caption, len(t.body_rows)) for t in tables] == [
        ("Table 1: Central forecasts", 1),
        ("Table 2: Downside scenario", 1),
    ]


def test_a_captioned_block_without_a_header_is_not_a_continuation():
    p1 = [
        (72, 745, "Table 1: Central forecasts"),
        *header(),
        *line(686, "OCR (%)", ["3", "3", "3", "3"]),
    ]
    p2 = [(72, 745, "Table 2: Downside scenario"), *line(700, "OCR (%)", ["9", "9", "9", "9"])]
    tables, rejections = read(p1, p2)
    assert len(tables) == 1 and len(tables[0].body_rows) == 1
    assert [r.code for r in rejections] == ["no_header"]


def test_a_caption_that_says_continued_is_a_continuation():
    p1 = [(72, 745, "Table 1: Forecasts"), *header(), *line(686, "OCR (%)", ["3", "3", "3", "3"])]
    p2 = [
        (72, 745, "Table 1 (continued)"),
        *header(),
        *line(686, "Annual CPI inflation (%)", ["2", "2", "2", "2"]),
    ]
    (t,), _ = read(p1, p2)
    assert t.page_end == 2 and len(t.body_rows) == 2


def test_a_header_drawn_in_two_pieces_is_one_header():
    xs = [250.0, 330.0]
    page = [
        (xs[0], 700, "Dec"), (xs[0] + 20, 700, "2026"), (xs[1], 700, "Mar"), (xs[1] + 20, 700, "2027"),
        *line(686, "OCR (%)", ["3.25", "3.00"], xs),
    ]  # fmt: skip
    (t,), _ = read(page)
    assert [c.headers for c in t.columns] == [("Dec 2026",), ("Mar 2027",)]
