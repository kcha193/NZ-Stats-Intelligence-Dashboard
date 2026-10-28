-- Removes all research tables (migrations 004, 005 and, when present, 006 to 009). Nothing outside research_* references
-- them, so the Stats NZ data, API and snapshot export are unaffected. Back up data/nzstats.db first: this deletes all
-- stored research commentary. Run with: sqlite3 data/nzstats.db < scripts/rollback/004_research_down.sql
BEGIN IMMEDIATE;
DROP TABLE IF EXISTS research_manual_import;
DROP TABLE IF EXISTS research_llm_reservation;
DROP TABLE IF EXISTS research_summary_publication;
DROP TABLE IF EXISTS research_summary_review;
DROP TABLE IF EXISTS research_forecast_claim;
DROP TABLE IF EXISTS research_llm_usage;
DROP TABLE IF EXISTS research_summary;
DROP TABLE IF EXISTS research_llm_run;
UPDATE research_publication
   SET current_version_id = NULL, duplicate_of_id = NULL, duplicate_of_version_id = NULL;
DROP TABLE research_run_item;
DROP TABLE research_run;
DROP TABLE research_source_health;
DROP TABLE research_section;
DROP TABLE research_document_version;
DROP TABLE research_publication;
DROP TABLE research_institution;
DELETE FROM schema_version WHERE version IN (4, 5, 6, 7, 8, 9);
COMMIT;
