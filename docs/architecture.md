# Architecture

One container, one SQLite file. The backend discovers releases, downloads each release's official data
files, validates and stores them as dated vintages, derives findings, and serves a read-only API plus
the built single-page app.

```
 Stats NZ                                         Browser
   | ICS calendar, month listing, release pages,    ^
   | official CSV downloads (10 s apart)            | JSON + static files
   v                                                |
 sources/ --> pipeline/ (discover, ingest) --> store/ (SQLite) --> api/ (FastAPI) --> frontend/
   fetcher        adapters/ validate/ stats/ insights/    ^
   artifact store      one transaction per release        |
                                      scheduler/ (APScheduler, Pacific/Auckland)
```

Boundaries: adapters know file layouts; `stats/` knows only numbers; `api/` only reads the store; the
frontend only calls the API. Types flow from Pydantic models to `frontend/src/api/schema.d.ts`.

## Data flow

1. **Discover**: the ICS export (official) and the month listing endpoint (undocumented) populate the
   `release` table: key (`<series slug>:<month year>`), title, scheduled or published time, page URL,
   category and importance (editorial, from `catalog.py`).
2. **Fetch**: the release page embeds JSON listing its downloads. Files are fetched through `Fetcher`
   (descriptive User-Agent, at least 10 s between requests even across processes, retries with backoff for network and 5xx,
   block-page detection) and stored content-addressed in `raw_artifact` and `data/raw/`.
3. **Parse and validate**: the migration adapter parses the age/sex and citizenship/visa/country CSVs and the
   embedded chart series into observations. `validate/` checks required series, period continuity, that the
   latest period matches the release title, magnitude against the previous vintage, and non-null headlines.
4. **Persist**: one SQLite transaction writes the vintages and their observations. Re-ingesting identical bytes
   is a no-op (`unchanged`). A failure writes an `ingest_run` row with an error class and leaves previous
   data untouched.
5. **Analyse**: `insights/` builds the release analysis (executive summary, context, revisions,
   interpretation) from stored observations. Each finding carries evidence ids (series, period, value,
   release). Inferences are labelled; no causal claims.
6. **Serve**: `api/` exposes read-only endpoints and the SPA fallback.

## Data model (SQLite, schema in `store/migrations/`)

| Table | Purpose |
|---|---|
| `release` | one row per scheduled or published release; status `scheduled/published/delayed/corrected/unavailable` |
| `raw_artifact` | downloaded files: URL, SHA-256, fetch time, HTTP status, content type, size and path under `data/raw/` |
| `series` | series definitions: key, unit, frequency, adjustment, definition |
| `vintage` | one per (release, series) bundle: capture time, source kind (`release_files` or `snapshot`), parser layout version, bundle hash |
| `observation` | (vintage, period) values with status `provisional/final/unknown`, standard error and the release whose file last published the figure (`released_in`, from the file's `month_of_release`) |
| `ingest_run` | every attempt: outcome, error class, detail (no raw exception text) |
| `source_health` | per source: last checked, last success, state and detail |

A vintage is the official data as published in one release. Revisions are computed between consecutive
vintages; where vintages do not exist the UI says so instead of reconstructing them.

## Scheduling (`scheduler/`)

In-process APScheduler in Pacific/Auckland: calendar refresh daily 06:00; a per-minute release watch that
touches the network only when a release is due, polling at offsets after the scheduled time
(`config/sources.toml`: 0, 1, 2, 5, 10, 15, 30, 60, 120, 180 minutes) and then marking the release
`unavailable`; a catch-up job daily 07:30; and a refresh plus catch-up shortly after start. A process-wide
lock serialises network work inside the server, and a `flock` file (`data/.request-pace`, `FilePacer`) keeps
requests at least 10 s apart across processes, so a CLI run beside the server cannot break the crawl delay. The same
file holds the 30 minute block cooldown (wall-clock deadline, written while the lock is still held), so a 403,
challenge page or unexpected HTML in one process stops requests from every process sharing `data/`. `nzstats serve --no-scheduler` disables all of it.

## Failure handling

| Class | Meaning | Behaviour |
|---|---|---|
| `network` | timeouts, connection errors, 5xx | retried with backoff; run recorded |
| `blocked` | 403, bot-protection page, or HTML where data was expected | not retried; all requests stop for 30 min across processes; source marked degraded |
| `not_found` | files not published yet | normal before publication; polling continues within its window |
| `layout_changed` | expected columns or embedded JSON missing | nothing stored; needs an adapter update |
| `validation_failed` | parsed but implausible | nothing stored; last-known-good stays live |
| `unexpected` | anything else | logged with traceback; only the exception type is stored and served |

The Data health page and `GET /api/health` show source state, recent runs and counts.

## API (read-only, `/api`)

`health`, `overview`, `releases` (filters: status, category, limit), `releases/{id}` (with analysis),
`calendar`, `series`, `series/{key}` (optional `vintage`), `series/{key}/csv`, `revisions/{key}`,
`migration/countries`. Unknown `/api/*` paths return JSON 404; other paths serve the SPA.

## Frontend

React Router pages (Overview, Migration, Release analysis, Calendar, Data health) over TanStack Query hooks.
`charts/options.ts` builds ECharts options as pure functions (unit-tested); `ChartCard` adds title, question,
unit, source, caveat, CSV, PNG and a data table. Dark mode follows `prefers-color-scheme`; print styles hide
navigation and append link URLs.

## Differences from the spec

- Release-page JSON and official CSVs are the data source; the ADE API is unused (needs a key, no vintages).
- Backfill window starts at 2024-06 because that is the oldest contiguous run of complete migration files.
- The Data Explorer, Revision Explorer, preferences and other categories are Phase 2 and 3.
