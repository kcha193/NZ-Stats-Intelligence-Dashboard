"""Phase 4AG: what one genuine-looking report may and may not become in the bank analytics (SYNTHETIC FIXTURE text only).

One bank's report is not a consensus; a missing period is never filled; a financial year is never a calendar year; every
accepted figure keeps the cell it was read from.
"""

from datetime import date

import pytest

from nzstats.research.bank_analytics import bank_comparison, bank_consensus
from nzstats.research.bank_view import bank_view
from nzstats.research.compare import horizon_of
from nzstats.sources.artifacts import ArtifactStore

from .pdf_stream_support import raw_pdf, row
from .test_table_forecast import line, page
from .test_table_view import ADAPTERS, auto, stored, table_pdf


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


def rows():
    return [
        *line(686, "OCR (%)", ["4.25", "3.75", "3.25", "3.00"]),
        *line(672, "Annual CPI inflation (%)", ["4.0", "3.1", "2.6", "2.2"]),
    ]


def test_one_banks_report_is_never_a_consensus(conn, artifacts):
    registry, _ = stored(conn, artifacts, table_pdf([page(rows())]))
    view = bank_view(conn, registry, auto(), ADAPTERS, drafts=[])
    assert view.forecasts  # the figures are there
    groups = bank_consensus(view).groups
    assert groups
    assert {g.title for g in groups} == {"Insufficient banks"}
    assert all(g.n == 1 for g in groups)


def test_a_period_the_report_does_not_print_is_not_invented(conn, artifacts):
    registry, _ = stored(conn, artifacts, table_pdf([page(rows())]))
    view = bank_view(conn, registry, auto(), ADAPTERS, drafts=[])
    horizons = {f.forecast.horizon for f in view.forecasts if f.forecast.indicator == "ocr"}
    assert horizons == {
        "June 2026 quarter",
        "September 2026 quarter",
    }  # the two forecast columns, nothing after them


def test_every_accepted_figure_keeps_the_cell_it_was_read_from(conn, artifacts):
    registry, _ = stored(conn, artifacts, table_pdf([page(rows())]))
    view = bank_view(conn, registry, auto(), ADAPTERS, drafts=[])
    for f in view.forecasts:
        (e,) = f.forecast.evidence
        assert e.page == 1 and str(f.raw_value) in e.quote and f.claim_path.startswith("tables[")


def test_a_printed_value_is_kept_as_printed_not_recomputed(conn, artifacts):
    body = table_pdf([page(line(686, "OCR (%)", ["4.25", "3.75", "3.30", "3.00"]))])
    registry, _ = stored(conn, artifacts, body)
    view = bank_view(conn, registry, auto(), ADAPTERS, drafts=[])
    june = next(f for f in view.forecasts if f.forecast.horizon == "June 2026 quarter")
    assert (june.raw_value, june.forecast.value) == (3.3, 3.3)


def test_a_financial_year_column_is_not_a_calendar_year(conn, artifacts):
    groups = [(250, 714, "Forecast")]
    body = table_pdf(
        [
            page(
                line(686, "Annual CPI inflation (%)", ["2.1", "2.4", "2.0", "1.9"]),
                head=["Mar-26 yr", "Jun-26 yr", "Sep-26 yr", "Dec-26 yr"],
                groups=groups,
            )
        ]
    )
    registry, _ = stored(conn, artifacts, body)
    view = bank_view(conn, registry, auto(), ADAPTERS, drafts=[])
    kinds = {f.forecast.horizon: horizon_of(f.forecast.horizon) for f in view.forecasts}
    assert kinds and all(
        h.startswith("year to ") for h in kinds
    )  # through-the-year to a month end, not a calendar year
    assert not any(h.isdigit() for h in kinds)


def test_real_style_drawing_gives_the_same_comparison_as_cell_drawing(conn, artifacts):
    """The same page drawn one BT..ET per row, with positioned cells, is read to the same figures."""
    items = page(rows())
    by_y: dict[float, list[tuple[float, str]]] = {}
    for x, y, text in items:
        by_y.setdefault(y, []).append((x, text))
    real = raw_pdf(["\n".join(row(y, sorted(cells)) for y, cells in by_y.items())])
    registry, _ = stored(conn, artifacts, real, published=date(2026, 10, 1))
    view = bank_view(conn, registry, auto(), ADAPTERS, drafts=[])
    got = {(f.forecast.indicator, f.forecast.horizon): f.forecast.value for f in view.forecasts}
    assert (
        got[("ocr", "June 2026 quarter")] == 3.25
        and got[("cpi_inflation", "year to June 2026")] == 2.6
    )
    ((_, comparison),) = [x for x in bank_comparison(view) if x[1].groups][:1]
    assert comparison.groups
