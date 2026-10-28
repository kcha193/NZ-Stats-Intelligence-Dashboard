-- Removes the Phase 3E manual-import audit log and the version `acquisition` column (migration 008). Back up
-- data/nzstats.db first. Imported versions stay stored (they become indistinguishable from crawled ones), so if the
-- permission to hold them has gone, delete them with the full research rollback instead.
-- Run with: sqlite3 data/nzstats.db < scripts/rollback/008_research_manual_import_down.sql
BEGIN IMMEDIATE;
DROP TABLE research_manual_import;
ALTER TABLE research_document_version DROP COLUMN acquisition;
DELETE FROM schema_version WHERE version = 8;
COMMIT;
