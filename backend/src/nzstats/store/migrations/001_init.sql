CREATE TABLE raw_artifact (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  http_status INTEGER NOT NULL,
  content_type TEXT,
  size_bytes INTEGER NOT NULL,
  path TEXT NOT NULL,
  UNIQUE (url, sha256)
);

CREATE TABLE release (
  id INTEGER PRIMARY KEY,
  release_key TEXT NOT NULL UNIQUE,
  series_slug TEXT NOT NULL,
  title TEXT NOT NULL,
  period_label TEXT,
  reference_period TEXT,
  published_at TEXT NOT NULL,
  status TEXT NOT NULL,
  page_url TEXT,
  headline TEXT,
  statsnz_id TEXT,
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX release_published_at ON release (published_at);

CREATE TABLE series (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  unit TEXT NOT NULL,
  frequency TEXT NOT NULL,
  seasonal_adjustment TEXT NOT NULL,
  definition TEXT NOT NULL,
  definition_id TEXT NOT NULL,
  category TEXT NOT NULL,
  source_url TEXT
);

CREATE TABLE vintage (
  id INTEGER PRIMARY KEY,
  release_id INTEGER NOT NULL REFERENCES release (id),
  series_id INTEGER NOT NULL REFERENCES series (id),
  captured_at TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('release_files', 'snapshot')),
  layout_version TEXT NOT NULL,
  bundle_sha256 TEXT NOT NULL,
  UNIQUE (release_id, series_id, bundle_sha256)
);
CREATE INDEX vintage_series ON vintage (series_id);

CREATE TABLE observation (
  vintage_id INTEGER NOT NULL REFERENCES vintage (id),
  period TEXT NOT NULL,
  value REAL NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('provisional', 'final', 'unknown')),
  std_error REAL,
  released_in TEXT,
  PRIMARY KEY (vintage_id, period)
) WITHOUT ROWID;

CREATE TABLE ingest_run (
  id INTEGER PRIMARY KEY,
  release_key TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  error_class TEXT,
  detail TEXT
);
CREATE INDEX ingest_run_release ON ingest_run (release_key, started_at);

CREATE TABLE source_health (
  source TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  last_checked_at TEXT,
  last_success_at TEXT,
  detail TEXT
);
