-- A duplicate publication records the exact stored version whose text it matched, so a later revision of
-- the original does not change what the duplicate is attributed to. Additive: one nullable column on a
-- research table. Rolled back together with the other research tables (scripts/rollback/004_research_down.sql).
ALTER TABLE research_publication
  ADD COLUMN duplicate_of_version_id INTEGER REFERENCES research_document_version (id);
