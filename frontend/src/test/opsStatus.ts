import type { OpsStatus } from "@/api/types";

/** A healthy, collecting dashboard. Tests override the parts a scenario is about. */
export function opsStatus(overrides: Partial<OpsStatus> = {}): OpsStatus {
  return {
    generated_at: "2026-10-30T16:00:00+13:00",
    overall: "ok",
    summary: "Everything checked is within its limits.",
    database: { readable: true, schema_version: 12, expected_schema_version: 12, instrumented: true, integrity: "not_checked" },
    process: {
      state: "running", pid: 4242, started_at: "2026-10-29T09:00:00+13:00", last_heartbeat_at: "2026-10-30T15:59:50+13:00",
      heartbeat_age_seconds: 10, scheduler_enabled: true, collection_mode: "scheduler", stop_reason: null, suspend_count: 0, last_suspend_at: null,
      last_suspend_seconds: null, unexpected_restarts_7d: 0,
    },
    collection: { mode: "enabled", summary: "Scheduled collection is on: the dashboard checks Stats NZ by itself." },
    refresh: { state: "never", phase: null, started_at: null, finished_at: null, running_for_seconds: null, last_success_at: null,
      ingested: 0, pending: 0, failures: 0, error_class: null },
    jobs: [],
    calendar: {
      state: "current", last_checked_at: "2026-10-30T06:00:40+13:00", last_success_at: "2026-10-30T06:00:40+13:00",
      last_success_age_hours: 10, missed_refreshes: 0, next_refresh_at: "2026-10-31T06:00:00+13:00",
    },
    next_release: {
      release_key: "labour-market-2026-09", title: "Labour market statistics: September 2026 quarter", series_slug: "labour-market",
      reference_period: "2026-09", scheduled_at: "2026-11-04T10:45:00+13:00", status: "scheduled",
    },
    known_upcoming_releases: 3,
    latest_ingestion: { release_key: "gdp-2026-06", finished_at: "2026-10-29T20:57:00+13:00", outcome: "ingested" },
    failed_runs: [],
    freshness: [
      {
        series_slug: "gdp", label: "Gross domestic product", state: "current", latest_release_key: "gdp-2026-06",
        latest_reference_period: "2026-06", latest_published_at: "2026-09-17T10:45:00+12:00", latest_captured_at: "2026-10-29T20:57:00+13:00",
        overdue: [], next_release_at: "2026-12-17T10:45:00+13:00", next_reference_period: "2026-09",
      },
    ],
    sources: [],
    backup: {
      directory: "backups", state: "ok", entries_seen: 1,
      latest: null,
      latest_good: { name: "nzstats-2026-10-30-0900", kind: "bundle", created_at: "2026-10-30T09:00:00+13:00", age_hours: 7, verification: "verified", raw_artifacts: 43, problems: [] },
    },
    alert_delivery: { state: "none_recorded", last_attempt_at: null, last_success_at: null, failures: 0, rate_limited: 0, window_hours: 24 },
    issues: [],
    notes: [],
    ...overrides,
  };
}
