import csv
import io
import zipfile
from dataclasses import replace

import pytest

from nzstats.domain import IngestError
from nzstats.sources.release_page import classify_download, parse_release_page
from tests.conftest import fixture_bytes, fixture_text
from tests.support import BASE


def parsed(month="2026-09", raw=None):
    from nzstats.adapters.ect.adapter import EctAdapter

    page = parse_release_page(fixture_text(f"ect_{month}_page.html"), BASE)
    return EctAdapter().parse(page, {"ect_zip": raw or fixture_bytes(f"ect_{month}.zip")})


def csv_rows():
    with zipfile.ZipFile(io.BytesIO(fixture_bytes("ect_2026-09.zip"))) as z:
        return list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8-sig"))))


def archive(rows, name="data.csv"):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, out.getvalue())
    return buf.getvalue()


def test_ect_download_detection_preserves_migration_classification():
    page = parse_release_page(fixture_text("ect_2026-09_page.html"), BASE)
    assert {classify_download(u) for u in page.download_urls} == {"workbook", "ect_zip"}
    assert classify_download("/unrelated.zip") is None
    assert classify_download("/migration-age-sex.csv") == "age_sex"


def test_official_history_measures_adjustments_and_quarters():
    from nzstats.adapters.ect.adapter import EctAdapter

    b = parsed()
    s = {s.definition.key: s for s in b.series}
    assert len(s["ect.m.sa.retail.value"].observations) >= 36
    assert s["ect.m.actual.total.count"].definition.unit == "transactions"
    assert s["ect.m.actual.total.average"].definition.unit == "NZD"
    assert s["ect.m.sa.retail.value"].definition.unit == "NZD million"
    assert s["ect.q.sa.retail.value"].definition.frequency.value == "quarterly"
    assert s["ect.m.actual.retail.value"].definition.adjustment.value == "none"
    assert s["ect.m.trend.retail.value"].definition.adjustment.value == "trend"
    errors = [
        f
        for f in EctAdapter().validate(b, reference_period="2026-09", previous={})
        if f.severity == "error"
    ]
    assert errors == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("UNITS", "Number"),
        ("Magnitude", "0"),
        ("Series_title_1", "Trend"),
        ("Series_title_2", "Unknown industry"),
        ("Data_value", "nan"),
        ("Data_value", "-1"),
        ("Period", "2026.13"),
    ],
)
def test_rejects_incompatible_source_rows(field, value):
    rows = csv_rows()
    row = next(
        r for r in rows if r["Series_reference"] == "ECTM.S19S1" and r["Period"] == "2026.09"
    )
    row[field] = value
    with pytest.raises(IngestError):
        parsed(raw=archive(rows))


def test_rejects_duplicate_observations_and_unsafe_archive():
    rows = csv_rows()
    rows.append(next(r for r in rows if r["Series_reference"] == "ECTM.S19S1"))
    with pytest.raises(IngestError):
        parsed(raw=archive(rows))
    with pytest.raises(IngestError):
        parsed(raw=archive(csv_rows(), "../escape.csv"))
    with pytest.raises(IngestError):
        parsed(raw=b"not a zip")


def test_validation_detects_gaps_missing_series_duplicates_and_reference_drift():
    from nzstats.adapters.ect.adapter import EctAdapter

    b = parsed()
    retail = next(s for s in b.series if s.definition.key == "ect.m.sa.retail.value")
    gap = replace(retail, observations=retail.observations[:20] + retail.observations[21:])
    for changed in [replace(b, series=(gap,)), replace(b, series=b.series + (retail,))]:
        assert any(
            f.severity == "error"
            for f in EctAdapter().validate(changed, reference_period="2026-09", previous={})
        )
    assert any(
        f.severity == "error"
        for f in EctAdapter().validate(b, reference_period="2026-08", previous={})
    )


def test_source_chart_mismatch_is_rejected():
    rows = csv_rows()
    next(r for r in rows if r["Series_reference"] == "ECTM.S1GS3" and r["Period"] == "2026.09")[
        "Data_value"
    ] = "2000"
    with pytest.raises(IngestError, match="reconcil"):
        parsed(raw=archive(rows))


def test_bundle_validation_rejects_incorrect_units_and_quarterly_metadata():
    from nzstats.adapters.ect.adapter import EctAdapter

    b = parsed()
    s = b.series[0]
    altered = replace(s, definition=replace(s.definition, unit="people"))
    bad = replace(b, series=tuple(altered if x == s else x for x in b.series))
    assert any(
        f.severity == "error" and f.rule == "metadata"
        for f in EctAdapter().validate(bad, reference_period="2026-09", previous={})
    )


