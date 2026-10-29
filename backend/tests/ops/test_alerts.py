"""Alerting: de-duplication, escalation, reminders, rate limits, delivery failures and payload hygiene."""

from __future__ import annotations

import json
import stat
from datetime import timedelta

import pytest

from nzstats.cli import main
from nzstats.ops.alerts import (
    FileNotifier,
    Notification,
    NotifierError,
    Policy,
    build_notifiers,
    process,
)
from nzstats.ops.report import Issue
from nzstats.store.db import connect
from tests.ops import support as S


class Recorder:
    name = "rec"

    def __init__(self) -> None:
        self.notes: list[Notification] = []

    def send(self, note: Notification) -> None:
        self.notes.append(note)

    @property
    def events(self) -> list[tuple[str, str]]:
        return [(n.event, i.key) for n in self.notes for i in n.items]


class Broken:
    name = "broken"

    def send(self, note: Notification) -> None:
        raise NotifierError("https://bot.example/token=SECRET-TOKEN refused")


def issue(key: str, severity: str = "attention", **kw) -> Issue:
    return Issue(
        key=key,
        severity=severity,
        category="release",
        title=f"title {key}",
        detail=kw.get("detail", f"detail {key}"),
        action="do the thing",
    )


@pytest.fixture()
def base(conn, clock, tmp_path):
    S.healthy_world(conn, clock.now)
    return S.status(conn, tmp_path, clock.now)


def check(conn, base, notifiers, now, *issues, policy=None):
    status = base.model_copy(update={"issues": list(issues), "overall": "attention"})
    return process(conn, status, notifiers, now=now, policy=policy)


def test_a_new_issue_is_delivered_once_and_recorded(conn, clock, base) -> None:
    rec = Recorder()
    result = check(conn, base, [rec], clock.now, issue("a:1"))
    assert rec.events == [("opened", "a:1")] and (result.sent, result.failed) == (1, 0)
    row = conn.execute("SELECT * FROM ops_notification").fetchone()
    assert (row["alert_key"], row["event"], row["notifier"], row["outcome"]) == (
        "a:1",
        "opened",
        "rec",
        "sent",
    )


def test_the_same_failure_is_not_repeated(conn, clock, base) -> None:
    rec = Recorder()
    for minutes in (0, 1, 30, 600):  # attention reminders are 72 h apart
        check(conn, base, [rec], clock.now + timedelta(minutes=minutes), issue("a:1"))
    assert rec.events == [("opened", "a:1")]


@pytest.mark.parametrize(
    ("severity", "hours", "expect_reminder"),
    [
        ("critical", 11, False),
        ("critical", 13, True),
        ("attention", 13, False),
        ("attention", 73, True),
    ],
)
def test_reminders_follow_the_severity(conn, clock, base, severity, hours, expect_reminder) -> None:
    rec = Recorder()
    check(conn, base, [rec], clock.now, issue("a:1", severity))
    check(conn, base, [rec], clock.now + timedelta(hours=hours), issue("a:1", severity))
    assert (("reminder", "a:1") in rec.events) == expect_reminder


def test_escalation_is_delivered_immediately_and_de_escalation_is_not(conn, clock, base) -> None:
    rec = Recorder()
    check(conn, base, [rec], clock.now, issue("a:1", "attention"))
    check(conn, base, [rec], clock.now + timedelta(minutes=5), issue("a:1", "critical"))
    check(conn, base, [rec], clock.now + timedelta(minutes=10), issue("a:1", "attention"))
    assert rec.events == [("opened", "a:1"), ("escalated", "a:1")]


def test_resolution_is_announced_once_and_a_return_opens_a_new_alert(conn, clock, base) -> None:
    rec = Recorder()
    check(conn, base, [rec], clock.now, issue("a:1"))
    for minutes in (10, 20):
        check(conn, base, [rec], clock.now + timedelta(minutes=minutes))
    check(conn, base, [rec], clock.now + timedelta(minutes=30), issue("a:1"))
    assert rec.events == [("opened", "a:1"), ("resolved", "a:1"), ("opened", "a:1")]


def test_an_alert_that_was_never_delivered_is_not_announced_as_resolved(conn, clock, base) -> None:
    rec = Recorder()
    check(conn, base, [Broken()], clock.now, issue("a:1"))
    check(conn, base, [rec], clock.now + timedelta(minutes=5))
    assert rec.events == []


def test_a_failed_delivery_is_retried_and_the_secret_in_the_error_is_never_stored(
    conn, clock, base
) -> None:
    rec = Recorder()
    first = check(conn, base, [Broken()], clock.now, issue("a:1"))
    assert first.delivery_failed
    assert conn.execute("SELECT last_notified_at FROM ops_alert").fetchone()[0] is None
    check(conn, base, [rec], clock.now + timedelta(minutes=5), issue("a:1"))
    assert rec.events == [("opened", "a:1")]
    dump = "\n".join(conn.iterdump())
    assert "SECRET-TOKEN" not in dump
    failed = conn.execute(
        "SELECT notifier, outcome, error_class FROM ops_notification WHERE outcome='failed'"
    ).fetchone()
    assert tuple(failed) == ("broken", "failed", "NotifierError")


