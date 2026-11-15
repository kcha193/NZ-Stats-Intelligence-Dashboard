"""A column header set on two lines that straddle the period line (Phase 4AK). SYNTHETIC FIXTURE text only.

The layout reproduces, by geometry alone, a real financial-markets table: a "Current" column whose header is one word
about 0.6 em above the period headers and a bracketed date about 0.6 em below them, then quarter-end columns. No bank
text or figure is used.
"""

from nzstats.research.extract import ExtractionLimits
from nzstats.research.table_forecast import interpret
from nzstats.research.table_grid import find_tables
from nzstats.research.table_words import Word, extract_words

from .pdf_table_support import Item, table_pdf

LABEL_X = 42.0
STACK_X = (118.0, 116.0)  # the upper and lower fragments of the stacked header
STACK_VALUE_X = 122.0
QUARTERS = ["Dec-26", "Mar-27", "Jun-27", "Sep-27"]
QX = [170.0, 220.0, 270.0, 320.0]
Y = 700.0  # the period line
UP, DOWN = 6.0, -6.0  # 0.6 em at the fixture's 10 pt


def rows(labels=("OCR (%)", "Rate B (%)"), top: float = Y - 20) -> list[Item]:
    out: list[Item] = []
    for n, label in enumerate(labels):
        y = top - 14 * n
        out += [(LABEL_X, y, label), (STACK_VALUE_X, y, "3.00")]
        out += [(x + 3, y, f"{2.75 - 0.25 * k:.2f}") for k, x in enumerate(QX)]
    return out


def periods(y: float = Y) -> list[Item]:
    return [(x, y, q) for x, q in zip(QX, QUARTERS, strict=True)]


def stacked_page(*extra: Item, upper="Current", lower="(13-Nov)") -> list[Item]:
    return [
        (LABEL_X, 740, "Table 9: Forecasts (SYNTHETIC)"),
        (STACK_X[0], Y + UP, upper),
        *periods(),
        (STACK_X[1], Y + DOWN, lower),
        *extra,
        *rows(),
    ]


def read(page: list[Item]):
    words = extract_words(table_pdf([page]), ExtractionLimits(), isolate=False)
    return find_tables(words)


def test_a_header_stacked_across_the_period_line_is_one_column():
    (t,), rejections = read(stacked_page())
    assert rejections == ()
    assert [c.headers for c in t.columns] == [("Current (13-Nov)",), *[(q,) for q in QUARTERS]]
    assert [(c.col, c.text) for c in t.body_rows[0][1:]] == [
        (0, "3.00"), (1, "2.75"), (2, "2.50"), (3, "2.25"), (4, "2.00"),
    ]  # fmt: skip


def test_the_stacked_fragments_keep_their_own_lines_and_positions():
    (t,), _ = read(stacked_page())
    assert [[c.text for c in line] for line in t.header_rows] == [
        ["Current"], QUARTERS, ["(13-Nov)"],
    ]  # fmt: skip
    upper, lower = t.header_rows[0][0], t.header_rows[2][0]
    assert (upper.x0, lower.x0) == STACK_X
    assert upper.y > t.header_rows[1][0].y > lower.y


def test_a_group_header_over_the_quarters_does_not_reach_the_stacked_column():
    (t,), rejections = read(stacked_page((QX[0], Y + 18, "Forecast")))
    assert rejections == ()
    assert [c.headers for c in t.columns] == [
        ("Current (13-Nov)",), *[("Forecast", q) for q in QUARTERS],
    ]  # fmt: skip


def test_a_group_header_over_the_stacked_column_covers_it():
    (t,), rejections = read(
        stacked_page((STACK_X[1], Y + 18, "Actual"), (QX[0], Y + 18, "Forecast"))
    )
    assert rejections == ()
    assert t.columns[0].headers == ("Actual", "Current (13-Nov)")
    assert t.columns[1].headers == ("Forecast", "Dec-26")


def _words(items: list[tuple[float, float, float, str]]) -> list[Word]:
    return [Word(1, x0, x1, y, 10.0, text) for x0, x1, y, text in items]


def test_a_stacked_fragment_overlapping_a_period_header_is_ambiguous():
    # The PDF word reader refuses glyphs drawn over each other, so this layout is built from positioned words directly.
    words = _words([
        (42.0, 80.0, 680.0, "OCR (%)"), (122.0, 140.0, 680.0, "3.00"), (180.0, 198.0, 680.0, "2.75"),
        (118.0, 152.0, Y + UP, "Current"),
        (170.0, 202.0, Y, "Dec-26"), (220.0, 252.0, Y, "Mar-27"), (223.0, 241.0, 680.0, "2.50"),
        (116.0, 175.0, Y + DOWN, "(13-November)"),  # overlaps "Dec-26"; no figure straddles the two
    ])  # fmt: skip
    tables, rejections = find_tables(words)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_the_same_layout_without_the_overlap_is_read():
    words = _words([
        (42.0, 80.0, 680.0, "OCR (%)"), (122.0, 140.0, 680.0, "3.00"), (173.0, 191.0, 680.0, "2.75"),
        (118.0, 152.0, Y + UP, "Current"),
        (170.0, 202.0, Y, "Dec-26"), (220.0, 252.0, Y, "Mar-27"), (223.0, 241.0, 680.0, "2.50"),
        (116.0, 155.0, Y + DOWN, "(13-Nov)"),
    ])  # fmt: skip
    (t,), rejections = find_tables(words)
    assert rejections == ()
    assert [c.headers for c in t.columns] == [("Current (13-Nov)",), ("Dec-26",), ("Mar-27",)]


