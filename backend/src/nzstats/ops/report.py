"""The operational-status report: one structure behind the CLI, the API and the alerts.

Every field is derived from the local database and local files. Free text from upstream (error messages, page
bodies) is never copied in: issues are built from release keys, source names, error classes, counts and times.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Level = Literal["ok", "attention", "critical"]
IssueLevel = Literal["attention", "critical"]
RANK: dict[str, int] = {"ok": 0, "attention": 1, "critical": 2}


class Issue(BaseModel):
    key: str  # stable across runs: the de-duplication identity of an alert
    severity: IssueLevel
    category: Literal[
        "database", "process", "scheduler", "calendar", "release", "source", "backup", "freshness"
    ]
    title: str
    detail: str
    action: str


class DatabaseInfo(BaseModel):
    readable: bool
    schema_version: int | None
    expected_schema_version: int
    instrumented: bool  # the operations tables exist (schema 11+)
    integrity: Literal["not_checked", "ok", "failed"] = "not_checked"


class ProcessInfo(BaseModel):
    state: Literal["never_started", "running", "stalled", "lost", "stopped"]
    pid: int | None = None
    started_at: str | None = None
    last_heartbeat_at: str | None = None
    heartbeat_age_seconds: int | None = None
    scheduler_enabled: bool | None = None
    stop_reason: str | None = None
    suspend_count: int = 0
    last_suspend_at: str | None = None
    last_suspend_seconds: int | None = None
    unexpected_restarts_7d: int = 0


class CollectionInfo(BaseModel):
    mode: Literal["enabled", "disabled", "paused", "unknown"]
    summary: str


class JobInfo(BaseModel):
    job_id: str
    state: Literal["running", "idle", "never_ran"]
    running_for_seconds: int | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    last_outcome: str | None = None
    last_error_class: str | None = None
    consecutive_failures: int = 0


class CalendarInfo(BaseModel):
    state: Literal["current", "missed", "stale", "never"]
    last_checked_at: str | None
    last_success_at: str | None
    last_success_age_hours: float | None
    missed_refreshes: int = 0
    next_refresh_at: str | None = None  # only while the scheduler is meant to be running


class ReleaseRefInfo(BaseModel):
    release_key: str
    title: str
    series_slug: str
    reference_period: str | None
    scheduled_at: str
    status: str


class LatestIngestion(BaseModel):
    release_key: str
    finished_at: str
    outcome: str


class FailedRun(BaseModel):
    release_key: str
    series_slug: str
    started_at: str | None
    outcome: str | None
    error_class: str | None


class OverdueRelease(BaseModel):
    release_key: str
    published_at: str
    hours_late: float
    status: str
    last_outcome: str | None
    last_error_class: str | None


class FreshnessRow(BaseModel):
    series_slug: str
    label: str
    state: Literal["current", "overdue", "no_data"]
    latest_release_key: str | None
    latest_reference_period: str | None
    latest_published_at: str | None
    latest_captured_at: str | None
    overdue: list[OverdueRelease]
    next_release_at: str | None
    next_reference_period: str | None


class SourceStatus(BaseModel):
    source: str
    state: str
    last_checked_at: str | None
    last_success_at: str | None
    age_hours: float | None
    expected: Literal["daily", "per_release"]
    expired: bool


class BackupEntry(BaseModel):
    name: str
    kind: Literal["bundle", "file"]
    created_at: str
    age_hours: float
    verification: Literal["verified", "unverified", "failed", "incomplete"]
    raw_artifacts: int | None
    problems: list[str]


class BackupInfo(BaseModel):
    directory: str
    state: Literal["ok", "stale", "none", "failed"]
    latest: BackupEntry | None
    latest_good: BackupEntry | None
    entries_seen: int


class AlertDelivery(BaseModel):
    """Whether alerts reach the operator. Kept apart from `overall`: a failing channel is not a failing dashboard."""

    state: Literal["none_recorded", "ok", "failing"]
    last_attempt_at: str | None
    last_success_at: str | None
    failures: int
    rate_limited: int
    window_hours: int


class OpsStatus(BaseModel):
    generated_at: str
    overall: Level
    summary: str
    database: DatabaseInfo
    process: ProcessInfo
    collection: CollectionInfo
    jobs: list[JobInfo]
    calendar: CalendarInfo
    next_release: ReleaseRefInfo | None
    known_upcoming_releases: int
    latest_ingestion: LatestIngestion | None
    failed_runs: list[FailedRun]
    freshness: list[FreshnessRow]
    sources: list[SourceStatus]
    backup: BackupInfo
    alert_delivery: AlertDelivery
    issues: list[Issue]
    notes: list[str]


def worst(levels: list[str]) -> Level:
    top = max((RANK[x] for x in levels), default=0)
    return ("ok", "attention", "critical")[top]  # type: ignore[return-value]
