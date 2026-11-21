"""Masked layout probe (Phase 4AO): cell coordinates and counts only, on SYNTHETIC workbooks."""

import json
import zipfile
from pathlib import Path

import pytest

from tests import synth
from xlsxinspect.guard import emit
from xlsxinspect.inspect import inspect
from xlsxinspect.layout import drawing_counts, layout


def _probe(tmp_path, wb=None):
    path = synth.save(wb or synth.vertical_book(), tmp_path / "v.xlsx")
    return layout(path.read_bytes())


def test_layout_reports_the_vertical_series_geometry(tmp_path):
    out = _probe(tmp_path)
    assert out["status"] == "ok"
    cover, data = out["layout"]
    assert cover["date_cols"] == [] and cover["marker_rows"] == []
    assert data["date_cols"] == [1] and data["date_col_counts"] == [12]
    assert (data["date_first_row"], data["date_last_row"]) == (3, 14)
    assert data["date_steps"] == [3] and data["date_monotonic"] is True
    assert (data["date_month_end"], data["date_month_start"], data["date_gaps"]) == (12, 0, 0)
    assert (data["marker_rows"], data["marker_cols"]) == ([11], [5])
    assert data["marker_date_index"] == [8]
    assert data["marker_merge_rows"] == [11, 14] and data["marker_merge_cols"] == [5, 5]
    assert (data["indicator_rows"], data["indicator_cols"]) == ([2], [2])
    assert (data["unit_rows"], data["unit_cols"]) == ([2, 2], [3, 4])
    assert data["source_rows"] == [16]
    assert data["numeric_cols"] == [2, 3, 4, 7]
    assert data["fill_change_rows"] == [11]
    assert data["text_rows"] == [1, 2, 5, 11, 16]


def test_layout_output_passes_the_guard_and_leaks_no_text_or_figure(tmp_path):
    line = emit(_probe(tmp_path))
    assert synth.SECRET_LABEL not in line and "987.65" not in line
    assert "Fictional" not in line and "Forecast" not in line and "2024" not in line
    assert json.loads(line)["status"] == "ok"


def test_marker_off_the_date_rows_has_no_index(tmp_path):
    wb = synth.vertical_book()
    ws = wb["Fictional data"]
    ws.unmerge_cells("E11:E14")
    ws["E11"] = None
    ws["H2"] = "Forecasts"
    out = _probe(tmp_path, wb)["layout"][1]
    assert out["marker_rows"] == [2] and out["marker_date_index"] == [-1]
    assert out["marker_merge_rows"] == [] and out["marker_merge_cols"] == []


def test_a_refused_archive_is_never_laid_out(tmp_path):
    path = tmp_path / "x.xlsx"
    path.write_bytes(b"not a zip")
    out = layout(path.read_bytes())
    assert out["status"] == "refused" and "layout" not in out


def test_drawing_counts_read_text_runs_only():
    xml = synth.drawing(
        "<a:p><a:r><a:t>Fictional ANZ outlook, published 5 November 2026</a:t></a:r></a:p>"
        "<a:p><a:r><a:t>Important notice: copyright applies</a:t></a:r></a:p>"
        "<a:p><a:r><a:t>Forecasts are shaded</a:t></a:r></a:p>"
        "<a:p><a:r><a:t>Source: Fictional Stats</a:t></a:r></a:p>"
        "<a:p><a:r><a:t>Interest rates are in per cent</a:t></a:r></a:p>"
    )
    assert drawing_counts([xml]) == {
        "drawing_text_runs": 5, "drawing_anz": 1, "drawing_notice": 1, "drawing_forecast": 1,
        "drawing_dates": 1, "drawing_sources": 1, "drawing_units": 1, "drawing_indicators": 0,
        "drawing_unit_hints": {"percent": 1, "annual": 0, "quarterly": 0, "seasonal": 0},
    }  # fmt: skip


