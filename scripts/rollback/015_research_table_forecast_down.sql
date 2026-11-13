-- Removes the Phase 4AF table-derived forecasts (migration 015). Back up data/nzstats.db first. This deletes only the
-- figures read from PDF tables; documents, summaries and claims are untouched and can be extracted again.
-- Run with: sqlite3 data/nzstats.db < scripts/rollback/015_research_table_forecast_down.sql
BEGIN IMMEDIATE;
DROP TABLE research_table_rejection;
DROP TABLE research_table_forecast;
DROP TABLE research_table_extraction;
DELETE FROM schema_version WHERE version = 15;
COMMIT;
