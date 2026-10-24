import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.config import load_settings
from nzstats.publish.snapshot import (
    FixtureDataError,
    MissingDataError,
    export_snapshot,
)
from tests.publish.conftest import EXPORT_NOW


def read(snapshot: Path, name: str) -> dict:
    return json.loads((snapshot / name).read_text(encoding="utf-8"))


def test_fixture_data_is_refused_unless_explicitly_allowed(full_dir, tmp_path):
    with pytest.raises(FixtureDataError):
        export_snapshot(full_dir, tmp_path / "out", now=EXPORT_NOW)
    assert not (tmp_path / "out").exists()


def test_an_allowed_fixture_export_is_labelled_fixture_origin(snapshot):
    assert read(snapshot, "manifest.json")["origin"] == "fixture"


def test_writes_one_enveloped_file_per_endpoint_and_a_manifest(snapshot):
    manifest = read(snapshot, "manifest.json")
    assert manifest["schema_version"] == 1
    for name in (
        "overview.json",
        "cpi.json",
        "ect.json",
        "health.json",
        "releases.json",
        "calendar.json",
        "migration/countries.json",
        "series/mig.m.net.json",
        "series/mig.ry.net.nz.json",
        "revisions/mig.m.net.json",
    ):
        assert name in manifest["files"], name
        env = read(snapshot, name)
        assert env["schema_version"] == 1 and env["snapshot_id"] == manifest["snapshot_id"]
        assert "payload" in env
    assert manifest["generated_at"] == "2026-10-24T08:00:00Z"
    assert manifest["attribution"]["licence"] == "CC BY 4.0"
    assert (
        manifest["data_updated_at"] == read(snapshot, "overview.json")["payload"]["data_updated_at"]
    )


def test_payloads_are_exactly_what_the_live_api_serves(full_dir, snapshot, tmp_path):
    """The exporter must not reimplement anything: every payload equals the API's own response."""
    from nzstats.publish.snapshot import _copy_database

    copy = tmp_path / "live"
    _copy_database(full_dir / "nzstats.db", copy)
    app = create_app(load_settings({"NZSTATS_DATA_DIR": str(copy)}))
    app.state.now = lambda: EXPORT_NOW
    with TestClient(app) as api:
        assert read(snapshot, "cpi.json")["payload"] == api.get("/api/cpi").json()
        assert read(snapshot, "ect.json")["payload"] == api.get("/api/ect").json()
        assert (
            read(snapshot, "series/mig.ry.net.json")["payload"]
            == api.get("/api/series/mig.ry.net").json()
        )
        assert (
            read(snapshot, "revisions/mig.m.net.json")["payload"]
            == api.get("/api/revisions/mig.m.net").json()
        )
        assert (
            read(snapshot, "migration/countries.json")["payload"]
            == api.get("/api/migration/countries", params={"months": 12, "top": 15}).json()
        )
        listing = read(snapshot, "releases.json")["payload"]
        assert listing == api.get("/api/releases", params={"limit": 200}).json()
        first = listing[0]["id"]
        assert (
            read(snapshot, f"releases/{first}.json")["payload"]
            == api.get(f"/api/releases/{first}").json()
        )


def test_every_release_has_a_detail_file(snapshot):
    listing = read(snapshot, "releases.json")["payload"]
    assert listing and all((snapshot / "releases" / f"{r['id']}.json").exists() for r in listing)


def test_provisional_and_final_status_and_revision_semantics_survive(snapshot):
    points = read(snapshot, "series/mig.m.net.json")["payload"]["points"]
    assert {p["status"] for p in points} >= {"provisional", "final"}
    assert all("released_in" in p for p in points)
    rev = read(snapshot, "revisions/mig.m.net.json")["payload"]
    assert rev["coverage"]["n_vintages"] >= 2 and rev["history"]


def test_health_is_reduced_to_public_freshness(snapshot):
    health = read(snapshot, "health.json")["payload"]
    assert health["recent_runs"] == []
    assert all(s["detail"] is None for s in health["sources"])
    assert all(s["detail"] is None for s in read(snapshot, "overview.json")["payload"]["freshness"])


def test_snapshot_id_ignores_export_time_but_not_content(full_dir, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    export_snapshot(full_dir, a, now=EXPORT_NOW, allow_fixtures=True)
    export_snapshot(full_dir, b, now=datetime(2026, 10, 24, 9, 30, tzinfo=UTC), allow_fixtures=True)
    ma, mb = read(a, "manifest.json"), read(b, "manifest.json")
    assert ma["generated_at"] != mb["generated_at"]
    assert ma["snapshot_id"] == mb["snapshot_id"]
    assert (
        read(a, "overview.json")["payload"]["generated_at"]
        != read(b, "overview.json")["payload"]["generated_at"]
    )


def test_no_private_text_reaches_the_output(full_dir, snapshot):
    blob = "\n".join(p.read_text(encoding="utf-8") for p in snapshot.rglob("*.json"))
    assert str(full_dir) not in blob and "nzstats.db" not in blob
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", blob)
    assert "Traceback" not in blob


def test_missing_expected_categories_fail_the_export_and_leave_nothing(
    migration_only_dir, tmp_path
):
    from tests.publish.test_provenance import FIXTURE_MARKER  # noqa: F401 (marker is present)

    out = tmp_path / "out"
    with pytest.raises(MissingDataError) as err:
        export_snapshot(migration_only_dir, out, now=EXPORT_NOW, allow_fixtures=True)
    assert "cpi" in str(err.value).lower() and "ect" in str(err.value).lower()
    assert not out.exists()


def test_the_source_database_is_not_modified(full_dir, tmp_path):
    db = full_dir / "nzstats.db"
    before = db.stat().st_mtime_ns, db.read_bytes()
    export_snapshot(full_dir, tmp_path / "out", now=EXPORT_NOW, allow_fixtures=True)
    assert (db.stat().st_mtime_ns, db.read_bytes()) == before


def _fail_a_release_with_secret_text(data_dir: Path, marker: str) -> None:
    """A published release whose latest ingestion failed with an error message that must stay private."""
    import sqlite3

    db = sqlite3.connect(data_dir / "nzstats.db")
    db.execute(
        "INSERT INTO release (release_key, series_slug, title, period_label, reference_period, published_at,"
        " status, first_seen_at, updated_at) VALUES ('international-migration:march 2025',"
        " 'international-migration', 'International migration: March 2025', 'March 2025', '2025-03',"
        " '2025-04-14T10:45:00Z', 'published', '2026-10-14T00:00:00Z', '2026-10-14T00:00:00Z')"
    )
    db.execute(
        "INSERT INTO ingest_run (release_key, started_at, finished_at, outcome, error_class, detail)"
        " VALUES ('international-migration:march 2025', '2026-10-14T11:00:00Z', '2026-10-14T11:00:05Z',"
        f" 'failed', 'validation_failed', '{marker}')"
    )
    db.commit()
    db.close()


def test_ingestion_error_text_never_reaches_the_snapshot(production_dir, tmp_path):
    marker = "PRIVATE-ERROR-DETAIL-7f3a"
    _fail_a_release_with_secret_text(production_dir, marker)
    out = tmp_path / "out"
    export_snapshot(production_dir, out, now=EXPORT_NOW)
    blob = "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*.json"))
    assert marker not in blob and "validation_failed" not in blob
    failed = next(
        r
        for r in read(out, "releases.json")["payload"]
        if r["title"] == "International migration: March 2025"
    )
    reason = read(out, f"releases/{failed['id']}.json")["payload"]["unavailable_reason"]
    assert reason and "not been verified" in reason
