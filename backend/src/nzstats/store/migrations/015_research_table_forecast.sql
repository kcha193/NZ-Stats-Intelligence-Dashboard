-- Phase 4AF: figures read deterministically from PDF forecast tables (research/table_*.py). Additive only: no existing
-- table, row, trigger or index is touched, and a document version with no extraction row simply has no table figures.
-- A stored value is exact decimal text; `raw_text` is what was printed; a missing figure has `value` NULL and `missing`
-- 1 (never zero). Rows are immutable. The text-bearing rows (forecasts, rejections) are deleted by a purge of their
-- document version (research/purge.py); the extraction row stays as a tombstone (hashes and counts, no content).
-- Rollback: scripts/rollback/015_research_table_forecast_down.sql.
CREATE TABLE research_table_extraction (
  id INTEGER PRIMARY KEY,
  version_id INTEGER NOT NULL REFERENCES research_document_version (id),
  interpreter_version TEXT NOT NULL CHECK (length(trim(interpreter_version)) > 0),
  words_sha256 TEXT NOT NULL CHECK (length(words_sha256) = 64),
  extracted_at TEXT NOT NULL,
  forecast_count INTEGER NOT NULL CHECK (forecast_count >= 0),
  rejection_count INTEGER NOT NULL CHECK (rejection_count >= 0),
  UNIQUE (version_id, interpreter_version, words_sha256)
);

CREATE TABLE research_table_forecast (
  id INTEGER PRIMARY KEY,
  extraction_id INTEGER NOT NULL REFERENCES research_table_extraction (id),
  ordinal INTEGER NOT NULL,
  indicator TEXT NOT NULL,
  label TEXT NOT NULL,
  period_text TEXT NOT NULL,
  horizon TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('forecast', 'actual')),
  unit TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  value TEXT,
  missing INTEGER NOT NULL CHECK (missing IN (0, 1)),
  author_role TEXT NOT NULL CHECK (author_role IN ('author', 'third_party')),
  footnote TEXT,
  page INTEGER NOT NULL,
  tbl INTEGER NOT NULL,
  tbl_row INTEGER NOT NULL,
  tbl_col INTEGER NOT NULL,
  evidence TEXT NOT NULL,
  CHECK ((missing = 1 AND value IS NULL) OR (missing = 0 AND value IS NOT NULL)),
  UNIQUE (extraction_id, ordinal)
);
CREATE INDEX research_table_forecast_extraction ON research_table_forecast (extraction_id, ordinal);

CREATE TABLE research_table_rejection (
  id INTEGER PRIMARY KEY,
  extraction_id INTEGER NOT NULL REFERENCES research_table_extraction (id),
  ordinal INTEGER NOT NULL,
  code TEXT NOT NULL CHECK (length(trim(code)) > 0),
  page INTEGER,
  tbl INTEGER,
  tbl_row INTEGER,
  tbl_col INTEGER,
  UNIQUE (extraction_id, ordinal)
);

-- Immutable, and nothing can be stored for the text of a purged version.
CREATE TRIGGER research_table_extraction_immutable BEFORE UPDATE ON research_table_extraction
BEGIN SELECT RAISE(ABORT, 'research_table_extraction is immutable'); END;
CREATE TRIGGER research_table_extraction_no_delete BEFORE DELETE ON research_table_extraction
BEGIN SELECT RAISE(ABORT, 'research_table_extraction is immutable'); END;
CREATE TRIGGER research_table_extraction_not_purged BEFORE INSERT ON research_table_extraction
WHEN (SELECT purged_at FROM research_document_version WHERE id = NEW.version_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'the text of a purged version cannot have table figures'); END;

CREATE TRIGGER research_table_forecast_immutable BEFORE UPDATE ON research_table_forecast
BEGIN SELECT RAISE(ABORT, 'research_table_forecast is immutable'); END;
CREATE TRIGGER research_table_forecast_no_delete BEFORE DELETE ON research_table_forecast
WHEN NOT EXISTS (
  SELECT 1 FROM research_table_extraction e JOIN research_document_version v ON v.id = e.version_id
  WHERE e.id = OLD.extraction_id AND v.purged_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT, 'research_table_forecast is immutable'); END;

CREATE TRIGGER research_table_rejection_immutable BEFORE UPDATE ON research_table_rejection
BEGIN SELECT RAISE(ABORT, 'research_table_rejection is immutable'); END;
CREATE TRIGGER research_table_rejection_no_delete BEFORE DELETE ON research_table_rejection
WHEN NOT EXISTS (
  SELECT 1 FROM research_table_extraction e JOIN research_document_version v ON v.id = e.version_id
  WHERE e.id = OLD.extraction_id AND v.purged_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT, 'research_table_rejection is immutable'); END;
