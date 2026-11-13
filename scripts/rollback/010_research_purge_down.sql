-- Removes the Phase 3F purge records and restores the original immutability triggers (migration 010). Back up
-- data/nzstats.db first. Content that was purged is NOT restored (it is gone by design): purged versions keep their
-- hashes, redacted summaries keep their placeholders, and nothing can re-publish them because their text no longer
-- exists. Run with: sqlite3 data/nzstats.db < scripts/rollback/010_research_purge_down.sql
BEGIN IMMEDIATE;
-- Migration 015's triggers read purged_at, so its objects go first (15 is recorded as not applied).
DROP TABLE IF EXISTS research_table_rejection;
DROP TABLE IF EXISTS research_table_forecast;
DROP TABLE IF EXISTS research_table_extraction;
DELETE FROM schema_version WHERE version = 15;
DROP TRIGGER research_claim_not_purged;
DROP TRIGGER research_summary_not_purged;
DROP TRIGGER research_publication_not_purged;
DROP TRIGGER research_section_not_purged;
DROP TRIGGER research_version_purge_final;
DROP TRIGGER research_version_purge_needs_record;
DROP TRIGGER research_claim_no_delete;
CREATE TRIGGER research_claim_no_delete BEFORE DELETE ON research_forecast_claim
BEGIN SELECT RAISE(ABORT, 'research_forecast_claim is immutable'); END;
DROP TRIGGER research_summary_content_immutable;
CREATE TRIGGER research_summary_content_immutable
BEFORE UPDATE OF version_id, run_id, attempt, provider, model, hosted, prompt_version, processing_version,
  verifier_version, parameters, input_sha256, output_sha256, raw_output, output_json, status, error_class,
  verification, created_at ON research_summary
BEGIN SELECT RAISE(ABORT, 'research_summary content is immutable'); END;
ALTER TABLE research_document_version DROP COLUMN purge_id;
ALTER TABLE research_document_version DROP COLUMN purged_at;
DROP TABLE research_purge_artifact;
DROP TABLE research_purge;
DELETE FROM schema_version WHERE version = 10;
COMMIT;
