from datetime import timedelta

import pandas as pd
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.clock import to_akl_iso
from nzstats.insights.countries import rank_countries
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.conftest import FIXTURES
from tests.support import NOW, ingest_months, page_url, release_ref_for


def test_country_api_provenance_identifies_selected_bundle(rt):
    ingest_months(rt, "2026-06", "2026-07")
    bundle = repo.latest_bundle(rt.conn, "mig.m.arrivals")
    with TestClient(create_app(rt.settings)) as client:
        response = client.get("/api/migration/countries")
    assert response.status_code == 200
    provenance = response.json()["provenance"]
    assert provenance == {
        "release_key": release_ref_for("2026-07").release_key,
        "title": "International migration: July 2026",
        "published_at": to_akl_iso(release_ref_for("2026-07").published_at),
        "source_url": page_url("2026-07"),
        "captured_at": to_akl_iso(NOW),
        "bundle_sha256": bundle[1],
    }


def test_country_correction_updates_provenance_and_withdraws_old_series(rt, site):
    ingest_months(rt, "2026-06")
    before = rank_countries(rt.conn, top=1000)
    corrected = pd.read_csv(FIXTURES / "im_2026-06_citizenship_country.csv")
    corrected = corrected[corrected.country_of_residence != "Togo"]
    site.override(
        site.file_url("2026-06", "citizenship_visa_country"),
        200,
        corrected.to_csv(index=False, quoting=1).encode(),
    )
    captured = NOW + timedelta(hours=1)
    key = release_ref_for("2026-06").release_key
    assert ingest_release(rt, key, now_fn=lambda: captured).outcome == "ingested"
    after = rank_countries(rt.conn, top=1000)
    assert before.provenance.bundle_sha256 != after.provenance.bundle_sha256
    assert after.provenance.captured_at == to_akl_iso(captured)
    assert after.provenance.release_key == before.provenance.release_key
    assert next(c for c in after.countries if c.name == "Togo").value == 0


def test_country_metadata_and_totals_use_exact_selected_bundle(rt, monkeypatch):
    ingest_months(rt, "2026-06")
    june = rank_countries(rt.conn)
    bundle = repo.latest_bundle(rt.conn, "mig.m.arrivals")
    ingest_months(rt, "2026-07")
    monkeypatch.setattr(repo, "latest_bundle", lambda *args: bundle)
    selected = rank_countries(rt.conn)
    assert selected.period_end == "2026-06"
    assert selected.total == june.total
    assert selected.countries == june.countries
    assert selected.provenance == june.provenance


def test_missing_country_data_has_nullable_provenance(rt):
    with TestClient(create_app(rt.settings)) as client:
        body = client.get("/api/migration/countries").json()
    assert body["available"] is False
    assert body["provenance"] is None


def test_unknown_country_source_url_is_not_invented(rt):
    ingest_months(rt, "2026-07")
    rt.conn.execute("UPDATE release SET page_url=NULL")
    assert rank_countries(rt.conn).provenance.source_url is None
