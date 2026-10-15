-- "Latest" used to be the highest vintage id, so a release that reverted to an earlier bundle
-- (A -> B -> A) could not make A current again: its vintages already existed. `activation` orders
-- vintages by when their bundle last became the release's current content; a revert bumps it.
ALTER TABLE vintage ADD COLUMN activation INTEGER NOT NULL DEFAULT 0;
UPDATE vintage SET activation = id;
CREATE INDEX vintage_activation ON vintage (series_id, activation);
