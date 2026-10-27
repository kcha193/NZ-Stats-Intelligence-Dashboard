-- Removes the Phase 3B summary tables (migration 006), and the 007 publication log that references them, and keeps the Phase 3A research tables. Back up
-- data/nzstats.db first: this deletes every stored summary, forecast claim, review decision and usage record.
-- Run with: sqlite3 data/nzstats.db < scripts/rollback/006_research_summaries_down.sql
BEGIN IMMEDIATE;
DROP TABLE IF EXISTS research_summary_publication;
DROP TABLE research_summary_review;
DROP TABLE research_forecast_claim;
DROP TABLE research_llm_usage;
DROP TABLE research_summary;
DROP TABLE research_llm_run;
DELETE FROM schema_version WHERE version IN (6, 7);
COMMIT;
