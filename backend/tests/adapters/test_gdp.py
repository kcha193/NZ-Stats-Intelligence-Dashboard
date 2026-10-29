"""GDP adapter on the real March and June 2026 quarter releases (excerpts of the official CSV)."""

from __future__ import annotations

import csv
import dataclasses
import io

import pytest

from nzstats.adapters.gdp.adapter import (
    RECONCILE_TOLERANCE_PP,
    GdpAdapter,
    chart_quarter,
    check_page_charts,
)
from nzstats.adapters.gdp.series import KEYS
from nzstats.domain import ErrorClass, IngestError, ObsStatus, Point
from nzstats.sources.release_page import parse_release_page
from tests.conftest import fixture_bytes, fixture_text

BASE = "https://www.stats.govt.nz"
JUNE_LATEST = {
    "gdp.production.cv.sa": 71805,
    "gdp.production.cv.nsa": 70642,
    "gdp.expenditure.cv.sa": 74135,
    "gdp.expenditure.cv.nsa": 73906,
    "gdp.expenditure.cp.sa": 115798,
    "gdp.expenditure.cp.nsa": 114916,
    "gdp.per_capita.production.cv.sa": 13410,
    "gdp.per_capita.expenditure.cp.sa": 21626,
    "gdp.production.cv.sa.pct_qoq": 0.2,
    "gdp.production.cv.sa.pct_yoy": 2.6,
    "gdp.production.cv.nsa.pct_annual_avg": 1.7,
    "gdp.expenditure.cv.sa.pct_qoq": 0.4,
}


def page(month: str):
    return parse_release_page(fixture_text(f"gdp_{month}_page.html"), BASE)


def csv_bytes(month: str) -> bytes:
    return fixture_bytes(f"gdp_{month}.csv")


def parse(month: str, raw: bytes | None = None, pg=None):
    return GdpAdapter().parse(
        pg or page(month), {"gdp_csv": raw if raw is not None else csv_bytes(month)}
    )


def by_key(bundle):
    return {s.definition.key: {o.period: o for o in s.observations} for s in bundle.series}


def points(bundle, key):
    return {p: Point(p, o.value, o.status) for p, o in by_key(bundle)[key].items()}


def edit(raw: bytes, ref: str, period: str, column: str, value: str) -> bytes:
    rows = list(csv.reader(io.StringIO(raw.decode())))
    header = rows[0]
    hit = 0
    for row in rows[1:]:
        if row[0] == ref and row[1] == period:
            row[header.index(column)] = value
            hit += 1
    assert hit == 1, (ref, period)
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue().encode()


@pytest.mark.parametrize(("month", "latest"), [("2026-06", "2026-06"), ("2026-03", "2026-03")])
def test_parses_every_pinned_series_to_the_reference_quarter(month, latest):
    bundle = parse(month)
    assert [s.definition.key for s in bundle.series] == list(KEYS)
    for key, obs in by_key(bundle).items():
        assert max(obs) == latest, key
    assert bundle.layout_version == "gdp-csv-v1"


def test_june_latest_values_match_the_official_file():
    data = by_key(parse("2026-06"))
    assert {k: data[k]["2026-06"].value for k in JUNE_LATEST} == JUNE_LATEST


def test_leading_blanks_are_skipped_not_zero():
    data = by_key(parse("2026-06"))
    assert min(data["gdp.production.cv.sa.pct_qoq"]) == "1986-09"
    assert min(data["gdp.production.cv.sa.pct_yoy"]) == "1987-06"
    assert min(data["gdp.production.cv.sa"]) == "1987-06"
    assert all(o.value > 0 for o in data["gdp.production.cv.sa"].values())


def test_status_maps_revised_to_unknown():
    data = by_key(parse("2026-03"))
    statuses = {o.status for o in data["gdp.production.cv.sa"].values()}
    assert statuses == {ObsStatus.FINAL, ObsStatus.UNKNOWN}


def test_march_2026_quarterly_growth_was_first_published_at_0_8_then_revised_to_0_9():
    march = by_key(parse("2026-03"))["gdp.production.cv.sa.pct_qoq"]["2026-03"].value
    june = by_key(parse("2026-06"))["gdp.production.cv.sa.pct_qoq"]["2026-03"].value
    assert (march, june) == (0.8, 0.9)


