-- Preserve the initial on-open catch-up boundary before discovery or ingestion can advance a series.
-- Late-discovered releases newer than this boundary remain eligible across partial feeds and restarts.
-- Existing history at/before the boundary stays the responsibility of explicit backfill.
CREATE TABLE refresh_catch_up (
    series_slug TEXT PRIMARY KEY,
    after_published_at TEXT NOT NULL
);
