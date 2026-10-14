import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from nzstats.adapters.migration.series import monthly_def
from nzstats.clock import parse_akl_naive
from nzstats.domain import ReleaseStatus
from nzstats.scheduler.planner import (
    mark_unavailable,
    next_poll_due,
    poll_candidates,
    releases_needing_ingest,
)
from nzstats.store import repo
from tests.support import release_ref_for

OFFSETS = [0, 1, 2, 5, 10, 15, 30, 60, 120, 180]
PUB = parse_akl_naive("2026-10-14 10:45:00")
SEEDED = datetime(2026, 10, 11, tzinfo=UTC)


@pytest.mark.parametrize(
    ("minutes_after", "attempts", "due"),
    [
        (-1, 0, False),
        (0, 0, True),
        (0.5, 1, False),
        (1, 1, True),
        (4, 3, False),
        (5, 3, True),
        (500, 10, False),
    ],
)
def test_next_poll_due(minutes_after, attempts, due) -> None:
    now = PUB + timedelta(minutes=minutes_after)
    assert next_poll_due(PUB, attempts, now, OFFSETS) is due


def _seed(conn, month="2026-07", status=ReleaseStatus.SCHEDULED, at="2026-10-14 10:45:00") -> str:
    ref = dataclasses.replace(release_ref_for(month, status), published_at=parse_akl_naive(at))
    repo.upsert_release(conn, ref, SEEDED)
    return ref.release_key


def _run(conn, key, at) -> None:
    repo.record_ingest_run(conn, key, at, at, "not_available", "not_found", None)


def test_candidate_follows_offset_schedule(rt) -> None:
    key = _seed(rt.conn)
    assert poll_candidates(rt.conn, rt.adapters, PUB - timedelta(minutes=1), OFFSETS) == []
    assert poll_candidates(rt.conn, rt.adapters, PUB, OFFSETS) == [key]
    _run(rt.conn, key, PUB)
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(seconds=30), OFFSETS) == []
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=1), OFFSETS) == [key]


def test_runs_before_the_scheduled_time_do_not_count_as_attempts(rt) -> None:
    key = _seed(rt.conn)
    _run(rt.conn, key, PUB - timedelta(days=1))
    assert poll_candidates(rt.conn, rt.adapters, PUB, OFFSETS) == [key]


def test_no_candidates_once_a_vintage_exists(rt) -> None:
    key = _seed(rt.conn)
    series_id = repo.upsert_series(rt.conn, monthly_def("net"))
    release_id = repo.get_release(rt.conn, key)["id"]
    repo.create_vintage(rt.conn, release_id, series_id, PUB, "release_files", "v", "sha")
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=1), OFFSETS) == []


def test_window_expires_and_marks_unavailable(rt) -> None:
    key = _seed(rt.conn)
    for minute in OFFSETS:
        _run(rt.conn, key, PUB + timedelta(minutes=minute))
    later = PUB + timedelta(minutes=181)
    assert poll_candidates(rt.conn, rt.adapters, later, OFFSETS) == []
    assert mark_unavailable(rt.conn, rt.adapters, later, OFFSETS) == [key]
    assert repo.get_release(rt.conn, key)["status"] == "unavailable"
    assert mark_unavailable(rt.conn, rt.adapters, later, OFFSETS) == []  # idempotent


def test_published_release_without_vintage_is_polled_but_never_marked_unavailable(rt) -> None:
    key = _seed(rt.conn, status=ReleaseStatus.PUBLISHED)
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=3), OFFSETS) == [key]
    for minute in OFFSETS:
        _run(rt.conn, key, PUB + timedelta(minutes=minute))
    assert mark_unavailable(rt.conn, rt.adapters, PUB + timedelta(hours=5), OFFSETS) == []


def test_catch_up_window(rt) -> None:
    old = _seed(rt.conn, month="2026-06", at="2026-09-01 10:45:00")
    recent = _seed(rt.conn, month="2026-07", at="2026-10-12 10:45:00")
    assert old != recent
    assert releases_needing_ingest(rt.conn, rt.adapters, PUB, 7) == [recent]
    assert releases_needing_ingest(rt.conn, rt.adapters, PUB, 60) == [old, recent]