def test_rejects_a_page_that_is_not_gdp():
    other = parse_release_page(fixture_text("cpi_2026-06_page.html"), BASE)
    with pytest.raises(IngestError, match="title"):
        parse("2026-06", pg=other)


def test_rejects_a_reference_quarter_after_publication():
    pg = page("2026-06")
    early = dataclasses.replace(pg, published_at=pg.published_at.replace(year=2026, month=5))
    with pytest.raises(IngestError) as e:
        parse("2026-06", pg=early)
    assert e.value.error_class is ErrorClass.VALIDATION_FAILED


def test_header_change_is_a_layout_change():
    raw = csv_bytes("2026-06").replace(b"Series_title_1", b"Series_title", 1)
    with pytest.raises(IngestError) as e:
        parse("2026-06", raw)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_metadata_change_on_a_pinned_series_fails():
    raw = edit(csv_bytes("2026-06"), "SNEQ.SG01RSC00B01", "2026.06", "UNITS", "Number")
    with pytest.raises(IngestError, match="metadata"):
        parse("2026-06", raw)


def test_magnitude_change_fails_even_on_the_inconsistent_per_capita_series():
    raw = edit(csv_bytes("2026-06"), "SNEQ.SG09NSC00B15NZ", "2026.06", "MAGNITUDE", "0")
    with pytest.raises(IngestError, match="metadata"):
        parse("2026-06", raw)


@pytest.mark.parametrize("period", ["2026.6", "2026-06", "26.06", "2026.07"])
def test_malformed_or_non_quarter_period_fails(period):
    raw = edit(csv_bytes("2026-06"), "SNEQ.SG01RSC00B01", "2026.06", "Period", period)
    with pytest.raises(IngestError):
        parse("2026-06", raw)


def test_duplicate_period_fails():
    raw = edit(csv_bytes("2026-06"), "SNEQ.SG01RSC00B01", "2026.03", "Period", "2026.06")
    with pytest.raises(IngestError, match="duplicate"):
        parse("2026-06", raw)


@pytest.mark.parametrize("value", ["abc", "nan", "inf"])
def test_non_numeric_value_fails(value):
    raw = edit(csv_bytes("2026-06"), "SNEQ.SG01RSC00B01", "2026.06", "Data_value", value)
    with pytest.raises(IngestError):
        parse("2026-06", raw)


def test_blank_inside_a_series_is_a_gap_and_fails():
    raw = edit(csv_bytes("2026-06"), "SNEQ.SG01RSC00B01", "2020.06", "Data_value", "")
    findings = GdpAdapter().validate(parse("2026-06", raw), reference_period="2026-06", previous={})
    assert any(f.rule == "continuity" and f.severity == "error" for f in findings)


def test_unknown_series_rows_are_ignored():
    raw = csv_bytes("2026-06") + (
        b"SNEQ.SG02RSC14P30A10E,2026.06,1,FINAL,Dollars,6,National Accounts - SNA 2008 - SNE,"
        b'"Series, other",Something else,,,,\n'
    )
    assert len(parse("2026-06", raw).series) == len(KEYS)


def test_oversized_file_is_refused():
    raw = csv_bytes("2026-06") + b"x" * (64 * 1024 * 1024)
    with pytest.raises(IngestError, match="size"):
        parse("2026-06", raw)


@pytest.mark.parametrize("month", ["2026-06", "2026-03"])
def test_real_release_validates_without_errors(month):
    findings = GdpAdapter().validate(parse(month), reference_period=month, previous={})
    assert [f for f in findings if f.severity == "error"] == []


def test_missing_required_series_fails_validation():
    bundle = parse("2026-06")
    trimmed = dataclasses.replace(bundle, series=bundle.series[1:])
    findings = GdpAdapter().validate(trimmed, reference_period="2026-06", previous={})
    assert any(f.rule == "coverage" and f.severity == "error" for f in findings)


