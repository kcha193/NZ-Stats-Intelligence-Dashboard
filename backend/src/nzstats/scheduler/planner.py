"""Scheduling decisions: which releases are due for a poll right now."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from nzstats.clock import from_utc_iso, to_utc_iso
from nzstats.domain import ReleaseStatus
from nzstats.store import repo


def next_poll_due(
    published_at: datetime, attempts: int, now: datetime, offsets_minutes: Sequence[int]
) -> bool:
    if attempts >= len(offsets_minutes):
        return False
    return now >= published_at + timedelta(minutes=offsets_minutes[attempts])


def _attempts(conn: sqlite3.Connection, release_key: str, published_at_utc: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM ingest_run WHERE release_key = ? AND started_at >= ?",
        (release_key, published_at_utc),
    ).fetchone()[0]


def _unvintaged(
    conn: sqlite3.Connection,
    adapters: Mapping[str, object],
    statuses: Sequence[str],
    not_before: str,
    not_after: str,
) -> list[sqlite3.Row]:
    slugs = list(adapters)
    return conn.execute(
        f"SELECT r.release_key, r.published_at FROM release r"
        f" WHERE r.series_slug IN ({','.join('?' * len(slugs))})"
        f" AND r.status IN ({','.join('?' * len(statuses))})"
        f" AND r.published_at >= ? AND r.published_at <= ?"
        f" AND NOT EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
        f" ORDER BY r.published_at",
        (*slugs, *statuses, not_before, not_after),
    ).fetchall()


def _window(offsets_minutes: Sequence[int]) -> timedelta:
    return timedelta(minutes=max(offsets_minutes) + 60)


def poll_candidates(
    conn: sqlite3.Connection,
    adapters: Mapping[str, object],
    now: datetime,
    offsets_minutes: Sequence[int],
) -> list[str]:
    statuses = (
        ReleaseStatus.SCHEDULED.value,
        ReleaseStatus.DELAYED.value,
        ReleaseStatus.PUBLISHED.value,
    )
    rows = _unvintaged(
        conn, adapters, statuses, to_utc_iso(now - _window(offsets_minutes)), to_utc_iso(now)
    )
    return [
        r["release_key"]
        for r in rows
        if next_poll_due(
            from_utc_iso(r["published_at"]),
            _attempts(conn, r["release_key"], r["published_at"]),
            now,
            offsets_minutes,
        )
    ]


def mark_unavailable(
    conn: sqlite3.Connection,
    adapters: Mapping[str, object],
    now: datetime,
    offsets_minutes: Sequence[int],
) -> list[str]:
    """Scheduled/delayed releases whose polling budget is spent without any data become unavailable."""
    statuses = (ReleaseStatus.SCHEDULED.value, ReleaseStatus.DELAYED.value)
    rows = _unvintaged(conn, adapters, statuses, "0000", to_utc_iso(now))
    marked = []
    for r in rows:
        if _attempts(conn, r["release_key"], r["published_at"]) >= len(offsets_minutes):
            repo.set_release_status(conn, r["release_key"], ReleaseStatus.UNAVAILABLE, now)
            marked.append(r["release_key"])
    return marked


def releases_needing_ingest(
    conn: sqlite3.Connection, adapters: Mapping[str, object], now: datetime, catch_up_days: int
) -> list[str]:
    """Releases already due (published_at <= now, within the catch-up window) with no vintage."""
    slugs = list(adapters)
    marks = ",".join("?" * len(slugs))
    rows = conn.execute(
        f"SELECT r.release_key FROM release r WHERE r.series_slug IN ({marks})"
        " AND r.published_at <= ? AND r.published_at >= ?"
        " AND NOT EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
        " ORDER BY r.published_at",
        (*slugs, to_utc_iso(now), to_utc_iso(now - timedelta(days=catch_up_days))),
    )
    return [r["release_key"] for r in rows]
