"""Executable tables for docs/superpowers/specs/2026-10-13-ingestion-health.md."""

from dataclasses import replace
from datetime import timedelta

import pytest

from nzstats.clock import to_utc_iso
from nzstats.domain import ReleaseStatus
from nzstats.pipeline.discover import attempt
from nzstats.pipeline.ingest import ingest_release
from nzstats.scheduler.planner import mark_unavailable, poll_candidates
from nzstats.store import repo
from tests.support import NOW, release_ref_for

SLUG = "international-migration"
SOURCE = f"release:{SLUG}"


def health(rt):
    return rt.conn.execute("SELECT * FROM source_health WHERE source=?", (SOURCE,)).fetchone()


def record(rt, key, outcome, at=NOW):
    repo.record_ingest_run(rt.conn, key, at, at, outcome, None, outcome)


# Expected failure by status group: scheduled/delayed; published/corrected/unavailable.
HISTORIES = [
    ((), False, False),
    (("not_available",), False, True),
    (("not_available",) * 3, False, True),
    (("skipped_no_adapter",), False, False),
    (("failed",), True, True),
    (("failed", "not_available"), True, True),
    (("failed", "not_available", "not_available", "skipped_no_adapter"), True, True),
    (("failed", "skipped_no_adapter"), True, True),
    (("failed", "unchanged"), False, False),
    (("failed", "ingested"), False, False),
    (("not_available", "ingested"), False, False),
    (("failed", "not_available", "ingested", "not_available"), False, True),
    (("ingested", "failed", "unchanged", "skipped_no_adapter"), False, False),
    (("ingested", "failed", "not_available", "unchanged", "failed"), True, True),
]


@pytest.mark.parametrize("status", list(ReleaseStatus))
@pytest.mark.parametrize("history,prepublication_failure,published_failure", HISTORIES)
def test_latest_meaningful_outcome_table(
    rt, status, history, prepublication_failure, published_failure
):
    ref = release_ref_for("2026-07", status)
    repo.upsert_release(rt.conn, ref, NOW)
    for outcome in history:
        record(rt, ref.release_key, outcome)  # Same timestamp: ID must break ties.
    expected = (
        prepublication_failure
        if status in (ReleaseStatus.SCHEDULED, ReleaseStatus.DELAYED)
        else published_failure
    )
    failures = repo.failing_releases(rt.conn, SLUG)
    assert [r["release_key"] for r in failures] == ([ref.release_key] if expected else [])
    if expected:
        assert health(rt)["state"] == "degraded"
    elif health(rt) is not None:
        assert health(rt)["state"] == "ok"


def test_outcome_order_uses_id_even_when_timestamps_go_backwards(rt):
    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)
    record(rt, ref.release_key, "failed", NOW + timedelta(days=1))
    record(rt, ref.release_key, "ingested", NOW)
    assert repo.failing_releases(rt.conn, SLUG) == []
    record(rt, ref.release_key, "failed", NOW - timedelta(days=1))
    assert [r["release_key"] for r in repo.failing_releases(rt.conn, SLUG)] == [ref.release_key]


@pytest.mark.parametrize("initial", [ReleaseStatus.SCHEDULED, ReleaseStatus.DELAYED])
@pytest.mark.parametrize(
    "target", [ReleaseStatus.PUBLISHED, ReleaseStatus.CORRECTED, ReleaseStatus.UNAVAILABLE]
)
def test_status_change_reinterprets_history_without_an_attempt(rt, initial, target):
    ref = release_ref_for("2026-07", initial)
    repo.upsert_release(rt.conn, ref, NOW)
    record(rt, ref.release_key, "not_available")
    assert health(rt) is None
    repo.set_release_status(rt.conn, ref.release_key, target, NOW + timedelta(hours=1))
    assert health(rt)["state"] == "degraded"
    assert health(rt)["last_checked_at"] is None
    assert health(rt)["last_success_at"] is None
    assert rt.conn.execute("SELECT COUNT(*) FROM ingest_run").fetchone()[0] == 1