def test_reference_period_mismatch_fails():
    findings = GdpAdapter().validate(parse("2026-06"), reference_period="2026-09", previous={})
    assert any(f.rule == "reference" and f.severity == "error" for f in findings)


def test_published_growth_that_does_not_reconcile_with_levels_fails():
    raw = edit(csv_bytes("2026-06"), "SNEQ.SG01RSC01B01PC", "2010.06", "Data_value", "1.0")
    findings = GdpAdapter().validate(parse("2026-06", raw), reference_period="2026-06", previous={})
    assert any(f.rule == "reconcile" and f.severity == "error" for f in findings)


def test_annual_average_is_reconciled_with_four_quarter_sums():
    raw = edit(csv_bytes("2026-06"), "SNEQ.SG01RAC01B01AC", "2010.06", "Data_value", "1.5")
    findings = GdpAdapter().validate(parse("2026-06", raw), reference_period="2026-06", previous={})
    assert any(f.rule == "reconcile" and "pct_annual_avg" in f.message for f in findings)


def test_tolerance_is_the_measured_one():
    assert RECONCILE_TOLERANCE_PP == 0.06


def test_revisions_against_the_previous_release_are_warnings_not_errors():
    june = parse("2026-06")
    previous = {s.definition.key: points(parse("2026-03"), s.definition.key) for s in june.series}
    findings = GdpAdapter().validate(june, reference_period="2026-06", previous=previous)
    assert [f for f in findings if f.severity == "error"] == []
    assert any(
        f.rule == "revisions" and "gdp.production.cv.sa.pct_qoq" in f.message for f in findings
    )


def test_lost_history_against_the_previous_release_fails():
    june = parse("2026-06")
    prior = points(parse("2026-03"), "gdp.production.cv.sa")
    prior["1980-03"] = Point("1980-03", 1.0, ObsStatus.FINAL)
    findings = GdpAdapter().validate(
        june, reference_period="2026-06", previous={"gdp.production.cv.sa": prior}
    )
    assert any(f.rule == "coverage" and f.severity == "error" for f in findings)


def test_large_growth_revision_is_flagged_for_review():
    june = parse("2026-06")
    prior = points(parse("2026-03"), "gdp.production.cv.sa.pct_qoq")
    prior["2025-12"] = Point("2025-12", 2.0, ObsStatus.FINAL)
    findings = GdpAdapter().validate(
        june, reference_period="2026-06", previous={"gdp.production.cv.sa.pct_qoq": prior}
    )
    assert any(f.rule == "large_revision" and f.severity == "warning" for f in findings)


@pytest.mark.parametrize(
    ("label", "quarter"),
    [
        ("Dec 2022", "2022-12"),
        ("Jun 2026", "2026-06"),
        ("Sept-22", "2022-09"),
        ("Mar-26", "2026-03"),
        ("Sep 2025", "2025-09"),
    ],
)
def test_chart_quarter_labels_in_both_published_formats(label, quarter):
    assert chart_quarter(label) == quarter


@pytest.mark.parametrize("label", ["2022 Dec", "December 2022", "Feb 2022", "Q4 2022", ""])
def test_unknown_chart_labels_fail_closed(label):
    with pytest.raises(IngestError):
        chart_quarter(label)


@pytest.mark.parametrize("month", ["2026-06", "2026-03"])
def test_page_charts_equal_the_published_series(month):
    data = {k: {p: o.value for p, o in v.items()} for k, v in by_key(parse(month)).items()}
    assert check_page_charts(page(month), data) == 15 * 2


def test_annual_growth_chart_is_annual_average_not_annual_change_of_the_quarter():
    data = {k: {p: o.value for p, o in v.items()} for k, v in by_key(parse("2026-06")).items()}
    data["gdp.production.cv.nsa.pct_annual_avg"] = data["gdp.production.cv.sa.pct_yoy"]
    with pytest.raises(IngestError, match="Annual growth"):
        check_page_charts(page("2026-06"), data)


def test_page_without_growth_charts_fails():
    pg = dataclasses.replace(page("2026-06"), charts=())
    with pytest.raises(IngestError, match="chart"):
        parse("2026-06", pg=pg)
