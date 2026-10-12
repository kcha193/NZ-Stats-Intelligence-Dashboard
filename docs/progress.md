# Progress and verification record

Last updated 2026-10-12. Branch `feat/phase-1`. Spec and plan: `docs/superpowers/`.

## Status

| Phase | State |
|---|---|
| Phase 1: core dashboard and International migration | **Built and verified except two items that need a Docker host and a date** (below). Not merged. |
| Phase 2: inflation, labour, GDP, housing, retail and trade, Data Explorer, Revision Explorer, comparisons | Not started |
| Phase 3: deeper release comparison, preferences, report export, optional grounded commentary, audit | Not started (the spec forbids starting before Phase 2 is verified) |

**Not done, so not claimed:**

1. **Docker image build and `docker compose up` have not been run.** The machine used has the Docker CLI and
   Compose 5.3.1 (`docker-compose config` validates the file) but no Docker daemon. The Dockerfile's key steps
   were simulated instead: a clean Python 3.12 venv, `pip install` from a copy containing only `backend/pyproject.toml`
   and `backend/src`, then `nzstats serve --no-scheduler` with the container's environment variables, serving
   `/api/health` (200), `/` (the built SPA) and `/migration` (SPA fallback). The CI `docker` job builds the image
   and checks `/api/health`; the first Docker host must also run the Compose quick start in the README.
2. **Live scheduler check is pending.** The International migration: August 2026 release is scheduled for
   14 Oct 2026 10:45 NZDT; today is 12 Oct. To close it: start `nzstats serve` against a data directory with
   history before 10:45 and confirm the release is ingested within the polling window (Data health page or
   `nzstats health`). The scheduler logic itself is unit-tested (offsets, window expiry, catch-up, blocked back-off).

## Verification evidence (2026-10-12, this machine)

| Check | Command | Result |
|---|---|---|
| Backend lint and format | `cd backend && ruff check . && ruff format --check .` | `All checks passed!`, 95 files formatted |
| Backend tests | `cd backend && pytest -o addopts=""` | **237 passed** |
| Frontend types | `cd frontend && npm run typecheck` | clean |
| Frontend tests | `cd frontend && npm test` | **12 files, 58 passed** |
| Frontend build | `cd frontend && npm run build` | built |
| Frontend lint | `npm run lint` (oxlint) | 3 warnings, all in generated `components/ui/*` (fast-refresh exports) |
| End to end | `cd frontend && npx playwright test` (Chromium, desktop 1440x900 and Pixel 7) | **16 passed**: overview, migration charts and CSV download, route reload and JSON 404, release analysis and print, no horizontal scroll on `/`, `/migration`, `/calendar`, `/health` |
| Compose file | `docker-compose config` | valid |
| Container-style install | clean venv, non-editable install, container env vars | health 200, SPA served |

## Real-site integration check (the only step that contacted stats.govt.nz)

Run 2026-10-12 against a scratch data directory, 10 s between requests, User-Agent
`NZStatsDashboard/0.1 (self-hosted)` (no contact address was sent; see rulings).

- `nzstats discover`: 222 releases seen, no errors.
- `nzstats backfill` (2024-06 onward): **first run ingested 17 of 26 releases; 9 failed with `layout_changed`.**
  Nothing was stored for the failures, the other 17 were intact, and Data health showed the errors.
- Root causes, from the stored real pages and files (not guessed):
  1. The adapter found the year-ended charts by title prefix, but editors retitle them from release to release: a
     leading space, "Est migration by citizenship, roll...", "years ended", and in two releases the footnote
     "Estimates from August 2024 onwards are provisional..." typed into the title field. The CSV header ("Year ended")
     plus the series row labels is stable and matched exactly one direction chart on all 26 pages.
  2. The September 2025 page has no year-ended citizenship chart at all.
  3. The June 2024 files repeat identical aggregate rows 2 or 3 times (Sep to Nov 2022). The repeated value equals the
     official chart value (Sep 2022 arrivals 12,561), so exact copies are collapsed; conflicting duplicates still fail.
- Fixes (each with tests that failed first): charts found by content; the citizenship chart is optional (warning, and the
  series gets no vintage from that release); exact duplicate rows collapsed.
- After the fix, the 9 releases were re-ingested from the real site: **all 26 releases from 2024-06 are ingested**;
  source health `ok`; `mig.ry.net` has 26 vintages and `mig.ry.net.nz` has 25 (September 2025 has none, by design).
