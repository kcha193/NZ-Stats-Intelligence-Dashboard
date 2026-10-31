"""Comparing a figure a document reports with the official series, as its author could have seen it (Phase 4I).

The observations are real excerpts from the official Stats NZ files the dashboard stores: real GDP growth for the
March 2026 quarter as first published (0.8) and as revised in the June 2026 quarter release (0.9), the CPI
all-groups index, and unadjusted monthly net migration.
"""

from datetime import date

import pytest

from nzstats.research.contract import Adjustment
from nzstats.research.official_compare import compare_figure
from nzstats.store.db import transaction

RELEASES = {
    # release key: (published at, UTC)
    "gross-domestic-product:march 2026 quarter": "2026-06-17T22:45:00Z",
    "gross-domestic-product:june 2026 quarter": "2026-09-16T22:45:00Z",
    "consumers-price-index:june 2026 quarter": "2026-07-20T22:45:00Z",
    "consumers-price-index:september 2026 quarter": "2026-10-21T21:45:00Z",
    "international-migration:august 2026": "2026-10-13T21:45:00Z",
    "labour-market-statistics:june 2026 quarter": "2026-08-04T22:45:00Z",
}
SERIES = {
    "gdp.production.cv.sa.pct_qoq": ("percent", "quarterly", "seasonally_adjusted"),
    "cpi.index.nsa.all_groups": ("index", "quarterly", "none"),
    "mig.m.net": ("people", "monthly", "none"),
    "mig.ry.net": ("people", "rolling_annual", "none"),
    "lci.all_wages.pct_yoy": ("percent", "quarterly", "none"),
}
VINTAGES = [
    ("gdp.production.cv.sa.pct_qoq", "gross-domestic-product:march 2026 quarter",
     {"2025-12": 0.5, "2026-03": 0.8}),
    ("gdp.production.cv.sa.pct_qoq", "gross-domestic-product:june 2026 quarter",
     {"2025-12": 0.5, "2026-03": 0.9, "2026-06": 0.2}),
    ("cpi.index.nsa.all_groups", "consumers-price-index:june 2026 quarter",
     {"2025-06": 1306.0, "2025-09": 1319.0, "2026-06": 1359.0}),
    ("cpi.index.nsa.all_groups", "consumers-price-index:september 2026 quarter",
     {"2025-06": 1306.0, "2025-09": 1319.0, "2026-06": 1359.0, "2026-09": 1368.0}),
    ("mig.m.net", "international-migration:august 2026", {"2026-07": 5154.0, "2026-08": 2193.0}),
    ("mig.ry.net", "international-migration:august 2026", {"2026-08": 20503.0}),
    ("lci.all_wages.pct_yoy", "labour-market-statistics:june 2026 quarter", {"2026-03": 2.0, "2026-06": 2.0}),
]  # fmt: skip


@pytest.fixture()
def official(conn):
    with transaction(conn):
        for key, published in RELEASES.items():
            conn.execute(
                "INSERT INTO release(release_key, series_slug, title, published_at, status, first_seen_at,"
                " updated_at) VALUES (?, ?, ?, ?, 'published', ?, ?)",
                (key, key.split(":")[0], key, published, published, published),
            )
        for key, (unit, frequency, adjustment) in SERIES.items():
            conn.execute(
                "INSERT INTO series(key, name, unit, frequency, seasonal_adjustment, definition,"
                " definition_id, category) VALUES (?, ?, ?, ?, ?, '', ?, 'test')",
                (key, key, unit, frequency, adjustment, key),
            )
        for n, (series, release, points) in enumerate(VINTAGES):
            vid = conn.execute(
                "INSERT INTO vintage(release_id, series_id, captured_at, source_kind, layout_version,"
                " bundle_sha256, activation) SELECT r.id, s.id, r.published_at, 'release_files', 'v1', ?, 1"
                " FROM release r, series s WHERE r.release_key = ? AND s.key = ?",
                (f"{n:064d}", release, series),
            ).lastrowid
            conn.executemany(
                "INSERT INTO observation(vintage_id, period, value, status) VALUES (?, ?, ?, 'final')",
                [(vid, period, value) for period, value in points.items()],
            )
    return conn


def compare(conn, series, period, measure, value, adjustment, on):
    return compare_figure(conn, series=series, period=period, measure=measure, document_value=value,
                          adjustment=adjustment, published_on=on)  # fmt: skip


