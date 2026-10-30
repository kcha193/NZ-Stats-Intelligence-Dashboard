"""Operational health with the on-open refresh (Phase 4G): no scheduler is expected, and none is reported missing."""

from __future__ import annotations

from datetime import timedelta

from nzstats.ops.thresholds import Thresholds
from tests.ops import support as S

T = Thresholds()


def on_open(conn, now) -> None:
    S.healthy_world(conn, now, enabled=False, mode="on_open")


def test_an_on_open_dashboard_is_ok_without_any_scheduler(conn, clock, tmp_path) -> None:
    on_open(conn, clock.now)
    S.add_refresh(
        conn, started=clock.now - timedelta(minutes=5), finished=clock.now - timedelta(minutes=4)
    )
    s = S.status(conn, tmp_path, clock.now)
    assert (s.overall, s.issues) == ("ok", [])
    assert (s.collection.mode, s.process.collection_mode) == ("on_open", "on_open")
    assert "opened" in s.collection.summary
    assert s.calendar.next_refresh_at is None and s.jobs == []
    assert (s.refresh.state, s.refresh.last_success_at) == ("completed", s.refresh.finished_at)


def test_no_scheduled_refresh_is_missed_when_none_is_scheduled(conn, clock, tmp_path) -> None:
    on_open(conn, clock.now)
    for source in ("calendar_refresh", "calendar_ics", "calendar_month"):
        S.add_source(
            conn,
            source,
            checked=clock.now - timedelta(days=5),
            success=clock.now - timedelta(days=5),
        )
    s = S.status(conn, tmp_path, clock.now)
    assert (s.calendar.state, s.calendar.missed_refreshes, s.issues) == ("current", 0, [])


def test_a_calendar_not_checked_for_a_week_says_to_open_the_dashboard(
    conn, clock, tmp_path
) -> None:
    on_open(conn, clock.now)
    S.add_source(
        conn,
        "calendar_refresh",
        checked=clock.now - timedelta(days=9),
        success=clock.now - timedelta(days=9),
    )
    s = S.status(conn, tmp_path, clock.now)
    issue = next(i for i in s.issues if i.key == "calendar:stale")
    assert issue.severity == "attention" and "Check now" in issue.action


def test_a_failed_check_is_attention_and_says_last_verified_data_is_shown(
    conn, clock, tmp_path
) -> None:
    on_open(conn, clock.now)
    S.add_refresh(
        conn, started=clock.now - timedelta(minutes=3), finished=clock.now - timedelta(minutes=2),
        state="failed", error_class="network", failures=[("calendar", "network")],
    )  # fmt: skip
    s = S.status(conn, tmp_path, clock.now)
    issue = next(i for i in s.issues if i.key == "refresh:failed")
    assert issue.severity == "attention" and "network" in issue.detail
    assert "last verified" in issue.detail
    assert (s.refresh.state, s.refresh.error_class, s.refresh.failures) == ("failed", "network", 1)


def test_a_check_running_too_long_is_reported(conn, clock, tmp_path) -> None:
    on_open(conn, clock.now)
    S.add_refresh(
        conn, started=clock.now - timedelta(seconds=T.job_running_attention_seconds + 60),
        state="running", phase="downloading",
    )  # fmt: skip
    s = S.status(conn, tmp_path, clock.now)
    assert s.refresh.state == "running" and s.refresh.phase == "downloading"
    assert "refresh:running_long" in S.keys(s)


def test_a_check_in_progress_is_not_a_fault(conn, clock, tmp_path) -> None:
    on_open(conn, clock.now)
    S.add_refresh(conn, started=clock.now - timedelta(minutes=2), state="running", phase="checking")
    s = S.status(conn, tmp_path, clock.now)
    assert (s.overall, s.refresh.state, s.refresh.running_for_seconds) == ("ok", "running", 120)


def test_an_interrupted_check_is_a_note_not_a_fault(conn, clock, tmp_path) -> None:
    on_open(conn, clock.now)
    S.add_refresh(
        conn,
        started=clock.now - timedelta(hours=1),
        finished=clock.now - timedelta(hours=1),
        state="interrupted",
    )
    s = S.status(conn, tmp_path, clock.now)
    assert s.overall == "ok" and s.refresh.state == "interrupted"
    assert any("interrupted" in n for n in s.notes)


