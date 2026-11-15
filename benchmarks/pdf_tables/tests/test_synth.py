"""The synthetic cases are internally consistent: every truth string was drawn, and every PDF is marked synthetic."""

import io

import pytest
from pypdf import PdfReader

from pdfbench.synth import cases

CASES = cases()
NAMES = [c.name for c in CASES]


def test_case_names_cover_the_two_real_layouts_and_the_controls():
    assert {"p5_annual", "p5_annual_hrules", "p8_stacked", "p8_stacked_hrules"} <= set(NAMES)
    assert {"ruled_control", "fused_superscript", "axis_noise", "tight_columns"} <= set(NAMES)


@pytest.mark.parametrize("case", CASES, ids=NAMES)
def test_pdf_is_marked_synthetic(case):
    reader = PdfReader(io.BytesIO(case.pdf))
    assert reader.metadata.title.startswith("SYNTHETIC FIXTURE")
    assert len(reader.pages) == max(t.page for t in case.truth)


@pytest.mark.parametrize("case", CASES, ids=NAMES)
def test_every_truth_string_was_drawn(case):
    drawn = {text for _, _, _, text in case.items}
    for table in case.truth:
        assert set(table.row_labels) <= drawn
        assert {f for header in table.col_headers for f in header} <= drawn
        assert set(table.values.values()) <= drawn
        assert {m for _, m in table.markers} <= drawn
        assert set(table.notes) <= drawn


@pytest.mark.parametrize("case", CASES, ids=NAMES)
def test_value_keys_index_real_rows_and_columns(case):
    for table in case.truth:
        for r, c in table.values:
            assert 0 <= r < len(table.row_labels)
            assert 0 <= c < len(table.col_headers)
        assert all(0 <= c < len(table.col_headers) for c in table.stacked)


def test_stacked_layout_matches_the_recorded_geometry():
    (case,) = [c for c in CASES if c.name == "p8_stacked"]
    first = case.truth[0]
    assert first.stacked == [0]
    assert len(first.col_headers) == 9 and len(first.row_labels) == 6
    assert len(case.truth[1].row_labels) == 4


def test_hrules_variants_draw_lines_and_borderless_ones_do_not():
    by = {c.name: c for c in CASES}
    assert by["p5_annual"].lines == [] and by["p8_stacked"].lines == []
    assert by["p5_annual_hrules"].lines and by["p8_stacked_hrules"].lines
    assert all(y0 == y1 for _, y0, _, y1 in by["p8_stacked_hrules"].lines)  # horizontal only
