import csv
import io
from dataclasses import replace

import pytest

from nzstats.adapters.base import ParsedBundle, ParsedSeries
from nzstats.adapters.cpi.adapter import (
    CHART_PCT_TOLERANCE,
    CONTRIBUTION_SUM_TOLERANCE_PP,
    SA_REVISION_MATERIALITY,
    CpiAdapter,
)
from nzstats.domain import ErrorClass, IngestError, Observation, ObsStatus, Point
from nzstats.sources.release_page import Chart
from tests.cpi_support import files, page

MONTHS = ("2025-12", "2026-03", "2026-06")


def parse(month="2026-06", pg=None, source=None):
    return CpiAdapter().parse(pg or page(month), source or files(month))


@pytest.fixture(scope="module")
def june():
    return parse()


def validate(bundle, reference="2026-06", previous=None):
    return CpiAdapter().validate(bundle, reference_period=reference, previous=previous or {})


def rules(findings, severity="error"):
    return {f.rule for f in findings if f.severity == severity}


def series(bundle, key):
    return next(s for s in bundle.series if s.definition.key == key)


def modified(bundle, key, observations=None, definition=None, drop=False):
    out = []
    for s in bundle.series:
        if s.definition.key != key:
            out.append(s)
        elif not drop:
            out.append(
                ParsedSeries(
                    definition or s.definition,
                    tuple(observations if observations is not None else s.observations),
                )
            )
    return ParsedBundle(bundle.layout_version, tuple(out))


def obs(key, period, value):
    return Observation(key, period, value, ObsStatus.FINAL)


@pytest.mark.parametrize("month", MONTHS)
def test_real_releases_validate_and_ingest(month):
    bundle = parse(month)
    assert rules(validate(bundle, month)) == set()


def test_discontinued_optional_series_only_warns(june):
    findings = validate(june)
    assert "optional" in rules(findings, "warning")
    assert any("miscellaneous" in f.message for f in findings if f.rule == "optional")


def test_reference_must_be_a_quarter_and_match_latest_core_period(june):
    assert "reference" in rules(validate(june, "2026-05"))
    key = "cpi.index.nsa.all_groups"
    short = modified(june, key, series(june, key).observations[:-1])
    assert "reference" in rules(validate(short))


def test_missing_core_series_is_a_coverage_error(june):
    assert "coverage" in rules(validate(modified(june, "cpi.index.nsa.tradables", drop=True)))


def test_gap_inside_a_run_is_a_continuity_error(june):
    key = "cpi.index.nsa.tradables"
    o = series(june, key).observations
    assert "continuity" in rules(validate(modified(june, key, o[:5] + o[6:])))


@pytest.mark.parametrize("bad", [0.0, -3.0, float("nan"), float("inf")])
def test_non_positive_or_non_finite_levels_are_value_errors(june, bad):
    key = "cpi.index.nsa.health"
    o = list(series(june, key).observations)
    o[-3] = obs(key, o[-3].period, bad)
    assert "values" in rules(validate(modified(june, key, o)))


def test_rebased_index_fails_the_base_check(june):
    key = "cpi.index.nsa.transport"
    scaled = [obs(key, o.period, o.value * 10) for o in series(june, key).observations]
    assert "base" in rules(validate(modified(june, key, scaled)))


def test_all_groups_must_lie_between_tradables_and_non_tradables(june):
    key = "cpi.index.nsa.all_groups"
    o = list(series(june, key).observations)
    o[-1] = obs(key, "2026-06", 1500.0)
    assert "ordering" in rules(validate(modified(june, key, o)))


def test_large_movement_warns(june):
    key = "cpi.index.nsa.all_groups"
    o = list(series(june, key).observations)
    o[-1] = obs(key, "2026-06", o[-2].value * 1.08)
    assert "structural_change" in rules(validate(modified(june, key, o)), "warning")