- Real values were compared with the official July 2026 headline ("net gain of 20,300 (± 1,800) in the July 2026 year,
  compared with 9,600 (± 200)"): stored year-ended net 20,350 and 9,592; arrivals 134,434 minus departures 114,084 =
  20,350; monthly net 5,170 (± 545); provisional starts at 2025-04, 16 months, as Stats NZ labels them. Revisions between
  the June and July 2026 vintages are real (for example April 2026 net: -99 then 44).
- Every one of the 26 releases has an analysis page through the API.

## Chart and design review

- Palette validated with the `dataviz` validator (categorical chart-1 to chart-4): light on `#ffffff` `#2b66a8, #c75f0c,
  #2a8a6c, #7b52b5` and dark on `#1c1917` `#4a8ccb, #d47a36, #3a9c7e, #8e78cf`, all checks pass (worst adjacent
  colour-blind separation 10.2 light and 8.9 dark, which the direct labels and legends cover; normal-vision floor 22.3
  and 20.5). The plan's starting hexes failed and were adjusted within their hue families.
- Overview, Migration, Release analysis, Calendar (list, month, filtered) and Data health were screenshotted on real
  fixture data at 1440 px (light and dark) and 390 px, and print output was checked. Defects found and fixed: lowercase
  months in titles, an awkward revision title, an empty gap on the Overview, x-axis label overlap, mobile horizontal
  overflow (grid min-width and an unwrapped control row), a select showing a raw value, and upcoming releases listed last.
- Per-chart checklist (question, encoding, unit, zero baseline, provisional distinction, latest-point label, source and
  date, caveat, export) passed for all six migration charts; the country chart is entirely "provisional" shaded because
  every 12-month window includes provisional months, which its caveat states.

## Whole-branch review

A fresh Opus reviewer read the whole branch. It found two Critical and four Important issues (and 20-odd Minor ones).
All six were fixed, each with a test that failed first:

1. A release without the year-ended citizenship chart ingested but had no analysis, which would blank the Overview.
2. The crawl delay was per process, so the CLI run beside the server could send requests less than 10 s apart, and a lost
   ingest race could mark an unchanged release `corrected`. Now a `flock` file shared through `data/` paces all processes
   (checked with two real processes) and `corrected` is decided inside the write transaction.
3. Raw exception text reached stored and served error detail on the network and parse paths.
4. The country ranking's prior-period change used a partial window for periods over 12 months.
5. Releases were marked `unavailable` after blocks, network errors or parser failures, and polled again minutes after a block.
6. First `docker compose up` on plain Linux needs `./data` owned by UID 10001 (now in the quick start).

The Minor findings are not fixed; they are listed under remaining work. Two automated post-commit security reviews also
found CSV formula injection (twice) and unescaped tooltip HTML; both are fixed with tests.

## Remaining work

Before merging or calling Phase 1 shipped:

- Run `docker compose up -d --build` on a Docker host and follow the README quick start (including `chown` of `./data`).
- Run the live scheduler check on 14 Oct 2026 (above).
- Set `NZSTATS_CONTACT` in `.env` (Kevin's choice; not sent so far). Review Stats NZ's terms before any public hosting.
- Push and open a PR only with Kevin's approval; CI has never run (no remote).

Deferred Minor findings (small, none blocks use):

- Reprocessing: ingest hashes only the CSVs, so parser fixes and page-only corrections are not applied to stored releases
  (add `nzstats ingest --reparse`); nothing re-checks a release after it has data, so `corrected` only follows a manual re-ingest.
- A release marked `unavailable` ignores a later ICS reschedule; discovery aborts on non-`IngestError` failures.
- API: `/api/calendar?to=9999-12-31` returns 500; `/api/releases` loads all rows before paging; the series CSV does not
  neutralise formulas; the vintage kind is missing from `ReleaseAnalysis` and `CountriesOut`.
- Analysis: the driver-share wording can overstate arrivals when both arrivals and departures move the same way; the
  citizenship chart title omits its period.
- Frontend: revision and chart data tables need `overflow-x-auto`; `/releases/abc` renders blank; the calendar month grid has
  no grid keyboard behaviour, no explanation for months outside the fetch window, and incomplete status and importance filters;
  TanStack Table is installed but unused.
- Hygiene: untrack `backend/src/nzstats.egg-info/`; the `.env.example` contact is a placeholder address; the shadcn CLI is a
  runtime dependency; add a Python lock file for reproducible images; Fetcher has no host allow-list for redirects.
- CI does not run the Playwright suite or the frontend lint.

## Resume steps for Phase 2

1. Read `docs/superpowers/specs/2026-10-11-nz-stats-dashboard-design.md` §12 and `docs/data-sources.md` ("Adding a source").
2. Pick one category (Consumers price index is the natural first: `consumers-price-index` is already in `catalog.py`).
   Verify its official files and release page manually and record them in `docs/data-sources.md` with the date. Do not guess.
3. Capture real fixture excerpts (see `scripts/capture_fixtures.py`) and probe how far back vintages exist
   (`scripts/probe_vintages.py`); set the backfill window from evidence.
4. Write the adapter (`adapters/<category>/`) test-first with a layout-drift case; add validation rules grounded in the real
   files; register it in `runtime.py`; move the category out of `INACTIVE_CATEGORIES`.
5. Reuse `ChartCard` and the option builders; add the Data Explorer and Revision Explorer once two categories exist.
6. Run the real-site integration check again for the new category and expect surprises: the Phase 1 run found three.
