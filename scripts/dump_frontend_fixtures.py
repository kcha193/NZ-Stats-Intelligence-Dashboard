"""Write API responses (from the seeded demo DB) as frontend test fixtures.

Usage: cd backend && python ../scripts/dump_frontend_fixtures.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient
from nzstats.api.app import create_app
from nzstats.config import load_settings
from nzstats.insights.ect import build_ect_dashboard
from nzstats.pipeline.ingest import ingest_release
from nzstats.runtime import build_runtime
from tests.ect_support import NOW as ECT_NOW
from tests.ect_support import seed_ect
from tests.support import BASE, NOW, FakeSite, seed_from_fixtures

OUT = ROOT / "frontend" / "src" / "test" / "fixtures"


def dump_ect_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        site = FakeSite()
        rt = build_runtime(
            load_settings({"NZSTATS_DATA_DIR": tmp}), fetcher=site.fetcher()
        )
        for month in ("2026-08", "2026-09"):
            _, key, _ = seed_ect(rt, site, month)
            result = ingest_release(rt, key, now_fn=lambda: ECT_NOW)
            assert result.outcome == "ingested", result.detail
        payload = build_ect_dashboard(rt.conn).model_dump(mode="json")
        # Keep real observations and provenance, limiting only fixture size. API retains full history.
        for series in payload["series"]:
            series["points"] = [p for p in series["points"] if p["period"] >= "2021-09"]
        (OUT / "ect.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        seed_from_fixtures(tmp)
        settings = load_settings({"NZSTATS_DATA_DIR": tmp, "NZSTATS_BASE_URL": BASE})
        app = create_app(settings)
        app.state.now = lambda: NOW
        with TestClient(app) as c:
            releases = c.get("/api/releases").json()
            july = next(
                r
                for r in releases
                if r["title"].endswith("July 2026") and r["has_analysis"]
            )
            scheduled = c.get("/api/releases", params={"status": "scheduled"}).json()
            payloads = {
                "overview": "/api/overview",
                "releases": "/api/releases",
                "release_detail": f"/api/releases/{july['id']}",
                "calendar": "/api/calendar",
                "series_net_m": "/api/series/mig.m.net",
                "series_net_ry": "/api/series/mig.ry.net",
                "series_arrivals_ry": "/api/series/mig.ry.arrivals",
                "series_departures_ry": "/api/series/mig.ry.departures",
                "countries": "/api/migration/countries",
                "revisions": "/api/revisions/mig.m.net",
                "health": "/api/health",
            }
            for name, url in payloads.items():
                (OUT / f"{name}.json").write_text(
                    json.dumps(c.get(url).json(), indent=1)
                )
            (OUT / "release_scheduled.json").write_text(
                json.dumps(
                    c.get(f"/api/releases/{scheduled[0]['id']}").json(), indent=1
                )
            )
    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    if "--ect-only" not in sys.argv:
        main()
    dump_ect_fixture()
