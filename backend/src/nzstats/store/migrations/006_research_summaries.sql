-- Phase 3B: evidence-grounded LLM summaries of research document versions. Additive, research-only: nothing
-- here references the Stats NZ statistical tables. Summaries are append-only (a new prompt or processing
-- version adds rows); only the review columns change, and only a verified summary can be approved.
-- Rollback: scripts/rollback/006_research_summaries_down.sql.

-- One deliberate `research summarise` invocation: the processing audit trail.
CREATE TABLE research_llm_run (
  id INTEGER PRIMARY KEY,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  hosted INTEGER NOT NULL,
  prompt_version TEXT NOT NULL,
  processing_version TEXT NOT NULL,
  limits TEXT NOT NULL DEFAULT '{}',
  dry_run INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  outcome TEXT,
  counts TEXT NOT NULL DEFAULT '{}',
  spent_usd REAL NOT NULL DEFAULT 0
);

CREATE TABLE research_summary (
  id INTEGER PRIMARY KEY,
  version_id INTEGER NOT NULL REFERENCES research_document_version (id),
  run_id INTEGER NOT NULL REFERENCES research_llm_run (id),
  attempt INTEGER NOT NULL DEFAULT 1,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  hosted INTEGER NOT NULL,
  prompt_version TEXT NOT NULL,
  processing_version TEXT NOT NULL,
  verifier_version TEXT NOT NULL,
  parameters TEXT NOT NULL DEFAULT '{}',
  input_sha256 TEXT NOT NULL,      -- the canonical request (rules, sections, provider, model, parameters)
  output_sha256 TEXT,              -- the raw model output
  raw_output TEXT,                 -- kept for audit; derived from licensed text, so local only
  output_json TEXT,                -- the validated OutlookSummary (NULL for invalid output or provider error)
  status TEXT NOT NULL
    CHECK (status IN ('verified', 'failed_verification', 'invalid_output', 'provider_error')),
  error_class TEXT,                -- fixed vocabulary, never a raw exception message
  verification TEXT,               -- the VerificationReport (errors, warnings, scope)
  review_status TEXT NOT NULL DEFAULT 'unreviewed'
    CHECK (review_status IN ('unreviewed', 'approved', 'rejected')),
  reviewed_by TEXT,
  reviewed_at TEXT,
  review_note TEXT,
  created_at TEXT NOT NULL,
  CHECK (status NOT IN ('verified', 'failed_verification') OR output_json IS NOT NULL),
  UNIQUE (version_id, provider, model, prompt_version, processing_version, input_sha256, attempt)
);
CREATE INDEX research_summary_version ON research_summary (version_id);

-- Explicit forecasts from verified summaries, one row per claim, for "what did each institution forecast".
CREATE TABLE research_forecast_claim (
  id INTEGER PRIMARY KEY,
  summary_id INTEGER NOT NULL REFERENCES research_summary (id),
  ordinal INTEGER NOT NULL,
  indicator TEXT NOT NULL,
  indicator_label TEXT NOT NULL,
  horizon TEXT NOT NULL,
  value REAL,
  unit TEXT,
  direction TEXT NOT NULL,
  scenario TEXT,                   -- NULL: the baseline or central forecast
  qualification TEXT,
  evidence TEXT NOT NULL,          -- JSON list of {version_id, section_ordinal, page, quote}
  UNIQUE (summary_id, ordinal)
);
CREATE INDEX research_forecast_claim_indicator ON research_forecast_claim (indicator);

-- One row per provider call, retries included: tokens, latency and estimated cost.
CREATE TABLE research_llm_usage (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES research_llm_run (id),
  version_id INTEGER NOT NULL REFERENCES research_document_version (id),
  summary_id INTEGER REFERENCES research_summary (id),
  call_no INTEGER NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  usage_estimated INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER NOT NULL,
  cost_usd REAL NOT NULL,
  outcome TEXT NOT NULL,
  error_class TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX research_llm_usage_run ON research_llm_usage (run_id);

-- Every human decision, in order. research_summary.review_status holds the latest.
CREATE TABLE research_summary_review (
  id INTEGER PRIMARY KEY,
  summary_id INTEGER NOT NULL REFERENCES research_summary (id),
  decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
  reviewer TEXT NOT NULL,
  note TEXT,
  decided_at TEXT NOT NULL
);

CREATE TRIGGER research_summary_content_immutable
BEFORE UPDATE OF version_id, run_id, attempt, provider, model, hosted, prompt_version, processing_version,
  verifier_version, parameters, input_sha256, output_sha256, raw_output, output_json, status, error_class,
  verification, created_at ON research_summary
BEGIN SELECT RAISE(ABORT, 'research_summary content is immutable'); END;

CREATE TRIGGER research_summary_no_delete BEFORE DELETE ON research_summary
BEGIN SELECT RAISE(ABORT, 'research_summary is immutable (append-only history)'); END;

CREATE TRIGGER research_summary_starts_unreviewed BEFORE INSERT ON research_summary
WHEN NEW.review_status != 'unreviewed'
BEGIN SELECT RAISE(ABORT, 'a new summary starts unreviewed'); END;

CREATE TRIGGER research_summary_approve_verified_only BEFORE UPDATE OF review_status ON research_summary
WHEN NEW.review_status = 'approved' AND OLD.status != 'verified'
BEGIN SELECT RAISE(ABORT, 'only verified summaries can be approved'); END;

CREATE TRIGGER research_summary_rejection_final BEFORE UPDATE OF review_status ON research_summary
WHEN OLD.review_status = 'rejected' AND NEW.review_status != 'rejected'
BEGIN SELECT RAISE(ABORT, 'a rejected summary stays rejected'); END;

CREATE TRIGGER research_review_verified_only BEFORE INSERT ON research_summary_review
WHEN NEW.decision = 'approved'
  AND (SELECT status FROM research_summary WHERE id = NEW.summary_id) != 'verified'
BEGIN SELECT RAISE(ABORT, 'only verified summaries can be approved'); END;

CREATE TRIGGER research_review_immutable BEFORE UPDATE ON research_summary_review
BEGIN SELECT RAISE(ABORT, 'review decisions are immutable'); END;

CREATE TRIGGER research_review_no_delete BEFORE DELETE ON research_summary_review
BEGIN SELECT RAISE(ABORT, 'review decisions are immutable'); END;

CREATE TRIGGER research_claim_verified_only BEFORE INSERT ON research_forecast_claim
WHEN (SELECT status FROM research_summary WHERE id = NEW.summary_id) != 'verified'
BEGIN SELECT RAISE(ABORT, 'claims are stored for verified summaries only'); END;

CREATE TRIGGER research_claim_immutable BEFORE UPDATE ON research_forecast_claim
BEGIN SELECT RAISE(ABORT, 'research_forecast_claim is immutable'); END;

CREATE TRIGGER research_claim_no_delete BEFORE DELETE ON research_forecast_claim
BEGIN SELECT RAISE(ABORT, 'research_forecast_claim is immutable'); END;

CREATE TRIGGER research_usage_immutable BEFORE UPDATE ON research_llm_usage
BEGIN SELECT RAISE(ABORT, 'research_llm_usage is immutable'); END;

CREATE TRIGGER research_usage_no_delete BEFORE DELETE ON research_llm_usage
BEGIN SELECT RAISE(ABORT, 'research_llm_usage is immutable'); END;
