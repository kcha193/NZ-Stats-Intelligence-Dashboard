-- Phase 4G on-open refresh. Opening the dashboard asks the local server for one bounded check of Stats NZ; each check
-- is one row here, so a reopened dashboard, a restarted server and `nzstats status` all see the last result.
-- Timestamps are UTC ISO-8601 like the rest of the schema. Only error classes are stored, never upstream text.

-- How the serve process collects: the APScheduler jobs ('scheduler'), a check when the dashboard is opened
-- ('on_open') or not at all ('off'). NULL on rows written before this migration: read `scheduler_enabled` instead.
ALTER TABLE ops_process ADD COLUMN collection_mode TEXT
  CHECK (collection_mode IN ('scheduler', 'on_open', 'off'));

CREATE TABLE refresh_run (
  id INTEGER PRIMARY KEY,
  trigger TEXT NOT NULL CHECK (trigger IN ('open', 'manual')),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  state TEXT NOT NULL CHECK (state IN ('running', 'completed', 'failed', 'interrupted')),
  phase TEXT NOT NULL CHECK (phase IN ('checking', 'downloading', 'validating', 'done')),
  discovered INTEGER NOT NULL DEFAULT 0,  -- missing releases the check found
  ingested INTEGER NOT NULL DEFAULT 0,
  unchanged INTEGER NOT NULL DEFAULT 0,
  requests INTEGER NOT NULL DEFAULT 0,    -- logical GETs sent to Stats NZ
  failures TEXT NOT NULL DEFAULT '[]',    -- JSON [{"key", "outcome", "error_class"}]
  pending TEXT NOT NULL DEFAULT '[]',     -- JSON [{"release_key", "reason"}]
  error_class TEXT                        -- why a failed check failed as a whole
);
CREATE INDEX refresh_run_started ON refresh_run (started_at);
