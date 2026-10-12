import csv
import io
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.clock import AKL
from nzstats.pipeline.discover import discover
from tests.conftest import FIXTURES
from tests.support import NOW, ingest_months


@pytest.fixture()
def client(rt):
    ids = ingest_months(rt, "2026-06", "2026-07")
    discover(rt, months=["2026-09", "2026-10"], now_fn=lambda: NOW)
    app = create_app(rt.settings)
    app.state.now = lambda: NOW  # deterministic "now" for the overview and calendar defaults
    with TestClient(app) as c:
        c.ids = ids
        yield c


def test_health(client) -> None:
    body = client.get("/api/health").json()
    assert body["database_ok"] is True
    sources = {s["source"]: s["state"] for s in body["sources"]}
    assert sources["release:international-migration"] == "ok"
    assert body["vintage_count"] > 0 and body["series_count"] > 10
    assert body["recent_runs"][0]["outcome"] in ("ingested", "unchanged")
    assert body["release_counts"].get("published", 0) >= 2


def test_releases_listing_and_filters(client) -> None:
    items = client.get("/api/releases").json()
    july = next(r for r in items if r["id"] == client.ids["2026-07"])
    assert july["has_analysis"] is True and july["category"] == "Migration"
    assert july["importance"] == "high" and july["published_at"].endswith("+12:00")
    assert items == sorted(items, key=lambda r: r["published_at"], reverse=True)
    only_sched = client.get("/api/releases", params={"status": "scheduled"}).json()
    assert only_sched and all(r["status"] == "scheduled" for r in only_sched)
    migration = client.get("/api/releases", params={"category": "Migration"}).json()
    assert migration and all(r["category"] == "Migration" for r in migration)
    assert len(client.get("/api/releases", params={"limit": 1}).json()) == 1


def test_release_detail_with_and_without_analysis(client) -> None:
    detail = client.get(f"/api/releases/{client.ids['2026-07']}").json()
    assert detail["analysis"]["executive_summary"] and detail["unavailable_reason"] is None
    scheduled = client.get(
        "/api/releases", params={"status": "scheduled", "category": "Migration"}
    ).json()
    assert scheduled, "the ICS fixture always lists upcoming migration releases"
    d2 = client.get(f"/api/releases/{scheduled[0]['id']}").json()
    assert d2["analysis"] is None and "Scheduled" in d2["unavailable_reason"]
    other = client.get("/api/releases", params={"status": "scheduled"}).json()
    non_migration = next(r for r in other if r["category"] != "Migration")
    reason = client.get(f"/api/releases/{non_migration['id']}").json()["unavailable_reason"]
    assert "not yet available" in reason
    assert client.get("/api/releases/987654").status_code == 404


def test_calendar_range_and_freshness(client) -> None:
    scheduled = client.get("/api/releases", params={"status": "scheduled"}).json()
    first_day = min(s["published_at"][:10] for s in scheduled)
    last_day = (date.fromisoformat(first_day) + timedelta(days=20)).isoformat()
    body = client.get("/api/calendar", params={"from": first_day, "to": last_day}).json()
    assert body["items"] and body["last_checked_at"] and body["last_success_at"]
    dates = [i["published_at"][:10] for i in body["items"]]
    assert dates == sorted(dates) and all(first_day <= d <= last_day for d in dates)
    for item in body["items"]:  # offsets follow Auckland daylight saving for that date
        stamp = datetime.fromisoformat(item["published_at"])
        assert stamp.utcoffset() == AKL.utcoffset(stamp.replace(tzinfo=None))
    assert client.get("/api/calendar", params={"from": "nonsense"}).status_code == 422


def test_calendar_bounds_are_inclusive_whole_auckland_days(client) -> None:
    scheduled = client.get("/api/releases", params={"status": "scheduled"}).json()
    day = min(s["published_at"][:10] for s in scheduled)
    before = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    after = (date.fromisoformat(day) + timedelta(days=1)).isoformat()

    def days(**params) -> list[str]:
        resp = client.get("/api/calendar", params=params)
        assert resp.status_code == 200
        return [i["published_at"][:10] for i in resp.json()["items"]]

    assert day in days(**{"from": day, "to": day})
    assert day not in days(**{"from": after, "to": "2100-01-01"})
    assert day not in days(**{"from": "2000-01-01", "to": before})


@pytest.mark.parametrize(
    ("params", "reference"),
    [
        ({"to": "9999-12-31"}, {"to": "2100-01-01"}),
        ({"from": "0001-01-01"}, {"from": "2000-01-01"}),
        (
            {"from": "0001-01-01", "to": "9999-12-31"},
            {"from": "2000-01-01", "to": "2100-01-01"},
        ),
    ],
)
def test_calendar_extreme_bounds_mean_unbounded_and_never_overflow(
    client, params, reference
) -> None:
    """Review #4245952779: date.max + 1 day (and date.min in UTC) used to raise OverflowError."""
    resp = client.get("/api/calendar", params=params)
    assert resp.status_code == 200
    ref = client.get("/api/calendar", params=reference).json()["items"]
    assert ref  # the comparison window holds the seeded releases
    assert resp.json()["items"] == ref


