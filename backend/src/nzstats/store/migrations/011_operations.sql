-- Phase 4F operational monitoring. `nzstats serve` records itself here; `nzstats status` only reads it.
-- Timestamps are UTC ISO-8601 like the rest of the schema.

-- One row per `nzstats serve` process (a "boot"). A clean shutdown sets stopped_at and stop_reason='clean'; a
-- process found dead without one is stamped stop_reason='unclean' by the next start.
CREATE TABLE ops_process (
  id INTEGER PRIMARY KEY,
  boot_id TEXT NOT NULL UNIQUE,
  pid INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  scheduler_enabled INTEGER NOT NULL CHECK (scheduler_enabled IN (0, 1)),
  last_heartbeat_at TEXT NOT NULL,
  stopped_at TEXT,
  stop_reason TEXT CHECK (stop_reason IN ('clean', 'unclean')),
  prior_unclean INTEGER NOT NULL DEFAULT 0,
  suspend_count INTEGER NOT NULL DEFAULT 0,
  last_suspend_at TEXT,
  last_suspend_seconds INTEGER,
  version TEXT
);
CREATE INDEX ops_process_started ON ops_process (started_at);

-- Latest state of each scheduler job (only the error class is kept, never the message).
CREATE TABLE ops_job (
  job_id TEXT PRIMARY KEY,
  boot_id TEXT NOT NULL,
  running_since TEXT,
  last_started_at TEXT,
  last_finished_at TEXT,
  last_success_at TEXT,
  last_outcome TEXT CHECK (last_outcome IN ('ok', 'error', 'missed', 'interrupted')),
  last_error_class TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0
);

-- De-duplication state for local alerts: one open row per issue key.
CREATE TABLE ops_alert (
  key TEXT PRIMARY KEY,
  severity TEXT NOT NULL CHECK (severity IN ('attention', 'critical')),
  title TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_notified_at TEXT,
  last_notified_severity TEXT,
  notify_count INTEGER NOT NULL DEFAULT 0,
  resolved_at TEXT
);

-- One row per delivery attempt, so a delivery failure is recorded apart from the failure it announced.
CREATE TABLE ops_notification (
  id INTEGER PRIMARY KEY,
  alert_key TEXT NOT NULL,
  event TEXT NOT NULL CHECK (event IN ('opened', 'escalated', 'reminder', 'resolved', 'digest')),
  severity TEXT NOT NULL,
  notifier TEXT NOT NULL,
  attempted_at TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('sent', 'failed', 'rate_limited')),
  error_class TEXT
);
CREATE INDEX ops_notification_attempted ON ops_notification (attempted_at);
