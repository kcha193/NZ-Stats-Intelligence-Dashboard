import csv
import io
import zipfile
from dataclasses import replace

import pytest

from nzstats.domain import IngestError, Point
from nzstats.sources.release_page import classify_download, parse_release_page
from tests.conftest import fixture_bytes, fixture_text
from tests.support import BASE


def parsed(month="2026-09", raw=None):
    from nzstats.adapters.ect.adapter import EctAdapter

    page = parse_release_page(fixture_text(f"ect_{month}_page.html"), BASE)
    return EctAdapter().parse(page, {"ect_zip": raw or fixture_bytes(f"ect_{month}.zip")})


def csv_rows(month="2026-09"):
    with zipfile.ZipFile(io.BytesIO(fixture_bytes(f"ect_{month}.zip"))) as z:
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


def test_validation_rejects_truncated_quarterly_history_against_prior_release():
    from nzstats.adapters.ect.adapter import EctAdapter

    adapter = EctAdapter()
    previous_bundle = parsed("2026-08")
    previous = {
        series.definition.key: {
            observation.period: Point(observation.period, observation.value, observation.status)
            for observation in series.observations
        }
        for series in previous_bundle.series
        if series.definition.key in adapter.previous_keys
    }
    current = parsed("2026-09")
    quarterly = next(
        series for series in current.series if series.definition.key == "ect.q.sa.retail.value"
    )
    truncated = replace(quarterly, observations=quarterly.observations[1:])
    changed = replace(
        current,
        series=tuple(truncated if series is quarterly else series for series in current.series),
    )

    findings = adapter.validate(changed, reference_period="2026-09", previous=previous)

    assert any(f.severity == "error" and f.rule == "coverage" for f in findings)


def test_validation_rejects_archive_without_quarterly_series():
    from nzstats.adapters.ect.adapter import EctAdapter

    current = parsed("2026-09")
    changed = replace(
        current,
        series=tuple(
            series for series in current.series if not series.definition.key.startswith("ect.q.")
        ),
    )

    findings = EctAdapter().validate(changed, reference_period="2026-09", previous={})

    assert any(f.severity == "error" and f.rule == "coverage" for f in findings)


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


def test_monthly_publication_without_new_quarter_retains_prior_coverage():
    from nzstats.adapters.ect.adapter import EctAdapter

    current = parsed("2026-08")
    previous = {
        s.definition.key: {
            o.period: Point(o.period, o.value, o.status)
            for o in s.observations
            if o.period <= "2026-07"
        }
        for s in current.series
    }
    findings = EctAdapter().validate(current, reference_period="2026-08", previous=previous)
    assert not [f for f in findings if f.severity == "error"]
    quarterly = next(s for s in current.series if s.definition.key == "ect.q.sa.retail.value")
    assert quarterly.observations[-1].period == "2026-06"


@pytest.mark.parametrize("month", ["2026-08", "2026-09"])
def test_initial_archive_rejects_stale_quarterly_series(month):
    rows = csv_rows(month)
    # Keep every earlier value, but remove the latest completed quarter from a mandatory
    # count series so embedded chart/percentage reconciliation cannot mask the reference guard.
    latest = "2026.06" if month == "2026-08" else "2026.09"
    rows = [r for r in rows if r["Series_reference"] != "ECTQ.S29A9" or r["Period"] != latest]
    with pytest.raises(IngestError, match="quarterly.*2026-(06|09)"):
        parsed(month, raw=archive(rows))


@pytest.mark.parametrize(
    "reference,expected_quarter",
    [
        ("2027-01", "2026-12"),
        ("2027-02", "2026-12"),
        ("2027-03", "2027-03"),
        ("2027-04", "2027-03"),
        ("2027-05", "2027-03"),
        ("2027-06", "2027-06"),
        ("2027-07", "2027-06"),
        ("2027-08", "2027-06"),
        ("2027-09", "2027-09"),
        ("2027-10", "2027-09"),
        ("2027-11", "2027-09"),
        ("2027-12", "2027-12"),
    ],
)
def test_quarterly_reference_tracks_completed_quarter(reference, expected_quarter):
    from nzstats.adapters.ect.adapter import EctAdapter
    from nzstats.stats.periods import add_months

    # Relabel real fixture periods to exercise the calendar boundary without invented values.
    bundle = parsed()
    quarterly = next(s for s in bundle.series if s.definition.key == "ect.q.actual.total.count")
    quarterly = replace(
        quarterly, observations=(replace(quarterly.observations[-1], period=expected_quarter),)
    )
    findings = EctAdapter().validate(
        replace(bundle, series=(quarterly,)), reference_period=reference, previous={}
    )
    assert not [f for f in findings if f.rule == "reference"]

    stale = replace(
        quarterly,
        observations=(
            replace(quarterly.observations[-1], period=add_months(expected_quarter, -3)),
        ),
    )
    findings = EctAdapter().validate(
        replace(bundle, series=(stale,)), reference_period=reference, previous={}
    )
    assert any(f.rule == "reference" and f.severity == "error" for f in findings)