@pytest.mark.parametrize("day", ["0001-01-01", "9999-12-31"])
def test_calendar_single_extreme_day_is_empty_not_an_error(client, day) -> None:
    resp = client.get("/api/calendar", params={"from": day, "to": day})
    assert resp.status_code == 200 and resp.json()["items"] == []


def test_series_listing_and_data(client) -> None:
    listing = client.get("/api/series", params={"category": "migration"}).json()
    keys = {s["key"] for s in listing}
    assert {"mig.m.net", "mig.ry.net"} <= keys
    net = client.get("/api/series/mig.m.net").json()
    assert net["points"][-1] == {
        "period": "2026-07",
        "value": 5170.0,
        "status": "provisional",
        "std_error": 545.0,
        "released_in": "2026-07",
    }
    assert net["series"]["frequency"] == "monthly" and net["vintage"]["title"].endswith("July 2026")
    sliced = client.get("/api/series/mig.m.net", params={"from": "2026-01", "to": "2026-03"}).json()
    assert [p["period"] for p in sliced["points"]] == ["2026-01", "2026-02", "2026-03"]
    june_key = client.get(f"/api/releases/{client.ids['2026-06']}").json()["release"]["release_key"]
    june = client.get("/api/series/mig.m.net", params={"vintage": june_key}).json()
    assert june["vintage"]["title"].endswith("June 2026")
    assert client.get("/api/series/nope").status_code == 404
    assert client.get("/api/series/mig.m.net", params={"vintage": "nope"}).status_code == 404
    assert client.get("/api/series/mig.m.net", params={"from": "2026"}).status_code == 422


def test_series_csv_download(client) -> None:
    r = client.get("/api/series/mig.m.net/csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "mig.m.net.csv" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    df = pd.read_csv(FIXTURES / "im_2026-07_age_sex.csv")
    total = df[(df.sex == "TOTAL") & (df.age == "TOTAL") & (df.direction == "Net")]
    assert len(rows) == len(total)
    assert {"series_key", "unit", "period", "value", "status", "release", "source"} <= set(rows[0])
    assert "CC BY 4.0" in rows[0]["source"]


def test_revisions_endpoint(client) -> None:
    body = client.get("/api/revisions/mig.m.net").json()
    assert body["coverage"]["kind"] == "release_files" and body["n_revised"] > 0
    assert body["rows"] and body["history"]
    assert client.get("/api/revisions/nope").status_code == 404
    assert client.get("/api/revisions/mig.m.net", params={"base": "nope"}).status_code == 404


def test_countries_endpoint(client) -> None:
    body = client.get("/api/migration/countries", params={"months": 12, "top": 3}).json()
    assert body["available"] and len(body["countries"]) == 3 and body["derived"] is True
    assert client.get("/api/migration/countries", params={"months": 0}).status_code == 422


def test_overview(client) -> None:
    body = client.get("/api/overview").json()
    kpi = {k["metric"]["series_key"]: k for k in body["kpis"]}
    assert kpi["mig.ry.net"]["metric"]["period"] == "2026-07"
    assert kpi["mig.ry.net"]["source_url"].startswith("https://www.stats.govt.nz/")
    assert body["featured"]["release"]["id"] == client.ids["2026-07"]
    assert body["upcoming"] and all(
        u["status"] in ("scheduled", "delayed") for u in body["upcoming"]
    )
    assert {c["name"] for c in body["inactive_categories"]} >= {"Prices and inflation"}
    assert any(f["source"] == "calendar_ics" for f in body["freshness"])


def test_openapi_builds(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/overview" in paths and "/api/series/{key}/csv" in paths


# --- the CSV export neutralises formulas (review #4246208524) -----------------------------------

FORMULAS = ['=HYPERLINK("http://evil.example","x")', "+1+1", "-2+3", "@SUM(1)", " =1+1", "\t=1+1"]


@pytest.mark.parametrize("title", FORMULAS)
def test_series_csv_neutralises_formula_like_text_from_upstream(client, rt, title) -> None:
    rt.conn.execute("UPDATE release SET title = ? WHERE id = ?", (title, client.ids["2026-07"]))
    resp = client.get("/api/series/mig.m.net/csv")
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert rows and {r["release"] for r in rows} == {"'" + title}


def test_series_csv_leaves_ordinary_text_and_numbers_alone(client) -> None:
    rows = list(csv.DictReader(io.StringIO(client.get("/api/series/mig.m.net/csv").text)))
    assert rows[0]["release"].startswith("International migration")
    assert not any(c.startswith("'") for r in rows for c in r.values())