def test_a_fragment_only_below_the_period_line_is_ambiguous():
    page = [
        (LABEL_X, 740, "Table 9 (SYNTHETIC)"),
        *periods(),
        (STACK_X[1], Y + DOWN, "(13-Nov)"),
        *rows(),
    ]
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_a_fragment_only_above_the_period_line_is_ambiguous():
    page = [
        (LABEL_X, 740, "Table 9 (SYNTHETIC)"),
        (STACK_X[0], Y + UP, "Current"),
        *periods(),
        *rows(),
    ]
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_a_lower_fragment_a_full_line_below_is_not_part_of_a_stacked_header():
    page = [
        (LABEL_X, 740, "Table 9 (SYNTHETIC)"),
        (STACK_X[0], Y + UP, "Current"),
        *periods(),
        (STACK_X[1], Y - 12, "(13-Nov)"),
        *rows(top=Y - 26),
    ]
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_every_stacked_cell_must_straddle_the_period_line():
    # A second header beside the stacked one, set only above the period line, is not a stacked cell.
    page = stacked_page((QX[-1] + 50, Y + UP, "Spot"))
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_a_separate_header_line_below_a_stacked_header_is_refused_not_dropped():
    page = [
        (LABEL_X, 740, "Table 9 (SYNTHETIC)"),
        (STACK_X[0], Y + UP, "Current"),
        *periods(),
        (STACK_X[1], Y + DOWN, "(13-Nov)"),
        (QX[0], Y - 12, "(sa)"),
        *rows(top=Y - 26),
    ]
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_two_header_lines_tied_for_the_most_cells_are_ambiguous():
    # Pin (defence in depth): the period line must be the one line with the most cells.
    page = stacked_page(*[(x, Y + 18, "Forecast") for x in QX])
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_two_lower_fragments_under_one_upper_fragment_are_ambiguous():
    page = stacked_page(lower="(13")
    page.append((STACK_X[1] + 30, Y + DOWN, "Nov)"))
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_a_lower_fragment_spanning_two_upper_fragments_is_ambiguous():
    page = [
        (LABEL_X, 740, "Table 9 (SYNTHETIC)"),
        (112.0, Y + UP, "Spot"),
        (150.0, Y + UP, "Now"),
        *periods(),
        (112.0, Y + DOWN, "(13-Nov-26)"),
        *rows(),
    ]
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def _interpret(page: list[Item]):
    tables, grid = read(page)
    forecasts, rejections = interpret(tables, publisher_names=("Example Bank",))
    return forecasts, (*grid, *rejections)


def test_no_actual_or_forecast_marker_is_inferred_for_any_column():
    forecasts, rejections = _interpret(stacked_page())
    assert forecasts == ()
    assert {(r.code, r.col) for r in rejections} == {
        ("actual_or_forecast_unstated", n) for n in range(5)
    } | {("unmapped_row", None)}


def test_marked_quarters_beside_a_stacked_column_are_read_and_the_stacked_column_is_not():
    forecasts, rejections = _interpret(stacked_page((QX[0], Y + 18, "Forecast")))
    assert [(f.col, f.period_text, f.kind, f.raw_text, f.unit) for f in forecasts] == [
        (1, "Dec-26", "forecast", "2.75", "percent"),
        (2, "Mar-27", "forecast", "2.50", "percent"),
        (3, "Jun-27", "forecast", "2.25", "percent"),
        (4, "Sep-27", "forecast", "2.00", "percent"),
    ]
    assert all(f.indicator == "ocr" for f in forecasts)
    assert ("actual_or_forecast_unstated", 0) in {(r.code, r.col) for r in rejections}


def test_a_stacked_table_continued_with_the_same_header_is_one_table():
    second = [
        (STACK_X[0], Y + UP, "Current"),
        *periods(),
        (STACK_X[1], Y + DOWN, "(13-Nov)"),
        *rows(),
    ]
    words = extract_words(table_pdf([stacked_page(), second]), ExtractionLimits(), isolate=False)
    (t,), rejections = find_tables(words)
    assert rejections == ()
    assert (t.page_start, t.page_end, len(t.body_rows)) == (1, 2, 4)


def test_a_continuation_whose_stacked_header_lost_a_fragment_is_not_joined():
    second = [(STACK_X[0], Y + UP, "Current"), *periods(), *rows()]
    words = extract_words(table_pdf([stacked_page(), second]), ExtractionLimits(), isolate=False)
    tables, rejections = find_tables(words)
    assert [(t.page_start, t.page_end) for t in tables] == [(1, 1)]
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_two_group_headers_starting_over_one_column_are_ambiguous():
    # Review finding (Phase 4AK): the second group header used to replace the first silently.
    page = stacked_page((112.0, Y + 18, "A"), (140.0, Y + 18, "B"))
    tables, rejections = read(page)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]


def test_a_line_less_than_one_em_above_the_period_line_is_not_a_group_header():
    # Review finding (Phase 4AK): such a line cannot be a row of its own, so it may not label every column below it.
    # The PDF reader refuses glyphs drawn over each other, so this is built from positioned words directly.
    words = _words([
        (170.0, 205.0, Y + UP, "Current"),
        (170.0, 202.0, Y, "Dec-26"), (220.0, 252.0, Y, "Mar-27"),
        (42.0, 80.0, 680.0, "OCR (%)"), (173.0, 191.0, 680.0, "2.75"), (223.0, 241.0, 680.0, "2.50"),
    ])  # fmt: skip
    tables, rejections = find_tables(words)
    assert tables == ()
    assert [r.code for r in rejections] == ["ambiguous_columns"]
