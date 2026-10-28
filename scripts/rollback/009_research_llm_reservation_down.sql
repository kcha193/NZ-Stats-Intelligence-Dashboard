-- Removes the Phase 3F model-spend reservations (migration 009). Back up data/nzstats.db first. The usage rows and the
-- per-run totals stay, so the rolling 30-day cap counts every settled call, but a reservation that was still held or
-- abandoned (a call whose cost was unknown) stops counting, so run nothing until the 30 days have passed or the cap is
-- lowered by that amount. Run with: sqlite3 data/nzstats.db < scripts/rollback/009_research_llm_reservation_down.sql
BEGIN IMMEDIATE;
DROP TABLE research_llm_reservation;
DELETE FROM schema_version WHERE version = 9;
COMMIT;