def test_metadata_and_unknown_series_are_rejected(june):
    key = "cpi.index.nsa.food"
    d = replace(series(june, key).definition, unit="percent")
    assert "metadata" in rules(validate(modified(june, key, definition=d)))
    unknown = ParsedSeries(replace(d, key="cpi.index.nsa.mystery"), series(june, key).observations)
    assert "metadata" in rules(validate(ParsedBundle("v", (*june.series, unknown))))


def test_duplicate_series_keys_are_rejected(june):
    assert "duplicates" in rules(validate(ParsedBundle("v", (*june.series, june.series[0]))))


def test_previous_periods_must_be_retained_and_revisions_are_reported(june):
    key = "cpi.index.nsa.all_groups"
    latest = {o.period: o for o in series(june, key).observations}
    previous = {key: {"1900-03": Point("1900-03", 5.0, ObsStatus.FINAL)}}
    assert "coverage" in rules(validate(june, previous=previous))
    revised = {key: {"2026-03": Point("2026-03", latest["2026-03"].value + 3, ObsStatus.FINAL)}}
    findings = validate(june, previous=revised)
    assert "revisions" in rules(findings, "warning") and "revisions" not in rules(findings)


def test_seasonally_adjusted_noise_is_not_a_revision(june):
    key = "cpi.index.sa.all_groups"
    value = series(june, key).observations[-2]
    for delta, expected in ((1e-8, False), (SA_REVISION_MATERIALITY * 4, True)):
        previous = {
            key: {value.period: Point(value.period, value.value + delta, ObsStatus.UNKNOWN)}
        }
        assert ("revisions" in rules(validate(june, previous=previous), "warning")) is expected


def test_contributions_must_cover_the_eleven_groups_and_sum_near_the_headline(june):
    key = "cpi.contrib.q.food"
    off = modified(june, key, [obs(key, "2026-06", 0.076 + CONTRIBUTION_SUM_TOLERANCE_PP + 0.1)])
    assert "contribution" in rules(validate(off))
    assert "contribution" in rules(validate(modified(june, key, drop=True)))


def test_absent_contribution_charts_only_warn(june):
    kept = tuple(s for s in june.series if ".contrib." not in s.definition.key)
    findings = validate(ParsedBundle(june.layout_version, kept))
    assert "contribution" in rules(findings, "warning") and "contribution" not in rules(findings)


def chart_edit(pg, label, mutate):
    charts = []
    for c in pg.charts:
        rows = list(csv.reader(io.StringIO(c.csv)))
        for row in rows:
            if row and row[0].lower() == label:
                mutate(rows, row)
        out = io.StringIO()
        csv.writer(out, lineterminator="\n").writerows(rows)
        charts.append(Chart(c.title, out.getvalue()))
    return replace(pg, charts=tuple(charts))


def test_published_percentage_must_match_the_computed_change():
    def bump(rows, row):
        row[-1] = str(float(row[-1]) + 2 * CHART_PCT_TOLERANCE)

    with pytest.raises(IngestError) as caught:
        parse(pg=chart_edit(page(), "cpi all groups (annual)", bump))
    assert caught.value.error_class is ErrorClass.VALIDATION_FAILED


def test_missing_percentage_rows_fail_as_layout_change():
    def drop(rows, row):
        rows.remove(row)

    with pytest.raises(IngestError) as caught:
        parse(pg=chart_edit(page(), "tradeables (annual)", drop))
    assert caught.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_alternative_tradables_spelling_and_bad_quarter_label():
    def rename(rows, row):
        row[0] = "Tradables (annual)"

    assert parse(pg=chart_edit(page(), "tradeables (annual)", rename)).series

    def relabel(rows, row):
        rows[0][1] = "Foo-22"

    with pytest.raises(IngestError) as caught:
        parse(pg=chart_edit(page(), "cpi all groups (annual)", relabel))
    assert caught.value.error_class is ErrorClass.LAYOUT_CHANGED