def test_pending_releases_are_counted(conn, clock, tmp_path) -> None:
    on_open(conn, clock.now)
    S.add_refresh(
        conn, started=clock.now - timedelta(minutes=5), finished=clock.now - timedelta(minutes=4),
        pending=[("a", "not_published_yet"), ("b", "catch_up_limit")],
    )  # fmt: skip
    assert S.status(conn, tmp_path, clock.now).refresh.pending == 2


def test_a_missed_release_says_how_on_open_collects_it(conn, clock, tmp_path) -> None:
    on_open(conn, clock.now)
    slug = S.SLUGS[0]
    S.add_release(conn, f"{slug}-2026-10", slug, clock.now - timedelta(days=2), ref="2026-10")
    s = S.status(conn, tmp_path, clock.now)
    issue = next(i for i in s.issues if i.key.startswith("release:overdue:"))
    assert "opened" in issue.action and "Check now" in issue.action


def test_old_reference_periods_alone_are_not_stale(conn, clock, tmp_path) -> None:
    """Twenty days since the last release, but the calendar lists nothing newer as published: current."""
    on_open(conn, clock.now)
    s = S.status(conn, tmp_path, clock.now)
    assert {r.state for r in s.freshness} == {"current"} and s.issues == []


def test_offline_mode_is_a_choice_not_a_fault(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now, enabled=False, mode="off")
    s = S.status(conn, tmp_path, clock.now)
    assert (s.overall, s.collection.mode) == (
        "ok",
        "disabled",
    ) and "offline" in s.collection.summary.lower()


def test_a_stopped_on_open_dashboard_is_paused(conn, clock, tmp_path) -> None:
    S.add_process(
        conn, started=clock.now - timedelta(days=2), beat=clock.now - timedelta(days=1),
        stopped=clock.now - timedelta(days=1), reason="clean", enabled=False, mode="on_open",
    )  # fmt: skip
    s = S.status(conn, tmp_path, clock.now)
    assert (s.process.state, s.collection.mode) == ("stopped", "paused")
    assert "on-open refresh" in s.collection.summary


def test_rows_written_before_phase_4g_still_read_as_scheduler_or_off(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)  # collection_mode NULL, scheduler_enabled 1
    s = S.status(conn, tmp_path, clock.now)
    assert (s.collection.mode, s.process.collection_mode, s.refresh.state) == (
        "enabled",
        "scheduler",
        "never",
    )


def test_the_terminal_report_shows_the_last_check(conn, clock, tmp_path) -> None:
    from nzstats.ops.render import render_text

    on_open(conn, clock.now)
    S.add_refresh(
        conn, started=clock.now - timedelta(minutes=5), finished=clock.now - timedelta(minutes=4),
        ingested=1, pending=[("a", "not_published_yet")],
    )  # fmt: skip
    text = render_text(S.status(conn, tmp_path, clock.now))
    assert "Collection     on_open" in text
    assert "Last check     completed at" in text and "1 ingested, 1 pending, 0 failure(s)" in text


def test_a_failed_release_older_than_the_newest_is_still_overdue(conn, clock, tmp_path) -> None:
    """Review P1: a later vintage must not hide an earlier published release that was attempted and never stored."""
    on_open(conn, clock.now)
    slug = S.SLUGS[0]
    S.add_release(conn, f"{slug}-2026-08", slug, clock.now - timedelta(days=25), ref="2026-08")
    S.add_run(
        conn, f"{slug}-2026-08", clock.now - timedelta(days=24), "failed", "validation_failed"
    )
    s = S.status(conn, tmp_path, clock.now)
    assert f"release:overdue:{slug}-2026-08" in S.keys(s)


def test_late_discovered_release_inside_refresh_boundary_is_overdue(conn, clock, tmp_path):
    on_open(conn, clock.now)
    slug = S.SLUGS[0]
    conn.execute(
        "INSERT INTO refresh_catch_up VALUES (?, ?)", (slug, S.iso(clock.now - timedelta(days=30)))
    )
    key = f"{slug}-2026-08"
    S.add_release(conn, key, slug, clock.now - timedelta(days=25), ref="2026-08")
    assert f"release:overdue:{key}" in S.keys(S.status(conn, tmp_path, clock.now))