@pytest.mark.parametrize(
    "history,expected",
    [
        (("not_available",), "ok"),
        (("failed", "not_available"), "degraded"),
        (("failed", "ingested"), "ok"),
    ],
)
def test_discovery_reschedule_recalculates_without_claiming_a_source_check(rt, history, expected):
    ref = release_ref_for("2026-07", ReleaseStatus.UNAVAILABLE)
    repo.upsert_release(rt.conn, ref, NOW)
    # Known earlier source success must survive both degradation and recalculation.
    earlier = NOW - timedelta(days=1)
    repo.set_source_health(rt.conn, SOURCE, earlier, ok=True, detail=None)
    for outcome in history:
        record(rt, ref.release_key, outcome)
    before = dict(health(rt))
    later = NOW + timedelta(hours=1)
    rescheduled = replace(ref, status=ReleaseStatus.SCHEDULED, published_at=later)
    errors = []
    assert attempt(rt, "calendar_ics", lambda: later, lambda: [rescheduled], errors) == 1
    assert not errors
    assert repo.get_release(rt.conn, ref.release_key)["status"] == "delayed"
    assert health(rt)["state"] == expected
    assert health(rt)["last_checked_at"] == before["last_checked_at"]
    assert health(rt)["last_success_at"] == before["last_success_at"]
    assert poll_candidates(rt.conn, rt.adapters, later, [0, 1]) == [ref.release_key]
    # Publication reactivates the gap; a later success still dominates earlier failures.
    published = replace(rescheduled, status=ReleaseStatus.PUBLISHED)
    attempt(rt, "calendar_month", lambda: later, lambda: [published], [])
    assert health(rt)["state"] == ("ok" if history[-1] == "ingested" else "degraded")
    assert health(rt)["last_checked_at"] == before["last_checked_at"]
    assert health(rt)["last_success_at"] == before["last_success_at"]


@pytest.mark.parametrize("status", [ReleaseStatus.SCHEDULED, ReleaseStatus.DELAYED])
def test_poll_exhaustion_degrades_immediately_and_valid_reschedule_recovers(rt, site, status):
    ref = replace(release_ref_for("2026-07", status), published_at=NOW)
    repo.upsert_release(rt.conn, ref, NOW)
    url = site.file_url("2026-07", "age_sex")
    good = site.routes[url]
    site.override(url, 404)
    offsets = [0, 1, 2]
    for minute in offsets:
        at = NOW + timedelta(minutes=minute)
        assert poll_candidates(rt.conn, rt.adapters, at, offsets) == [ref.release_key]
        assert (
            ingest_release(rt, ref.release_key, now_fn=lambda at=at: at).outcome == "not_available"
        )
    assert health(rt) is None
    later = NOW + timedelta(minutes=3)
    assert mark_unavailable(rt.conn, rt.adapters, later, offsets) == [ref.release_key]
    assert health(rt)["state"] == "degraded"
    assert health(rt)["last_checked_at"] is None
    assert health(rt)["last_success_at"] is None
    assert mark_unavailable(rt.conn, rt.adapters, later, offsets) == []
    # Daily retry while unavailable remains a data gap and records an actual check.
    assert ingest_release(rt, ref.release_key, now_fn=lambda: later).outcome == "not_available"
    assert health(rt)["state"] == "degraded"
    assert health(rt)["last_checked_at"] == to_utc_iso(later)
    new_slot = NOW + timedelta(days=1)
    repo.upsert_release(rt.conn, replace(ref, published_at=new_slot), new_slot)
    assert health(rt)["state"] == "ok"
    assert health(rt)["last_checked_at"] == to_utc_iso(later)
    assert health(rt)["last_success_at"] is None
    assert poll_candidates(rt.conn, rt.adapters, new_slot, offsets) == [ref.release_key]
    site.override(url, *good)
    assert ingest_release(rt, ref.release_key, now_fn=lambda: new_slot).outcome == "ingested"
    assert health(rt)["last_success_at"] == to_utc_iso(new_slot)


