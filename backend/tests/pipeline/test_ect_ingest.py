import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.pipeline.ingest import ingest_release
from nzstats.store import repo
from tests.ect_support import NOW, seed_ect


def test_ect_registered_ingests_and_is_idempotent(rt, site):
    assert "electronic-card-transactions" in rt.adapters
    rid, key, url = seed_ect(rt, site)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    n = rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0]
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "unchanged"
    assert rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0] == n
    assert len(repo.latest_points(rt.conn, "ect.m.sa.retail.value")) >= 36
    assert rt.conn.execute("SELECT COUNT(*) FROM raw_artifact").fetchone()[0] == 2
    # Malformed replacement fails without changing the last valid bundle or measurements.
    before = repo.release_bundle(rt.conn, rid)
    site.routes[url] = (200, b"broken", "application/zip")
    outcome = ingest_release(rt, key, now_fn=lambda: NOW)
    assert outcome.outcome == "failed"
    assert repo.release_bundle(rt.conn, rid) == before
    assert rt.conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0] == n
    assert (
        rt.conn.execute(
            "SELECT state FROM source_health WHERE source='release:electronic-card-transactions'"
        ).fetchone()[0]
        == "degraded"
    )


def test_real_previous_release_records_revisions_and_scheduler_catches_ect(rt, site):
    from nzstats.insights.revisions import revision_view
    from nzstats.scheduler.jobs import job_catch_up

    rid, old, _ = seed_ect(rt, site, "2026-08")
    assert ingest_release(rt, old, now_fn=lambda: NOW).outcome == "ingested"
    _, new, _ = seed_ect(rt, site)
    outcomes = job_catch_up(rt, now_fn=lambda: NOW)
    assert any(o.release_key == new and o.outcome == "ingested" for o in outcomes)
    view = revision_view(rt.conn, "ect.m.sa.retail.value")
    assert view.n_revised > 0 and view.coverage.n_vintages == 2


def test_ect_api_analysis_overview_calendar_and_freshness(rt, site):
    rid, key, _ = seed_ect(rt, site)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    app = create_app(rt.settings)
    app.state.now = lambda: NOW
    with TestClient(app) as client:
        detail = client.get(f"/api/releases/{rid}").json()
        assert detail["release"]["has_analysis"]
        assert detail["analysis"]["headline_metrics"][0]["series_key"] == "ect.m.sa.retail.value"
        retail = detail["analysis"]["headline_metrics"][0]
        assert retail["change_prior"]["percent"] == pytest.approx(-0.4, abs=0.05)
        assert retail["change_prior"]["absolute"] == pytest.approx(-30, abs=0.5)
        assert detail["analysis"]["revisions"]["available"] is False
        dashboard = client.get("/api/ect").json()
        assert dashboard["analysis"]["release"]["id"] == rid
        assert any(s["series"]["frequency"] == "quarterly" for s in dashboard["series"])
        assert all(s["vintage"]["release_key"] == key for s in dashboard["series"])
        overview = client.get("/api/overview").json()
        assert any(k["metric"]["series_key"] == "ect.m.sa.retail.value" for k in overview["kpis"])
        assert any(
            r["id"] == rid and r["has_analysis"]
            for r in client.get("/api/calendar").json()["items"]
        )
        assert any(
            s["source"] == "release:electronic-card-transactions" and s["last_success_at"]
            for s in client.get("/api/health").json()["sources"]
        )


def test_ect_api_empty_is_explicit(rt):
    with TestClient(create_app(rt.settings)) as client:
        assert client.get("/api/ect").status_code == 404


def test_scoped_backfill_never_downloads_migration(rt, site):
    from nzstats.pipeline.ingest import backfill
    from tests.support import release_ref_for

    _, key, _ = seed_ect(rt, site)
    repo.upsert_release(rt.conn, release_ref_for("2026-07"), NOW)
    results = backfill(
        rt,
        since="2026-09",
        until="2026-09",
        series_slug="electronic-card-transactions",
        now_fn=lambda: NOW,
    )
    assert any(o.release_key == key and o.outcome == "ingested" for o in results)
    assert not any("international-migration" in u for u in site.requests)


def test_failed_database_write_rolls_back_all_ect_series(rt, site, monkeypatch):
    _, key, _ = seed_ect(rt, site)
    original = repo.insert_observations
    calls = 0

    def failing_insert(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected storage failure")
        return original(*args)

    monkeypatch.setattr(repo, "insert_observations", failing_insert)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "failed"
    for table in ("series", "vintage", "observation", "vintage_series_definition"):
        assert rt.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_analysis_does_not_claim_an_increase_or_decrease_for_unchanged_industries(rt, site):
    from nzstats.adapters.ect.series import INDUSTRIES
    from nzstats.insights.ect import build_ect_dashboard

    _, key, _ = seed_ect(rt, site)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    for industry, _ in INDUSTRIES.values():
        vid = repo.list_vintages(rt.conn, f"ect.m.sa.{industry}.value")[-1].vintage_id
        rt.conn.execute(
            "UPDATE observation SET value=(SELECT value FROM observation WHERE vintage_id=? AND period='2026-08') WHERE vintage_id=? AND period='2026-09'",
            (vid, vid),
        )
    text = next(
        i.text
        for i in build_ect_dashboard(rt.conn).analysis.executive_summary
        if i.id == "industry"
    )
    assert "increase" not in text.lower() and "decrease" not in text.lower()
