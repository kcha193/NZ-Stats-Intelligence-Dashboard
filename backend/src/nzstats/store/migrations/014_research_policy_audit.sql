-- Phase 4W: an append-only audit of operator-run inference policies (research/policy.py). Metadata only: no prompt text,
-- document text, model output or credential has a column here. The reservation ledger (migration 009) stays the authority on
-- what was spent and attempted; this table adds what it cannot say (which policy, which pinned prompt and verifier, which
-- refusal, who confirmed) and is a second, independent record that a document's content was already used, so retagging a run
-- or renaming a document cannot restore a spent attempt. Additive and research-only.
-- Rollback: scripts/rollback/014_research_policy_audit_down.sql.
CREATE TABLE research_policy_event (
  id INTEGER PRIMARY KEY,
  event TEXT NOT NULL CHECK (event IN ('refused', 'executed', 'revoked')),
  policy_id TEXT NOT NULL CHECK (length(trim(policy_id)) > 0),
  policy_sha256 TEXT NOT NULL CHECK (length(policy_sha256) = 64),
  version_id INTEGER REFERENCES research_document_version (id),
  content_sha256 TEXT,
  request_sha256 TEXT,
  model TEXT,
  provider_id TEXT,
  prompt_version TEXT,
  prompt_sha256 TEXT,
  verifier_version TEXT,
  verifier_sha256 TEXT,
  attempt_no INTEGER,
  outcome TEXT,
  summary_id INTEGER,
  run_id INTEGER,
  reserved_usd REAL CHECK (reserved_usd IS NULL OR reserved_usd >= 0),
  cost_usd REAL CHECK (cost_usd IS NULL OR cost_usd >= 0),
  input_tokens INTEGER,
  output_tokens INTEGER,
  errors INTEGER,
  warnings INTEGER,
  refusal_code TEXT,
  detail TEXT,                      -- fixed, content-free wording only
  operator TEXT NOT NULL CHECK (length(trim(operator)) > 0),
  created_at TEXT NOT NULL,
  CHECK (event != 'refused' OR refusal_code IS NOT NULL),
  CHECK (event != 'executed' OR (version_id IS NOT NULL AND content_sha256 IS NOT NULL AND request_sha256 IS NOT NULL))
);
CREATE INDEX research_policy_event_policy ON research_policy_event (policy_sha256, event);
-- One executed event per document content, whichever policy, version row or title it arrives under.
CREATE UNIQUE INDEX research_policy_event_content_once ON research_policy_event (content_sha256) WHERE event = 'executed';

CREATE TRIGGER research_policy_event_immutable BEFORE UPDATE ON research_policy_event
BEGIN SELECT RAISE(ABORT, 'research_policy_event is append-only'); END;

CREATE TRIGGER research_policy_event_no_delete BEFORE DELETE ON research_policy_event
BEGIN SELECT RAISE(ABORT, 'research_policy_event is append-only'); END;