@pytest.mark.parametrize(
    ("runs", "percent", "annual", "quarterly", "seasonal"),
    [
        (("%",), 1, 0, 0, 0),
        (("percent",), 1, 0, 0, 0),
        (("5percent",), 1, 0, 0, 0),
        (("5per cent",), 1, 0, 0, 0),
        (("supercent",), 0, 0, 0, 0),
        (("per ", "cent"), 1, 0, 0, 0),
        (("per", "centage"), 0, 0, 0, 0),
        (("p.a.",), 0, 1, 0, 0),
        (("5p.a.",), 0, 1, 0, 0),
        (("p. a.",), 0, 1, 0, 0),
        (("per annum",), 0, 1, 0, 0),
        (("% p.", "a."), 1, 1, 0, 0),
        (("annual q/q seasonally adjusted",), 0, 1, 1, 1),
    ],
)
def test_drawing_units_match_logical_paragraph_text(runs, percent, annual, quarterly, seasonal):
    text = "".join(f'<a:r><a:rPr b="1"/><a:t>{run}</a:t></a:r>' for run in runs)
    out = drawing_counts([synth.drawing(f"<a:p>{text}</a:p>")])
    assert out["drawing_text_runs"] == len(runs)
    assert out["drawing_units"] == percent
    assert out["drawing_unit_hints"] == {
        "percent": percent,
        "annual": annual,
        "quarterly": quarterly,
        "seasonal": seasonal,
    }


def test_drawing_paragraphs_shapes_and_line_breaks_are_boundaries():
    first = "<a:r><a:t>per </a:t></a:r>"
    second = "<a:r><a:t>cent</a:t></a:r>"
    out = drawing_counts(
        [
            synth.drawing(f"<a:p>{first}</a:p><a:p>{second}</a:p>"),
            synth.drawing(f"<a:p>{first}</a:p>", f"<a:p>{second}</a:p>"),
            synth.drawing(f"<a:p>{first}<a:br/>{second}</a:p>"),
        ]
    )
    assert out["drawing_text_runs"] == 6
    assert out["drawing_units"] == 0


def test_drawing_ignores_text_outside_drawingml_paragraph_runs():
    xml = synth.drawing("<a:p><xdr:t>percent</xdr:t><a:r><a:t>per</a:t></a:r></a:p>")
    out = drawing_counts([xml])
    assert out["drawing_text_runs"] == 1
    assert out["drawing_units"] == 0


def test_drawing_fields_keep_their_own_text_boundary():
    xml = synth.drawing(
        '<a:p><a:r><a:t>per </a:t></a:r><a:fld id="id"><a:t/></a:fld><a:r><a:t>cent</a:t></a:r></a:p>'
        '<a:p><a:fld id="id"><a:t>% p.a.</a:t></a:fld></a:p>'
    )
    out = drawing_counts([xml])
    assert out["drawing_text_runs"] == 4
    assert out["drawing_unit_hints"] == {"percent": 1, "annual": 1, "quarterly": 0, "seasonal": 0}


def test_print_headers_and_footers_detect_units_by_section(tmp_path):
    path = synth.save(synth.vertical_book(), tmp_path / "v.xlsx")
    page_text = (
        b'<headerFooter differentOddEven="1" differentFirst="1">'
        b"<oddHeader>per cent</oddHeader>"
        b"<evenHeader>&amp;Lper &amp;Rcent</evenHeader>"
        b"<firstHeader>&amp;Cper &amp;Acent</firstHeader>"
        b"<oddFooter>&amp;Lper &amp;Bcent&amp;B&amp;Cper annum</oddFooter>"
        b"<evenFooter>&amp;C&amp;&quot;percent,Regular&quot;q/q</evenFooter>"
        b"<firstFooter>&amp;Cp. a.&amp;R&amp;KFF0000%</firstFooter>"
        b"</headerFooter>"
    )
    sheet = synth.sheet1(path).replace(b"</worksheet>", page_text + b"</worksheet>")
    raw = synth.rewrite(path, {"xl/worksheets/sheet1.xml": sheet}).read_bytes()
    for out in (inspect(Path(), raw=raw), layout(raw)):
        assert out["status"] == "ok"
        assert out["header_unit_hints"] == {"percent": 1, "annual": 0, "quarterly": 0, "seasonal": 0}
        assert out["footer_unit_hints"] == {"percent": 2, "annual": 2, "quarterly": 1, "seasonal": 0}


