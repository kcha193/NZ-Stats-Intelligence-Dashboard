"""Scoring against ground truth, on hand-built tables (no parser involved)."""

import random

import pytest

from pdfbench.metrics import _match, numeric, score
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


def test_a_detached_marker_under_a_value_column_is_a_false_positive():
    truth = TruthTable(1, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"}, value_markers={(0, 0): "1"})
    s = score([truth], [_t([["", "2026f"], ["", "1"], ["Prices", "2.5"]])])
    assert s.values_aligned == 1 and s.markers_kept == 0
    assert s.numeric_false_positive == 1  # a lone digit under a period header reads as a figure


def test_a_detached_marker_in_the_label_column_is_not_a_figure():
    s = score([TRUTH], [_t([["", "Current (11 Nov)", "2026f"], ["1", "", ""], *PERFECT[1:]])])
    assert s.numeric_false_positive == 0


def test_leading_decimal_fragments_are_numeric():
    for cell in (".25", "-.25", "+.25", "−.25", "–.25", "(.25)", ".25%", ".25 2.5", " .25 ", ".25¹"):
        assert numeric(cell), cell


def test_existing_number_forms_stay_numeric():
    for cell in ("2.5", "-2.5", "−2.5", "1,234.56", "2.5%", "(2.5)", "2.5 2.4", "2026", "0.25", "2.5¹"):
        assert numeric(cell), cell


def test_non_numbers_stay_non_numeric():
    for cell in (
        ".",
        "-.",
        "..25",
        ".abc",
        ".25.",
        ".25.3",
        "2..5",
        ".,25",
        ".-25",
        "-",
        "%",
        "()",
        "",
        "Prices",
        "Dec-26",
        "2026f",
        "a.25",
        ".25-.30",
        "-.25-.30",
        ".25/.30",
        "1/.25",
        "+.",
        "(.)",
        "−.",
    ):
        assert not numeric(cell), cell


def test_leading_decimal_fragment_of_a_truth_value_is_one_false_positive():
    truth = TruthTable(1, BOX, ["OCR"], [["2026f"]], {(0, 0): "4.25"})
    s = score([truth], [_t([["", "2026f"], ["OCR", ".25"]])])
    assert (s.values_present, s.values_aligned) == (0, 0)
    assert s.numeric_false_positive == 1


def test_a_parsed_cell_is_consumed_once_across_truth_tables_on_a_page():
    first = TruthTable(1, BOX, ["A"], [["2026f"]], {(0, 0): "2.5"})
    second = TruthTable(1, BOX, ["B"], [["2027f"]], {(0, 0): "2.5"})
    s = score([first, second], [_t([["", "2026f"], ["A", "2.5"]])])
    assert s.values_truth == 2
    assert s.values_present == 1


def test_a_marked_truth_takes_its_marked_cell_before_a_plain_one():
    marked = TruthTable(1, BOX, ["A"], [["2026f"]], {(0, 0): "2.5"}, value_markers={(0, 0): "1"})
    plain = TruthTable(1, BOX, ["B"], [["2027f"]], {(0, 0): "2.5"})
    got = [_t([["", "2026f", "2027f"], ["A", "2.5¹", ""], ["B", "", "2.5"]])]
    for order in ([marked, plain], [plain, marked]):
        assert score(order, got).values_present == 2


# Alignment consumes physical cells: one parsed cell aligns at most one truth occurrence (PR #65 review).
PRICES = TruthTable(1, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"})
ONE_CELL = [["", "2026f"], ["Prices", "2.5"]]


def _counts(s):
    return s.values_truth, s.values_present, s.values_aligned


def test_one_parsed_cell_aligns_one_of_two_identical_truth_tables():
    s = score([PRICES, PRICES], [_t(ONE_CELL)])
    assert _counts(s) == (2, 1, 1)


def test_two_distinct_cells_with_the_same_text_both_align():
    s = score([PRICES, PRICES], [_t(ONE_CELL), _t(ONE_CELL)])
    assert _counts(s) == (2, 2, 2)


def test_a_duplicate_within_one_truth_table_needs_its_own_cell():
    truth = TruthTable(1, BOX, ["Prices", "Prices"], [["2026f"]], {(0, 0): "2.5", (1, 0): "2.5"})
    assert _counts(score([truth], [_t(ONE_CELL)])) == (2, 1, 1)
    two_rows = [["", "2026f"], ["Prices", "2.5"], ["Prices", "2.5"]]
    assert _counts(score([truth], [_t(two_rows)])) == (2, 2, 2)


def test_cells_on_each_page_are_counted_on_their_own_page():
    second = TruthTable(2, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"})
    assert _counts(score([PRICES, second], [_t(ONE_CELL), _t(ONE_CELL, page=2)])) == (2, 2, 2)
    assert _counts(score([PRICES, second], [_t(ONE_CELL)])) == (2, 1, 1)
    assert _counts(score([PRICES, second], [_t(ONE_CELL, page=2)])) == (2, 1, 1)


def test_the_same_figure_aligns_only_under_its_own_row_and_column():
    truth = TruthTable(
        1, BOX, ["A", "B"], [["2026f"], ["2027f"]], {(0, 0): "2.5", (0, 1): "1.0", (1, 0): "3.0", (1, 1): "2.5"}
    )
    swapped = [["", "2026f", "2027f"], ["A", "2.5", "1.0"], ["B", "2.5", "3.0"]]  # row B's figures swapped
    assert _counts(score([truth], [_t(swapped)])) == (4, 4, 2)


def test_a_misplaced_duplicate_is_present_but_never_aligned_twice():
    misplaced = [["", "2026f", "2027f"], ["Prices", "", "2.5"]]  # under a foreign column
    s = score([PRICES, PRICES], [_t(ONE_CELL), _t(misplaced)])
    assert _counts(s) == (2, 2, 1)


def test_a_marked_value_keeps_its_marker_whichever_cell_comes_first():
    marked = TruthTable(1, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"}, value_markers={(0, 0): "1"})
    plain_cell, marked_cell = _t(ONE_CELL), _t([["", "2026f"], ["Prices", "2.5¹"]])
    for got in ([plain_cell, marked_cell], [marked_cell, plain_cell]):
        alone = score([marked], got)
        assert (alone.values_aligned, alone.markers_kept) == (1, 1)
        for truth in ([marked, PRICES], [PRICES, marked]):
            s = score(truth, got)
            assert _counts(s) == (2, 2, 2)
            assert (s.markers_truth, s.markers_kept) == (1, 1)


def test_a_plain_cell_alone_cannot_keep_a_marker():
    marked = TruthTable(1, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"}, value_markers={(0, 0): "1"})
    s = score([marked, PRICES], [_t(ONE_CELL)])
    assert _counts(s) == (2, 1, 1)
    assert s.markers_kept == 0


def test_truth_order_and_parsed_table_order_do_not_change_the_score():
    stacked = TruthTable(1, BOX, ["Prices"], [["Annual", "2026f"]], {(0, 0): "2.5"}, stacked=[0])
    flat = TruthTable(1, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"})
    joined = _t([["", "Annual"], ["", "2026f"], ["Prices", "2.5"]])  # one cell both truth tables can claim
    extra = _t([["", "2027f"], ["Prices", "2.5"]])
    first = score([stacked, flat], [joined, extra])
    assert _counts(first) == (2, 2, 1)
    for truth in ([stacked, flat], [flat, stacked]):
        for got in ([joined, extra], [extra, joined]):
            assert score(truth, got) == first


def test_scores_keep_their_bounds_and_ignore_order_on_random_tables():
    rng = random.Random(4)
    labels, headers, figures = ["A", "B"], ["2026f", "2027f"], ["2.5", "2.4"]

    def truth_table(page):
        keys = [(r, c) for r in range(2) for c in range(2) if rng.random() < 0.7]
        values = {k: rng.choice(figures) for k in keys}
        marked = {k: "1" for k in keys if rng.random() < 0.3}
        return TruthTable(page, BOX, labels, [[h] for h in headers], values, stacked=[0], value_markers=marked)

    def cell():
        return rng.choice(["", *figures, "2.5¹", "2.4¹"])

    def parsed(page):
        grid = [["", rng.choice(headers), rng.choice(headers)]]
        grid += [[rng.choice(labels), cell(), cell()] for _ in range(rng.randint(1, 3))]
        return _t(grid, page=page)

    for _ in range(400):
        truth = [truth_table(rng.choice([1, 2])) for _ in range(rng.randint(1, 4))]
        got = [parsed(rng.choice([1, 2])) for _ in range(rng.randint(0, 4))]
        s = score(truth, got)
        assert 0 <= s.values_aligned <= s.values_present <= s.values_truth
        assert 0 <= s.markers_kept <= s.markers_truth and 0 <= s.stacked_joined <= s.stacked_truth
        cells = sum(1 for t in got for row in t.grid for c in row if c in {*figures, "2.5¹", "2.4¹"})
        assert s.values_present <= cells
        assert score(truth[::-1], got[::-1]) == s


def test_a_value_reading_as_another_value_plus_its_marker_is_refused():
    # "2.5 1" is both the plain text of one value and "2.5" with marker 1: a cell reading it cannot be attributed, and
    # the marker count would depend on parsed-table order (independent review, PR #65).
    truth = TruthTable(
        1, BOX, ["Prices", "Prices"], [["2026f"]], {(0, 0): "2.5", (1, 0): "2.5 1"}, value_markers={(0, 0): "1"}
    )
    plain, marked = _t(ONE_CELL), _t([["", "2026f"], ["Prices", "2.5 1"], ["Prices", "2.5 1"]])
    for got in ([plain, marked], [marked, plain]):
        with pytest.raises(ValueError, match="ambiguous"):
            score([truth], got)
    other_page = TruthTable(2, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5 1"})
    plain_truth = TruthTable(1, BOX, ["Prices"], [["2026f"]], {(0, 0): "2.5"}, value_markers={(0, 0): "1"})
    assert score([plain_truth, other_page], [plain, marked]).markers_kept == 1  # pages are separate


def test_matching_a_long_chain_does_not_recurse():
    n = 3000  # value i accepts cells i-1 and i, so the last value's path runs through every other value
    wants = [[(0, 0, 0)]] + [[(0, 0, i - 1), (0, 0, i)] for i in range(1, n)]
    assert len(_match(wants[::-1])) == n


# Overlapping period headers: "2026" inside "2026f" is not a foreign header there (PR #65 review).
OVERLAP = TruthTable(1, BOX, ["Prices"], [["2026f"], ["2026"]], {(0, 0): "2.5", (0, 1): "2.4"})


def test_overlapping_headers_align_on_an_exact_grid():
    for headers in (["2026f", "2026"], ["2026", "2026f"]):
        truth = TruthTable(1, BOX, ["Prices"], [[h] for h in headers], {(0, 0): "2.5", (0, 1): "2.4"})
        assert score([truth], [_t([["", *headers], ["Prices", "2.5", "2.4"]])]).values_aligned == 2


@pytest.mark.parametrize(
    "grid",
    [
        [["", "", "2026f 2026"], ["Prices", "2.5", "2.4"]],  # both headers collapsed over the second column
        [["", "2026f 2026", ""], ["Prices", "2.5", "2.4"]],  # ... over the first
        [["", "2026f2026", ""], ["Prices", "2.5", "2.4"]],  # glued into one word
    ],
)
def test_a_collapsed_overlapping_header_does_not_align(grid):
    s = score([OVERLAP], [_t(grid)])
    assert s.values_aligned == 0
