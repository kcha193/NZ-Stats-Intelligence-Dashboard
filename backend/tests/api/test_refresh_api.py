"""The refresh API: only the local dashboard can start a check, and nothing else (probes, GETs, startup) ever does."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.cli import main
from nzstats.config import load_settings
from nzstats.pipeline.refresh import RefreshCoordinator
from tests.conftest import fixture_bytes
from tests.pipeline.test_refresh import CALENDAR, seed_july_missing
from tests.support import BASE, NOW

ORIGIN = "http://127.0.0.1:8000"
DASHBOARD = {"Origin": ORIGIN, "X-NZStats-Client": "dashboard", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture()
def site(site):
    site.override(CALENDAR[3], 200, fixture_bytes("release_month_2026-10.json"), "application/json")
    return site


@pytest.fixture()
def settings(tmp_path):
    return load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_BASE_URL": BASE})


def no_network(settings):
    raise AssertionError("a check was started")


def client(
    settings, *, mode="on_open", factory=no_network, **kw
) -> tuple[TestClient, RefreshCoordinator]:
    coordinator = RefreshCoordinator(
        settings, runtime_factory=factory, now_fn=lambda: NOW, backup=None
    )
    app = create_app(settings, collection_mode=mode, refresh=coordinator, **kw)
    return TestClient(app, base_url=ORIGIN), coordinator


def runs(settings) -> int:
    import sqlite3

    conn = sqlite3.connect(settings.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM refresh_run").fetchone()[0]
    finally:
        conn.close()


def test_the_dashboard_starts_a_check_and_gets_its_status_at_once(rt, site) -> None:
    seed_july_missing(rt)
    c, coordinator = client(rt.settings, factory=lambda s: rt)
    first = c.post("/api/refresh", headers=DASHBOARD, json={})
    assert first.status_code == 200
    body = first.json()
    assert body["started"] is True and body["mode"] == "on_open" and body["state"] == "running"
    coordinator.join(30)
    done = c.get("/api/refresh/status").json()
    assert (done["state"], done["ingested"], done["started"]) == ("completed", 1, False)
    again = c.post("/api/refresh", headers=DASHBOARD, json={}).json()
    assert again["started"] is False and again["run_id"] == done["run_id"]  # reused, not repeated


@pytest.mark.parametrize("outcome", ["completed", "failed", "interrupted"])
def test_status_and_trigger_remain_valid_across_terminal_commit(rt, site, monkeypatch, outcome):
    import nzstats.pipeline.refresh as refresh

    if outcome == "failed":
        for url in CALENDAR:
            site.override(url, 503, b"", "text/html")
    if outcome == "interrupted":
        original = refresh.run_refresh

        def interrupted(*args, **kwargs):
            kwargs["stop"].set()
            return original(*args, **kwargs)

        monkeypatch.setattr(refresh, "run_refresh", interrupted)

    c, coordinator = client(rt.settings, factory=lambda _: rt)
    before, commit, after, release = (threading.Event() for _ in range(4))
    finish = coordinator._finish

    def gated_finish(run_id, result):
        before.set()
        assert commit.wait(10)
        finish(run_id, result)
        after.set()
        assert release.wait(10)

    coordinator._finish = gated_finish
    assert coordinator.trigger() and before.wait(10)
    try:
        for expected in ("running", outcome):
            if expected != "running":
                commit.set()
                assert after.wait(10)
            for _ in range(10):
                for response in (
                    c.get("/api/refresh/status"),
                    c.post("/api/refresh", headers=DASHBOARD, json={}),
                ):
                    assert response.status_code == 200
                    body = response.json()
                    assert body["state"] == expected
                    assert body["phase"] in (
                        ("checking", "downloading", "validating")
                        if expected == "running"
                        else (None,)
                    )
            row = rt.conn.execute(
                "SELECT state, phase FROM refresh_run ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert tuple(row) == (expected, "checking" if expected == "running" else "done")
    finally:
        commit.set()
        release.set()
        coordinator.join(10)


def test_check_now_is_sent_as_manual(rt, site) -> None:
    seed_july_missing(rt)
    c, coordinator = client(rt.settings, factory=lambda s: rt)
    c.post("/api/refresh", headers=DASHBOARD, json={"manual": True})
    coordinator.join(30)
    assert c.get("/api/refresh/status").json()["trigger"] == "manual"


@pytest.mark.parametrize(
    ("headers", "base"),
    [
        ({}, ORIGIN),  # a script or probe with no Origin
        ({**DASHBOARD, "Origin": "https://evil.example"}, ORIGIN),  # another site's page
        (
            {**DASHBOARD, "Origin": "http://localhost:8000"},
            ORIGIN,
        ),  # a different origin, even if local
        ({**DASHBOARD, "Origin": "null"}, ORIGIN),  # sandboxed frame or file://
        (
            {k: v for k, v in DASHBOARD.items() if k != "X-NZStats-Client"},
            ORIGIN,
        ),  # a plain form post
        ({**DASHBOARD, "Sec-Fetch-Site": "cross-site"}, ORIGIN),
        (
            {**DASHBOARD, "Origin": "http://evil.example:8000"},
            "http://evil.example:8000",
        ),  # DNS rebinding
        (
            {**DASHBOARD, "Origin": "http://192.168.1.5:8000"},
            "http://192.168.1.5:8000",
        ),  # from the LAN
    ],
)
def test_anything_but_the_local_dashboard_is_refused(settings, headers, base) -> None:
    c, _ = client(settings)
    c.base_url = base
    response = c.post("/api/refresh", headers=headers, json={})
    assert response.status_code == 403 and runs(settings) == 0


def test_a_cross_origin_preflight_gets_no_permission(settings) -> None:
    c, _ = client(settings)
    response = c.options(
        "/api/refresh",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-nzstats-client",
        },
    )
    assert "access-control-allow-origin" not in response.headers and runs(settings) == 0


def test_localhost_and_ipv6_loopback_dashboards_are_accepted(settings) -> None:
    for origin in ("http://localhost:8000", "http://[::1]:8000"):
        c, _ = client(settings, mode="off")
        c.base_url = origin
        assert (
            c.post("/api/refresh", headers={**DASHBOARD, "Origin": origin}, json={}).status_code
            == 200
        )


@pytest.mark.parametrize(
    "path",
    ["/api/health", "/api/ops/status", "/api/refresh/status", "/api/overview", "/", "/inflation"],
)
def test_probes_and_page_loads_never_start_a_check(settings, path) -> None:
    with client(settings)[0] as c:  # with the lifespan, as `serve` runs it
        c.get(path)
    assert runs(settings) == 0


def test_offline_mode_answers_without_any_network_activity(settings) -> None:
    c, _ = client(settings, mode="off")
    body = c.post("/api/refresh", headers=DASHBOARD, json={"manual": True}).json()
    assert (body["mode"], body["started"], body["state"]) == ("off", False, "never")
    assert runs(settings) == 0


def test_on_open_mode_never_starts_apscheduler(settings, monkeypatch) -> None:
    import nzstats.scheduler.jobs as jobs

    monkeypatch.setattr(jobs, "build_scheduler", lambda rt: pytest.fail("APScheduler was started"))
    c, _ = client(settings, record_ops=True)
    with c:
        assert c.get("/api/refresh/status").json()["mode"] == "on_open"
    import sqlite3

    conn = sqlite3.connect(settings.db_path)
    row = conn.execute("SELECT scheduler_enabled, collection_mode FROM ops_process").fetchone()
    conn.close()
    assert row == (0, "on_open")


def test_startup_marks_an_abandoned_check_interrupted(settings) -> None:
    import sqlite3

    from nzstats.store.db import connect, migrate

    conn = connect(settings.db_path)
    migrate(conn)
    conn.execute(
        "INSERT INTO refresh_run(trigger, started_at, state, phase) VALUES ('open', '2026-10-11T02:00:00Z', 'running', 'downloading')"
    )
    conn.close()
    c, _ = client(settings)
    assert c.get("/api/refresh/status").json()["state"] == "interrupted"
    assert (
        sqlite3.connect(settings.db_path).execute("SELECT state FROM refresh_run").fetchone()[0]
        == "interrupted"
    )


def test_serve_refuses_on_open_refresh_beyond_loopback(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path))
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: pytest.fail("served"))
    assert main(["serve", "--host", "0.0.0.0"]) == 2
    assert "loopback" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "mode"),
    [
        ([], "on_open"),
        (["--no-scheduler"], "off"),
        (["--offline"], "off"),
        (["--refresh", "off"], "off"),
        (["--refresh", "scheduler"], "scheduler"),
    ],
)
def test_serve_modes(monkeypatch, tmp_path, argv, mode) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path))
    import uvicorn

    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **k: seen.update(app=app, **k))
    assert main(["serve", "--host", "127.0.0.1", *argv]) == 0
    assert seen["app"].state.collection_mode == mode and seen["host"] == "127.0.0.1"
    assert (seen["app"].state.refresh is not None) is (mode == "on_open")


def test_the_container_keeps_its_scheduler_beyond_loopback(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path))
    import uvicorn

    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **k: seen.update(app=app))
    assert main(["serve", "--host", "0.0.0.0", "--refresh", "scheduler"]) == 0  # noqa: S104
    assert seen["app"].state.collection_mode == "scheduler"
