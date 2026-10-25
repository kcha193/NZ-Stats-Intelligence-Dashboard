-- Phase 3A: institutional research commentary. A separate domain: nothing here references, and no
-- existing table references, the Stats NZ statistical tables (release, series, vintage, observation,
-- ingest_run, source_health). Additive only; scripts/rollback/004_research_down.sql removes it.
CREATE TABLE research_institution (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  review_status TEXT NOT NULL CHECK (review_status IN ('approved', 'needs_review', 'restricted')),
  content_policy TEXT NOT NULL CHECK (content_policy IN ('full_text', 'metadata_only', 'none')),
  synced_at TEXT NOT NULL
);

-- One row per stable document identity: doc_key = '<institution>:<host><path>' of the normalised URL.
CREATE TABLE research_publication (
  id INTEGER PRIMARY KEY,
  institution_id INTEGER NOT NULL REFERENCES research_institution (id),
  doc_key TEXT NOT NULL UNIQUE,
  canonical_url TEXT NOT NULL,
  title TEXT NOT NULL,
  series TEXT,
  categories TEXT NOT NULL DEFAULT '[]',
  published_on TEXT,       -- the institution's publication date, a civil date in Pacific/Auckland
  published_at TEXT,       -- the exact instant (UTC) when the source states one, else NULL
  published_precision TEXT CHECK (published_precision IN ('instant', 'day', 'month')),
  reference_period TEXT,   -- set only from explicit text; never derived from published_on
  content_status TEXT NOT NULL CHECK (content_status IN ('extracted', 'link_only')),
  current_version_id INTEGER REFERENCES research_document_version (id),
  duplicate_of_id INTEGER REFERENCES research_publication (id),
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);
CREATE INDEX research_publication_inst_date ON research_publication (institution_id, published_on);

-- One row per distinct extracted text of a publication (revisions). A revert reuses the older row.
CREATE TABLE research_document_version (
  id INTEGER PRIMARY KEY,
  publication_id INTEGER NOT NULL REFERENCES research_publication (id),
  version_no INTEGER NOT NULL,
  content_sha256 TEXT NOT NULL,   -- raw bytes as fetched
  text_sha256 TEXT NOT NULL,      -- normalised extracted text; the change-detection key
  format TEXT NOT NULL CHECK (format IN ('html', 'pdf')),
  fetched_at TEXT NOT NULL,
  extracted_at TEXT NOT NULL,
  extractor_version TEXT NOT NULL,
  raw_artifact_id INTEGER REFERENCES raw_artifact (id),
  title TEXT NOT NULL,
  page_count INTEGER,
  char_count INTEGER NOT NULL,
  licence_snapshot TEXT NOT NULL, -- the registry policy in force when this was stored
  superseded_at TEXT,
  UNIQUE (publication_id, text_sha256),
  UNIQUE (publication_id, version_no)
);

-- Evidence anchors: Phase 3B cites (version, ordinal, page) and quotes text from here.
CREATE TABLE research_section (
  id INTEGER PRIMARY KEY,
  version_id INTEGER NOT NULL REFERENCES research_document_version (id),
  ordinal INTEGER NOT NULL,
  heading TEXT,
  text TEXT NOT NULL,
  page_start INTEGER,
  page_end INTEGER,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  UNIQUE (version_id, ordinal)
);

CREATE TABLE research_run (
  id INTEGER PRIMARY KEY,
  institution_id INTEGER NOT NULL REFERENCES research_institution (id),
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  dry_run INTEGER NOT NULL DEFAULT 0,
  counts TEXT NOT NULL DEFAULT '{}',
  error_class TEXT,
  detail TEXT
);
CREATE INDEX research_run_inst ON research_run (institution_id, started_at);

CREATE TABLE research_run_item (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES research_run (id),
  url TEXT NOT NULL,
  publication_id INTEGER REFERENCES research_publication (id),
  version_id INTEGER REFERENCES research_document_version (id),
  outcome TEXT NOT NULL,
  error_class TEXT,
  detail TEXT
);
CREATE INDEX research_run_item_run ON research_run_item (run_id);

CREATE TABLE research_source_health (
  institution_id INTEGER PRIMARY KEY REFERENCES research_institution (id),
  state TEXT NOT NULL,
  last_checked_at TEXT,
  last_success_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  detail TEXT
);
