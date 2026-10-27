-- Removes the Phase 3C publication decisions (migration 007) and keeps every summary and review. Back up
-- data/nzstats.db first. With the table gone nothing is publication-approved, so nothing can be served publicly.
-- Run with: sqlite3 data/nzstats.db < scripts/rollback/007_research_publication_down.sql
BEGIN IMMEDIATE;
DROP TABLE research_summary_publication;
DELETE FROM schema_version WHERE version = 7;
COMMIT;
