"""Masked layout probe (Phase 4AO): cell coordinates and counts only, on SYNTHETIC workbooks."""

import json

from tests import synth
from xlsxinspect.guard import emit
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
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?><xdr:wsDr xmlns:xdr="x" xmlns:a="a"><xdr:sp><xdr:txBody>'
        b"<a:p><a:r><a:t>Fictional ANZ outlook, published 5 November 2026</a:t></a:r></a:p>"
        b"<a:p><a:r><a:t>Important notice: copyright applies</a:t></a:r></a:p>"
        b"<a:p><a:r><a:t>Forecasts are shaded</a:t></a:r></a:p>"
        b"<a:p><a:r><a:t>Source: Fictional Stats</a:t></a:r></a:p>"
        b"<a:p><a:r><a:t>Interest rates are in per cent</a:t></a:r></a:p>"
        b"</xdr:txBody></xdr:sp></xdr:wsDr>"
    )
    assert drawing_counts([xml]) == {
        "drawing_text_runs": 5, "drawing_anz": 1, "drawing_notice": 1, "drawing_forecast": 1,
        "drawing_dates": 1, "drawing_sources": 1, "drawing_units": 1, "drawing_indicators": 0,
    }  # fmt: skip


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
