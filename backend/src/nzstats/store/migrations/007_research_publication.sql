-- Phase 3C: per-summary publication decisions. Human review (006) says a summary reflects its evidence; publication
-- is a separate, later decision that it may be shown publicly. Append-only: the latest decision wins. Additive and
-- research-only. Rollback: scripts/rollback/007_research_publication_down.sql.
CREATE TABLE research_summary_publication (
  id INTEGER PRIMARY KEY,
  summary_id INTEGER NOT NULL REFERENCES research_summary (id),
  decision TEXT NOT NULL CHECK (decision IN ('publish', 'withdraw')),
  approver TEXT NOT NULL CHECK (length(trim(approver)) > 0),
  note TEXT NOT NULL CHECK (length(trim(note)) > 0),   -- private: never served
  decided_at TEXT NOT NULL
);
CREATE INDEX research_summary_publication_summary ON research_summary_publication (summary_id, id);

CREATE TRIGGER research_publication_approved_only BEFORE INSERT ON research_summary_publication
WHEN NEW.decision = 'publish' AND NOT EXISTS (
  SELECT 1 FROM research_summary
  WHERE id = NEW.summary_id AND status = 'verified' AND review_status = 'approved')
BEGIN SELECT RAISE(ABORT, 'only an approved, verified summary can be published'); END;

CREATE TRIGGER research_publication_immutable BEFORE UPDATE ON research_summary_publication
BEGIN SELECT RAISE(ABORT, 'publication decisions are immutable'); END;

CREATE TRIGGER research_publication_no_delete BEFORE DELETE ON research_summary_publication
BEGIN SELECT RAISE(ABORT, 'publication decisions are immutable'); END;