def test_print_text_ignores_unreferenced_worksheets(tmp_path):
    path = synth.save(synth.vertical_book(), tmp_path / "v.xlsx")
    page_text = b"<headerFooter><oddHeader>per cent</oddHeader></headerFooter>"
    sheet = synth.sheet1(path).replace(b"</worksheet>", page_text + b"</worksheet>")
    synth.rewrite(path, {}, {"xl/worksheets/unreferenced.xml": sheet})
    out = inspect(path)
    assert out["status"] == "ok"
    assert out["header_unit_hints"] == {"percent": 0, "annual": 0, "quarterly": 0, "seasonal": 0}


@pytest.mark.parametrize("workbook_part", ["xl/workbook.xml", "xl/primary.xml"])
def test_print_text_uses_only_the_selected_workbook_part(tmp_path, workbook_part):
    path = synth.save(synth.vertical_book(), tmp_path / "v.xlsx")
    with zipfile.ZipFile(path) as archive:
        package = archive.read("[Content_Types].xml")
        root_rels = archive.read("_rels/.rels")
        book = archive.read("xl/workbook.xml")
        book_rels = archive.read("xl/_rels/workbook.xml.rels")

    valid_header = b"<headerFooter><oddHeader>per annum</oddHeader></headerFooter>"
    unused_header = b"<headerFooter><oddHeader>percent</oddHeader></headerFooter>"
    sheet = synth.sheet1(path)
    edits = {"xl/worksheets/sheet1.xml": sheet.replace(b"</worksheet>", valid_header + b"</worksheet>")}
    added = {
        "xl/unused.xml": book,
        "xl/_rels/unused.xml.rels": book_rels.replace(b"/xl/worksheets/sheet", b"/xl/worksheets/unused"),
        "xl/worksheets/unused1.xml": sheet.replace(b"</worksheet>", unused_header + b"</worksheet>"),
        "xl/worksheets/unused2.xml": sheet,
    }
    if workbook_part != "xl/workbook.xml":
        edits["[Content_Types].xml"] = package.replace(b"/xl/workbook.xml", b"/xl/primary.xml")
        edits["_rels/.rels"] = root_rels.replace(b"xl/workbook.xml", b"xl/primary.xml")
        edits["xl/workbook.xml"] = edits["xl/_rels/workbook.xml.rels"] = None
        added.update({workbook_part: book, "xl/_rels/primary.xml.rels": book_rels})
    synth.rewrite(path, edits, added)
    out = inspect(path)
    assert out["status"] == "ok"
    assert out["header_unit_hints"] == {"percent": 0, "annual": 1, "quarterly": 0, "seasonal": 0}


def test_cell_and_title_annual_basis_does_not_imply_percent(tmp_path):
    wb = synth.vertical_book()
    ws = wb.active
    ws.title = "Fictional rates p. a."
    ws["B2"] = "p.a."
    ws["B3"] = "per cent"
    ws["B4"] = "q/q"
    path = synth.save(wb, tmp_path / "v.xlsx")
    base = inspect(path)
    assert base["sheets"][0]["unit_hints"] == {"percent": 1, "annual": 1, "quarterly": 1, "seasonal": 0}
    sheet = layout(path.read_bytes())["layout"][0]
    assert (sheet["unit_rows"], sheet["unit_cols"]) == ([2, 3, 4], [2, 2, 2])
    assert sheet["title_units"] == 1
    assert sheet["title_unit_hints"] == {"percent": 0, "annual": 1, "quarterly": 0, "seasonal": 0}


def _noted(tmp_path, note: str, *, shade=True):
    wb = synth.vertical_book()
    ws = wb["Fictional data"]
    ws.unmerge_cells("E11:E14")
    ws["E11"] = None
    if not shade:
        from openpyxl.styles import PatternFill

        for row in range(3, 15):
            for col in (2, 3, 4):
                ws.cell(row=row, column=col).fill = PatternFill()
    ws["A18"] = note
    return _probe(tmp_path, wb)["layout"][1]


def test_a_note_below_the_data_names_the_first_forecast_quarter_by_index(tmp_path):
    out = _noted(tmp_path, "Forecasts from the September 2025 quarter onwards")
    assert out["note_rows"] == [16, 18] and out["note_forecast_rows"] == [18]
    assert out["note_period_index"] == [6] and out["note_period_count"] == [1]
    assert out["note_period_quarter_index"] == [6]
    assert out["date_months"] == [3, 6, 9, 12]


