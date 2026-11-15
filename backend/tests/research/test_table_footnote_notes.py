"""Notes under a table that start with a footnote marker set as a small plain digit (Phase 4AK). SYNTHETIC FIXTURE.

A real outlook sets its footnote markers below a table as a small digit on its own line, a little above the definition
text. The note walk did not know that line, so it stopped there and never read the source line beneath. A source that
names another forecaster was then ignored, and the figures were attributed to the publisher. Built from positioned words:
the fixture PDF writer draws every item at one font size.
"""

from nzstats.research.table_forecast import interpret
from nzstats.research.table_grid import find_tables
from nzstats.research.table_words import Word


def _w(x0: float, x1: float, y: float, text: str, size: float = 10.0) -> Word:
    return Word(1, x0, x1, y, size, text)


def table(label: str = "OCR (%)") -> list[Word]:
    return [
        _w(250, 280, 714, "Forecast"),
        _w(250, 282, 700, "Dec-26"),
        _w(72, 140, 686, label),
        _w(253, 271, 686, "2.50"),
    ]


def marker(digit: str = "1", size: float = 5.0) -> list[Word]:
    return [_w(72, 75, 677, digit, size), _w(78, 140, 674.5, "Definition text", 7.5)]


def run(words: list[Word]):
    tables, grid = find_tables(words)
    forecasts, rejections = interpret(tables, publisher_names=("Example Bank",))
    return tables, forecasts, (*grid, *rejections)


def test_a_source_line_below_a_small_digit_footnote_is_read():
    tables, forecasts, _ = run([*table(), *marker(), _w(72, 160, 663, "Source: RBNZ", 7.5)])
    assert [len(t.notes) for t in tables] == [2]
    assert [f.author_role for f in forecasts] == ["third_party"]


def test_the_small_digit_becomes_a_footnote_marker_in_the_note():
    tables, _, _ = run([*table(), *marker()])
    assert tables[0].notes == ("¹ Definition text",)


def test_a_footnote_definition_does_not_qualify_unmarked_rows():
    _, forecasts, rejections = run([*table(), *marker()])
    assert [(f.indicator, f.author_role) for f in forecasts] == [("ocr", "author")]
    assert rejections == ()


def test_a_footnoted_row_stays_unresolved_with_its_definition_attached():
    _, forecasts, rejections = run([*table("OCR¹ (%)"), *marker()])
    assert forecasts == ()
    assert [r.code for r in rejections] == ["footnote_unresolved"]


def test_a_full_size_digit_below_a_table_is_not_a_footnote_marker():
    tables, _, _ = run([*table(), _w(72, 78, 672, "7"), _w(72, 160, 660, "Source: RBNZ")])
    assert [len(t.notes) for t in tables] == [0]


def test_a_small_digit_away_from_the_row_labels_is_not_a_marker():
    # Second review (Phase 4AK): a chart tick or a page number under a table must not open the note walk.
    for digit in (_w(400, 403, 677, "5", 6.0), _w(300, 306, 672, "12", 7.0)):
        tables, forecasts, _ = run([*table(), digit, _w(72, 160, 663, "Source: RBNZ", 7.5)])
        assert [len(t.notes) for t in tables] == [0]
        assert [f.author_role for f in forecasts] == ["author"]


def test_zero_is_not_a_footnote_marker():
    tables, _, _ = run([*table(), *marker("0")])
    assert [len(t.notes) for t in tables] == [0]


def test_a_line_back_at_the_margin_after_a_definition_is_unmarked_context():
    # A footnote definition wraps under its own text; a line starting back under the marker is a new, unmarked note.
    words = [*table(), *marker(), _w(72, 160, 663, "Forecasts are RBNZ", 7.5)]
    tables, forecasts, _ = run(words)
    assert tables[0].notes == ("¹ Definition text", "Forecasts are RBNZ")
    assert [f.author_role for f in forecasts] == ["third_party"]


def test_a_wrapped_definition_line_stays_with_its_marker():
    words = [*table(), *marker(), _w(78, 140, 664, "continued", 7.5)]
    tables, forecasts, _ = run(words)
    assert tables[0].notes == ("¹ Definition text continued",)
    assert [f.author_role for f in forecasts] == ["author"]
