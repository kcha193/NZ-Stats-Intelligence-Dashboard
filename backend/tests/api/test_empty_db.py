from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.config import load_settings


def test_every_endpoint_renders_an_empty_state(tmp_path) -> None:
    settings = load_settings({"NZSTATS_DATA_DIR": str(tmp_path)})
    with TestClient(create_app(settings)) as c:
        overview = c.get("/api/overview").json()
        assert overview["kpis"] == [] and overview["featured"] is None
        assert overview["latest_releases"] == [] and overview["upcoming"] == []
        assert c.get("/api/releases").json() == []
        assert c.get("/api/calendar").json()["items"] == []
        assert c.get("/api/series").json() == []
        health = c.get("/api/health").json()
        assert health["database_ok"] and health["vintage_count"] == 0
        countries = c.get("/api/migration/countries").json()
        assert countries["available"] is False and "No country data" in countries["note"]
        assert c.get("/api/series/mig.m.net").status_code == 404
