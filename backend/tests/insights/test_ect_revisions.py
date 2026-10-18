"""ECT revision comparisons stay between publications, not correction bundles."""

from dataclasses import replace
from datetime import timedelta

import pytest

from nzstats.clock import to_akl_iso
from nzstats.domain import Observation
from nzstats.insights.ect import build_ect_dashboard
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from nzstats.store.db import transaction
from tests.ect_support import NOW, seed_ect

RETAIL = "ect.m.sa.retail.value"


def _ingest_ect(rt, site, *months: str) -> dict[str, int]:
    ids = {}
    for month in months:
        release_id, release_key, _ = seed_ect(rt, site, month)
        outcome = ingest_release(rt, release_key, now_fn=lambda: NOW)
        assert outcome.outcome == "ingested", outcome.detail
        ids[month] = release_id
    return ids


def _clone_current_bundle(
    rt,
    release_id: int,
    digest: str,
    *,
    retail_period: str,
    retail_delta: float = 0,
    retail_definition_id: str | None = None,
):
    """Store a corrected copy of a real fixture bundle and return its retail vintage."""
    source_bundle = repo.release_bundle(rt.conn, release_id)
    assert source_bundle is not None
    stored = repo.bundle_series(rt.conn, release_id, source_bundle)
    captured_at = NOW + timedelta(minutes=len(repo.release_bundles(rt.conn, release_id)) + 1)
    with transaction(rt.conn):
        for definition, observations in stored:
            if definition.key == RETAIL and retail_definition_id is not None:
                definition = replace(definition, definition_id=retail_definition_id)
            series_id = repo.upsert_series(rt.conn, definition)
            vintage_id = repo.create_vintage(
                rt.conn,
                release_id,
                series_id,
                captured_at,
                "release_files",
                "test-correction",
                digest,
            )
            assert vintage_id is not None
            repo.insert_observations(
                rt.conn,
                vintage_id,
                [
                    Observation(
                        definition.key,
                        observation.period,
                        observation.value
                        + (
                            retail_delta
                            if definition.key == RETAIL and observation.period == retail_period
                            else 0
                        ),
                        observation.status,
                        observation.std_error,
                        observation.released_in,
                    )
                    for observation in observations
                ],
            )
    vintage = repo.bundle_vintage(rt.conn, RETAIL, release_id, digest)
    assert vintage is not None
    return vintage


def _analysis(rt, release_id: int):
    dashboard = build_ect_dashboard(rt.conn, release_id)
    assert dashboard is not None
    return dashboard.analysis


def _previous_decomposition(analysis):
    assert len(analysis.previous_comparison.decompositions) == 1
    return analysis.previous_comparison.decompositions[0]


def test_consecutive_releases_use_one_prior_publication_and_reconcile(rt, site):
    ids = _ingest_ect(rt, site, "2026-08", "2026-09")

    analysis = _analysis(rt, ids["2026-09"])
    decomposition = _previous_decomposition(analysis)

    assert analysis.revisions.available
    assert analysis.revisions.against_title.endswith("August 2026")
    assert analysis.previous_comparison.previous_release_title == analysis.revisions.against_title
    assert decomposition.previous_release_title == analysis.revisions.against_title
    assert decomposition.revision_component + decomposition.new_period_component == pytest.approx(
        decomposition.total_change
    )


def test_corrected_release_keeps_corrections_separate_from_prior_publication(rt, site):
    ids = _ingest_ect(rt, site, "2026-08", "2026-09")
    _clone_current_bundle(
        rt, ids["2026-09"], "september-correction", retail_period="2026-08", retail_delta=7
    )

    analysis = _analysis(rt, ids["2026-09"])

    assert analysis.corrections.available
    assert analysis.revisions.available
    assert analysis.revisions.against_title.endswith("August 2026")
    assert analysis.previous_comparison.previous_release_title == analysis.revisions.against_title
    assert (
        _previous_decomposition(analysis).previous_release_title == analysis.revisions.against_title
    )


def test_multiple_corrections_compare_latest_bundle_with_prior_publication(rt, site):
    ids = _ingest_ect(rt, site, "2026-08", "2026-09")
    previous_correction = _clone_current_bundle(
        rt, ids["2026-09"], "september-correction-1", retail_period="2026-08", retail_delta=7
    )
    _clone_current_bundle(
        rt, ids["2026-09"], "september-correction-2", retail_period="2026-08", retail_delta=11
    )

    analysis = _analysis(rt, ids["2026-09"])

    assert analysis.revisions.against_title.endswith("August 2026")
    assert analysis.corrections.available
    assert analysis.corrections.against_captured_at == to_akl_iso(previous_correction.captured_at)


def test_latest_correction_of_prior_publication_is_the_comparison_vintage(rt, site):
    ids = _ingest_ect(rt, site, "2026-08")
    corrected = _clone_current_bundle(
        rt, ids["2026-08"], "august-correction", retail_period="2026-08", retail_delta=10_000
    )
    ids.update(_ingest_ect(rt, site, "2026-09"))
    corrected_value = repo.vintage_points(rt.conn, corrected.vintage_id)["2026-08"].value

    analysis = _analysis(rt, ids["2026-09"])
    decomposition = _previous_decomposition(analysis)

    assert analysis.revisions.against_title.endswith("August 2026")
    assert decomposition.previous_published_value == corrected_value
    assert any(
        row.period == "2026-08" and row.original == corrected_value
        for row in analysis.revisions.largest
    )


def test_corrected_first_publication_has_corrections_but_no_revision_base(rt, site):
    ids = _ingest_ect(rt, site, "2026-09")
    _clone_current_bundle(
        rt, ids["2026-09"], "first-correction", retail_period="2026-08", retail_delta=7
    )

    analysis = _analysis(rt, ids["2026-09"])

    assert analysis.corrections.available
    assert not analysis.revisions.available
    assert not analysis.previous_comparison.available
    assert "No earlier publication" in analysis.revisions.note


def test_historical_corrected_release_never_uses_a_future_publication(rt, site):
    ids = _ingest_ect(rt, site, "2026-08")
    _clone_current_bundle(
        rt, ids["2026-08"], "historical-correction", retail_period="2026-07", retail_delta=7
    )
    ids.update(_ingest_ect(rt, site, "2026-09"))

    analysis = _analysis(rt, ids["2026-08"])

    assert analysis.corrections.available
    assert not analysis.revisions.available
    assert analysis.revisions.against_title is None
    assert not analysis.previous_comparison.decompositions


def test_out_of_order_backfill_still_uses_publication_order(rt, site):
    ids = _ingest_ect(rt, site, "2026-09", "2026-08")

    analysis = _analysis(rt, ids["2026-09"])

    assert analysis.revisions.available
    assert analysis.revisions.against_title.endswith("August 2026")
    assert _previous_decomposition(analysis).previous_release_title.endswith("August 2026")


def test_incompatible_definitions_withhold_revisions_and_decomposition(rt, site):
    ids = _ingest_ect(rt, site, "2026-08", "2026-09")
    _clone_current_bundle(
        rt,
        ids["2026-09"],
        "methodology-change",
        retail_period="2026-08",
        retail_definition_id="ect-retail-incompatible",
    )

    analysis = _analysis(rt, ids["2026-09"])

    assert not analysis.revisions.available
    assert "incompatible" in analysis.revisions.note.lower()
    assert not analysis.previous_comparison.available
    assert not analysis.previous_comparison.decompositions
