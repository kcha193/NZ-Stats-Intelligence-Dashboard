"""Correction labels follow the compared publication's retained measurement definitions."""

from dataclasses import replace

import pytest

from nzstats.insights.migration import build_release_analysis
from nzstats.store import repo
from tests.pipeline.test_ingest import (
    _CITIZENSHIP_CHART,
    _bump_net_rolling,
    _drop_chart,
    _edit_page,
    _ingest,
)
from tests.support import NOW, ingest_months


@pytest.mark.parametrize(
    ("series_key", "edit", "expected_label"),
    [
        ("mig.ry.net", _bump_net_rolling, "Net migration (year ended)"),
        (
            "mig.ry.net.nz",
            _drop_chart(_CITIZENSHIP_CHART),
            "Net migration, NZ citizens (year ended)",
        ),
    ],
    ids=["changed-series", "withdrawn-series"],
)
def test_historical_correction_retains_metadata_after_newer_publication_change(
    rt, site, series_key, edit, expected_label
):
    june = ingest_months(rt, "2026-06")["2026-06"]
    _edit_page(site, "2026-06", edit)
    assert _ingest(rt, repo.get_release_by_id(rt.conn, june)["release_key"]).outcome == "ingested"

    july = ingest_months(rt, "2026-07")["2026-07"]
    july_bundle = repo.release_bundle(rt.conn, july)
    definition, observations = next(
        (d, obs) for d, obs in repo.bundle_series(rt.conn, july, july_bundle) if d.key == series_key
    )
    # Simulate a later publication adopting new metadata, retaining real fixture observations.
    series_id = repo.upsert_series(
        rt.conn,
        replace(definition, name="Net migration, new presentation", unit="thousands of people"),
    )
    vintage_id = repo.create_vintage(
        rt.conn, july, series_id, NOW, "release_files", "test-metadata", "newer-metadata"
    )
    repo.insert_observations(rt.conn, vintage_id, observations)
    assert repo.get_series_row(rt.conn, series_key)["unit"] == "thousands of people"

    analysis = build_release_analysis(rt.conn, june, analysable_slugs={"international-migration"})
    assert analysis.corrections.available
    correction = next(s for s in analysis.corrections.series if s.series_key == series_key)
    assert correction.n_changed > 0
    assert correction.label == expected_label
    assert correction.unit == "people"
