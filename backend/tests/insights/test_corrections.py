"""Corrections within one publication are distinct from revisions between publications."""

import io

import pandas as pd

from nzstats.insights.migration import build_release_analysis
from nzstats.store import repo
from tests.conftest import fixture_bytes
from tests.pipeline.test_ingest import (
    _CITIZENSHIP_CHART,
    _bump_net_rolling,
    _drop_chart,
    _edit_page,
    _ingest,
)
from tests.support import ingest_months, page_url


def _analysis(rt, rid):
    return build_release_analysis(rt.conn, rid, analysable_slugs={"international-migration"})


def test_first_capture_has_no_same_publication_correction(rt):
    rid = ingest_months(rt, "2026-07")["2026-07"]
    correction = _analysis(rt, rid).corrections
    assert not correction.available
    assert correction.series == []
    assert correction.against_captured_at is None


def test_corrected_first_publication_exposes_chart_change_without_previous_publication(rt, site):
    rid = ingest_months(rt, "2026-07")["2026-07"]
    original = repo.latest_points(rt.conn, "mig.ry.net")
    _edit_page(site, "2026-07", _bump_net_rolling)
    key = repo.get_release_by_id(rt.conn, rid)["release_key"]
    assert _ingest(rt, key).outcome == "ingested"
    analysis = _analysis(rt, rid)
    assert analysis.revisions.available is False
    assert "No earlier publication" in analysis.revisions.note
    assert "No earlier vintage" not in analysis.revisions.note
    correction = analysis.corrections
    assert correction.available and correction.against_captured_at
    assert [s.series_key for s in correction.series] == ["mig.ry.net"]
    series = correction.series[0]
    assert series.n_changed == 1
    row = series.changes[0]
    assert row.original == original[row.period].value
    assert row.revised == row.original + 1


def test_same_publication_correction_keeps_earlier_publication_revisions_separate(rt, site):
    ids = ingest_months(rt, "2026-06", "2026-07")
    rid = ids["2026-07"]
    earlier = _analysis(rt, rid).revisions.model_dump()
    _edit_page(site, "2026-07", _bump_net_rolling)
    assert _ingest(rt, repo.get_release_by_id(rt.conn, rid)["release_key"]).outcome == "ingested"
    analysis = _analysis(rt, rid)
    assert analysis.revisions.model_dump() == earlier  # monthly series did not change
    assert analysis.corrections.available
    assert len(repo.list_vintages(rt.conn, "mig.ry.net")) == 3


def test_standard_error_only_correction_is_exposed(rt, site):
    rid = ingest_months(rt, "2026-07")["2026-07"]
    df = pd.read_csv(io.BytesIO(fixture_bytes("im_2026-07_age_sex.csv")))
    select = (df.year_month == "2026-07") & (df.direction == "Net")
    old = float(df.loc[select, "standard_error"].iloc[0])
    df.loc[select, "standard_error"] = old + 1
    site.override(site.file_url("2026-07", "age_sex"), 200, df.to_csv(index=False).encode())
    assert _ingest(rt, repo.get_release_by_id(rt.conn, rid)["release_key"]).outcome == "ingested"
    correction = _analysis(rt, rid).corrections
    series = next(s for s in correction.series if s.series_key == "mig.m.net")
    assert series.n_changed == 1
    row = series.changes[0]
    assert row.original == row.revised
    assert row.original_std_error == old and row.revised_std_error == old + 1


def test_withdrawn_optional_series_are_explicit_corrections(rt, site):
    rid = ingest_months(rt, "2026-07")["2026-07"]
    _edit_page(site, "2026-07", _drop_chart(_CITIZENSHIP_CHART))
    assert _ingest(rt, repo.get_release_by_id(rt.conn, rid)["release_key"]).outcome == "ingested"
    correction = _analysis(rt, rid).corrections
    series = next(s for s in correction.series if s.series_key == "mig.ry.net.nz")
    assert series.n_changed > 8
    assert len(series.changes) == 8
    assert all(row.original is not None and row.revised is None for row in series.changes)


def test_reverted_bundle_is_compared_with_the_bundle_it_replaced(rt, site):
    rid = ingest_months(rt, "2026-07")["2026-07"]
    key = repo.get_release_by_id(rt.conn, rid)["release_key"]
    page = site.routes[page_url("2026-07")]
    _edit_page(site, "2026-07", _bump_net_rolling)
    assert _ingest(rt, key).outcome == "ingested"
    forward = _analysis(rt, rid).corrections.series[0].changes[0]
    site.override(page_url("2026-07"), *page)
    assert _ingest(rt, key).outcome == "ingested"
    reverse = _analysis(rt, rid).corrections.series[0].changes[0]
    assert (reverse.original, reverse.revised) == (forward.revised, forward.original)
    assert len(repo.list_vintages(rt.conn, "mig.ry.net")) == 2


def test_correction_series_have_statistical_labels_and_units(rt, site):
    rid = ingest_months(rt, "2026-07")["2026-07"]
    _edit_page(site, "2026-07", _bump_net_rolling)
    assert _ingest(rt, repo.get_release_by_id(rt.conn, rid)["release_key"]).outcome == "ingested"
    corrected = _analysis(rt, rid).corrections.series[0]
    assert corrected.label == "Net migration (year ended)"
    assert corrected.unit == "people"