def test_one_failing_channel_does_not_stop_another_and_the_alert_counts_as_delivered(
    conn, clock, base
) -> None:
    rec = Recorder()
    result = check(conn, base, [Broken(), rec], clock.now, issue("a:1"))
    assert (result.sent, result.failed, result.delivery_failed) == (1, 1, False)
    assert check(conn, base, [rec], clock.now + timedelta(minutes=1), issue("a:1")).changes == []


def test_the_rate_limit_defers_deliveries_and_nothing_is_lost(conn, clock, base) -> None:
    rec, policy = Recorder(), Policy(max_per_hour=2, digest_threshold=10)
    many = [issue(f"a:{n}") for n in range(4)]
    first = check(conn, base, [rec], clock.now, *many, policy=policy)
    assert (first.sent, first.rate_limited) == (2, 2) and len(rec.events) == 2
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM ops_notification WHERE outcome='rate_limited'"
        ).fetchone()[0]
        == 2
    )
    assert (
        check(conn, base, [rec], clock.now + timedelta(minutes=30), *many, policy=policy).sent == 0
    )  # still inside the hour
    later = check(
        conn, base, [rec], clock.now + timedelta(hours=1, minutes=1), *many, policy=policy
    )
    assert later.sent == 2 and sorted(k for _, k in rec.events) == [f"a:{n}" for n in range(4)]


def test_a_storm_of_changes_is_one_digest(conn, clock, base) -> None:
    rec = Recorder()
    result = check(conn, base, [rec], clock.now, *[issue(f"a:{n}") for n in range(5)])
    assert len(rec.notes) == 1 and rec.notes[0].event == "digest" and len(rec.notes[0].items) == 5
    assert result.sent == 1
    assert (
        check(
            conn,
            base,
            [rec],
            clock.now + timedelta(minutes=1),
            *[issue(f"a:{n}") for n in range(5)],
        ).changes
        == []
    )


def test_the_payload_has_only_the_allow_listed_fields(conn, clock, base) -> None:
    rec = Recorder()
    check(conn, base, [rec], clock.now, issue("a:1", detail="bell\x07 and\nnewline " + "x" * 900))
    payload = rec.notes[0].to_payload()
    assert set(payload) == {"event", "generated_at", "overall", "alerts"}
    (alert,) = payload["alerts"]
    assert set(alert) == {"key", "severity", "title", "detail", "action", "first_seen_at"}
    assert (
        "\x07" not in alert["detail"]
        and "\n" not in alert["detail"]
        and len(alert["detail"]) <= 400
    )


def test_upstream_error_text_never_reaches_a_channel(conn, clock, tmp_path) -> None:
    S.healthy_world(conn, clock.now)
    S.add_release(conn, "x-2026-10", S.SLUGS[0], clock.now - timedelta(hours=9), ref="2026-10")
    S.add_run(
        conn,
        "x-2026-10",
        clock.now - timedelta(hours=8),
        "failed",
        "network",
        "GET https://www.stats.govt.nz/?api_key=SECRET-KEY: timeout",
    )
    S.add_source(
        conn,
        f"release:{S.SLUGS[1]}",
        state="degraded",
        checked=clock.now,
        detail="x: failed with Authorization: Bearer SECRET-BEARER",
    )
    status = S.status(conn, tmp_path, clock.now)
    sink = tmp_path / "ops" / "alerts.jsonl"
    result = process(conn, status, [FileNotifier(sink)], now=clock.now)
    assert result.sent >= 1
    text = sink.read_text()
    assert "SECRET" not in text and "api_key" not in text and "Bearer" not in text


def test_the_file_channel_is_private_and_reports_only_the_error_class(tmp_path) -> None:
    sink = tmp_path / "ops" / "alerts.jsonl"
    note = Notification("opened", "t", "attention", ())
    FileNotifier(sink).send(note)
    assert (
        stat.S_IMODE(sink.stat().st_mode) == 0o600
        and stat.S_IMODE(sink.parent.stat().st_mode) == 0o700
    )
    assert json.loads(sink.read_text())["event"] == "opened"
    blocked = tmp_path / "file"
    blocked.write_text("")
    with pytest.raises(NotifierError) as exc:
        FileNotifier(blocked / "x" / "alerts.jsonl").send(note)
    assert str(exc.value) == "NotADirectoryError"


def test_unknown_channels_are_refused_not_ignored(tmp_path) -> None:
    with pytest.raises(ValueError, match="telegram"):
        build_notifiers("log,telegram", S.settings(tmp_path))
    assert [n.name for n in build_notifiers("log, file", S.settings(tmp_path))] == ["log", "file"]


# --- command ------------------------------------------------------------------------------------------------------


@pytest.fixture()
def cli_world(db_path, clock, monkeypatch):
    data = db_path.parent
    conn = connect(db_path)
    S.healthy_world(conn, clock.now)
    S.add_release(conn, "x-2026-10", S.SLUGS[0], clock.now - timedelta(hours=9), ref="2026-10")
    conn.close()
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(data))
    monkeypatch.setattr("nzstats.ops.collect.utc_now", lambda: clock.now)
    monkeypatch.setattr("nzstats.cli.utc_now", lambda: clock.now)
    return data


