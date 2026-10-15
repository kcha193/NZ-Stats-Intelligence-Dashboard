import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nzstats.clock import parse_akl_naive
from nzstats.domain import (
    Adjustment,
    Frequency,
    Observation,
    ObsStatus,
    Point,
    ReleaseRef,
    ReleaseStatus,
    SeriesDef,
)
from nzstats.store import repo
from nzstats.store.db import connect, migrate, transaction

NOW = datetime(2026, 10, 11, 3, 0, tzinfo=UTC)


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "t.db")
    migrate(c)
    return c


def _ref(
    key="international-migration:august 2026",
    at="2026-10-14 10:45:00",
    status=ReleaseStatus.SCHEDULED,
    **kw,
) -> ReleaseRef:
    return ReleaseRef(
        release_key=key,
        series_slug="international-migration",
        title="International migration: August 2026",
        period_label="August 2026",
        reference_period="2026-08",
        published_at=parse_akl_naive(at),
        status=status,
        **kw,
    )


def _series(key="mig.m.net") -> SeriesDef:
    return SeriesDef(
        key,
        "Net migration",
        "people",
        Frequency.MONTHLY,
        Adjustment.NONE,
        "def",
        "mig",
        "migration",
    )


def test_upsert_release_is_idempotent(conn) -> None:
    a = repo.upsert_release(conn, _ref(), NOW)
    b = repo.upsert_release(conn, _ref(), NOW)
    assert a == b
    assert conn.execute("SELECT COUNT(*) FROM release").fetchone()[0] == 1


def test_published_is_never_downgraded_to_scheduled(conn) -> None:
    repo.upsert_release(conn, _ref(status=ReleaseStatus.PUBLISHED, page_url="http://p"), NOW)
    repo.upsert_release(conn, _ref(status=ReleaseStatus.SCHEDULED), NOW)
    row = repo.get_release(conn, "international-migration:august 2026")
    assert row["status"] == "published" and row["page_url"] == "http://p"


def test_later_scheduled_time_marks_release_delayed(conn) -> None:
    repo.upsert_release(conn, _ref(at="2026-10-14 10:45:00"), NOW)
    repo.upsert_release(conn, _ref(at="2026-10-16 10:45:00"), NOW)
    row = repo.get_release(conn, "international-migration:august 2026")
    assert row["status"] == "delayed"
    assert row["published_at"] == "2026-10-15T21:45:00Z"


def test_vintage_idempotent_and_observations(conn) -> None:
    rid = repo.upsert_release(conn, _ref(), NOW)
    sid = repo.upsert_series(conn, _series())
    with transaction(conn):
        vid = repo.create_vintage(conn, rid, sid, NOW, "release_files", "v1", "sha-a")
        n = repo.insert_observations(
            conn,
            vid,
            [
                Observation(
                    "mig.m.net", "2026-07", 5170.0, ObsStatus.PROVISIONAL, 545.0, "2026-07"
                ),
                Observation("mig.m.net", "2026-06", 100.0, ObsStatus.FINAL, 0.0, "2020-09"),
            ],
        )
    assert n == 2
    assert repo.has_vintage(conn, rid, "sha-a") and not repo.has_vintage(conn, rid, "sha-b")
    assert repo.create_vintage(conn, rid, sid, NOW, "release_files", "v1", "sha-a") is None
    pts = repo.latest_points(conn, "mig.m.net")
    assert pts["2026-07"] == Point("2026-07", 5170.0, ObsStatus.PROVISIONAL)


def test_latest_and_previous_points_follow_release_order(conn) -> None:
    sid = repo.upsert_series(conn, _series())
    june = _ref("im:june", "2026-07-14 10:45:00")
    july = _ref("im:july", "2026-08-14 10:45:00")
    rj = repo.upsert_release(conn, june, NOW)
    rl = repo.upsert_release(conn, july, NOW)
    with transaction(conn):
        # insert the newer release first: ordering must follow publication time, not insert order
        vl = repo.create_vintage(conn, rl, sid, NOW, "release_files", "v1", "s2")
        repo.insert_observations(
            conn, vl, [Observation("mig.m.net", "2026-05", 120.0, ObsStatus.FINAL)]
        )
        vj = repo.create_vintage(conn, rj, sid, NOW, "release_files", "v1", "s1")
        repo.insert_observations(
            conn, vj, [Observation("mig.m.net", "2026-05", 100.0, ObsStatus.PROVISIONAL)]
        )
    assert repo.latest_points(conn, "mig.m.net")["2026-05"].value == 120.0
    before_july = repo.previous_points(conn, "mig.m.net", july.published_at)
    assert before_july["2026-05"].value == 100.0
    assert repo.previous_points(conn, "mig.m.net", june.published_at) == {}
    infos = repo.list_vintages(conn, "mig.m.net")
    assert [i.release_key for i in infos] == ["im:june", "im:july"]
    assert infos[0].title == "International migration: August 2026"


def test_orphan_observation_is_rejected(conn) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO observation(vintage_id, period, value, status) "
            "VALUES (999, '2026-01', 1, 'final')"
        )