def test_quarter_tokens_match_the_row_inside_that_quarter(tmp_path):
    assert _noted(tmp_path, "Forecasts begin 2025Q4")["note_period_index"] == [7]
    assert _noted(tmp_path, "Forecast period starts Q1-26")["note_period_index"] == [8]


def test_a_note_without_a_period_has_no_index(tmp_path):
    out = _noted(tmp_path, "Shaded cells are forecasts", shade=False)
    assert out["note_forecast_rows"] == [18] and out["note_period_index"] == [-1]
    assert out["note_period_count"] == [0] and out["fill_change_rows"] == []


def test_a_note_naming_a_period_outside_the_dates_has_no_index(tmp_path):
    out = _noted(tmp_path, "Forecasts from March 2031")
    assert out["note_period_index"] == [-1] and out["note_period_count"] == [1]


def test_fill_and_font_changes_are_seen_in_any_column(tmp_path):
    from openpyxl.styles import Font

    wb = synth.vertical_book()
    ws = wb["Fictional data"]
    ws.cell(row=7, column=1).font = Font(bold=True)
    out = _probe(tmp_path, wb)["layout"][1]
    assert out["fill_change_rows"] == [11] and out["font_change_rows"] == [7, 8]


def test_source_word_rows_count_any_mention(tmp_path):
    out = _noted(tmp_path, "Data sources: Fictional Stats")
    assert out["note_source_rows"] == [16, 18] and out["source_rows"] == [16]


def test_note_wording_is_classified_by_fixed_patterns(tmp_path):
    assert _noted(tmp_path, "Forecasts from March 2026")["note_wording"] == [1]  # from / begin / start
    assert _noted(tmp_path, "Actual data to December 2025; forecasts thereafter")["note_wording"] == [2]  # to / until
    assert _noted(tmp_path, "Forecasts as at March 2026")["note_wording"] == [3]  # as at / as of / updated
    assert _noted(tmp_path, "Shaded cells are forecasts")["note_wording"] == [0]
    assert _noted(tmp_path, "Forecasts from March 2026, as at January 2026")["note_wording"] == [4]  # several


def test_style_changes_are_reported_per_column(tmp_path):
    from openpyxl.styles import Font

    wb = synth.vertical_book()
    ws = wb["Fictional data"]
    for row in range(11, 15):
        ws.cell(row=row, column=3).font = Font(italic=True)
    out = _probe(tmp_path, wb)["layout"][1]
    assert (out["col_font_change_cols"], out["col_font_change_rows"]) == ([3], [11])
    assert (out["col_fill_change_cols"], out["col_fill_change_rows"]) == ([2, 3, 4], [11, 11, 11])


def test_legend_style_words_are_coded(tmp_path):
    assert _noted(tmp_path, "Forecasts are shown in bold")["note_style"] == [1]
    assert _noted(tmp_path, "Italics denote forecasts")["note_style"] == [2]
    assert _noted(tmp_path, "Forecasts in red")["note_style"] == [3]
    assert _noted(tmp_path, "Shaded cells are forecasts")["note_style"] == [4]
    assert _noted(tmp_path, "Forecasts as at March 2026")["note_style"] == [0]
    assert _noted(tmp_path, "Forecasts in bold italics")["note_style"] == [5]


def test_font_change_attributes_are_a_bitmask(tmp_path):
    from copy import copy

    from openpyxl.styles.colors import Color

    wb = synth.vertical_book()
    ws = wb["Fictional data"]
    for row in range(11, 15):
        italic, red = (copy(ws.cell(row=row, column=c).font) for c in (3, 4))
        italic.i = True
        red.b, red.color = True, Color("FFFF0000")
        ws.cell(row=row, column=3).font, ws.cell(row=row, column=4).font = italic, red
    out = _probe(tmp_path, wb)["layout"][1]
    assert out["col_font_change_cols"] == [3, 4] and out["col_font_change_attr"] == [2, 1 | 16]


def test_sheet_title_units_and_indicators_are_counted(tmp_path):
    wb = synth.vertical_book()
    wb["Fictional data"].title = "OCR and rates (%)"
    out = _probe(tmp_path, wb)["layout"]
    assert out[1]["title_units"] == 1 and out[1]["title_indicators"] == 1
    assert out[0]["title_units"] == 0 and out[0]["title_indicators"] == 0
