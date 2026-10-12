import json
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


# --- stale feeds cannot undo a reschedule (review #4245952774 / #4246141425) --------------------

AUGUST = "international-migration:august 2026"
ICS = f"{BASE}/release-calendar/calendar-export/"
MONTH = f"{BASE}/api/v1/releaseCalendarMonth/2026-10"
NEW_SLOT_UTC = "2026-10-19T21:45:00Z"  # 20 Oct 2026 10:45 NZDT
OLD_SLOT_UTC = "2026-10-13T21:45:00Z"  # 14 Oct 2026 10:45 NZDT


def _move_in_ics(site, to_day: str) -> None:
    status, body, ctype = site.routes[ICS]
    text = body.decode("utf-8")
    start = text.index("UID:8364@")
    end = text.index("END:VEVENT", start)
    block = text[start:end].replace("20261014T104500", f"{to_day}T104500")
    site.override(ICS, status, (text[:start] + block + text[end:]).encode(), ctype)


def _move_in_month(site, to_stamp: str) -> None:
    status, body, ctype = site.routes[MONTH]
    payload = json.loads(body)
    for item in payload["items"]["upcoming"]:
        if item["DisplayName"] == "International migration: August 2026":
            item["PublicationDate"] = to_stamp
    site.override(MONTH, status, json.dumps(payload).encode(), ctype)


def _go_unavailable(rt) -> None:
    discover(rt, months=["2026-10"], now_fn=lambda: NOW)
    assert repo.get_release(rt.conn, AUGUST)["published_at"] == OLD_SLOT_UTC
    repo.set_release_status(rt.conn, AUGUST, ReleaseStatus.UNAVAILABLE, NOW)


def test_fresh_ics_slot_survives_a_stale_month_feed_read_afterwards(rt, site) -> None:
    _go_unavailable(rt)
    _move_in_ics(site, "20261020")  # month feed still lists the old 14 Oct slot
    for _ in range(2):  # and stays put on later discovery runs
        discover(rt, months=["2026-10"], now_fn=lambda: NOW)
        row = repo.get_release(rt.conn, AUGUST)
        assert (row["status"], row["published_at"]) == ("delayed", NEW_SLOT_UTC)


def test_fresh_month_slot_survives_a_stale_ics_feed_read_before_it(rt, site) -> None:
    _go_unavailable(rt)
    _move_in_month(site, "2026-10-20 10:45:00")  # ICS (refreshed daily) still lists 14 Oct
    for _ in range(2):
        discover(rt, months=["2026-10"], now_fn=lambda: NOW)
        row = repo.get_release(rt.conn, AUGUST)
        assert (row["status"], row["published_at"]) == ("delayed", NEW_SLOT_UTC)