@pytest.mark.parametrize("status", [ReleaseStatus.SCHEDULED, ReleaseStatus.DELAYED])
def test_neutral_retries_and_unrelated_success_cannot_hide_failure(rt, site, status):
    a, b = release_ref_for("2026-06", status), release_ref_for("2026-07")
    for ref in (a, b):
        repo.upsert_release(rt.conn, ref, NOW)
    url = site.file_url("2026-06", "age_sex")
    good = site.routes[url]
    site.override(url, 500)
    assert ingest_release(rt, a.release_key, now_fn=lambda: NOW).outcome == "failed"
    before = dict(health(rt))
    site.override(url, 404)
    for minute in (1, 2, 3):
        at = NOW + timedelta(minutes=minute)
        assert ingest_release(rt, a.release_key, now_fn=lambda at=at: at).outcome == "not_available"
        assert dict(health(rt)) == before
    assert ingest_release(rt, b.release_key, now_fn=lambda: NOW).outcome == "ingested"
    assert ingest_release(rt, b.release_key, now_fn=lambda: NOW).outcome == "unchanged"
    assert health(rt)["state"] == "degraded"
    assert a.release_key in health(rt)["detail"]
    assert b.release_key not in health(rt)["detail"]
    site.override(url, *good)
    assert ingest_release(rt, a.release_key, now_fn=lambda: NOW).outcome == "ingested"
    assert health(rt)["state"] == "ok"


@pytest.mark.parametrize(
    "status", [ReleaseStatus.PUBLISHED, ReleaseStatus.CORRECTED, ReleaseStatus.UNAVAILABLE]
)
def test_gap_and_failure_preserve_vintages_then_unchanged_clears_them(rt, site, status):
    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)
    assert ingest_release(rt, ref.release_key, now_fn=lambda: NOW).outcome == "ingested"
    snapshots = {
        table: [tuple(r) for r in rt.conn.execute(f"SELECT * FROM {table}")]
        for table in ("vintage", "observation")
    }
    repo.set_release_status(rt.conn, ref.release_key, status, NOW)
    url = site.file_url("2026-07", "age_sex")
    good = site.routes[url]
    for code, expected in ((500, "failed"), (404, "not_available")):
        site.override(url, code)
        assert ingest_release(rt, ref.release_key, now_fn=lambda: NOW).outcome == expected
        assert health(rt)["state"] == "degraded"
        for table, snapshot in snapshots.items():
            assert [tuple(r) for r in rt.conn.execute(f"SELECT * FROM {table}")] == snapshot
    site.override(url, *good)
    recovered = NOW + timedelta(hours=1)
    assert ingest_release(rt, ref.release_key, now_fn=lambda: recovered).outcome == "unchanged"
    assert health(rt)["state"] == "ok"
    assert health(rt)["detail"] is None
    assert health(rt)["last_success_at"] == to_utc_iso(recovered)


def test_multiple_failures_remain_ordered_and_clear_individually(rt):
    a, b = release_ref_for("2026-06", ReleaseStatus.SCHEDULED), release_ref_for("2026-07")
    for ref in (a, b):
        repo.upsert_release(rt.conn, ref, NOW)
        record(rt, ref.release_key, "failed")
    record(rt, a.release_key, "not_available")
    assert [r["release_key"] for r in repo.failing_releases(rt.conn, SLUG)] == [
        a.release_key,
        b.release_key,
    ]
    record(rt, b.release_key, "unchanged")
    assert [r["release_key"] for r in repo.failing_releases(rt.conn, SLUG)] == [a.release_key]
    assert health(rt)["state"] == "degraded"
    record(rt, a.release_key, "ingested")
    assert repo.failing_releases(rt.conn, SLUG) == []
    assert health(rt)["state"] == "ok"
