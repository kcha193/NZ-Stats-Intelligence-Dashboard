# NZ Stats Intelligence Dashboard — Design Spec

Date: 2026-10-11. Status: approved in conversation; pending written-spec review.
Scope: whole-system architecture. Phase 1 is specified in full; Phases 2–3 are
outlined and each gets its own plan.

## 1. Intent

A self-hosted, automatically updated dashboard that turns Stats NZ releases into
explained intelligence: what changed, how the result compares historically, and
whether earlier estimates were revised. Audience: executive / analyst users.
Runs on a small Linux server or Synology NAS. No paid AI, no notifications.
International migration is the first fully working category.

Success criteria for Phase 1: the app builds and starts via Docker Compose; the
migration pipeline ingests real Stats NZ releases end to end (including the
14 Oct 2026 International migration: August 2026 release); revision history
reflects real vintages; tests pass; charts have been visually inspected.

## 2. Verified source facts (probed 2026-10-11)

| Need | Mechanism | Notes |
|---|---|---|
| Upcoming releases | `GET /release-calendar/calendar-export` (ICS) | Official. ~146 events, `TZID=Pacific/Auckland`, stable UIDs (`<id>@https://www.stats.govt.nz/`). No URL or category; category derived from title (`<Series>: <Month Year>`). |
| Published/upcoming by month | `GET /api/v1/releaseCalendarMonth/YYYY-MM` (JSON) | **Undocumented**, used by the site's own front end. Range 2012-07 onward. Gives `PublicationDate`, `PageLink`, `Title`, `MetaDescription` (headline sentence). May change without notice. |
| Release content | Release page `/information-releases/<slug>/` embeds JSON in a `data-value` attribute | Contains headline text, `GraphTableBlock.SeriesData[].GraphCsvData` (chart series as CSV) and `DocumentBlock` links to official downloads. |
| Official data files | `/assets/Uploads/<Series>/<Release>/Download-data/*.csv|xlsx` | Migration: one xlsx plus CSVs by citizenship/visa/country and by age/sex. Past releases keep their files (July 2024 confirmed). Each release's files are a **vintage**. |
| ADE / API portal | `portal.apis.stats.govt.nz`, registration + subscription key | Endpoints not verified without a key; no vintage history. Optional connector in Phase 2+, disabled unless `STATSNZ_API_KEY` is set. |
| Access rules | `robots.txt`: crawl-delay 10s, disallows `/admin`, `/Security` | Content CC BY 4.0. Site is behind Incapsula bot protection; a descriptive User-Agent worked. Terms-and-conditions page is JS-rendered and was not machine-read; Kevin to review manually. |

Rules that follow: identify with a descriptive User-Agent; enforce ≥10 s between
requests to stats.govt.nz; cache aggressively; attribute Stats NZ (CC BY 4.0) in
the UI; never invent endpoints.

## 3. Approach: release-bundle ingestion

The calendar sources discover releases. Each release's official downloads are the
data. One indicator adapter per category parses those files. Every release is a
vintage, so revisions come from real history, and one pipeline serves all
categories. Rejected: ADE-first (key required, no vintages, unverifiable) and
HTML scraping (structured files exist).

## 4. Architecture

Monorepo, one container.

```
backend/src/nzstats/
  sources/     calendar_ics, calendar_month, release_page, downloader (throttle, cache, retry)
  adapters/    base protocol + migration/ (versioned per file layout)
  validate/    structural + sanity checks
  stats/       pure functions: changes, rolling, percentile, revision, compatibility
  insights/    deterministic templated findings with evidence ids
  store/       SQLite (WAL), SQL migrations, repositories
  pipeline/    discover -> fetch -> validate -> normalise -> calculate -> persist
  api/         read-only FastAPI + Pydantic response models
  scheduler/   APScheduler (in-process), Pacific/Auckland
  cli.py       ingest, backfill, health
frontend/      React + TS + Vite + Tailwind + shadcn/ui + ECharts
data/          gitignored: nzstats.db, raw artifacts
```

Boundaries: adapters know file layouts; `stats/` knows only numbers; `api/`
only reads the store; frontend only calls the API. FastAPI serves the built SPA
in production. Python 3.12 in Docker; ruff line-length 100; pytest.

## 5. Data model (SQLite)

