"""Labour market adapter on the real March (revised) and June 2026 quarter releases (zip excerpts)."""

from __future__ import annotations

import csv
import dataclasses
import io
import zipfile

import pytest

from nzstats.adapters.labour import adapter as labour
from nzstats.adapters.labour.adapter import (
    IDENTITY_LEVEL_TOLERANCE,
    IDENTITY_RATE_TOLERANCE_PP,
    LCI_TOLERANCE_PP,
    LabourAdapter,
    headline_rates,
)
from nzstats.adapters.labour.series import KEYS
from nzstats.domain import ErrorClass, IngestError, ObsStatus, Point
from nzstats.sources.release_page import parse_release_page
from tests.conftest import fixture_bytes, fixture_text

BASE = "https://www.stats.govt.nz"
JUNE_LATEST = {
    "hlfs.rate.unemployment.sa": 5.6,
    "hlfs.rate.employment.sa": 66.7,
    "hlfs.rate.participation.sa": 70.7,
    "hlfs.rate.underutilisation.sa": 13.8,
    "hlfs.level.employed.sa": 2905,
    "hlfs.level.unemployed.sa": 171,
    "hlfs.level.labour_force.sa": 3076,
    "hlfs.level.working_age_population.sa": 4353,
    "lci.all_wages.index": 1459,
    "lci.all_wages.pct_qoq": 0.6,
    "lci.all_wages.pct_yoy": 2.0,
}


def page(month: str):
    return parse_release_page(fixture_text(f"labour_{month}_page.html"), BASE)


def parse(month: str, raw: bytes | None = None, pg=None):
    data = raw if raw is not None else fixture_bytes(f"labour_{month}.zip")
    return LabourAdapter().parse(pg or page(month), {"labour_zip": data})


def by_key(bundle):
    return {s.definition.key: {o.period: o for o in s.observations} for s in bundle.series}


def points(bundle, key):
    return {p: Point(p, o.value, o.status) for p, o in by_key(bundle)[key].items()}


def rezip(month: str, change) -> bytes:
    """The fixture zip with `change(name, text) -> text | None` applied to each member (None drops it)."""
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(fixture_bytes(f"labour_{month}.zip"))) as src,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            text = src.read(info).decode("utf-8")
            changed = text if info.is_dir() else change(info.filename, text)
            if changed is not None:
                dst.writestr(info.filename, changed)
    return out.getvalue()


def edit_value(month: str, ref: str, period: str, column: str, value: str) -> bytes:
    def change(name, text):
        rows = list(csv.reader(io.StringIO(text)))
        header = rows[0]
        if "Series_reference" not in header:
            return text
        for row in rows[1:]:
            if (
                row[header.index("Series_reference")] == ref
                and row[header.index("Period")] == period
            ):
                row[header.index(column)] = value
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerows(rows)
        return out.getvalue()

    return rezip(month, change)


def errors(bundle, reference="2026-06", previous=None):
    findings = LabourAdapter().validate(bundle, reference_period=reference, previous=previous or {})
    return [f for f in findings if f.severity == "error"]


@pytest.mark.parametrize("month", ["2026-06", "2026-03"])
def test_parses_every_pinned_series_to_the_reference_quarter(month):
    bundle = parse(month)
    assert [s.definition.key for s in bundle.series] == list(KEYS)
    assert all(max(obs) == month for obs in by_key(bundle).values())
    assert bundle.layout_version == "labour-zip-v1"


def test_june_latest_values_match_the_official_files():
    data = by_key(parse("2026-06"))
    assert {k: data[k]["2026-06"].value for k in JUNE_LATEST} == JUNE_LATEST


def test_surveys_keep_separate_categories():
    cats = {s.definition.key: s.definition.category for s in parse("2026-06").series}
    assert {c for k, c in cats.items() if k.startswith("hlfs.")} == {"labour:hlfs"}
    assert {c for k, c in cats.items() if k.startswith("lci.")} == {"labour:lci"}


def test_status_maps_revised_to_unknown():
    statuses = {o.status for o in by_key(parse("2026-06"))["hlfs.rate.unemployment.sa"].values()}
    assert statuses == {ObsStatus.FINAL, ObsStatus.UNKNOWN}


