"""Operational health: every state the dashboard can be in, decided from local data alone."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nzstats.clock import to_akl_iso
from nzstats.ops.thresholds import Thresholds
from tests.ops import support as S

T = Thresholds()


def at(clock):
    return clock.now


def sev(s, key) -> str:
    return next(i.severity for i in s.issues if i.key == key)


# --- healthy and disabled --------------------------------------------------------------------------------------


def test_a_healthy_collecting_dashboard_is_ok(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    s = S.status(conn, tmp_path, clock.now)
    assert (s.overall, s.issues) == ("ok", [])
    assert (s.process.state, s.collection.mode) == ("running", "enabled")
    assert s.calendar.state == "current" and s.calendar.next_refresh_at.startswith(
        "2026-10-31T06:00:00+13:00"
    )
    assert {r.state for r in s.freshness} == {"current"}


def test_a_deliberately_disabled_scheduler_is_not_a_fault(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now, enabled=False)
    s = S.status(conn, tmp_path, clock.now)
    assert (s.overall, s.issues) == ("ok", [])
    assert (s.process.state, s.collection.mode) == ("running", "disabled")
    assert "deliberately off" in s.collection.summary
    assert s.calendar.next_refresh_at is None  # nothing is going to run at 06:00


def test_a_disabled_scheduler_never_reports_a_missed_refresh_or_stalled_jobs(
    conn, clock, tmp_path
) -> None:
    S.healthy_world(conn, clock.now, enabled=False)
    S.add_source(
        conn,
        "calendar_refresh",
        checked=clock.now - timedelta(days=5),
        success=clock.now - timedelta(days=5),
    )
    s = S.status(conn, tmp_path, clock.now)
    assert s.calendar.state == "current" and s.calendar.missed_refreshes == 0 and s.issues == []


def test_with_collection_off_a_calendar_older_than_a_week_asks_for_a_manual_refresh(
    conn, clock, tmp_path
) -> None:
    S.healthy_world(conn, clock.now, enabled=False)
    old = clock.now - timedelta(days=8)
    S.add_source(conn, "calendar_refresh", checked=old, success=old)
    s = S.status(conn, tmp_path, clock.now)
    assert S.keys(s) == ["calendar:stale"]
    assert (
        "scripts/run.sh discover" in s.issues[0].action
        and "--no-scheduler" not in s.issues[0].action
    )


def test_no_dashboard_has_ever_run_is_unknown_not_stalled(conn, clock, tmp_path) -> None:
    S.add_source(conn, "calendar_refresh", checked=clock.now, success=clock.now)
    s = S.status(conn, tmp_path, clock.now)
    assert (s.process.state, s.collection.mode) == ("never_started", "unknown")
    assert not [k for k in S.keys(s) if k.startswith(("process:", "scheduler:"))]


# --- process and scheduler --------------------------------------------------------------------------------------


def _beat(conn, clock, seconds_ago, *, pid=100, enabled=True, **kw):
    S.add_process(
        conn,
        started=clock.now - timedelta(days=1),
        beat=clock.now - timedelta(seconds=seconds_ago),
        pid=pid,
        enabled=enabled,
        **kw,
    )


@pytest.mark.parametrize(
    ("silent", "severity"),
    [(T.heartbeat_stale_seconds + 1, "attention"), (T.heartbeat_critical_seconds + 1, "critical")],
)
def test_a_live_process_with_a_silent_heartbeat_is_stalled(
    conn, clock, tmp_path, silent, severity
) -> None:
    _beat(conn, clock, silent)
    s = S.status(conn, tmp_path, clock.now, pid_alive=lambda pid: True)
    assert s.process.state == "stalled" and s.collection.mode == "enabled"
    assert sev(s, "process:stalled") == severity and s.overall == severity


def test_a_dead_process_without_a_clean_stop_is_lost_and_collection_is_paused(
    conn, clock, tmp_path
) -> None:
    _beat(conn, clock, 3600)
    s = S.status(conn, tmp_path, clock.now, pid_alive=lambda pid: False)
    assert (s.process.state, s.collection.mode) == ("lost", "paused")
    assert sev(s, "process:lost") == "attention"
    assert "scripts/run.sh" in s.issues[0].action


def test_a_fresh_heartbeat_from_a_process_that_no_longer_exists_is_lost_at_once(
    conn, clock, tmp_path
) -> None:
    _beat(conn, clock, 5)  # it reported 5 seconds ago, then was killed
    s = S.status(conn, tmp_path, clock.now, pid_alive=lambda pid: False)
    assert (s.process.state, s.collection.mode) == ("lost", "paused") and "process:lost" in S.keys(
        s
    )


def test_a_clean_stop_is_not_a_fault(conn, clock, tmp_path) -> None:
    stopped = clock.now - timedelta(hours=2)
    _beat(conn, clock, 7200, stopped=stopped, reason="clean")
    s = S.status(conn, tmp_path, clock.now, pid_alive=lambda pid: False)
    assert (s.process.state, s.collection.mode) == ("stopped", "paused")
    assert not [k for k in S.keys(s) if k.startswith("process:")]


def test_a_paused_dashboard_does_not_claim_the_scheduler_missed_refreshes(
    conn, clock, tmp_path
) -> None:
    _beat(conn, clock, 3600 * 30, stopped=clock.now - timedelta(hours=30), reason="clean")
    S.add_source(
        conn,
        "calendar_refresh",
        checked=clock.now - timedelta(days=2),
        success=clock.now - timedelta(days=2),
    )
    s = S.status(conn, tmp_path, clock.now, pid_alive=lambda pid: False)
    assert "calendar:missed" not in S.keys(s) and s.calendar.missed_refreshes == 0


def test_an_unexpected_restart_is_flagged_for_a_day_then_only_noted(conn, clock, tmp_path) -> None:
    S.add_process(
        conn,
        boot="bbbbbbbb22",
        started=clock.now - timedelta(hours=2),
        beat=clock.now,
        prior_unclean=1,
    )
    s = S.status(conn, tmp_path, clock.now)
    assert "process:unexpected_restart:bbbbbbbb" in S.keys(s)
    later = S.status(conn, tmp_path, clock.now + timedelta(hours=23))
    assert "process:unexpected_restart:bbbbbbbb" not in S.keys(later)
    assert any("unclean restart" in n for n in later.notes)


def _watch(conn, clock, idle_seconds, *, running=None, suspend=None):
    S.add_process(
        conn,
        started=clock.now - timedelta(days=1),
        beat=clock.now,
        suspend_at=suspend,
        suspend_seconds=3600 if suspend else None,
    )
    S.add_job(
        conn,
        "release_watch",
        finished=clock.now - timedelta(seconds=idle_seconds),
        running=running,
        started=clock.now - timedelta(seconds=idle_seconds),
    )
    S.add_source(
        conn,
        "calendar_refresh",
        checked=clock.now - timedelta(hours=10),
        success=clock.now - timedelta(hours=10),
    )


@pytest.mark.parametrize(
    ("idle", "expected"),
    [
        (120, None),
        (T.watch_attention_seconds + 1, "attention"),
        (T.watch_critical_seconds + 1, "critical"),
    ],
)
def test_a_scheduler_that_should_be_ticking_but_is_not(
    conn, clock, tmp_path, idle, expected
) -> None:
    _watch(conn, clock, idle)
    s = S.status(conn, tmp_path, clock.now)
    assert ("scheduler:no_progress" in S.keys(s)) == (expected is not None)
    if expected:
        assert sev(s, "scheduler:no_progress") == expected


def test_a_laptop_that_has_just_woken_is_given_time_to_catch_up(conn, clock, tmp_path) -> None:
    _watch(conn, clock, 3 * 3600, suspend=clock.now - timedelta(minutes=2))
    s = S.status(conn, tmp_path, clock.now)
    assert "scheduler:no_progress" not in S.keys(s)
    assert any("woke from sleep" in n for n in s.notes)


def test_the_same_gap_long_after_waking_is_reported(conn, clock, tmp_path) -> None:
    _watch(conn, clock, 3 * 3600, suspend=clock.now - timedelta(minutes=30))
    assert "scheduler:no_progress" in S.keys(S.status(conn, tmp_path, clock.now))


def test_a_new_process_is_not_called_stuck_before_its_first_tick(conn, clock, tmp_path) -> None:
    S.add_process(conn, started=clock.now - timedelta(seconds=60), beat=clock.now)
    S.add_source(conn, "calendar_refresh", checked=clock.now, success=clock.now)
    s = S.status(conn, tmp_path, clock.now)
    assert not [k for k in S.keys(s) if k.startswith(("scheduler:", "calendar:"))]


@pytest.mark.parametrize(
    ("running_for", "expected"),
    [
        (600, None),
        (T.job_running_attention_seconds + 60, "attention"),
        (T.job_running_critical_seconds + 60, "critical"),
    ],
)
def test_long_running_ingestion(conn, clock, tmp_path, running_for, expected) -> None:
    _watch(conn, clock, 7200, running=clock.now - timedelta(seconds=running_for))
    s = S.status(conn, tmp_path, clock.now)
    assert "scheduler:no_progress" not in S.keys(s)  # busy, not idle
    job = next(j for j in s.jobs if j.job_id == "release_watch")
    assert job.state == "running" and job.running_for_seconds == running_for
    key = "scheduler:job_running_long:release_watch"
    assert (key in S.keys(s)) == (expected is not None)
    if expected:
        assert sev(s, key) == expected


def test_a_job_that_keeps_raising_escalates(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    S.add_job(
        conn, "catch_up", finished=clock.now, outcome="error", error="OperationalError", failures=1
    )
    assert sev(S.status(conn, tmp_path, clock.now), "scheduler:job_failing:catch_up") == "attention"
    S.add_job(
        conn,
        "catch_up",
        finished=clock.now,
        outcome="error",
        error="OperationalError",
        failures=T.job_failures_critical,
    )
    assert sev(S.status(conn, tmp_path, clock.now), "scheduler:job_failing:catch_up") == "critical"


def test_errors_left_by_an_earlier_process_are_not_blamed_on_this_one(
    conn, clock, tmp_path
) -> None:
    S.healthy_world(conn, clock.now)
    S.add_job(
        conn,
        "catch_up",
        boot="oldboot999",
        finished=clock.now,
        outcome="error",
        error="OperationalError",
        failures=5,
    )
    assert "scheduler:job_failing:catch_up" not in S.keys(S.status(conn, tmp_path, clock.now))


# --- calendar ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days_without", "missed", "severity"),
    [
        (0, 0, None),
        (1, 1, "attention"),
        (2, 2, "attention"),
        (T.calendar_missed_critical, 3, "critical"),
    ],
)
def test_missed_refreshes_escalate_with_the_count(
    conn, clock, tmp_path, days_without, missed, severity
) -> None:
    S.healthy_world(
        conn, clock.now
    )  # now is 16:00 NZDT, so this morning's 06:00 refresh is 10 h old
    last = clock.now - timedelta(hours=10, days=days_without)
    S.add_source(conn, "calendar_refresh", checked=last, success=last)
    s = S.status(conn, tmp_path, clock.now)
    assert s.calendar.missed_refreshes == missed
    assert ("calendar:missed" in S.keys(s)) == (severity is not None)
    if severity:
        assert sev(s, "calendar:missed") == severity and s.calendar.state == "missed"


def test_a_failed_refresh_that_never_completed_a_batch_still_counts_as_missed(
    conn, clock, tmp_path
) -> None:
    """calendar_refresh succeeds only when every feed succeeded in one run, so a degraded refresh leaves it stale."""
    S.healthy_world(conn, clock.now)
    stale = clock.now - timedelta(days=4)
    S.add_source(
        conn,
        "calendar_refresh",
        state="degraded",
        checked=clock.now - timedelta(hours=10),
        success=stale,
        detail="calendar_ics: network: x",
    )
    s = S.status(conn, tmp_path, clock.now)
    assert s.calendar.state == "missed" and sev(s, "calendar:missed") == "critical"
    assert "source:degraded:calendar_refresh" in S.keys(s)


def test_a_missed_refresh_across_the_spring_forward_day(conn, clock, tmp_path) -> None:
    now = datetime(2026, 9, 26, 19, 5, tzinfo=UTC)  # 08:05 NZDT Sun 27 Sep
    S.add_process(conn, started=now - timedelta(days=1), beat=now)
    S.add_job(conn, "release_watch", finished=now - timedelta(seconds=30))
    last = datetime(2026, 9, 25, 18, 0, 30, tzinfo=UTC)  # 06:00:30 NZST Sat 26 Sep: only 25 h ago
    S.add_source(conn, "calendar_refresh", checked=last, success=last)
    s = S.status(conn, tmp_path, now)
    assert s.calendar.missed_refreshes == 1 and "calendar:missed" in S.keys(s)
    just_inside = S.status(conn, tmp_path, datetime(2026, 9, 26, 18, 59, tzinfo=UTC))
    assert just_inside.calendar.missed_refreshes == 0


def test_never_refreshed_is_flagged_once_the_startup_refresh_has_had_its_chance(
    conn, clock, tmp_path
) -> None:
    S.add_process(conn, started=clock.now - timedelta(hours=1), beat=clock.now)
    S.add_job(conn, "release_watch", finished=clock.now - timedelta(seconds=20))
    assert "calendar:never" in S.keys(S.status(conn, tmp_path, clock.now))


# --- releases, freshness, sources ------------------------------------------------------------------------------


def _slug():
    return S.SLUGS[0]


def test_old_observations_are_not_a_missed_release(conn, clock, tmp_path) -> None:
    """Nothing is due: the newest data is 200 days old because Stats NZ has not published since."""
    S.healthy_world(conn, clock.now)
    conn.execute("UPDATE release SET published_at='2026-04-01T00:00:00Z'")
    s = S.status(conn, tmp_path, clock.now)
    assert {r.state for r in s.freshness} == {"current"} and not [
        k for k in S.keys(s) if k.startswith("release:")
    ]


def test_a_published_release_with_no_data_is_overdue_only_after_the_grace_period(
    conn, clock, tmp_path
) -> None:
    S.healthy_world(conn, clock.now)
    pub = clock.now - timedelta(minutes=200)
    S.add_release(conn, "x-2026-10", _slug(), pub, status="scheduled", ref="2026-10")
    assert not [k for k in S.keys(S.status(conn, tmp_path, clock.now)) if k.startswith("release:")]
    late = S.status(conn, tmp_path, clock.now + timedelta(minutes=60))
    assert "release:overdue:x-2026-10" in S.keys(late)
    row = next(r for r in late.freshness if r.series_slug == _slug())
    assert row.state == "overdue" and row.overdue[0].release_key == "x-2026-10"


def test_an_overdue_release_becomes_critical_beyond_the_catch_up_window(
    conn, clock, tmp_path
) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(
        conn,
        "x-2026-10",
        _slug(),
        clock.now - timedelta(days=8),
        status="unavailable",
        ref="2026-10",
    )
    assert sev(S.status(conn, tmp_path, clock.now), "release:overdue:x-2026-10") == "critical"


def test_an_older_release_that_was_skipped_is_a_history_gap_not_a_stale_dashboard(
    conn, clock, tmp_path
) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(
        conn, "old-2026-01", _slug(), clock.now - timedelta(days=90), ref="2026-01"
    )  # older than the newest vintage
    assert not [k for k in S.keys(S.status(conn, tmp_path, clock.now)) if k.startswith("release:")]


def test_the_overdue_action_depends_on_whether_collection_is_running(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(
        conn,
        "x-2026-10",
        _slug(),
        clock.now - timedelta(hours=9),
        status="scheduled",
        ref="2026-10",
    )
    on = S.status(conn, tmp_path, clock.now).issues[0]
    conn.execute("UPDATE ops_process SET scheduler_enabled=0")
    off = S.status(conn, tmp_path, clock.now).issues[0]
    assert "polls for 3 hours" in on.action and "Collection is not running" in off.action


def test_a_rejected_file_points_to_review_not_to_retrying(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(conn, "x-2026-10", _slug(), clock.now - timedelta(hours=9), ref="2026-10")
    S.add_run(
        conn,
        "x-2026-10",
        clock.now - timedelta(hours=8),
        "failed",
        "validation_failed",
        "[continuity] SECRET-UPSTREAM-TEXT",
    )
    issue = next(
        i
        for i in S.status(conn, tmp_path, clock.now).issues
        if i.key == "release:overdue:x-2026-10"
    )
    assert "validation_failed" in issue.detail and "do not loosen" in issue.action
    assert "SECRET-UPSTREAM-TEXT" not in issue.model_dump_json()


def test_the_next_release_is_the_earliest_supported_scheduled_one(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(
        conn, "late", _slug(), clock.now + timedelta(days=9), status="scheduled", ref="2026-11"
    )
    S.add_release(
        conn, "soon", S.SLUGS[1], clock.now + timedelta(days=2), status="scheduled", ref="2026-10"
    )
    S.add_release(
        conn, "unsupported", "some-other-series", clock.now + timedelta(hours=1), status="scheduled"
    )
    S.add_release(conn, "already", _slug(), clock.now + timedelta(hours=2), status="published")
    s = S.status(conn, tmp_path, clock.now)
    assert (s.next_release.release_key, s.known_upcoming_releases) == ("soon", 2)


def test_a_degraded_calendar_source_is_critical_after_three_days(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    S.add_source(
        conn,
        "calendar_ics",
        state="degraded",
        checked=clock.now,
        success=clock.now - timedelta(days=1),
        detail="calendar_ics: network: x",
    )
    assert sev(S.status(conn, tmp_path, clock.now), "source:degraded:calendar_ics") == "attention"
    S.add_source(
        conn,
        "calendar_ics",
        state="degraded",
        checked=clock.now,
        success=clock.now - timedelta(days=4),
        detail="calendar_ics: network: x",
    )
    assert sev(S.status(conn, tmp_path, clock.now), "source:degraded:calendar_ics") == "critical"


def test_a_degraded_release_source_is_not_reported_twice_when_its_release_is_overdue(
    conn, clock, tmp_path
) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(conn, "x-2026-10", _slug(), clock.now - timedelta(hours=9), ref="2026-10")
    S.add_source(
        conn, f"release:{_slug()}", state="degraded", checked=clock.now, detail="x-2026-10: failed"
    )
    S.add_source(
        conn, f"release:{S.SLUGS[1]}", state="degraded", checked=clock.now, detail="old: failed"
    )
    ks = S.keys(S.status(conn, tmp_path, clock.now))
    assert (
        f"source:degraded:release:{_slug()}" not in ks
        and f"source:degraded:release:{S.SLUGS[1]}" in ks
    )


def test_recent_block_pages_are_reported_and_old_ones_are_not(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    S.add_run(conn, "r1", clock.now - timedelta(hours=30), "failed", "blocked")
    assert "source:blocked" not in S.keys(S.status(conn, tmp_path, clock.now))
    S.add_run(conn, "r2", clock.now - timedelta(hours=2), "failed", "blocked")
    assert "source:blocked" in S.keys(S.status(conn, tmp_path, clock.now))


def test_latest_ingestion_and_failed_runs(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    key = f"{_slug()}-2026-09"
    S.add_run(conn, key, clock.now - timedelta(days=20), "ingested")
    S.add_release(conn, "bad-1", _slug(), clock.now - timedelta(days=60), ref="2026-08")
    S.add_run(conn, "bad-1", clock.now - timedelta(days=59), "failed", "layout_changed")
    s = S.status(conn, tmp_path, clock.now)
    assert s.latest_ingestion.release_key == key and s.latest_ingestion.outcome == "ingested"
    assert [(f.release_key, f.error_class) for f in s.failed_runs] == [("bad-1", "layout_changed")]


# --- backups, alerts, database ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bk", "key", "severity"),
    [
        (S.backup("none"), "backup:none", "attention"),
        (S.backup("stale", 8 * 24), "backup:stale", "attention"),
        (S.backup("stale", 31 * 24), "backup:stale", "critical"),
        (
            S.backup(
                "failed", 5, verification="incomplete", problems=["2 raw artifact(s) are missing"]
            ),
            "backup:failed",
            "attention",
        ),
    ],
)
def test_backup_age_and_state(conn, clock, tmp_path, bk, key, severity) -> None:
    S.healthy_world(conn, clock.now)
    s = S.status(conn, tmp_path, clock.now, bk=bk)
    assert sev(s, key) == severity and s.overall == severity


def test_alert_delivery_failures_do_not_make_the_dashboard_unhealthy(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    conn.execute(
        "INSERT INTO ops_notification(alert_key, event, severity, notifier, attempted_at, outcome, error_class)"
        " VALUES ('k','opened','critical','file',?, 'failed','PermissionError')",
        (S.iso(clock.now - timedelta(hours=1)),),
    )
    s = S.status(conn, tmp_path, clock.now)
    assert (s.overall, s.alert_delivery.state, s.alert_delivery.failures) == ("ok", "failing", 1)


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [
        ([("log", "sent", 1), ("file", "sent", 1)], "ok"),
        ([("log", "sent", 1), ("file", "failed", 1), ("file", "failed", 2)], "failing"),
        ([("log", "failed", 1), ("file", "sent", 1)], "failing"),
        ([("log", "failed", 1), ("file", "failed", 1)], "failing"),
        ([], "none_recorded"),
        ([("file", "sent", 25)], "none_recorded"),
        ([("file", "failed", 25)], "none_recorded"),
        ([("file", "rate_limited", 1)], "none_recorded"),
        ([("log", "sent", 1)], "ok"),
        ([("file", "sent", 1)], "ok"),
        ([("log", "failed", 1)], "failing"),
        ([("file", "failed", 1)], "failing"),
        ([("file", "sent", 25), ("file", "failed", 1), ("log", "sent", 1)], "failing"),
        ([("file", "failed", 25), ("log", "sent", 1)], "ok"),
        ([("file", "failed", 2), ("file", "sent", 1)], "ok"),
        ([("file", "failed", 1), ("log", "rate_limited", 1)], "failing"),
    ],
)
def test_alert_delivery_is_evaluated_per_notifier(
    conn, clock, tmp_path, attempts, expected
) -> None:
    S.healthy_world(conn, clock.now)
    for notifier, outcome, hours_ago in attempts:
        conn.execute(
            "INSERT INTO ops_notification(alert_key, event, severity, notifier, attempted_at, outcome)"
            " VALUES ('k', 'opened', 'critical', ?, ?, ?)",
            (notifier, S.iso(clock.now - timedelta(hours=hours_ago)), outcome),
        )
    status = S.status(conn, tmp_path, clock.now)
    delivery = status.alert_delivery
    assert (status.overall, status.issues, delivery.state) == ("ok", [], expected)
    assert delivery.failures == sum(o == "failed" and h <= 24 for _, o, h in attempts)
    assert delivery.rate_limited == sum(o == "rate_limited" and h <= 24 for _, o, h in attempts)
    for field, outcomes in (("last_attempt_at", {"sent", "failed"}), ("last_success_at", {"sent"})):
        times = [clock.now - timedelta(hours=h) for _, o, h in attempts if o in outcomes]
        assert getattr(delivery, field) == (to_akl_iso(max(times)) if times else None)


def test_a_database_behind_the_code_is_reported_without_touching_it(conn, clock, tmp_path) -> None:
    conn.execute("DELETE FROM schema_version WHERE version>=11")
    for table in ("refresh_run", "ops_process", "ops_job", "ops_alert", "ops_notification"):
        conn.execute(f"DROP TABLE {table}")
    s = S.status(conn, tmp_path, clock.now, bk=S.backup("none"))
    assert s.database.instrumented is False and s.database.schema_version == 10
    assert "database:schema_behind" in S.keys(s) and s.process.state == "never_started"


def test_overall_is_the_worst_issue_and_issues_list_critical_first(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(conn, "x-2026-10", _slug(), clock.now - timedelta(days=9), ref="2026-10")
    s = S.status(conn, tmp_path, clock.now, bk=S.backup("none"))
    assert s.overall == "critical" and [i.severity for i in s.issues] == ["critical", "attention"]


def test_a_calendar_nobody_is_meant_to_refresh_is_never_critical(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now, enabled=False)
    old = clock.now - timedelta(days=5)
    S.add_source(
        conn,
        "calendar_refresh",
        state="degraded",
        checked=old,
        success=old,
        detail="calendar_ics: network: x",
    )
    s = S.status(conn, tmp_path, clock.now)
    assert sev(s, "source:degraded:calendar_refresh") == "attention" and s.overall == "attention"


def test_time_the_host_spent_asleep_does_not_count_as_a_long_running_job(
    conn, clock, tmp_path
) -> None:
    S.add_process(
        conn,
        started=clock.now - timedelta(days=1),
        beat=clock.now,
        suspend_at=clock.now - timedelta(hours=2),
        suspend_seconds=3 * 3600,
    )
    S.add_job(
        conn,
        "release_watch",
        running=clock.now - timedelta(hours=5),
        started=clock.now - timedelta(hours=5),
        finished=clock.now - timedelta(hours=6),
    )
    S.add_source(
        conn,
        "calendar_refresh",
        checked=clock.now - timedelta(hours=10),
        success=clock.now - timedelta(hours=10),
    )
    s = S.status(conn, tmp_path, clock.now)
    job = next(j for j in s.jobs if j.job_id == "release_watch")
    assert (
        job.running_for_seconds == 2 * 3600
        and "scheduler:job_running_long:release_watch" in S.keys(s)
    )
    assert (
        sev(s, "scheduler:job_running_long:release_watch") == "critical"
    )  # 2 h awake is still too long
    S.add_job(
        conn,
        "release_watch",
        running=clock.now - timedelta(hours=3, minutes=20),
        started=clock.now - timedelta(hours=4),
        finished=clock.now - timedelta(hours=6),
    )
    short = S.status(conn, tmp_path, clock.now)
    assert next(j for j in short.jobs if j.job_id == "release_watch").running_for_seconds == 20 * 60
    assert "scheduler:job_running_long:release_watch" not in S.keys(short)


def test_an_overdue_alert_title_is_built_from_the_slug_not_the_upstream_page_title(
    conn, clock, tmp_path
) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(
        conn,
        "x-2026-10",
        S.SLUGS[0],
        clock.now - timedelta(hours=9),
        ref="2026-10",
        title="UPSTREAM <b>INJECTED</b> TITLE",
    )
    issue = next(
        i
        for i in S.status(conn, tmp_path, clock.now).issues
        if i.key == "release:overdue:x-2026-10"
    )
    assert "INJECTED" not in issue.model_dump_json() and issue.title.startswith(S.SLUGS[0])
