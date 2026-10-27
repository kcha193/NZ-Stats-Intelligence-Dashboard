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
from nzstats.insights.cpi import build_cpi_dashboard
from nzstats.insights.ect import build_ect_dashboard
from nzstats.pipeline.ingest import ingest_release
from nzstats.runtime import build_runtime
from tests.cpi_support import NOW as CPI_NOW
from tests.cpi_support import ingest_cpi
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


def dump_cpi_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        site = FakeSite()
        rt = build_runtime(load_settings({"NZSTATS_DATA_DIR": tmp}), fetcher=site.fetcher())
        ids = ingest_cpi(rt, site, "2026-03", "2026-06")
        payload = build_cpi_dashboard(rt.conn).model_dump(mode="json")
        # Keep real observations and provenance, limiting only fixture size. API retains full history.
        for series in payload["series"]:
            series["points"] = [p for p in series["points"] if p["period"] >= "2012-03"]
        (OUT / "cpi.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
        assert payload["analysis"]["release"]["id"] == ids["2026-06"] and CPI_NOW


def dump_research_fixtures() -> None:
    """SYNTHETIC research responses (fictional institutions) from scripts/seed_research_demo.py, served by the real API."""
    from nzstats.research.api import research_router
    from nzstats.research.registry import load_registry

    sys.path.insert(0, str(ROOT / "scripts"))
    from seed_e2e_db import seed_cpi_from_fixtures
    from seed_research_demo import main as seed_research

    with tempfile.TemporaryDirectory() as tmp:
        seed_cpi_from_fixtures(Path(tmp))  # real CPI releases, so forecast evaluation has official outcomes
        seed_research(Path(tmp))
        registry = load_registry(Path(tmp) / "research_sources.synthetic.toml")
        app = create_app(
            load_settings({"NZSTATS_DATA_DIR": tmp}),
            routers=[research_router(enabled=True, registry=lambda: registry)],
        )
        with TestClient(app) as c:
            feed = c.get("/api/research/feed").json()
            by_key: dict[str, int] = {}
            for item in feed["items"]:  # newest first: each institution's newest document
                by_key.setdefault(item["institution"]["key"], item["id"])
            payloads = {
                "research_synthetic_feed": feed,
                "research_synthetic_forecasts": c.get("/api/research/forecasts").json(),
                "research_synthetic_forecasts_gdp": c.get(
                    "/api/research/forecasts", params={"indicator": "gdp"}
                ).json(),
                "research_synthetic_detail_excerpt": c.get(
                    f"/api/research/summaries/{by_key['harbourside']}"
                ).json(),
                "research_synthetic_detail_summary": c.get(
                    f"/api/research/summaries/{by_key['southern']}"
                ).json(),
                "research_synthetic_detail_link_only": c.get(
                    f"/api/research/summaries/{by_key['tasman']}"
                ).json(),
                "research_synthetic_history": c.get("/api/research/forecast-history").json(),
                "research_synthetic_evaluation": c.get(
                    "/api/research/forecast-evaluation", params={"indicator": "cpi_inflation"}
                ).json(),
                "research_synthetic_evaluation_gdp": c.get(
                    "/api/research/forecast-evaluation", params={"indicator": "gdp"}
                ).json(),
                "research_synthetic_consensus": c.get("/api/research/consensus").json(),
            }
        for name, payload in payloads.items():
            (OUT / f"{name}.json").write_text(json.dumps(payload, indent=1) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dump_research_fixtures()
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
                "series_net_nz_ry": "/api/series/mig.ry.net.nz",
                "series_net_nonnz_ry": "/api/series/mig.ry.net.nonnz",
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
    only = [a for a in sys.argv[1:] if a.endswith("-only")]
    if not only:
        main()
    if not only or "--ect-only" in only:
        dump_ect_fixture()
    if not only or "--cpi-only" in only:
        dump_cpi_fixture()
