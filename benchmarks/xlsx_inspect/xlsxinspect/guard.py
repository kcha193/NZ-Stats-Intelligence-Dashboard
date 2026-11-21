"""The only way out of the inspector: a fixed key vocabulary, and values that cannot carry document text.

Accepted values: int, finite float, bool, None, a fixed code, lists of those, and the file's SHA-256 under `sha256`.
A sheet name, cell text, figure or error message is refused, so nothing from the workbook can leave by accident.
"""

from __future__ import annotations

import json
import math
import re

CODES = frozenset({"ok", "refused", "error", "visible", "hidden", "very_hidden"})
KEYS = frozenset(
    {
        "sha256", "status", "archive", "workbook", "sheets",
        # archive
        "bytes", "members", "unpacked_bytes", "max_ratio", "encrypted", "unsafe_path", "vba_part", "external_link_parts",
        "xml_declarations", "macro_content_type", "over_limit", "not_zip", "unreadable", "active_content_parts",
        "external_targets",
        # workbook
        "chartsheets", "defined_names", "has_created", "has_modified", "modified_ymd", "warnings",
        # sheet
        "state", "rows", "cols", "numeric", "text", "booleans", "dates", "percent_format", "literal_percent_format",
        "year_like_numbers", "merged_period_headers", "merged_period_header_cols",
        "formulas", "formulas_cached", "formulas_uncached", "formulas_external", "merged", "comments",
        "indicator_labels", "label_columns", "period_headers", "period_header_rows", "period_header_cols",
        "period_kinds", "forecast_markers", "actual_markers", "anz_mentions", "other_forecaster_mentions",
        "notice_cells", "unit_hints", "header_unit_hints", "footer_unit_hints",
        # layout probe (Phase 4AO): row/column indices and counts only
        "layout", "drawing", "date_cols", "date_col_counts", "date_first_row", "date_last_row", "date_steps",
        "date_monotonic", "date_month_end", "date_month_start", "date_gaps", "marker_rows", "marker_cols",
        "marker_date_index", "marker_merge_rows", "marker_merge_cols", "indicator_rows", "indicator_cols", "unit_rows",
        "unit_cols", "source_rows", "numeric_cols", "text_rows", "merge_min_rows", "merge_min_cols", "merge_max_rows",
        "merge_max_cols", "fill_change_rows", "drawing_text_runs", "drawing_anz", "drawing_notice", "drawing_forecast",
        "drawing_dates", "drawing_sources", "font_change_rows", "note_rows", "note_source_rows",
        "note_forecast_rows", "note_period_index", "note_period_quarter_index", "note_period_count", "date_months",
        "note_wording", "col_fill_change_cols", "col_fill_change_rows", "col_font_change_cols", "col_font_change_rows",
        "col_font_change_attr", "note_style", "title_units", "title_unit_hints", "title_indicators", "drawing_units",
        "drawing_indicators", "drawing_unit_hints",
        # nested vocabularies
        "ocr", "cpi_inflation", "gdp", "unemployment",
        "quarter", "month_end", "year_to", "calendar",
        "percent", "annual", "quarterly", "seasonal",
    }
)  # fmt: skip
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _check(value: object, path: str, key: str | None = None) -> None:
    if isinstance(value, dict):
        for k, inner in value.items():
            if not isinstance(k, str) or k not in KEYS:
                raise ValueError(f"key refused at {path}")
            _check(inner, f"{path}/{k}", k)
    elif isinstance(value, list):
        for inner in value:
            if isinstance(inner, list):
                raise TypeError(f"nested list refused at {path}")
            _check(inner, f"{path}[]")
    elif isinstance(value, bool) or value is None or isinstance(value, int):
        return
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite value at {path}")
    elif isinstance(value, str):
        if key == "sha256" and _SHA.match(value):
            return
        if key != "sha256" and value in CODES:
            return
        raise ValueError(f"string value refused at {path}")
    else:
        raise ValueError(f"type refused at {path}")


def emit(data: dict) -> str:
    _check(data, "")
    return json.dumps(data, sort_keys=True)