# --- regressions from the final review ----------------------------------------------------------


def _failed(conn, key, at, error_class) -> None:
    repo.record_ingest_run(conn, key, at, at, "failed", error_class, None)


@pytest.mark.parametrize(
    "error_class", ["blocked", "network", "layout_changed", "validation_failed"]
)
def test_a_release_is_not_marked_unavailable_when_attempts_failed_for_other_reasons(
    rt, error_class
) -> None:
    """'Stats NZ files were not available' needs evidence: every attempt must have been a 404."""
    key = _seed(rt.conn)
    for i, minute in enumerate(OFFSETS):
        if i == 3:
            _failed(rt.conn, key, PUB + timedelta(minutes=minute), error_class)
        else:
            _run(rt.conn, key, PUB + timedelta(minutes=minute))
    later = PUB + timedelta(minutes=181)
    assert mark_unavailable(rt.conn, rt.adapters, later, OFFSETS) == []
    assert repo.get_release(rt.conn, key)["status"] == "scheduled"


def test_polling_backs_off_after_a_blocked_response(rt) -> None:
    key = _seed(rt.conn)
    _failed(rt.conn, key, PUB, "blocked")
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=1), OFFSETS) == []
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=10), OFFSETS) == []
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=30), OFFSETS) == [key]


def test_rescheduled_unavailable_release_is_polled_again_at_the_new_time(rt) -> None:
    """Review #4245952774: a calendar reschedule must put an unavailable release back in polling."""
    key = _seed(rt.conn)
    for minute in OFFSETS:
        _run(rt.conn, key, PUB + timedelta(minutes=minute))
    later = PUB + timedelta(minutes=181)
    assert mark_unavailable(rt.conn, rt.adapters, later, OFFSETS) == [key]

    new_pub = parse_akl_naive("2026-11-20 10:45:00")
    ref = dataclasses.replace(
        release_ref_for("2026-07", ReleaseStatus.SCHEDULED), published_at=new_pub
    )
    repo.upsert_release(rt.conn, ref, later)
    assert repo.get_release(rt.conn, key)["status"] == "delayed"

    assert poll_candidates(rt.conn, rt.adapters, new_pub - timedelta(minutes=1), OFFSETS) == []
    assert poll_candidates(rt.conn, rt.adapters, new_pub, OFFSETS) == [key]  # attempts reset


def test_exhausted_release_with_a_non_404_failure_keeps_a_daily_retry(rt) -> None:
    """Review #4266163936: a failed (not 404) release never becomes unavailable, so once the
    polling budget and the catch-up window are spent it must still be retried once a day."""
    key = _seed(rt.conn, at="2026-09-01 10:45:00")
    start = parse_akl_naive("2026-09-01 10:45:00")
    for i, minute in enumerate(OFFSETS):
        at = start + timedelta(minutes=minute)
        if i == 3:
            _failed(rt.conn, key, at, "network")
        else:
            _run(rt.conn, key, at)
    assert mark_unavailable(rt.conn, rt.adapters, PUB, OFFSETS) == []
    assert repo.get_release(rt.conn, key)["status"] == "scheduled"

    assert releases_needing_ingest(rt.conn, rt.adapters, PUB, 7) == [key]
    _failed(rt.conn, key, PUB, "network")  # today's retry failed again
    assert releases_needing_ingest(rt.conn, rt.adapters, PUB + timedelta(hours=1), 7) == []
    assert releases_needing_ingest(rt.conn, rt.adapters, PUB + timedelta(days=1), 7) == [key]


def test_old_release_that_was_never_attempted_is_not_swept_into_the_daily_retry(rt) -> None:
    """Historic releases left to `backfill` stay outside catch-up; only attempted ones retry."""
    _seed(rt.conn, month="2026-06", at="2026-09-01 10:45:00")
    assert releases_needing_ingest(rt.conn, rt.adapters, PUB, 7) == []
