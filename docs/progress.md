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
| Backend tests | `cd backend && pytest -o addopts=""` | **280 passed** |
| Frontend types | `cd frontend && npm run typecheck` | clean |
| Frontend tests | `cd frontend && npm test` | **12 files, 67 passed** |
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

## Codex review round 1 (PR #1, commit 2c73d9b)

Four P2 findings, each validated against the code and fixed with a test that failed first:

1. Vintage digest ignored page-embedded charts (#4245952768). The digest now covers the downloaded files plus every
   chart's title and CSV body on the release page (never the surrounding HTML, so nonces and markup cannot cause false
   revisions). A corrected chart, or the optional citizenship chart appearing later, yields a new vintage.
   Upgrade note: the digest value changed, so a database ingested before this commit gets one extra vintage with
   identical values (marked `corrected`) on the first manual re-ingest of each release. No such database exists outside
   development; if one does, re-seed it.
2. An `unavailable` release ignored a calendar reschedule (#4245952774). A later scheduled time now returns it to
   `delayed` with the new time, which resets its polling attempts (see round 2 for the final rule).
3. `/api/calendar?to=9999-12-31` returned 500 (#4245952779). `date.max` is now an unbounded upper bound. `from=0001-01-01`
   had the same defect through the UTC conversion and is fixed alike.
4. Delayed releases sorted as past (#4245952785). The calendar's upcoming predicate is now `scheduled` or `delayed`,
   also applied to the Scheduled status filter.

## Codex review round 2 (PR #1, commit 261f80c)

Three further findings, each validated and fixed with a test that failed first:

1. Default revision base used insertion order (#4246141419, P1). `revision_view` required `vintage_id < compare.vintage_id`,
   so ingesting an older release after a newer one (backfill or retry) made `/api/revisions/{key}` return 404. The base is
   now the vintage immediately before `compare` in publication order.
2. A stale second feed could rewind a reschedule (#4246141425). `discover()` stores the ICS result and then the month
   result, and neither is reliably fresher (the ICS refreshes daily, the month endpoint is undocumented). The slot of an
   unpublished (`scheduled`, `delayed`, `unavailable`) release now only moves later, so it converges on the latest slot any
   feed reported in either read order. This replaces round 1's "earlier slot becomes scheduled" rule: a pull-forward is not
   applied until the calendar lists the release as published, which sets its actual time.
3. Migration script and version marker were not atomic (#4246141437). The script, the `schema_version` insert and `COMMIT`
   now run in one `BEGIN IMMEDIATE` script and roll back on any failure, so a failed migration leaves no partial schema.
   Not changed: two processes migrating a brand-new database at the same instant still race (the loser fails and retries on
   its next start); this predates the review.

## Codex review round 3 (PR #1, commit 9b82eb4)

Two findings, both on the deferred-minor list from the whole-branch review, validated and fixed with tests that failed first:

1. Driver-share wording ignored signs (#4246208518). Net is arrivals minus departures, so same-direction moves offset and a
   share of their "combined movement" credited the larger side for a net change that is only the difference. The
   statement is now made only when arrivals and departures do not move the same way (then |change in net| is exactly the
   sum of the two and the share is exact) and says so. The real July 2026 release (arrivals up, departures down) keeps its
   61%. Frontend fixture regenerated: one sentence changed.
2. The backend series CSV wrote upstream text unguarded (#4246208524). All text cells, including the upstream release title,
   now get the same leading-quote guard as the frontend export (`'` before a first significant `= + - @`, or a leading
   tab/CR/LF, after skipping whitespace and invisible characters). Numeric cells are untouched.

## Codex review round 4 (PR #1, commit 1b1e888)

Three findings, validated and fixed with tests that failed first:

1. Backfill dropped discovery failures (#4246272300). A month whose calendar request failed left no trace: the run printed
   its successes and exited 0. Each failed month is now returned as a `failed` outcome (`calendar_month:YYYY-MM`) and the
   CLI exits 1 and prints its detail. The month listing for months with no releases must answer 200 with empty lists;
   a 404 is a failure.
2. A later successful month cleared an earlier failure (#4246272308). The `calendar_month` health is now one verdict per
   discovery or backfill run: `ok` only if every requested month succeeded, otherwise `degraded` with every error joined.
3. Country ranking mixed vintages (#4246272317). Each place series was read from its own latest vintage, so a place the
   newest country file omits kept an older release's value (real fixtures: Togo, 2025-10 = 1 in June, absent in July).
   Every place is now read from the same ingested bundle as the latest arrivals total (release plus bundle digest, so a
   corrected bundle that drops a place is handled too); a place absent from that bundle counts as zero, as the ranking
   note already states. Stored data and vintages are untouched. Places absent from the latest bundle now appear as zero
   rows (visible in the regions list); only the top countries are shown.

## Codex review round 5 (PR #1, commit e9a777e)

Three findings, validated and fixed with tests that failed first:

1. The CLI exited 0 when a release was `not_available` (#4246379621). `ingest` and `backfill` now exit 1 for `failed` and
   for `not_available`, since a requested release that was not ingested is a gap.
2. The Published filter hid corrected releases (#4246379625). Published now includes `corrected`, as Scheduled includes `delayed`.
3. Month navigation showed blank months (#4246379631). The month view now requests the month it shows (`from`/`to` are the first
   and last day), defaults to the current Pacific/Auckland month, and keeps the navigation visible with an explanation when a
   month holds no matching releases. The list view still uses the API's default window.

## Codex review round 6 (PR #1, commit ec224f6)

Two findings, validated and fixed:

1. A corrected release's analysis mixed bundles (#4253628351). Each series was read from its newest vintage for the release,
   so after a page-only correction that removed the optional citizenship chart (detectable since round 1) the analysis kept
   the old bundle's citizenship series. The analysis now reads every series from the release's newest bundle, and an
   optional series that bundle lacks is unavailable. The previous-release comparison is unchanged: it only reads the required
   series, which every bundle contains. Test failed first.
2. README and troubleshooting still said a page-only chart correction is not detected and told operators to delete vintages
   (#4253628355). Both now state the digest covers the files and the embedded chart data; only the parser-fix limitation remains.

## Remaining work

Before merging or calling Phase 1 shipped:

- Run `docker compose up -d --build` on a Docker host and follow the README quick start (including `chown` of `./data`).
- Run the live scheduler check on 14 Oct 2026 (above).
- Set `NZSTATS_CONTACT` in `.env` (Kevin's choice; not sent so far). Review Stats NZ's terms before any public hosting.
- Push and open a PR only with Kevin's approval; CI has never run (no remote).

Deferred Minor findings (small, none blocks use):

- Reprocessing: parser fixes are not applied to stored releases whose files and charts are unchanged
  (add `nzstats ingest --reparse`); nothing re-checks a release after it has data, so `corrected` only follows a manual re-ingest.
- Discovery aborts on non-`IngestError` failures.
- API: `/api/releases` loads all rows before paging; the vintage kind is missing from `ReleaseAnalysis` and `CountriesOut`.
- Analysis: the citizenship chart title omits its period.
- Frontend: revision and chart data tables need `overflow-x-auto`; `/releases/abc` renders blank; the calendar month grid has
  no grid keyboard behaviour and the importance filter has no Low option; TanStack Table is installed but unused.
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
