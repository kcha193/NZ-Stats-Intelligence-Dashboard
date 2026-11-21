-- Reverses migration 016: restores the html/pdf-only format CHECKs. Back up data/nzstats.db first.
-- REFUSES while any xlsx version or import exists: re-inserting such a row fails the restored CHECK and the transaction
-- is abandoned unchanged. Purge (nzstats research purge) or remove those rows first, deliberately.
-- `.bail on` makes the sqlite3 shell stop at that first error instead of running on; keep it the first statement.
-- Run with: sqlite3 data/nzstats.db < scripts/rollback/016_research_xlsx_format_down.sql
.bail on
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;
PRAGMA defer_foreign_keys = ON;

CREATE TABLE research_document_version_m016 AS SELECT * FROM research_document_version;
CREATE TABLE research_manual_import_m016 AS SELECT * FROM research_manual_import;
DROP TABLE research_manual_import;
DROP TABLE research_document_version;

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
  superseded_at TEXT, acquisition TEXT NOT NULL DEFAULT 'crawler' CHECK (acquisition IN ('crawler', 'manual')), purged_at TEXT, purge_id INTEGER,
  UNIQUE (publication_id, text_sha256),
  UNIQUE (publication_id, version_no)
);
INSERT INTO research_document_version SELECT * FROM research_document_version_m016;
DROP TABLE research_document_version_m016;

CREATE TABLE research_manual_import (
  id INTEGER PRIMARY KEY,
  institution_id INTEGER NOT NULL REFERENCES research_institution (id),
  url TEXT NOT NULL,                       -- the document's address on an allowed host (checked, never requested)
  publication_id INTEGER REFERENCES research_publication (id),
  version_id INTEGER REFERENCES research_document_version (id),
  outcome TEXT NOT NULL CHECK (outcome IN ('new', 'updated', 'reactivated', 'unchanged', 'duplicate')),
  file_format TEXT NOT NULL CHECK (file_format IN ('html', 'pdf')),
  content_sha256 TEXT NOT NULL,            -- the supplied bytes
  text_sha256 TEXT NOT NULL,               -- the extracted text
  imported_by TEXT NOT NULL CHECK (length(trim(imported_by)) > 0),
  note TEXT NOT NULL CHECK (length(trim(note)) > 0),   -- private: where and how the copy was obtained; never served
  licence_snapshot TEXT NOT NULL,          -- the registry permissions in force at import
  imported_at TEXT NOT NULL
);
INSERT INTO research_manual_import SELECT * FROM research_manual_import_m016;
DROP TABLE research_manual_import_m016;

CREATE INDEX research_manual_import_institution ON research_manual_import (institution_id, id);
CREATE TRIGGER research_manual_import_immutable BEFORE UPDATE ON research_manual_import
BEGIN SELECT RAISE(ABORT, 'manual import records are immutable'); END;
CREATE TRIGGER research_manual_import_no_delete BEFORE DELETE ON research_manual_import
BEGIN SELECT RAISE(ABORT, 'manual import records are immutable'); END;
CREATE TRIGGER research_version_purge_final BEFORE UPDATE OF purged_at, purge_id ON research_document_version
WHEN OLD.purged_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a purge cannot be undone'); END;
CREATE TRIGGER research_version_purge_needs_record BEFORE UPDATE OF purged_at ON research_document_version
WHEN NEW.purged_at IS NOT NULL AND OLD.purged_at IS NULL
  AND (NEW.purge_id IS NULL OR NOT EXISTS (SELECT 1 FROM research_purge WHERE id = NEW.purge_id))
BEGIN SELECT RAISE(ABORT, 'a version is purged only under a recorded purge'); END;
DELETE FROM schema_version WHERE version = 16;
COMMIT;