def test_ingest_run_and_health(conn) -> None:
    repo.record_ingest_run(
        conn,
        "k",
        NOW,
        NOW + timedelta(seconds=3),
        "failed",
        "validation_failed",
        "net != arrivals - departures",
    )
    repo.set_source_health(conn, "calendar_ics", NOW, ok=True, detail=None)
    repo.set_source_health(conn, "calendar_ics", NOW + timedelta(hours=1), ok=False, detail="x")
    row = conn.execute("SELECT * FROM source_health WHERE source='calendar_ics'").fetchone()
    assert row["state"] == "degraded"
    assert row["last_success_at"] == "2026-10-11T03:00:00Z"
    assert row["last_checked_at"] == "2026-10-11T04:00:00Z"
    assert conn.execute("SELECT COUNT(*) FROM ingest_run").fetchone()[0] == 1


# --- unavailable releases accept a reschedule (review #4245952774) ------------------------------

KEY = "international-migration:august 2026"


def _unavailable(conn, at="2026-10-14 10:45:00") -> None:
    repo.upsert_release(conn, _ref(at=at), NOW)
    repo.set_release_status(conn, KEY, ReleaseStatus.UNAVAILABLE, NOW)


def test_unavailable_release_moved_later_becomes_delayed_with_the_new_time(conn) -> None:
    _unavailable(conn)
    repo.upsert_release(conn, _ref(at="2026-11-20 10:45:00"), NOW)
    row = repo.get_release(conn, KEY)
    assert row["status"] == "delayed"
    assert row["published_at"] == "2026-11-19T21:45:00Z"


def test_an_unpublished_release_never_moves_to_an_earlier_slot(conn) -> None:
    """Review #4246141425: feeds disagree about freshness, so the latest reported slot wins.

    Whichever feed is read second, a stale (earlier) slot must not rewind a reschedule. A release
    that really comes out early is picked up when the calendar lists it as published.
    """
    for status in (ReleaseStatus.SCHEDULED, ReleaseStatus.DELAYED, ReleaseStatus.UNAVAILABLE):
        key = f"international-migration:{status.value} 2026"
        repo.upsert_release(conn, _ref(key=key, at="2026-10-20 10:45:00"), NOW)
        repo.set_release_status(conn, key, status, NOW)
        repo.upsert_release(conn, _ref(key=key, at="2026-10-14 10:45:00"), NOW)
        row = repo.get_release(conn, key)
        assert (row["status"], row["published_at"]) == (status.value, "2026-10-19T21:45:00Z")


def test_slot_converges_on_the_latest_report_in_any_feed_order(conn) -> None:
    for order in (("2026-10-20", "2026-10-14"), ("2026-10-14", "2026-10-20")):
        key = f"international-migration:order {order[0]}"
        repo.upsert_release(conn, _ref(key=key, at="2026-10-14 10:45:00"), NOW)
        repo.set_release_status(conn, key, ReleaseStatus.UNAVAILABLE, NOW)
        for day in order * 2:
            repo.upsert_release(conn, _ref(key=key, at=f"{day} 10:45:00"), NOW)
        row = repo.get_release(conn, key)
        assert (row["status"], row["published_at"]) == ("delayed", "2026-10-19T21:45:00Z")


def test_unavailable_release_stays_unavailable_while_the_calendar_repeats_the_same_time(
    conn,
) -> None:
    """Every discovery run re-lists the original slot; that must not undo the polling verdict."""
    _unavailable(conn)
    repo.upsert_release(conn, _ref(at="2026-10-14 10:45:00"), NOW)
    row = repo.get_release(conn, KEY)
    assert row["status"] == "unavailable"
    assert row["published_at"] == "2026-10-13T21:45:00Z"


def test_unavailable_release_that_is_now_published_becomes_published(conn) -> None:
    _unavailable(conn)
    repo.upsert_release(conn, _ref(status=ReleaseStatus.PUBLISHED, at="2026-10-14 10:45:00"), NOW)
    assert repo.get_release(conn, KEY)["status"] == "published"


def test_reactivating_an_older_bundle_makes_it_the_latest_without_duplicating_rows(conn) -> None:
    rid = repo.upsert_release(conn, _ref(), NOW)
    sid = repo.upsert_series(conn, _series())
    with transaction(conn):
        for sha, value in (("sha-a", 1.0), ("sha-b", 2.0)):
            vid = repo.create_vintage(conn, rid, sid, NOW, "release_files", "v1", sha)
            repo.insert_observations(
                conn, vid, [Observation("mig.m.net", "2026-07", value, ObsStatus.FINAL, None, None)]
            )
    assert repo.release_bundle(conn, rid) == "sha-b"
    with transaction(conn):
        assert repo.reactivate_bundle(conn, rid, "sha-a") == 1
    assert repo.release_bundle(conn, rid) == "sha-a"
    assert repo.latest_bundle(conn, "mig.m.net") == (rid, "sha-a")
    assert repo.latest_points(conn, "mig.m.net")["2026-07"].value == 1.0
    assert [i.vintage_id for i in repo.list_vintages(conn, "mig.m.net")][-1] == repo.bundle_vintage(
        conn, "mig.m.net", rid, "sha-a"
    ).vintage_id
    assert len(repo.list_vintages(conn, "mig.m.net")) == 2
    with transaction(conn):
        assert repo.reactivate_bundle(conn, rid, "sha-missing") == 0
