-- Phase 3F: targeted purge of stored source content when a permission is withdrawn. A purge removes the licensed
-- text (sections), derived model output and forecast claims, and the raw files, but keeps every audit fact: the
-- version row stays as a tombstone (ids, hashes, timestamps, how it was obtained), the summary rows stay with their
-- content columns redacted, and the append-only logs (manual imports, reviews, publication decisions, usage, model
-- spend) are never touched. Redaction is possible only for a version already marked purged, and only to fixed
-- placeholder values. Additive and research-only. Rollback: scripts/rollback/010_research_purge_down.sql.

CREATE TABLE research_purge (
  id INTEGER PRIMARY KEY,
  institution_id INTEGER NOT NULL REFERENCES research_institution (id),
  reason TEXT NOT NULL CHECK (reason IN ('permission_withdrawn', 'takedown', 'other')),
  scope TEXT NOT NULL,                        -- JSON: the selector used (acquisition filter or version ids)
  purged_by TEXT NOT NULL CHECK (length(trim(purged_by)) > 0),
  note TEXT NOT NULL CHECK (length(trim(note)) > 0),   -- private; never served
  versions INTEGER NOT NULL,
  sections INTEGER NOT NULL,
  summaries INTEGER NOT NULL,                 -- summaries whose stored output was redacted
  claims INTEGER NOT NULL,
  withdrawn INTEGER NOT NULL,                 -- published summaries withdrawn by this purge
  artifacts INTEGER NOT NULL,                 -- raw artifacts scheduled for removal
  purged_at TEXT NOT NULL
);
CREATE INDEX research_purge_institution ON research_purge (institution_id, id);

-- The raw artifacts a purge removed, kept as evidence of what was destroyed (hash and address, never the bytes).
-- `removed_at` is NULL while the removal is pending (a crash between the database step and the file step leaves a
-- pending row that `research purge` finishes).
CREATE TABLE research_purge_artifact (
  id INTEGER PRIMARY KEY,
  purge_id INTEGER NOT NULL REFERENCES research_purge (id),
  raw_artifact_id INTEGER NOT NULL,           -- no foreign key: the raw_artifact row is deleted
  url TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  path TEXT NOT NULL,
  outcome TEXT CHECK (outcome IS NULL OR outcome IN ('removed', 'file_kept_shared', 'file_missing', 'unsafe_path')),
  removed_at TEXT,
  UNIQUE (purge_id, raw_artifact_id)
);

CREATE TRIGGER research_purge_immutable BEFORE UPDATE ON research_purge
BEGIN SELECT RAISE(ABORT, 'purge records are immutable'); END;
CREATE TRIGGER research_purge_no_delete BEFORE DELETE ON research_purge
BEGIN SELECT RAISE(ABORT, 'purge records are immutable'); END;
CREATE TRIGGER research_purge_artifact_no_delete BEFORE DELETE ON research_purge_artifact
BEGIN SELECT RAISE(ABORT, 'purge records are immutable'); END;
CREATE TRIGGER research_purge_artifact_facts BEFORE UPDATE OF purge_id, raw_artifact_id, url, sha256, path
  ON research_purge_artifact
BEGIN SELECT RAISE(ABORT, 'purge records are immutable'); END;
CREATE TRIGGER research_purge_artifact_once BEFORE UPDATE ON research_purge_artifact
WHEN OLD.removed_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'purge records are immutable'); END;

-- The tombstone: a purged version keeps its row and hashes; its text and files are gone.
ALTER TABLE research_document_version ADD COLUMN purged_at TEXT;
ALTER TABLE research_document_version ADD COLUMN purge_id INTEGER;   -- the purge that removed it (no foreign key: see rollback)

CREATE TRIGGER research_version_purge_needs_record BEFORE UPDATE OF purged_at ON research_document_version
WHEN NEW.purged_at IS NOT NULL AND OLD.purged_at IS NULL
  AND (NEW.purge_id IS NULL OR NOT EXISTS (SELECT 1 FROM research_purge WHERE id = NEW.purge_id))
BEGIN SELECT RAISE(ABORT, 'a version is purged only under a recorded purge'); END;
CREATE TRIGGER research_version_purge_final BEFORE UPDATE OF purged_at, purge_id ON research_document_version
WHEN OLD.purged_at IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'a purge cannot be undone'); END;
CREATE TRIGGER research_section_not_purged BEFORE INSERT ON research_section
WHEN (SELECT purged_at FROM research_document_version WHERE id = NEW.version_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'the text of a purged version cannot be stored again'); END;
CREATE TRIGGER research_publication_not_purged BEFORE INSERT ON research_summary_publication
WHEN NEW.decision = 'publish' AND EXISTS (
  SELECT 1 FROM research_summary s JOIN research_document_version v ON v.id = s.version_id
  WHERE s.id = NEW.summary_id AND v.purged_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT, 'a summary of purged text cannot be published'); END;

-- Redaction: the one permitted change to a stored summary or claim, and only once its version is purged.
DROP TRIGGER research_summary_content_immutable;
CREATE TRIGGER research_summary_content_immutable
BEFORE UPDATE OF version_id, run_id, attempt, provider, model, hosted, prompt_version, processing_version,
  verifier_version, parameters, input_sha256, output_sha256, raw_output, output_json, status, error_class,
  verification, created_at ON research_summary
WHEN NOT (
  (SELECT purged_at FROM research_document_version WHERE id = OLD.version_id) IS NOT NULL
  AND NEW.version_id IS OLD.version_id AND NEW.run_id IS OLD.run_id AND NEW.attempt IS OLD.attempt
  AND NEW.provider IS OLD.provider AND NEW.model IS OLD.model AND NEW.hosted IS OLD.hosted
  AND NEW.prompt_version IS OLD.prompt_version AND NEW.processing_version IS OLD.processing_version
  AND NEW.verifier_version IS OLD.verifier_version AND NEW.parameters IS OLD.parameters
  AND NEW.input_sha256 IS OLD.input_sha256 AND NEW.output_sha256 IS OLD.output_sha256
  AND NEW.status IS OLD.status AND NEW.error_class IS OLD.error_class AND NEW.created_at IS OLD.created_at
  AND NEW.raw_output IS NULL
  AND (NEW.output_json IS OLD.output_json OR NEW.output_json = '{"redacted":true}')
  AND (NEW.verification IS OLD.verification OR NEW.verification = '{"redacted":true}')
)
BEGIN SELECT RAISE(ABORT, 'research_summary content is immutable'); END;

DROP TRIGGER research_claim_no_delete;
CREATE TRIGGER research_claim_no_delete BEFORE DELETE ON research_forecast_claim
WHEN NOT EXISTS (
  SELECT 1 FROM research_summary s JOIN research_document_version v ON v.id = s.version_id
  WHERE s.id = OLD.summary_id AND v.purged_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT, 'research_forecast_claim is immutable'); END;
