-- Phase 3E: permission-compliant manual import of an owner-supplied document. How each stored version was obtained
-- (`acquisition`), and an append-only audit record of every import attempt that reached the store, whatever its
-- outcome. Additive and research-only. Rollback: scripts/rollback/008_research_manual_import_down.sql.
ALTER TABLE research_document_version
  ADD COLUMN acquisition TEXT NOT NULL DEFAULT 'crawler' CHECK (acquisition IN ('crawler', 'manual'));

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
CREATE INDEX research_manual_import_institution ON research_manual_import (institution_id, id);

CREATE TRIGGER research_manual_import_immutable BEFORE UPDATE ON research_manual_import
BEGIN SELECT RAISE(ABORT, 'manual import records are immutable'); END;

CREATE TRIGGER research_manual_import_no_delete BEFORE DELETE ON research_manual_import
BEGIN SELECT RAISE(ABORT, 'manual import records are immutable'); END;
