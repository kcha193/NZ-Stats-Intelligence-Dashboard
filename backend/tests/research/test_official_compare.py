"""Comparing a figure a document reports with the official series, as its author could have seen it (Phase 4I).

The observations are real excerpts from the official Stats NZ files the dashboard stores: real GDP growth for the
March 2026 quarter as first published (0.8) and as revised in the June 2026 quarter release (0.9), the CPI
all-groups index, and unadjusted monthly net migration.
"""

from datetime import date

import pytest

from nzstats.clock import from_utc_iso
from nzstats.research.contract import Adjustment
from nzstats.research.official_compare import compare_figure
from nzstats.store.db import transaction
from nzstats.store.repo import create_vintage, reactivate_bundle

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
        for series, release, points in VINTAGES:
            row = conn.execute(
                "SELECT r.id AS release_id, s.id AS series_id, r.published_at"
                " FROM release r, series s WHERE r.release_key = ? AND s.key = ?",
                (release, series),
            ).fetchone()
            vid = create_vintage(conn, row["release_id"], row["series_id"],
                                 from_utc_iso(row["published_at"]), "release_files", "v1",
                                 f"{row['release_id']:064d}")  # fmt: skip
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


def _add_gdp_correction(official):
    """A SYNTHETIC same-release correction, created through the real activation bookkeeping."""
    original = official.execute(
        "SELECT v.release_id, v.series_id, v.bundle_sha256 FROM vintage v JOIN series s ON s.id=v.series_id "
        "JOIN release r ON r.id=v.release_id WHERE s.key=? AND r.release_key=?",
        ("gdp.production.cv.sa.pct_qoq", "gross-domestic-product:march 2026 quarter"),
    ).fetchone()
    vid = create_vintage(official, original["release_id"], original["series_id"],
                         from_utc_iso("2026-09-01T00:00:00Z"), "release_files", "v1", "f" * 64)  # fmt: skip
    official.execute(
        "INSERT INTO observation(vintage_id, period, value, status) VALUES (?, '2026-03', 0.9, 'final')",
        (vid,),
    )
    return original


def test_later_correction_is_not_visible_before_its_capture(official):
    _add_gdp_correction(official)
    early = compare(
        official, "gdp.production.cv.sa.pct_qoq", "2026-03", "level", 0.8, SA, date(2026, 8, 1)
    )
    assert (early.status, early.official) == ("match", 0.8)
    late = compare(
        official, "gdp.production.cv.sa.pct_qoq", "2026-03", "level", 0.9, SA, date(2026, 9, 10)
    )
    assert (late.status, late.official) == ("match", 0.9)


@pytest.mark.parametrize("restore_correction", [False, True])
@pytest.mark.parametrize(
    ("on", "status", "value"),
    [
        (date(2026, 8, 1), "match", 0.8),
        (date(2026, 9, 10), "not_comparable", None),
        (date(2026, 9, 15), "not_comparable", None),
    ],
)
def test_a_reverted_bundles_unknown_activation_date_cannot_rewrite_history(
    official, restore_correction, on, status, value
):
    original = _add_gdp_correction(official)
    reactivate_bundle(official, original["release_id"], original["bundle_sha256"])
    if restore_correction:
        reactivate_bundle(official, original["release_id"], "f" * 64)
    # A -> B -> A (or back to B) stores no reactivation date. Only the interval before B's
    # initial capture is known; current activation must not be projected onto later document dates.
    result = compare(official, "gdp.production.cv.sa.pct_qoq", "2026-03", "level", 0.8, SA, on)
    assert (result.status, result.official) == (status, value)
    if status == "not_comparable":
        assert "activation" in result.reason


def test_a_newer_unambiguous_release_supersedes_an_older_reverted_release(official):
    original = _add_gdp_correction(official)
    reactivate_bundle(official, original["release_id"], original["bundle_sha256"])
    result = compare(official, "gdp.production.cv.sa.pct_qoq", "2026-03", "level", 0.9,
                     SA, date(2026, 10, 15))  # fmt: skip
    assert (result.status, result.official, result.released_on) == ("match", 0.9, "2026-09-17")


@pytest.mark.parametrize("baseline", [None, 0.0])
def test_missing_or_zero_baseline_in_the_selected_vintage_does_not_use_an_older_one(
    official, baseline
):
    """SYNTHETIC newer index and unavailable denominator: an older 4.1% is no substitute."""
    latest = official.execute(
        "SELECT v.id FROM vintage v JOIN series s ON s.id=v.series_id "
        "JOIN release r ON r.id=v.release_id WHERE s.key='cpi.index.nsa.all_groups' "
        "AND r.release_key='consumers-price-index:september 2026 quarter'"
    ).fetchone()[0]
    official.execute(
        "UPDATE observation SET value=1400 WHERE vintage_id=? AND period='2026-06'", (latest,)
    )
    if baseline is None:
        official.execute(
            "DELETE FROM observation WHERE vintage_id=? AND period='2025-06'", (latest,)
        )
    else:
        official.execute(
            "UPDATE observation SET value=? WHERE vintage_id=? AND period='2025-06'",
            (baseline, latest),
        )
    early = compare(official, "cpi.index.nsa.all_groups", "2026-06", "change_on_year", 4.1,
                    NSA, date(2026, 10, 15))  # fmt: skip
    assert (early.status, early.official) == ("match", 4.1)
    late = compare(official, "cpi.index.nsa.all_groups", "2026-06", "change_on_year", 4.1,
                   NSA, date(2026, 10, 28))  # fmt: skip
    assert (late.status, late.official) == ("no_official_value", None)


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


def test_comparison_uses_the_selected_vintages_definition(official):
    official.execute(
        "UPDATE series SET seasonal_adjustment='trend', frequency='quarterly' WHERE key='mig.m.net'"
    )
    good = compare(
        official, "mig.m.net", "2026-08", "change_on_previous", -57.5, NSA, date(2026, 10, 15)
    )
    assert (good.status, good.official) == ("match", -57.5)
    wrong = compare(
        official, "mig.m.net", "2026-08", "level", 2193, Adjustment.TREND, date(2026, 10, 15)
    )
    assert wrong.status == "not_comparable"


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