def test_march_2026_unemployment_first_published_at_5_3_then_revised_to_5_4():
    march = by_key(parse("2026-03"))["hlfs.rate.unemployment.sa"]["2026-03"].value
    june = by_key(parse("2026-06"))["hlfs.rate.unemployment.sa"]["2026-03"].value
    assert (march, june) == (5.3, 5.4)


def test_the_page_headline_gives_the_latest_and_revised_previous_rate():
    assert headline_rates(page("2026-06")) == {"2026-06": 5.6, "2026-03": 5.4}
    assert headline_rates(page("2026-03")) == {"2026-03": 5.3, "2025-12": 5.4}


def test_headline_that_disagrees_with_the_file_fails():
    raw = edit_value("2026-06", "HLFQ.S1F3S", "2026.03", "Data_value", "5.3")
    with pytest.raises(IngestError, match="headline"):
        parse("2026-06", raw)


def test_unrecognised_headline_wording_only_warns():
    pg = dataclasses.replace(page("2026-06"), headline="Employment rose in the June 2026 quarter.")
    bundle = parse("2026-06", pg=pg)
    assert any("headline" in w for w in bundle.warnings)


def test_rejects_a_page_that_is_not_the_labour_market_release():
    other = parse_release_page(fixture_text("gdp_2026-06_page.html"), BASE)
    with pytest.raises(IngestError, match="title"):
        parse("2026-06", pg=other)


def test_only_hlfs_and_lci_members_are_read():
    raw = rezip("2026-06", lambda n, t: "not,a,real\nfile\n" if "/qes-" in n or "/lms-" in n else t)
    assert len(parse("2026-06", raw).series) == len(KEYS)


@pytest.mark.parametrize("member", ["/hlfs-", "/lci-"])
def test_missing_member_is_a_layout_change(member):
    raw = rezip("2026-06", lambda n, t: None if member in n else t)
    with pytest.raises(IngestError) as e:
        parse("2026-06", raw)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_two_hlfs_members_are_a_layout_change():
    raw = rezip("2026-06", lambda n, t: t)
    out = io.BytesIO(raw)
    with zipfile.ZipFile(out, "a") as z:
        z.writestr("labour-market-statistics-june-2026/hlfs-jun26qtr-tables.csv", "x")
    with pytest.raises(IngestError, match="member"):
        parse("2026-06", out.getvalue())


def test_not_a_zip_is_a_layout_change():
    with pytest.raises(IngestError) as e:
        parse("2026-06", b"PK\x03\x04 not really")
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_archive_size_cap(monkeypatch):
    monkeypatch.setattr(labour, "MAX_ARCHIVE", 1000)
    with pytest.raises(IngestError, match="size"):
        parse("2026-06")


def test_member_size_cap_uses_the_declared_size(monkeypatch):
    monkeypatch.setattr(labour, "MAX_MEMBER", 1000)
    with pytest.raises(IngestError, match="size"):
        parse("2026-06")


def test_member_count_cap():
    out = io.BytesIO(fixture_bytes("labour_2026-06.zip"))
    with zipfile.ZipFile(out, "a") as z:
        for n in range(5):
            z.writestr(f"labour-market-statistics-june-2026/extra-{n}.csv", "x")
    with pytest.raises(IngestError, match="members"):
        parse("2026-06", out.getvalue())


def test_row_cap(monkeypatch):
    monkeypatch.setattr(labour, "MAX_ROWS", 100)
    with pytest.raises(IngestError, match="row"):
        parse("2026-06")


def test_header_missing_a_required_column_is_a_layout_change():
    raw = rezip(
        "2026-06", lambda n, t: t.replace("MAGNTUDE", "MAGNITUDE", 1) if "/hlfs-" in n else t
    )
    with pytest.raises(IngestError) as e:
        parse("2026-06", raw)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_a_new_classification_on_a_pinned_series_fails():
    raw = edit_value("2026-06", "HLFQ.S1F3S", "2026.06", "Regional Council", "Auckland")
    with pytest.raises(IngestError, match="metadata"):
        parse("2026-06", raw)