# --- Actual-value consistency (audit finding F1) -------------------------------------------------


def _consistency_errors(bundle):
    from nzstats.adapters.ect.adapter import EctAdapter

    findings = EctAdapter().validate(bundle, reference_period="2026-09", previous={})
    return [f for f in findings if f.severity == "error" and f.rule == "consistency"]


def _altered(bundle, key, *, factor=1.0, offset=0.0, period=None, drop=None):
    """Copy of a parsed bundle with one series scaled/shifted, or one period removed."""
    from nzstats.adapters.base import ParsedBundle, ParsedSeries

    def change(o):
        if period is None or o.period == period:
            return replace(o, value=o.value * factor + offset)
        return o

    series = []
    for s in bundle.series:
        if s.definition.key == key:
            obs = tuple(change(o) for o in s.observations if o.period != drop)
            s = ParsedSeries(s.definition, obs)
        series.append(s)
    return ParsedBundle(bundle.layout_version, tuple(series))


@pytest.mark.parametrize("month", ["2026-08", "2026-09"])
def test_official_releases_satisfy_actual_value_consistency(month):
    assert _consistency_errors(parsed(month)) == []


@pytest.mark.parametrize(
    "key",
    [
        "ect.m.actual.core.value",  # the audited case: passes percentage and chart reconciliation
        "ect.m.actual.retail.value",
        "ect.m.actual.total.value",
        "ect.m.actual.durables.value",
        "ect.q.actual.durables.value",  # quarterly industries must equal their three months
        "ect.q.actual.retail.value",  # quarterly aggregates: coarse plausibility only
        "ect.q.actual.total.count",
        "ect.m.actual.total.count",
        "ect.m.actual.total.average",
    ],
)
def test_actual_levels_scaled_by_ten_fail_consistency(key):
    assert _consistency_errors(_altered(parsed(), key, factor=10)), key


def test_core_actual_levels_scaled_by_ten_are_rejected_at_parse():
    rows = csv_rows()
    for r in rows:
        if r["Series_reference"] == "ECTM.S19A2" and r["Data_value"]:
            r["Data_value"] = str(float(r["Data_value"]) * 10)
    with pytest.raises(IngestError, match="consistency"):
        parsed(raw=archive(rows))


def test_source_rounding_residuals_are_accepted_but_real_discrepancies_are_not():
    bundle = parsed()
    period = "2020-06"
    levels = {s.definition.key: {o.period: o.value for o in s.observations} for s in bundle.series}
    parts = ("consumables", "durables", "hospitality", "apparel", "motor_vehicles", "fuel")
    components = sum(levels[f"ect.m.actual.{p}.value"][period] for p in parts)
    retail = levels["ect.m.actual.retail.value"][period]

    def with_residual(residual):
        return _altered(
            bundle,
            "ect.m.actual.retail.value",
            offset=components + residual - retail,
            period=period,
        )

    # Six rounded components plus the rounded aggregate can legitimately differ by up to 7 x 0.05.
    assert _consistency_errors(with_residual(0.3)) == []
    assert _consistency_errors(with_residual(-0.3)) == []
    assert _consistency_errors(with_residual(0.6))


def test_seasonally_adjusted_components_are_not_forced_to_add_up():
    bundle = parsed()
    sa = {s.definition.key: s for s in bundle.series if ".sa." in s.definition.key}
    retail = {o.period: o.value for o in sa["ect.m.sa.retail.value"].observations}
    parts = [
        {o.period: o.value for o in sa[f"ect.m.sa.{i}.value"].observations}
        for i in ("consumables", "durables", "hospitality", "apparel", "motor_vehicles", "fuel")
    ]
    # Independently adjusted: the official file really does differ by tens of millions.
    assert abs(retail["2021-11"] - sum(p["2021-11"] for p in parts)) > 10
    assert _consistency_errors(bundle) == []


def test_missing_component_period_is_skipped_not_treated_as_zero():
    bundle = parsed()
    first = min(
        o.period
        for s in bundle.series
        if s.definition.key == "ect.m.actual.fuel.value"
        for o in s.observations
    )
    trimmed = _altered(bundle, "ect.m.actual.fuel.value", drop=first)
    assert _consistency_errors(trimmed) == []
