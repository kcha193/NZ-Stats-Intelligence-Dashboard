-- Removes the Phase 4W policy audit (migration 014). Back up data/nzstats.db first. This deletes the audit of operator-run
-- policies only; the reservation ledger (research_llm_*) is untouched and still counts every attempt and dollar.
-- Run with: sqlite3 data/nzstats.db < scripts/rollback/014_research_policy_audit_down.sql
BEGIN IMMEDIATE;
DROP TRIGGER research_policy_event_no_delete;
DROP TRIGGER research_policy_event_immutable;
DROP INDEX research_policy_event_content_once;
DROP INDEX research_policy_event_policy;
DROP TABLE research_policy_event;
DELETE FROM schema_version WHERE version = 14;
COMMIT;
