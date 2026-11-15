"""Scoring against ground truth, on hand-built tables (no parser involved)."""

from pdfbench.metrics import score
from pdfbench.model import BenchTable, TruthTable

BOX = (0.0, 0.0, 1.0, 1.0)

TRUTH = TruthTable(
    page=1,
    bbox=BOX,
    row_labels=["Prices", "Jobless rate"],
    col_headers=[["Current", "(11 Nov)"], ["2026f"]],
    values={(0, 0): "2.5", (0, 1): "2.4", (1, 0): "4.9", (1, 1): "4.6"},
    stacked=[0],
    markers=[(0, "1")],
    notes=["Source: Other Forecaster"],
)


def _t(grid, notes=(), page=1):
    return BenchTable(page, BOX, [list(r) for r in grid], notes=list(notes))


PERFECT = [
    ["", "Current (11 Nov)", "2026f"],
    ["Prices¹", "2.5", "2.4"],
    ["Jobless rate", "4.9", "4.6"],
]


def test_perfect_grid_scores_everything():
    s = score([TRUTH], [_t(PERFECT, notes=["Source: Other Forecaster"])])
    assert (s.tables_truth, s.tables_found, s.tables_extra, s.tables_merged) == (1, 1, 0, 0)
    assert (s.values_truth, s.values_present, s.values_aligned) == (4, 4, 4)
    assert (s.stacked_truth, s.stacked_joined) == (1, 1)
    assert (s.markers_truth, s.markers_kept) == (1, 1)
    assert (s.notes_truth, s.notes_kept) == (1, 1)
    assert s.numeric_false_positive == 0


def test_stacked_fragments_in_different_columns_are_not_joined():
    grid = [["", "Current", ""], ["", "(11 Nov)", "2026f"], ["Prices", "2.5", "2.4"], ["Jobless rate", "4.9", "4.6"]]
    grid[0] = ["", "", "Current"]  # "Current" drifted over the next column
    s = score([TRUTH], [_t(grid)])
    assert s.stacked_joined == 0
    assert s.values_aligned == 0  # neither column now carries exactly its own header fragments


def test_shifted_column_is_present_but_not_aligned():
    grid = [["", "Current (11 Nov)", "2026f", ""], ["Prices", "", "2.5", "2.4"], ["Jobless rate", "", "4.9", "4.6"]]
    s = score([TRUTH], [_t(grid)])
    assert s.values_present == 4
    assert s.values_aligned == 0


def test_fused_footnote_digit_is_a_false_positive_not_a_match():
    truth = TruthTable(1, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"}, value_markers={(0, 0): "1"})
    s = score([truth], [_t([["", "2026f"], ["Prices", "2.51"]])])
    assert s.values_present == 0 and s.values_aligned == 0
    assert s.numeric_false_positive == 1
    assert s.markers_kept == 0


def test_separable_value_marker_is_kept():
    truth = TruthTable(1, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"}, value_markers={(0, 0): "1"})
    for cell in ("2.5¹", "2.5 1"):
        s = score([truth], [_t([["", "2026f"], ["Prices", cell]])])
        assert (s.values_aligned, s.markers_kept, s.numeric_false_positive) == (1, 1, 0)


def test_two_numbers_in_one_cell_are_a_false_positive():
    grid = [["", "Current (11 Nov) 2026f"], ["Prices", "2.5 2.4"], ["Jobless rate", "4.9 4.6"]]
    s = score([TRUTH], [_t(grid)])
    assert s.values_present == 0
    assert s.numeric_false_positive == 2


def test_axis_ticks_read_as_a_table_are_extra_and_false_positive():
    s = score([TRUTH], [_t(PERFECT), _t([["5", "2019"], ["4", "2020"]])])
    assert s.tables_extra == 1
    assert s.numeric_false_positive == 4


def test_one_parsed_table_spanning_two_truth_tables_is_merged():
    other = TruthTable(1, BOX, ["OCR", "Bill rate"], [["Dec-26"]], {(0, 0): "2.25", (1, 0): "2.40"})
    grid = [*PERFECT, ["", "Dec-26", ""], ["OCR", "2.25", ""], ["Bill rate", "2.40", ""]]
    s = score([TRUTH, other], [_t(grid)])
    assert (s.tables_found, s.tables_merged) == (2, 1)


def test_tables_on_another_page_do_not_count():
    s = score([TRUTH], [_t(PERFECT, page=2)])
    assert (s.tables_found, s.values_present, s.tables_extra) == (0, 0, 1)


def test_duplicate_values_need_one_cell_each():
    truth = TruthTable(1, BOX, ["A", "B"], [["2026f"]], {(0, 0): "2.25", (1, 0): "2.25"})
    s = score([truth], [_t([["", "2026f"], ["A", "2.25"], ["B", ""]])])
    assert s.values_present == 1 and s.values_aligned == 1
