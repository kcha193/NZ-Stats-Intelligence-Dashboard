-- Existing vintages retain the best metadata available at upgrade. Future vintages snapshot
-- their exact definition before an older backfill or methodology change can overwrite it.
CREATE TABLE vintage_series_definition (
  vintage_id INTEGER PRIMARY KEY REFERENCES vintage(id),
  key TEXT NOT NULL, name TEXT NOT NULL, unit TEXT NOT NULL, frequency TEXT NOT NULL,
  seasonal_adjustment TEXT NOT NULL, definition TEXT NOT NULL, definition_id TEXT NOT NULL,
  category TEXT NOT NULL, source_url TEXT
);
INSERT INTO vintage_series_definition
SELECT v.id, s.key, s.name, s.unit, s.frequency, s.seasonal_adjustment, s.definition,
       s.definition_id, s.category, s.source_url
FROM vintage v JOIN series s ON s.id=v.series_id;
CREATE TRIGGER snapshot_vintage_definition AFTER INSERT ON vintage BEGIN
  INSERT INTO vintage_series_definition
  SELECT NEW.id, key, name, unit, frequency, seasonal_adjustment, definition,
         definition_id, category, source_url FROM series WHERE id=NEW.series_id;
END;