All timestamps are stored as UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`) so text ordering is correct
across NZST/NZDT; they are converted to Pacific/Auckland at the API boundary.

- `raw_artifact(id, url, sha256, fetched_at, http_status, content_type, size_bytes, path)` —
  raw bytes kept on disk; same sha256 is never re-processed.
- `release(id, release_key, series_slug, title, period_label, reference_period, published_at,
  status, page_url, headline, statsnz_id, ...)` — `release_key` (normalised title) is the
  natural key shared by the ICS and month endpoints; status: scheduled | published | delayed |
  corrected | unavailable (only set when evidence supports it).
- `series(id, key, name, unit, frequency, seasonal_adjustment, definition, definition_id,
  category, source_url)` — series sharing a `definition_id` measure the same concept; this
  drives comparison compatibility.
- `vintage(id, release_id, series_id, captured_at, source_kind, layout_version, bundle_sha256)`
  — `source_kind`: `release_files` (true vintage) or `snapshot` (captured by the monitor); the
  UI states which applies. Unique on `(release_id, series_id, bundle_sha256)`.
- `observation(vintage_id, period, value, status, std_error, released_in)` — status:
  provisional | final | unknown; `std_error` as published (zero on final estimates);
  `released_in` is the 'YYYY-MM' release that last published the value (the source's
  `month_of_release`). Primary key `(vintage_id, period)`.
- `ingest_run(id, release_key, started_at, finished_at, outcome, error_class, detail)` and
  `source_health(source, state, last_checked_at, last_success_at, detail)`.

Revision = difference in value for the same `(series, period)` between vintages;
computed in `stats/`, never stored as an observation. Frequency, unit,
seasonal-adjustment and definition live on `series`; comparison functions refuse
incompatible pairs.

## 6. Ingestion and reliability

- **Discovery**: ICS refreshed daily; month endpoint for published history and
  backfill. If the month endpoint breaks, fall back to ICS + information-release
  pages; health page shows degraded discovery.
- **Release-aware polling**: from each scheduled publication time, poll for the
  release page/files at short intervals with backoff for a bounded window, then
  stop. No continuous scraping.
- **Success definition**: downloaded + parsed + validated + committed in one
  transaction. Validation: expected series present; period continuity; latest
  period equals the release title's period; magnitude sanity vs previous vintage;
  non-null headline values. Failure leaves last-known-good data live, records an
  `ingest_run` with an error class (network, blocked, layout_changed,
  validation_failed, unexpected), and surfaces on the health page.
- **Errors**: retries with exponential backoff for network/5xx; a block page
  (Incapsula challenge, non-expected content type) is classified `blocked`, not
  retried hot.
- **Backfill**: walks the month endpoint backward; depth is limited by
  availability and layout support of old files, reported honestly (Plan task 0
  is a spike measuring real depth).
- **No synthetic values** in production; fixtures are real excerpts from
  official files.

## 7. Statistics and insights

`stats/` provides: absolute and percentage change (undefined for zero
denominator; percentages flagged non-meaningful for sign changes), percentage-point
differences, MoM/QoQ/YoY, rolling sums/means, percentile rank with sample size,
and revision calculations (absolute; percent only when meaningful). Monthly and
rolling-annual series are distinct `series` and never mixed on one axis without
labelling.

Insights are templated, deterministic, and each carries evidence ids (observation
or calculation references). "Rare" is reported as rarity only, never as economic
significance. Interpretation text separates observation from inference and avoids
causal claims. Optional LLM commentary is deferred to Phase 3 and must be grounded
in these evidence ids.

## 8. API (read-only)

`/api/overview`, `/api/releases`, `/api/releases/{id}` (analysis payload),
`/api/calendar`, `/api/migration/*`, `/api/series/{key}` (+ `.csv`),
`/api/revisions/{series}`, `/api/health`. Every payload carries source URL,
publication date, vintage kind and provisional/final flags.

## 9. Frontend

Phase 1 pages: Overview, Release Analysis (per release), International Migration,
Release Calendar, Data Health. Inactive categories are shown as inactive, not
faked. Charts follow the brief's visualisation standards (informative titles,
units, honest axes, latest-observation highlight, provisional styling, source and
date, caveats). Design params: DESIGN_VARIANCE 5, MOTION_INTENSITY 2,
VISUAL_DENSITY 7.

Taste skill: Kevin's installed `design-taste-frontend`
(github.com/leonxlnx/taste-skill), at
`~/.agents/skills/design-taste-frontend/SKILL.md`. It is not exposed through the
Skill tool, so it is read directly in targeted sections (it is ~87 KB; never load
it whole). Its §13 lists dashboards, data tables and dense product UI as out of
scope, so it is applied as follows:

- Used: §0 brief inference ("Design Read" stated before frontend work), §1/§7
  dials at the values above, §6 performance/accessibility, §8 dark mode, §9 AI
  tells (forbidden patterns), §14 pre-flight check at each frontend review.
- Not used: landing-page/hero/portfolio guidance (§4 hero rules, §5 motion and
  glass effects, §10-§12).
- Where it defers to other tools: components stay shadcn/ui (per the brief; a
  dense, neutral system suits §2's enterprise/dashboard row); charts follow the
  `dataviz` skill plus the visualisation standards above; data tables use
  TanStack Table.

Accessibility, loading, empty and error states on every page; print stylesheet
for Release Analysis.

## 10. Operations

Docker Compose: one service, one volume (`data/`), env via `.env`
(`.env.example` committed, no secrets). Healthcheck on `/api/health`. Backup =
copy `data/` (SQLite online backup command documented). CI on GitHub Actions:
ruff, pytest, frontend typecheck/build/tests. Docs: README, CLAUDE.md,
architecture, data-source registry, data dictionary, troubleshooting.

## 11. Testing

TDD for `stats/`, adapters, validation, store, pipeline. Parser tests use real
excerpts from official files, including a layout-drift case. Pipeline tests cover
idempotency, duplicate prevention, revision capture, blocked/failed fetches and
last-known-good preservation. Frontend: component and navigation tests,
Playwright smoke at desktop and mobile widths. Real integration check against
stats.govt.nz at the end of Phase 1, throttled.

## 12. Phases

1. **Phase 1**: scaffolding, store, calendar sources, migration adapter,
   pipeline + scheduler, API, shell + Overview/Release Analysis/Migration/
   Calendar/Health, Docker, CI, docs.
2. **Phase 2**: Inflation, Labour, GDP, Housing, trade/retail indicators where a
   verified source exists; Data Explorer; Revision Explorer; optional ADE
   connector (only with a key).
3. **Phase 3**: deeper release comparison, preferences, report export,
   optional grounded commentary, performance/a11y, production audit. Not started
   before Phases 1–2 are verified.

## 13. Risks and open items

- Month endpoint is undocumented and may change (fallback in §6).
- Older release files may have different layouts; adapters are versioned.
- Incapsula may block rapid or datacentre traffic; throttle and cache.
- Vintage depth unknown until the Plan task 0 spike.
- Provisional/final labelling must be derived from each release's own wording;
  confirmed in the migration parser spike, otherwise `unknown`.
- Stats NZ terms page not machine-read; Kevin to review before public hosting.
