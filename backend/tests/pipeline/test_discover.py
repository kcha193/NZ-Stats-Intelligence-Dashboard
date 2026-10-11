from datetime import UTC, datetime

from nzstats.domain import ReleaseStatus
from nzstats.pipeline.discover import current_and_next_months, discover
from nzstats.store import repo
from tests.support import BASE, NOW, release_ref_for


def test_current_and_next_months_use_auckland_calendar() -> None:
    # 2026-09-30 20:00 UTC is already 1 Oct in Auckland (NZDT, UTC+13)
    assert current_and_next_months(datetime(2026, 9, 30, 20, tzinfo=UTC)) == ["2026-10", "2026-11"]
    assert current_and_next_months(datetime(2026, 12, 20, tzinfo=UTC)) == ["2026-12", "2027-01"]


def test_discover_upserts_calendar_and_months_idempotently(rt) -> None:
    first = discover(rt, months=["2026-09"], now_fn=lambda: NOW)
    n = rt.conn.execute("SELECT COUNT(*) FROM release").fetchone()[0]
    second = discover(rt, months=["2026-09"], now_fn=lambda: NOW)
    assert first.refs > 0 and not first.errors and not second.errors
    assert rt.conn.execute("SELECT COUNT(*) FROM release").fetchone()[0] == n
    health = {r["source"]: r["state"] for r in rt.conn.execute("SELECT * FROM source_health")}
    assert health == {"calendar_ics": "ok", "calendar_month": "ok"}


def test_ics_failure_degrades_health_but_month_endpoint_still_runs(rt, site) -> None:
    site.override(f"{BASE}/release-calendar/calendar-export/", 403, b"", "text/html")
    result = discover(rt, months=["2026-09"], now_fn=lambda: NOW)
    assert len(result.errors) == 1 and "blocked" in result.errors[0]
    health = {r["source"]: r["state"] for r in rt.conn.execute("SELECT * FROM source_health")}
    assert health["calendar_ics"] == "degraded" and health["calendar_month"] == "ok"
    assert rt.conn.execute("SELECT COUNT(*) FROM release").fetchone()[0] > 0


def test_calendar_never_downgrades_a_published_release(rt) -> None:
    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)
    discover(rt, months=[], now_fn=lambda: NOW)  # ICS lists only upcoming events
    row = repo.get_release(rt.conn, ref.release_key)
    assert row["status"] == ReleaseStatus.PUBLISHED.value
