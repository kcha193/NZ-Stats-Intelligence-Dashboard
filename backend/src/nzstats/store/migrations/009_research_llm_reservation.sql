-- Phase 3F: concurrency-safe model spending. Every provider call reserves its worst-case cost here, inside the
-- database's write lock, before the provider is contacted, so two processes cannot both spend the same remainder
-- of the rolling cap. A reservation is settled to the actual cost when the call returns; one that never settles
-- (the process died or the call was interrupted) keeps counting at its reserved worst case, because whether the
-- provider billed it is unknown. Additive and research-only. Rollback: scripts/rollback/009_research_llm_reservation_down.sql.
CREATE TABLE research_llm_reservation (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES research_llm_run (id),
  version_id INTEGER NOT NULL REFERENCES research_document_version (id),
  call_no INTEGER NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  reserved_usd REAL NOT NULL CHECK (reserved_usd >= 0),     -- the worst case for this call
  state TEXT NOT NULL DEFAULT 'held' CHECK (state IN ('held', 'settled', 'abandoned')),
  actual_usd REAL CHECK (actual_usd IS NULL OR actual_usd >= 0),
  settle_basis TEXT CHECK (settle_basis IS NULL OR settle_basis IN
    ('reported', 'estimated', 'not_billed', 'worst_case', 'interrupted')),
  created_at TEXT NOT NULL,
  closed_at TEXT,
  CHECK ((state = 'settled') = (actual_usd IS NOT NULL)),
  CHECK ((state = 'held') = (closed_at IS NULL))
);
CREATE INDEX research_llm_reservation_created ON research_llm_reservation (created_at);
CREATE INDEX research_llm_reservation_run ON research_llm_reservation (run_id, state);

CREATE TRIGGER research_reservation_no_delete BEFORE DELETE ON research_llm_reservation
BEGIN SELECT RAISE(ABORT, 'research_llm_reservation is append-only'); END;

CREATE TRIGGER research_reservation_immutable
BEFORE UPDATE OF run_id, version_id, call_no, provider, model, reserved_usd, created_at ON research_llm_reservation
BEGIN SELECT RAISE(ABORT, 'research_llm_reservation facts are immutable'); END;

-- held -> settled | abandoned, once. A closed reservation never changes again.
CREATE TRIGGER research_reservation_closed BEFORE UPDATE ON research_llm_reservation
WHEN OLD.state != 'held'
BEGIN SELECT RAISE(ABORT, 'a closed reservation cannot change'); END;