def test_quarterly_source_must_be_quarter_end():
    rows = csv_rows()
    next(r for r in rows if r["Series_reference"] == "ECTQ.S19S1" and r["Period"] == "2026.09")[
        "Period"
    ] = "2026.08"
    with pytest.raises(IngestError):
        parsed(raw=archive(rows))


@pytest.mark.parametrize(
    "key,percent,absolute,tolerance",
    [
        ("ect.m.sa.retail.value", -0.4, -30, 0.55),
        ("ect.m.sa.core.value", -0.7, -41, 0.55),
        ("ect.m.sa.total.value", -0.5, -51, 0.55),
        ("ect.m.sa.hospitality.value", -2.3, None, 0),
        ("ect.m.sa.apparel.value", -2.0, None, 0),
        ("ect.m.sa.durables.value", -0.4, None, 0),
        ("ect.m.sa.consumables.value", 0.3, None, 0),
        ("ect.m.sa.motor_vehicles.value", 0.6, None, 0),
        ("ect.m.sa.fuel.value", 2.9, None, 0),
        ("ect.q.sa.retail.value", 0.1, 14, 0.55),
        ("ect.q.sa.core.value", 0.4, 79, 0.55),
    ],
)
def test_september_headlines_reconcile_with_official_file(key, percent, absolute, tolerance):
    from nzstats.insights.ect import metric

    s = next(s for s in parsed().series if s.definition.key == key)
    m = metric(s.definition, s.observations)
    assert m.change_prior.percent == pytest.approx(percent, abs=0.065)
    if absolute is not None:
        assert m.change_prior.absolute == pytest.approx(absolute, abs=tolerance)


def test_actual_benchmarks_are_rounded_and_not_missing_as_zero():
    b = parsed()
    s = {s.definition.key: s for s in b.series}
    total = s["ect.m.actual.total.value"].observations[-1].value
    count = s["ect.m.actual.total.count"].observations[-1].value
    average = s["ect.m.actual.total.average"].observations[-1].value
    assert total / 1000 == pytest.approx(9.2, abs=0.05)
    assert count / 1_000_000 == pytest.approx(167, abs=0.5)
    assert average == pytest.approx(55, abs=0.5)
    assert total * 1_000_000 / count == pytest.approx(average, abs=0.1)
    # Confidential early values are omitted; real lockdown zeros remain valid numeric values.
    assert s["ect.m.actual.core.value"].observations[0].period == "2002-10"


def test_archive_member_and_size_limits(monkeypatch):
    import nzstats.adapters.ect.adapter as adapter

    raw = fixture_bytes("ect_2026-09.zip")
    monkeypatch.setattr(adapter, "MAX_UNPACKED", 100)
    with pytest.raises(IngestError, match="limit"):
        parsed(raw=raw)


def test_publication_before_data_is_rejected():
    from datetime import UTC, datetime

    from nzstats.adapters.ect.adapter import EctAdapter

    page = parse_release_page(fixture_text("ect_2026-09_page.html"), BASE)
    with pytest.raises(IngestError, match="publication"):
        EctAdapter().parse(
            replace(page, published_at=datetime(2026, 8, 1, tzinfo=UTC)),
            {"ect_zip": fixture_bytes("ect_2026-09.zip")},
        )


def test_nonfinite_embedded_chart_cannot_bypass_reconciliation():
    from nzstats.adapters.ect.adapter import EctAdapter

    page = parse_release_page(fixture_text("ect_2026-09_page.html"), BASE)
    chart = page.charts[1]
    page = replace(page, charts=(replace(chart, csv=chart.csv.replace("0.3", "nan")),))
    with pytest.raises(IngestError, match="chart"):
        EctAdapter().parse(page, {"ect_zip": fixture_bytes("ect_2026-09.zip")})


def test_missing_industry_series_is_rejected_even_without_chart():
    from nzstats.adapters.ect.adapter import EctAdapter

    b = parsed()
    changed = replace(
        b, series=tuple(s for s in b.series if s.definition.key != "ect.m.sa.hospitality.value")
    )
    assert any(
        f.severity == "error"
        for f in EctAdapter().validate(changed, reference_period="2026-09", previous={})
    )
