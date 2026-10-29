"""Local alerting: turn changes in operational status into notifications, once, without flooding.

The engine knows nothing about channels. A `Notifier` is anything with a `name` and a `send(Notification)`; the two
shipped here write to the log and to a local JSON-lines file. A remote channel (Telegram, email, a webhook) is added
by implementing `Notifier` and registering it in `NOTIFIER_FACTORIES`; none exists, and none is configured or contacted
without the owner's explicit approval (see docs/phase-4f-operational-health.md, "External approvals").

Rules, each covered by tests:

* An alert is keyed by the issue key. It is delivered when it opens, again if it escalates ATTENTION -> CRITICAL, as a
  reminder after `reminder_hours` while it stays open, and once when it resolves. A repeated failure is not repeated.
* A delivery that no channel accepted is retried on the next check; it does not count as delivered.
* At most `max_per_hour` deliveries per hour; the rest are recorded as rate-limited and retried later. More than
  `digest_threshold` changes in one check are sent as a single digest.
* Payloads are built only from the structured issue fields (keys, titles, counts, times, error classes): never from
  upstream response text, exception messages, paths or settings, so no credential can reach a channel.
* Every attempt is recorded in `ops_notification`, so a failing channel is visible apart from the failure it announced.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from nzstats.clock import to_akl_iso, to_utc_iso
from nzstats.config import Settings
from nzstats.ops.report import RANK, OpsStatus
from nzstats.ops.text import clean
from nzstats.store.db import transaction

log = logging.getLogger("nzstats.alerts")
Event = Literal["opened", "escalated", "reminder", "resolved", "digest"]


class NotifierError(Exception):
    """A channel could not deliver. Carry no secret in the message: only the exception class is recorded."""


@dataclass(frozen=True)
class AlertItem:
    key: str
    severity: str
    title: str
    detail: str
    action: str
    first_seen_at: str


@dataclass(frozen=True)
class Notification:
    event: Event
    generated_at: str
    overall: str
    items: tuple[AlertItem, ...]

    def to_payload(self) -> dict:
        """The complete, allow-listed message. Nothing outside these fields can be sent."""
        return {
            "event": self.event,
            "generated_at": self.generated_at,
            "overall": self.overall,
            "alerts": [
                {
                    k: getattr(i, k)
                    for k in ("key", "severity", "title", "detail", "action", "first_seen_at")
                }
                for i in self.items
            ],
        }


class Notifier(Protocol):
    name: str

    def send(self, note: Notification) -> None: ...


class LogNotifier:
    name = "log"

    def send(self, note: Notification) -> None:
        for item in note.items:
            level = logging.ERROR if item.severity == "critical" else logging.WARNING
            log.log(
                level, "ALERT %s [%s] %s -- %s", note.event, item.severity, item.title, item.action
            )


class FileNotifier:
    """Appends one JSON line per notification to a file only the owner can read."""

    name = "file"

    def __init__(self, path: Path) -> None:
        self._path = path

    def send(self, note: Notification) -> None:
        try:
            self._path.parent.mkdir(
                exist_ok=True, mode=0o700
            )  # not parents: never invent a missing data directory
            fd = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(note.to_payload(), sort_keys=True) + "\n")
        except OSError as exc:
            raise NotifierError(type(exc).__name__) from None


NOTIFIER_FACTORIES: Mapping[str, Callable[[Settings], Notifier]] = {
    "log": lambda settings: LogNotifier(),
    "file": lambda settings: FileNotifier(settings.ops_dir / "alerts.jsonl"),
}
DEFAULT_CHANNELS = "log,file"


def build_notifiers(channels: str, settings: Settings) -> list[Notifier]:
    names = [c.strip() for c in channels.split(",") if c.strip()]
    unknown = [n for n in names if n not in NOTIFIER_FACTORIES]
    if unknown:
        raise ValueError(
            f"unknown alert channel(s): {', '.join(unknown)} (available: {', '.join(NOTIFIER_FACTORIES)})"
        )
    return [NOTIFIER_FACTORIES[n](settings) for n in names]


@dataclass(frozen=True)
class Policy:
    reminder_hours: Mapping[str, int] = field(
        default_factory=lambda: {"critical": 12, "attention": 72}
    )
    max_per_hour: int = 6
    digest_threshold: int = 3


@dataclass
class AlertResult:
    changes: list[tuple[str, str]] = field(default_factory=list)  # (event, key)
    sent: int = 0
    failed: int = 0
    rate_limited: int = 0

    @property
    def delivery_failed(self) -> bool:
        return self.failed > 0 and self.sent == 0


def _stamp(dt: datetime) -> str:
    return to_utc_iso(dt)


def _units_this_hour(conn: sqlite3.Connection, now: datetime) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT alert_key, event, attempted_at FROM ops_notification"
        " WHERE outcome IN ('sent', 'failed') AND attempted_at > ?)",
        (_stamp(now - timedelta(hours=1)),),
    ).fetchone()[0]


def _plan(conn: sqlite3.Connection, status: OpsStatus, now: datetime, policy: Policy):
    """Update the open-alert table to match `status` and return the notifications now owed (event, AlertItem)."""
    owed: list[tuple[Event, AlertItem]] = []
    active = {i.key: i for i in status.issues}
    open_rows = {
        r["key"]: r for r in conn.execute("SELECT * FROM ops_alert WHERE resolved_at IS NULL")
    }
    for key, issue in active.items():
        row = open_rows.get(key)
        if row is None:
            conn.execute(
                "INSERT INTO ops_alert(key, severity, title, first_seen_at, last_seen_at) VALUES (?,?,?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET severity=excluded.severity, title=excluded.title,"
                " first_seen_at=excluded.first_seen_at, last_seen_at=excluded.last_seen_at,"
                " last_notified_at=NULL, last_notified_severity=NULL, notify_count=0, resolved_at=NULL",
                (key, issue.severity, issue.title, _stamp(now), _stamp(now)),
            )
            first_seen, event = _stamp(now), "opened"
        else:
            conn.execute(
                "UPDATE ops_alert SET severity=?, title=?, last_seen_at=? WHERE key=?",
                (issue.severity, issue.title, _stamp(now), key),
            )
            first_seen, event = row["first_seen_at"], None
            if row["last_notified_at"] is None:
                event = (
                    "opened"  # never delivered (rate-limited or every channel failed): still owed
                )
            elif RANK[issue.severity] > RANK[row["last_notified_severity"] or "ok"]:
                event = "escalated"
            elif now - datetime.fromisoformat(
                row["last_notified_at"].replace("Z", "+00:00")
            ) >= timedelta(hours=policy.reminder_hours[issue.severity]):
                event = "reminder"
        if event:
            owed.append(
                (
                    event,
                    AlertItem(
                        key,
                        issue.severity,
                        clean(issue.title),
                        clean(issue.detail, 400),
                        clean(issue.action, 400),
                        to_akl_iso(first_seen),
                    ),
                )
            )
    for key, row in open_rows.items():
        if key not in active:
            if row["last_notified_at"] is None:  # never announced, so there is nothing to retract
                conn.execute("UPDATE ops_alert SET resolved_at=? WHERE key=?", (_stamp(now), key))
            else:  # stays open until the "resolved" notice is delivered, so a failed or rate-limited one is retried
                owed.append(
                    (
                        "resolved",
                        AlertItem(
                            key,
                            row["severity"],
                            clean(row["title"]),
                            "No longer detected.",
                            "None needed.",
                            to_akl_iso(row["first_seen_at"]),
                        ),
                    )
                )
    return owed


def process(
    conn: sqlite3.Connection,
    status: OpsStatus,
    notifiers: list[Notifier],
    *,
    now: datetime,
    policy: Policy | None = None,
) -> AlertResult:
    policy = policy or Policy()
    result = AlertResult()
    with transaction(conn):
        owed = _plan(conn, status, now, policy)
    result.changes = [(e, i.key) for e, i in owed]
    resolving = {i.key for e, i in owed if e == "resolved"}
    if not owed:
        return result
    units: list[tuple[Event, tuple[AlertItem, ...]]] = (
        [("digest", tuple(i for _, i in owed))]
        if len(owed) > policy.digest_threshold
        else [(e, (i,)) for e, i in owed]
    )
    for event, items in units:
        note = Notification(event, status.generated_at, status.overall, items)
        row_key = "*digest*" if event == "digest" else items[0].key
        if _units_this_hour(conn, now) >= policy.max_per_hour:
            result.rate_limited += 1
            conn.execute(
                "INSERT INTO ops_notification(alert_key, event, severity, notifier, attempted_at, outcome)"
                " VALUES (?,?,?,?,?, 'rate_limited')",
                (
                    row_key,
                    event,
                    max(items, key=lambda i: RANK[i.severity]).severity,
                    "*",
                    _stamp(now),
                ),
            )
            continue
        delivered = False
        for notifier in notifiers:
            error: str | None = None
            try:
                notifier.send(note)
                result.sent += 1
                delivered = True
            except Exception as exc:  # a channel failing must not stop the others or hide the alert
                error = type(exc).__name__
                result.failed += 1
                log.error("alert channel %s failed: %s", notifier.name, error)
            conn.execute(
                "INSERT INTO ops_notification(alert_key, event, severity, notifier, attempted_at, outcome, error_class)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    row_key,
                    event,
                    max(items, key=lambda i: RANK[i.severity]).severity,
                    notifier.name,
                    _stamp(now),
                    "failed" if error else "sent",
                    error,
                ),
            )
        if delivered:
            for item in items:
                if item.key in resolving:
                    conn.execute(
                        "UPDATE ops_alert SET resolved_at=? WHERE key=?", (_stamp(now), item.key)
                    )
                else:
                    conn.execute(
                        "UPDATE ops_alert SET last_notified_at=?, last_notified_severity=?, notify_count=notify_count+1 WHERE key=?",
                        (_stamp(now), item.severity, item.key),
                    )
    return result


def deliver_unrecorded(status: OpsStatus, notifiers: list[Notifier]) -> AlertResult:
    """Send the current issues with no state, for when the database that holds the state cannot be read.

    The worst condition must not be the one that stays silent. There is no de-duplication here, so a caller that checks
    often repeats it each time; that is the right trade for "the database is gone".
    """
    result = AlertResult()
    items = tuple(
        AlertItem(
            i.key,
            i.severity,
            clean(i.title),
            clean(i.detail, 400),
            clean(i.action, 400),
            status.generated_at,
        )
        for i in status.issues
    )
    result.changes = [("opened", i.key) for i in items]
    for notifier in notifiers if items else []:
        try:
            notifier.send(Notification("opened", status.generated_at, status.overall, items))
            result.sent += 1
        except Exception as exc:
            result.failed += 1
            log.error("alert channel %s failed: %s", notifier.name, type(exc).__name__)
    return result