SA, NSA, UNSTATED = Adjustment.SEASONALLY_ADJUSTED, Adjustment.UNADJUSTED, Adjustment.NOT_STATED


@pytest.mark.parametrize(
    ("on", "expected", "status"),
    [(date(2026, 8, 1), 0.8, "differs"),  # only the March quarter release existed: first published 0.8
     (date(2026, 10, 15), 0.9, "match")],  # the June quarter release had revised it to 0.9
)  # fmt: skip
def test_a_revised_figure_is_compared_with_the_release_published_by_the_document_date(
    official, on, expected, status
):
    r = compare(official, "gdp.production.cv.sa.pct_qoq", "2026-03", "level", 0.9, SA, on)
    assert (r.status, r.official) == (status, expected)


def test_no_look_ahead_to_a_release_after_the_document(official):
    early = compare(official, "cpi.index.nsa.all_groups", "2026-09", "change_on_year", 3.7, UNSTATED,
                    date(2026, 10, 15))  # fmt: skip
    assert early.status == "no_official_value" and early.official is None
    late = compare(official, "cpi.index.nsa.all_groups", "2026-09", "change_on_year", 3.7, UNSTATED,
                   date(2026, 10, 28))  # fmt: skip
    assert (late.status, late.official, late.released_on) == ("match", 3.7, "2026-10-22")


def test_an_annual_change_from_index_numbers_is_rounded_half_away_from_zero(official):
    r = compare(official, "cpi.index.nsa.all_groups", "2026-06", "change_on_year", 4.1, UNSTATED,
                date(2026, 10, 15))  # fmt: skip
    assert (r.status, r.official) == ("match", 4.1)  # 1359 / 1306 = +4.06%


def test_a_monthly_figure_with_no_stated_adjustment_basis_is_not_compared(official):
    """Treasury's monthly net migration (3,190) does not say whether it is seasonally adjusted."""
    r = compare(official, "mig.m.net", "2026-07", "level", 3190, UNSTATED, date(2026, 10, 15))
    assert r.status == "not_comparable" and r.official is None
    assert "adjustment basis" in r.reason and "more than one basis" in r.reason


def test_a_stated_basis_that_differs_from_the_series_is_not_compared(official):
    r = compare(official, "mig.m.net", "2026-07", "level", 3190, SA, date(2026, 10, 15))
    assert r.status == "not_comparable" and "seasonally adjusted" in r.reason
    same_basis = compare(official, "mig.m.net", "2026-07", "level", 3190, NSA, date(2026, 10, 15))
    assert (same_basis.status, same_basis.official) == (
        "differs",
        5150.0,
    )  # 5,154 to the nearest 10


@pytest.mark.parametrize("value", [5150, 5200, 5154])
def test_the_official_value_is_rounded_to_the_precision_the_document_states(official, value):
    r = compare(official, "mig.m.net", "2026-07", "level", value, NSA, date(2026, 10, 15))
    assert (r.status, r.official) == ("match", float(value))


def test_an_unknown_series_has_no_official_value(official):
    r = compare(official, "no.such.series", "2026-07", "level", 1.0, NSA, date(2026, 10, 15))
    assert r.status == "no_official_value"


def test_reported_decimal_precision_is_preserved(official):
    result = compare_figure(official, series="gdp.production.cv.sa.pct_qoq", period="2026-03",
                            measure="level", document_value="1.0", adjustment=SA,
                            published_on=date(2026, 8, 1))  # fmt: skip
    assert (result.status, result.official) == ("differs", 0.8)


def test_a_series_that_already_holds_an_annual_change_is_compared_as_one(official):
    """LCI salary and wage rates, annual: the stored value is the change; no basis stated is conventional."""
    r = compare(
        official, "lci.all_wages.pct_yoy", "2026-06", "annual", 2.0, UNSTATED, date(2026, 10, 15)
    )
    assert (r.status, r.official) == ("match", 2.0)
    refused = compare(
        official, "lci.all_wages.pct_yoy", "2026-06", "annual", 2.0, SA, date(2026, 10, 15)
    )
    assert refused.status == "not_comparable"


def test_a_rolling_year_total_with_no_stated_basis_is_compared_at_the_documents_rounding(official):
    r = compare(official, "mig.ry.net", "2026-08", "level", 20500, UNSTATED, date(2026, 10, 15))
    assert (r.status, r.official) == ("match", 20500.0)  # 20,503 to the nearest hundred