def test_lci_metadata_change_fails():
    raw = edit_value("2026-06", "LCIQ.SG53Z9", "2026.06", "Group", "Something else")
    with pytest.raises(IngestError, match="metadata"):
        parse("2026-06", raw)


@pytest.mark.parametrize("value", ["", "NA", "abc", "nan"])
def test_missing_or_non_numeric_value_fails(value):
    raw = edit_value("2026-06", "HLFQ.S1A3S", "2026.06", "Data_value", value)
    with pytest.raises(IngestError):
        parse("2026-06", raw)


@pytest.mark.parametrize("period", ["2026.6", "2026.05", "2026-06"])
def test_malformed_or_non_quarter_period_fails(period):
    raw = edit_value("2026-06", "HLFQ.S1A3S", "2026.06", "Period", period)
    with pytest.raises(IngestError):
        parse("2026-06", raw)


def test_duplicate_period_fails():
    raw = edit_value("2026-06", "HLFQ.S1A3S", "2026.03", "Period", "2026.06")
    with pytest.raises(IngestError, match="duplicate"):
        parse("2026-06", raw)


@pytest.mark.parametrize("month", ["2026-06", "2026-03"])
def test_real_release_validates_without_errors(month):
    assert errors(parse(month), reference=month) == []


def test_tolerances_are_the_measured_ones():
    assert (IDENTITY_LEVEL_TOLERANCE, IDENTITY_RATE_TOLERANCE_PP, LCI_TOLERANCE_PP) == (
        1.5,
        0.08,
        0.06,
    )


def test_labour_force_identity_is_checked():
    raw = edit_value("2026-06", "HLFQ.S1Z3S", "2010.06", "Data_value", "2500")
    assert any(f.rule == "identity" for f in errors(parse("2026-06", raw)))


def test_rate_identity_is_checked_away_from_the_headline_quarters():
    raw = edit_value("2026-06", "HLFQ.S1H3S", "2010.06", "Data_value", "70.0")
    assert any(
        f.rule == "identity" and "employment" in f.message for f in errors(parse("2026-06", raw))
    )


def test_lci_changes_reconcile_with_the_index():
    raw = edit_value("2026-06", "LCIQ.SG53Z9AC", "2015.06", "Data_value", "4.0")
    assert any(f.rule == "reconcile" for f in errors(parse("2026-06", raw)))


def test_missing_required_series_fails_validation():
    bundle = parse("2026-06")
    trimmed = dataclasses.replace(bundle, series=bundle.series[1:])
    assert any(f.rule == "coverage" for f in errors(trimmed))


def test_reference_mismatch_fails():
    assert any(f.rule == "reference" for f in errors(parse("2026-06"), reference="2026-09"))


def test_revisions_are_warnings_and_lost_history_is_an_error():
    june = parse("2026-06")
    previous = {s.definition.key: points(parse("2026-03"), s.definition.key) for s in june.series}
    findings = LabourAdapter().validate(june, reference_period="2026-06", previous=previous)
    assert [f for f in findings if f.severity == "error"] == []
    assert any(f.rule == "revisions" and "hlfs.rate.unemployment.sa" in f.message for f in findings)
    previous["hlfs.rate.unemployment.sa"]["1980-03"] = Point("1980-03", 4.0, ObsStatus.FINAL)
    assert any(f.rule == "coverage" for f in errors(june, previous=previous))


def test_an_overlong_line_is_refused_before_it_is_held_in_memory(monkeypatch):
    monkeypatch.setattr(labour, "MAX_LINE", 200)
    with pytest.raises(IngestError, match="line"):
        parse("2026-06")


def test_a_record_spanning_lines_is_refused():
    def change(name, text):
        if "/hlfs-" not in name:
            return text
        head, _, rest = text.partition("\n")
        return head + '\n"HLFQ.S1F3S\n",2026.06\n' + rest

    with pytest.raises(IngestError) as e:
        parse("2026-06", rezip("2026-06", change))
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED
