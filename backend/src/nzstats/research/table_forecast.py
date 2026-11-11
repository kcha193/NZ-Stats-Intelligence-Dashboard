"""Table rows as forecasts (Phase 4AF, interpreter `tables-1`): fixed phrase maps, no guessing.

`table_grid` says where cells are; this module says what a row and a column *mean*, by fixed rules only, and refuses
(with a fixed code, never text) whatever it cannot read exactly. It never fills a missing figure, converts a unit,
reads an actual as a forecast, or repairs a period. The row label is kept as printed; the adjustment wording in it is
for `bank_forecast` to derive, as it does for model-extracted claims. Every figure keeps its printed text and the cell
it came from. All text is untrusted data.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from nzstats.research.compare import _ANNUAL, _ANNUAL_AVERAGE, _QUARTERLY, _THROUGH_YEAR, horizon_of
from nzstats.research.table_grid import Cell, Column, GridTable, Rejection
from nzstats.research.table_parse import (
    Period,
    column_kind,
    parse_value,
    period_of,
    unit_of_text,
)

INTERPRETER_VERSION = "tables-1"

_NOT_A_LEVEL = re.compile(
    r"%\s*of\s*gdp|per ?cent of gdp|share of gdp|\bto gdp\b|/\s*gdp", re.IGNORECASE
)
_INDICATORS: dict[str, re.Pattern[str]] = {
    "ocr": re.compile(r"\bocr\b|official cash rate", re.IGNORECASE),
    "cpi_inflation": re.compile(r"\bcpi\b|consumers?'? price|\binflation\b", re.IGNORECASE),
    "gdp": re.compile(r"\bgdp\b|gross domestic product", re.IGNORECASE),
    "unemployment": re.compile(r"unemployment", re.IGNORECASE),
}
_RATE_INDICATORS = frozenset({"ocr", "unemployment"})
_SOURCE = re.compile(r"^sources?\s*[:\-]\s*(.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class TableForecast:
    table: int
    page: int
    row: int
    col: int
    indicator: str
    label: str
    period_text: str
    horizon: str
    kind: Literal["forecast", "actual"]
    unit: str
    raw_text: str
    value: Decimal | None
    missing: bool
    author_role: Literal["author", "third_party"]
    footnote: str | None
    evidence: dict[str, Any]


def _indicator(label: str) -> set[str]:
    text = _NOT_A_LEVEL.sub(" ", label)
    return {name for name, pattern in _INDICATORS.items() if pattern.search(text)}


def _author_role(t: GridTable, publisher_names: Sequence[str]) -> Literal["author", "third_party"]:
    """The bank unless a source line exists and does not name it."""
    for note in t.notes:
        if (m := _SOURCE.match(note.strip())) and not any(
            name.lower() in m[1].lower() for name in publisher_names
        ):
            return "third_party"
    return "author"


def _footnotes(t: GridTable) -> dict[str, str]:
    return {
        n[0]: n
        for n in (note.strip() for note in t.notes)
        if n and not _SOURCE.match(n) and n[0] in "*†‡¹²³⁴⁵⁶⁷⁸⁹"
    }


def _columns(t: GridTable, out: list[Rejection]) -> dict[int, tuple[Column, Period, str]]:
    """Value columns whose kind and period are stated and unique: column index -> (column, period, kind)."""
    ok: dict[int, tuple[Column, Period, str]] = {}
    for col in t.columns:
        if col.role != "value":
            continue
        kind = column_kind(col.headers)
        if kind == "unknown":
            out.append(
                Rejection("actual_or_forecast_unstated", t.page_start, t.index, None, col.index)
            )
            continue
        period, code = period_of(col.headers)
        if period is None:
            out.append(Rejection(code or "unparsed_period", t.page_start, t.index, None, col.index))
            continue
        ok[col.index] = (col, period, kind)
    seen: dict[Period, list[int]] = {}
    for index, (_, period, _) in ok.items():
        seen.setdefault(period, []).append(index)
    for indices in seen.values():
        if len(indices) > 1:
            for index in indices:
                del ok[index]
                out.append(Rejection("contradictory_period", t.page_start, t.index, None, index))
    return ok


def _horizon(period: Period, label: str, indicator: str) -> tuple[str | None, str | None]:
    annual = bool(
        _ANNUAL.search(label) or _THROUGH_YEAR.search(label) or _ANNUAL_AVERAGE.search(label)
    )
    quarterly = bool(_QUARTERLY.search(label))
    if annual and quarterly:
        return None, "period_basis_unstated"
    if period.kind == "calendar":
        text = period.render("calendar")
    elif period.kind == "quarter":
        text = None if annual else period.render("quarter")
    elif period.kind == "year_to":
        text = None if quarterly else period.render("year_to")
    elif annual:
        text = period.render("year_to")
    elif quarterly:
        text = period.render("quarter")
    elif indicator in _RATE_INDICATORS:
        text = period.render("quarter") or period.render("month")
    else:
        return None, "period_basis_unstated"
    if text is None:
        return None, "contradictory_period"
    return (text, None) if horizon_of(text) else (None, "unparsed_period")


def interpret(
    tables: Sequence[GridTable], *, publisher_names: Sequence[str]
) -> tuple[tuple[TableForecast, ...], tuple[Rejection, ...]]:
    forecasts: list[TableForecast] = []
    rejections: list[Rejection] = []
    for t in tables:
        columns = _columns(t, rejections)
        role = _author_role(t, publisher_names)
        notes = _footnotes(t)
        units = {c.index for c in t.columns if c.role == "unit"}
        for row in t.body_rows:
            label_cell = row[0]
            at = (label_cell.page, t.index, label_cell.row)
            found = _indicator(label_cell.text)
            if len(found) != 1:
                code = "ambiguous_indicator" if found else "unmapped_row"
                rejections.append(Rejection(code, *at))
                continue
            (indicator,) = found
            unit_text = " ".join(c.text for c in row[1:] if c.col in units)
            unit, code = unit_of_text(label_cell.text, t.caption or "", unit_text)
            if unit is None:
                rejections.append(Rejection(code or "unit_unstated", *at))
                continue
            cells = {c.col: c for c in row[1:]}
            for index, (column, period, kind) in columns.items():
                horizon, code = _horizon(period, label_cell.text, indicator)
                if horizon is None:
                    rejections.append(Rejection(code or "unparsed_period", *at, index))
                    continue
                cell = cells.get(index)
                parsed = parse_value(cell.text if cell else "")
                if parsed.kind == "reject" or (parsed.footnote and parsed.footnote in notes):
                    code = parsed.code or "footnote_unresolved"
                    rejections.append(
                        Rejection(code, cell.page if cell else at[0], t.index, at[2], index)
                    )
                    continue
                forecasts.append(
                    _forecast(
                        t,
                        label_cell,
                        column,
                        cell,
                        index,
                        indicator,
                        horizon,
                        kind,
                        unit,
                        parsed,
                        role,
                    )
                )
    return tuple(forecasts), tuple(rejections)


def _forecast(
    t,
    label_cell: Cell,
    column: Column,
    cell: Cell | None,
    index,
    indicator,
    horizon,
    kind,
    unit,
    parsed,
    role,
):
    page = cell.page if cell else label_cell.page
    bbox = [cell.x0, cell.x1, cell.y] if cell else None
    return TableForecast(
        table=t.index,
        page=page,
        row=label_cell.row,
        col=index,
        indicator=indicator,
        label=label_cell.text,
        period_text=column.headers[-1],
        horizon=horizon,
        kind=kind,  # type: ignore[arg-type]
        unit=unit,
        raw_text=parsed.raw if cell else "",
        value=parsed.value,
        missing=parsed.kind == "missing",
        author_role=role,
        footnote=parsed.footnote,
        evidence={
            "page": page,
            "table": t.index,
            "row": label_cell.row,
            "col": index,
            "bbox": bbox,
            "cell_text": cell.text if cell else "",
            "absent": cell is None,
            "row_label": label_cell.text,
            "header_texts": list(column.headers),
            "caption": t.caption,
        },
    )