def test_alert_check_delivers_once_then_stays_quiet(cli_world, capsys) -> None:
    assert main(["alert-check", "--channels", "file"]) == 1  # the application's state: ATTENTION
    out = capsys.readouterr().out
    assert "Alerts: 2 change(s); delivered 2" in out
    lines = (cli_world / "ops" / "alerts.jsonl").read_text().splitlines()
    assert sorted(json.loads(line)["alerts"][0]["key"] for line in lines) == [
        "backup:none",
        "release:overdue:x-2026-10",
    ]
    assert main(["alert-check", "--channels", "file"]) == 1
    assert "Alerts: 0 change(s)" in capsys.readouterr().out
    assert len((cli_world / "ops" / "alerts.jsonl").read_text().splitlines()) == 2


def test_a_delivery_failure_is_reported_apart_from_the_application_state(
    cli_world, capsys, monkeypatch
) -> None:
    monkeypatch.setattr("nzstats.ops.alerts.NOTIFIER_FACTORIES", {"file": lambda s: Broken()})
    assert main(["alert-check", "--channels", "file"]) == 1  # still the application's exit code
    captured = capsys.readouterr()
    assert "ALERT DELIVERY PROBLEM" in captured.err and "failed 2" in captured.out
    assert "SECRET-TOKEN" not in captured.out + captured.err


def test_alert_check_with_an_unknown_channel_cannot_run(cli_world, capsys) -> None:
    assert main(["alert-check", "--channels", "telegram"]) == 3
    assert "unknown alert channel" in capsys.readouterr().err


def test_alert_check_never_creates_a_missing_database(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "nowhere"))
    assert main(["alert-check", "--channels", "log,file"]) == 2
    assert not (tmp_path / "nowhere").exists()


def test_a_resolved_notice_that_could_not_be_delivered_is_retried_not_lost(
    conn, clock, base
) -> None:
    rec = Recorder()
    check(conn, base, [rec], clock.now, issue("a:1", "critical"))
    check(
        conn, base, [Broken()], clock.now + timedelta(minutes=5)
    )  # resolves, but no channel works
    assert conn.execute("SELECT resolved_at FROM ops_alert").fetchone()[0] is None
    check(conn, base, [rec], clock.now + timedelta(minutes=10))
    check(conn, base, [rec], clock.now + timedelta(minutes=15))
    assert rec.events == [("opened", "a:1"), ("resolved", "a:1")]
    assert conn.execute("SELECT resolved_at FROM ops_alert").fetchone()[0] is not None


def test_a_rate_limited_resolved_notice_is_sent_later(conn, clock, base) -> None:
    rec, policy = Recorder(), Policy(max_per_hour=1, digest_threshold=10)
    check(conn, base, [rec], clock.now, issue("a:1"), policy=policy)
    check(
        conn, base, [rec], clock.now + timedelta(minutes=5), policy=policy
    )  # resolved, but over the hourly limit
    assert rec.events == [("opened", "a:1")]
    check(conn, base, [rec], clock.now + timedelta(hours=1, minutes=1), policy=policy)
    assert rec.events == [("opened", "a:1"), ("resolved", "a:1")]


def test_an_alert_that_returns_before_its_resolved_notice_goes_out_is_simply_still_open(
    conn, clock, base
) -> None:
    rec = Recorder()
    check(conn, base, [rec], clock.now, issue("a:1"))
    check(conn, base, [Broken()], clock.now + timedelta(minutes=5))
    check(conn, base, [rec], clock.now + timedelta(minutes=10), issue("a:1"))
    assert (
        rec.events == [("opened", "a:1")]
        and conn.execute("SELECT resolved_at FROM ops_alert").fetchone()[0] is None
    )


def test_an_unreadable_database_still_alerts_without_creating_anything(
    tmp_path, monkeypatch, capsys
) -> None:
    rec = Recorder()
    monkeypatch.setattr("nzstats.ops.alerts.NOTIFIER_FACTORIES", {"rec": lambda s: rec})
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "nowhere"))
    assert main(["alert-check", "--channels", "rec"]) == 2
    assert [k for _, k in rec.events] == ["database:unreadable"] and not (
        tmp_path / "nowhere"
    ).exists()
    main(["alert-check", "--channels", "rec"])
    assert len(rec.events) == 2  # no state to de-duplicate with: repeated, deliberately


def test_the_file_channel_does_not_invent_a_missing_data_directory(tmp_path) -> None:
    with pytest.raises(NotifierError):
        FileNotifier(tmp_path / "missing" / "ops" / "alerts.jsonl").send(
            Notification("opened", "t", "critical", ())
        )
    assert not (tmp_path / "missing").exists()


def test_two_alert_checks_cannot_run_at_once(cli_world, capsys) -> None:
    import fcntl

    with (cli_world / "nzstats.db.alert-lock").open("a+b") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert main(["alert-check", "--channels", "file"]) == 3
    assert "another alert-check is running" in capsys.readouterr().err
    assert not (cli_world / "ops" / "alerts.jsonl").exists()
