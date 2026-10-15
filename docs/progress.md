# Progress and verification record

Last updated 2026-10-15. Branch `feat/phase-1`. Spec and plan: `docs/superpowers/`.

## Review completion cycle — 15 October 2026

Continued PR #1 from `3c2ed2b` (CI green, 59 of 61 threads resolved, Codex quota exhausted).

Earlier on 15 October (`2bcb809`..`3c2ed2b`, Codex rounds not recorded above): every derivable rolling
total and the required citizenship series are validated; country totals reconcile for every stored
month; country provisional flags come from the month; truncated calendar envelopes, non-finite standard
errors and a release-month response missing either group are rejected; and a release that reverts to an
earlier bundle (A -> B -> A) reactivates it. That last change adds schema migration
`002_vintage_activation.sql` (`vintage.activation`, backfilled from `id`). "Latest" now orders by
activation, and existing databases migrate on start.

This cycle, each fix has a test that failed first:

1. Concurrent artifact writes (#4280133530). Both writers used `<sha>.tmp`, so the slower `os.replace`
   raised `FileNotFoundError` and recorded a valid ingest as failed. Each writer now uses its own
   `mkstemp` file, and the files keep mode 0644 so host backups can read them.
2. Paired charts mixed bundles (#4280133522). Arrivals/departures and the monthly/year-ended net panels
   combined independently cached series. For example, `mig.ry.net` cached by the Overview before a new
   release could sit next to a fresh `mig.m.net`. All three paired charts now compare release and
   capture time. A mismatch reloads both series once; if it persists, the pair is not combined and the
   page says why.
3. Redirects skipped the crawl delay (independent review). httpx followed redirects inside one pacer
   turn, so the hops went out with no 10 s gap and could leave the host. The fetcher now follows up to
   five same-host hops, each paced, and records the final URL.
4. Blocks stopped only one release (independent review). After a 403 or a challenge page, batch loops
   kept requesting other URLs. The fetcher now refuses every request for 30 minutes. This is per
   process: a CLI run started during the cooldown still makes its first request.
5. The Overview trend title quoted a provisional value with no period or status. It now states both, as
   the Migration charts do.
6. Truncated history passed validation (#4280291084, #4280291091). A monthly file cut to its latest 12
   months, or a year-ended chart left with only its latest column, kept a correct latest value. It passed
   every check and replaced the full history as the live vintage. Real files start in 2001 (monthly
   2001-01, year-ended 2001-12, June and July 2026). A series whose coverage now starts later than its
   previous vintage is a `coverage` error, and the adapter loads the previous vintage of every required
   and optional series. An isolated blank interior cell is still accepted, as decided in rounds 8 and 12.
   Not verified: whether any 2024–2025 release started later than its predecessor; if one did, its
   backfill now fails visibly instead of passing.

Verification: **523 backend** (ruff lint/format clean, 99 files), **115 frontend** (typecheck, build;
lint has the 3 known shadcn warnings), **18 Playwright** (desktop and mobile). Playwright ran on port
8766 through a temporary config because an unrelated local process held 8765. Compose config validates.
There is no local Docker daemon; the GitHub Actions `docker` job builds the image and checks
`/api/health`.

**Live scheduler milestone not verified.** No `nzstats serve` was running on 14 October. Every local
database still shows *International migration: August 2026* as `scheduled`, with no ingest run after
11 October. Stats NZ was not contacted to compensate. As captured on 11 October, the next opportunity is
*September 2026*, scheduled for 12 Nov 2026 10:45 NZDT (confirm in the calendar first).

Known and not changed (independent review, Medium): `_bundle_digest` hashes every chart's title and CSV.
An editorial retitle, or an edit to a chart the adapter does not read, therefore creates a new vintage
with identical values and marks the release `corrected` on the next re-ingest. Values stay correct. The
fix (hashing only the charts the adapter reads) changes every stored digest, which gives each release
one extra vintage once. It needs a decision rather than a quick patch. Also known: 429 `Retry-After` is
ignored (paced retries); explicit `?base=` newer than `compare` returns inverted revisions (the UI never
sends it); no `fsync` before the artifact rename.

## Focused retry, backfill and provenance cycle — 14 October 2026

Continued PR #1 from `93211ff`, preserving the uncommitted fixes already in its
worktree. This is one implementation and review cycle for comments #4255168462,
#4255168469 and #4255168477. The ingestion-health model is unchanged.

- Unresolved `unavailable` releases remain eligible at any age, with at most one
  ingestion attempt per Auckland calendar day. Eligibility uses the job's explicit
  clock and persisted attempts. The minute watcher excludes these releases;
  recovery and rescheduling restore the existing lifecycle behaviour. The blocked
  cooldown, HTTP pacing and network retry handling remain intact.
- Backfill validates inclusive `YYYY-MM` reference-period bounds before any
  request/write; invalid or reversed bounds raise `ValueError`, and missing
  reference periods are excluded. Publication-month discovery scans through the
  current Auckland month (or `until`, if later) to find delayed publications,
  filtering references to the same interval used by ingestion. For example, a
  June-only request discovers June's August publication without fetching July's
  release files. Calendar request failures still appear in the outcome list.
- Country totals, rankings and nullable provenance come from the same selected
  release bundle, including corrections. The API, generated frontend types and
  fixtures agree. Captions show the actual release URL, publication date and
  capture time; CSV adds the period bounds, denominator, series key, release key,
  timestamps, bundle digest and derivation note, retaining formula protection.
- Shared `ChartCard` PNG export composes the chart bitmap with wrapped plain-text
  title, question, source URL, publication date, capture time and caveat. Export
  status is announced accessibly. Wide provenance tables scroll within a named,
  keyboard-accessible region. No upstream HTML is interpreted.
- Baseline reproduction in an isolated archive of `93211ff`: **25 backend and
  4 frontend failures**. Additional failing regressions exposed cold discovery
  of a later publication and table overflow on desktop/mobile; both pass after
  their focused fixes. Added **33 backend cases**, **3 frontend tests** and one
  Playwright scenario running on both viewports.
- Full local verification: **437 backend**, **101 frontend**, **18 Playwright**
  pass. Ruff lint/format (97 files), TypeScript, frontend lint, production build,
  API generation and fixture regeneration pass. Exported mobile PNG visually
  inspected; browser assertions check caption text, bitmap pixels and bounds,
  and downloaded CSV provenance. Existing warnings: Starlette/httpx deprecation,
  three UI Fast Refresh exports, large chart bundle.
- Independent read-only review found no actionable issues across retry frequency,
  boundaries, same-bundle consistency, corrected/withdrawn data, API types and
  PNG/CSV provenance. Publication-month scanning, sparse-file zero rows and the
  nullable contract were checked and retained for the reasons above.
- Local Docker image/startup checks remain unavailable: no daemon. Final-head
  backend/frontend/Docker CI is required before resolving review threads. Remote
  CI and the single final Codex review are recorded on PR #1; this record does
  not claim remote results in advance.

## Focused ingestion-health cycle — 13 October 2026

Continued PR #1 from `e087c40`, with one implementation/verification cycle and no
merge. The [behavioural specification](superpowers/specs/2026-10-13-ingestion-health.md)
was written before the regression tests and implementation.

- `failing_releases()` now ranks meaningful outcomes by run ID after excluding
  neutral observations. Current release status determines whether a 404 is a gap.
- Repository outcome/status writes refresh health, covering discovery publication,
  valid rescheduling and scheduler exhaustion without pipeline imports. Neutral
  observations and status-only recalculation preserve both source timestamps.
- No schema, polling schedule, observations or vintage changes. A successful
  release cannot mask another release's unresolved failure.
- New database/lifecycle suite: **47 failed / 41 passed before**, **88 passed after**.
  Existing published-404 coverage already passed at the starting commit; extended
  coverage confirms published/corrected/unavailable gaps and recovery.
- Full backend: **404 passed**. Ruff lint and format pass (96 files). Frontend:
  **98 passed**, lint/typecheck/build pass; generated API types unchanged.
  Playwright: **16 passed** on desktop/mobile. Compose configuration validates.
- Local Docker build/start unavailable: no daemon. Final-head GitHub Actions must
  supply the container build/start check. Existing non-blocking warnings remain:
  Starlette/httpx deprecation, three UI Fast Refresh exports, large chart bundle.
- Focused independent review found no actionable defects. Final-head CI and the
  single final GitHub Codex review are recorded on PR #1 after push; this local
  verification record does not claim their result in advance.

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
2. **Live scheduler check is pending.** The August 2026 release (14 Oct 2026) was missed: no scheduler was
   running (see the 15 October cycle). Next: September 2026, scheduled 12 Nov 2026 10:45 NZDT. To close it: start `nzstats serve` against a data directory with
   history before 10:45 and confirm the release is ingested within the polling window (Data health page or
   `nzstats health`). The scheduler logic itself is unit-tested (offsets, window expiry, catch-up, blocked back-off).

## Verification evidence (2026-10-12, this machine)

| Check | Command | Result |
|---|---|---|
| Backend lint and format | `cd backend && ruff check . && ruff format --check .` | `All checks passed!`, 95 files formatted |
| Backend tests | `cd backend && pytest -o addopts=""` | **313 passed** |
| Frontend types | `cd frontend && npm run typecheck` | clean |
| Frontend tests | `cd frontend && npm test` | **13 files, 98 passed** |
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

## Codex review round 7 (PR #1, commit c6bdfda)

Two findings, validated and fixed with tests that failed first:

1. A later success cleared another release's failure (#4253658288). `release:<slug>` health was last-write-wins, so a failed
   June followed by an unchanged July left the source `ok` over a data gap. Health is now derived from the releases whose
   most recent ingest run failed: `degraded` with each such release named (first three, then a count) until that release
   itself succeeds. A release that failed and is never retried keeps the source degraded, which is deliberate.
2. An all-blank optional citizenship series caused a 500 (#4253658294). The parser kept a series whose cells were all blank
   or `..` as a vintage with no observations, and the analysis took `max` of an empty mapping. The adapter now omits an empty
   optional series (validation warns it was not published) and the analysis loader treats an empty optional series as
   unavailable, which also covers vintages stored before this fix. Required series must still hold data.

## Codex review round 8 (PR #1, commit 07a126d)

Three findings, all from partially blank year-ended chart cells, validated and fixed with tests that failed first:

1. The citizenship insight could pair figures from different periods (#4253711085). It is now emitted only when the NZ and
   non-NZ series end in the same period.
2. The citizenship chart could combine different vintages or periods (#4253711087). It now declines to combine the two series
   unless both come from the same release and ingest, and quotes both values for the latest period they share, naming it.
3. A streak could bridge a missing month (#4253711094). `_streak` now ends at the first non-adjacent pair of periods.

Not changed: validation still accepts a required year-ended series with an isolated blank cell inside the chart. The two
consumers that assume adjacent months (the streak and the citizenship pair) now cope; a continuity rule for the rolling
series is not added without evidence of such a gap in a real file.

## Review round 9 and provisional-status audit (PR #1, commit f925eb6)

Two Codex findings, then a cross-layer audit of how provisional status travels from the Stats NZ file to the screen.

Findings, each fixed with tests that failed first:

1. The combined monthly/year-ended chart dropped year-ended statuses (#4253748549). The API already carries them
   (derived: provisional while any of the twelve months is; 16 points from 2025-04 in the real July file). The chart now keeps
   the full year-ended points, flags them in its tooltip, shades a labelled "Provisional" band on that panel, and exports
   separate `monthly_status` and `year_ended_status` columns.
2. The provisional sentence treated first-to-last as a range (#4253748554). It now names exactly the provisional months:
   a range only for consecutive months, otherwise each run is listed, with evidence for every run boundary. The
   `provisional_window` validation warning is unchanged.

Audit method: traced status through the parser (`with_rolling_status`), validation, storage, API, insights, charts, tooltips, titles,
captions and CSV exports, and checked the real June and July files. Facts established: arrivals, departures and net carry
identical monthly statuses in both files; the real data holds no `unknown` statuses; required series always share one bundle.

Additional defects found and fixed, each with a regression test:

- Chart titles quoted a provisional latest value with no status (trend, arrivals/departures, citizenship). They now add
  ", provisional" (or ", status unknown").
- Arrivals/departures and citizenship CSVs had one `status` column for two series and dropped periods present in only
  one. Each series now has its own status column and no period is dropped.
- The country ranking's prior window could be built from provisional months with no flag, in the API, the CSV and the change
  figures. `CountryRank.prior_provisional` (null when the prior window is withheld) and a CSV column now say so.
- The year-ended series caveat and `docs/data-dictionary.md` did not state that the year-ended status is derived. Both do.
- The release summary's provisional insight covered monthly estimates only, so year-ended figures quoted elsewhere in the
  narrative were unflagged. It now says year-ended totals that include a provisional month are provisional too.

Examined, no defect demonstrated, not changed: tooltips and bar opacity on the single-series charts; the revisions chart
and table (statuses are exported and tabulated); vintage pairing of required series (one bundle by construction, and
validation rejects a bundle without them); a validation rule for monthly statuses disagreeing across arrivals, departures
and net (they never do in real files, but year-ended statuses are derived from net, so such a rule is a candidate if
Stats NZ changes the files).

## Review round 10 (PR #1, commit 03d70a6)

Three findings, validated and fixed with tests that failed first:

1. The provisional band covered final months between provisional ones (#4254034473). This was the same root cause as the
   wording finding of round 9 (a first-to-last span treated as contiguous), and the stacked panel added in round 9 had it
   too. A shared `provisionalRuns` now builds one band per run of consecutive provisional periods for both charts; a
   `grep` for first/last provisional spans found no other consumer. The `provisional_window` validation warning now says the
   months are "spanning" a range rather than implying the range is provisional.
2. The Overview requested a series that does not exist on a first run (#4254034477). After `discover` and before the first
   backfill the trend got a 404 and showed an error panel. A 404 now shows a note that the trend appears once the first release
   is ingested; other failures still show the error panel.
3. Unexpected discovery failures aborted without recording health (#4254034483). `attempt` caught only `IngestError`, so e.g.
   an undecodable calendar body raised past the health update. Other exceptions are now logged in full, recorded as an
   `unexpected` degraded error naming only the exception type, and the run continues (also for backfill months).

## Review round 11 (PR #1, commit 4c43b00)

One finding, validated and fixed with a test that failed first:

- The calendar's "last successful check" took the newest success of either feed (#4254067563). With the ICS refreshed and the
  month feed failing, it reported the current run as a success and, because the attempt time equalled it, hid the last-attempt
  warning. The calendar is complete only with both feeds, so its last success is now the oldest of the feeds' last successes
  (empty while a feed that has been tried has never succeeded); the last attempt stays the newest. An ICS-only installation
  reports the ICS time. This was the only place that aggregated freshness across feeds; the Overview lists each source
  separately.

## Review round 12 (PR #1, commit d048bb2)

Two findings, validated and fixed with tests that failed first:

1. The citizenship chart's same-vintage check passed on stale data (#4254096575). When a corrected release dropped both
   optional series, each series' latest vintage was still the superseded one, so the two matched each other. This is the same
   "latest vintage per series" root cause as the country ranking and the release analysis, which already read one bundle.
   The series API now marks a vintage `superseded` when its release was re-ingested into a newer bundle without that series,
   and the chart declines to show superseded series. Data from an older release that a newer release simply lacks is not
   superseded and keeps its own release label. Audit of every consumer of per-series latest or previous vintages: the
   analysis, ranking and revisions are bundle-based or single-series; the only client-side pairings are of required series
   (always one bundle) and this guarded optional pair.
2. A blank interior chart cell closed the gap on the category axis (#4254096579). The line, bar and stacked charts now use a
   continuous month axis, so a month without an observation keeps its place and the line breaks there. Ingestion is not
   changed to reject such gaps: no real file has one, and rejecting would block a release rather than show it honestly.

## Review round 13 (PR #1, commit 74294a6)

Two findings, validated and fixed with tests that failed first:

1. Calendar freshness was still derived from per-feed timestamps (#4254126251). Round 11 changed the aggregation (oldest
   success, newest attempt), but timestamps recorded per feed cannot describe one refresh: a normal successful run showed a
   later "last attempt" than its "last success", and alternating single-feed successes produced a success time although no
   refresh completed. Discovery now records one `calendar_refresh` health row per run, healthy only if every feed in that run
   succeeded, and the calendar API reports that row. Backfill does not update it (it never reads the ICS feed).
2. Revision responses reported `superseded=false` regardless (#4254126260). `VintageOut.superseded` no longer has a default and
   `vintage_out(conn, v)` always computes it, so no construction site can omit it. Its meaning is now exact and tested: a
   vintage is superseded when a newer bundle of its release does not include the series (withdrawn). A series the newer bundle
   revised is not superseded: its older vintage is the original of a revision. The revisions chart notes a superseded comparison.

## Review round 14 (PR #1, commit 260ea47)

Two findings, validated and fixed with tests that failed first:

1. `nzstats ingest --release-key` exited 0 for a release with no adapter (#4254166732): it was neither ingested nor recorded.
   `skipped_no_adapter` now counts as a gap in the exit code. Catch-up and backfill only select releases that have an
   adapter, so the outcome can only come from an explicit key.
2. A 404 on a release already `published` or `corrected` left `release:<slug>` health untouched (#4254166737). Missing files
   are expected only before publication, so for a published or corrected release `not_available` now refreshes health and
   `failing_releases` counts the latest `not_available` run as failing; it recovers when the release ingests again.

## Remaining work

Before merging or calling Phase 1 shipped:

- Run `docker compose up -d --build` on a Docker host and follow the README quick start (including `chown` of `./data`).
- Run the live scheduler check at the next migration release (12 Nov 2026 10:45 NZDT as captured).
- Set `NZSTATS_CONTACT` in `.env` (Kevin's choice; not sent so far). Review Stats NZ's terms before any public hosting.
- Decide the bundle-digest scope (15 October cycle) before merge or as the first follow-up.

Deferred Minor findings (small, none blocks use):

- Reprocessing: parser fixes are not applied to stored releases whose files and charts are unchanged
  (add `nzstats ingest --reparse`); nothing re-checks a release after it has data, so `corrected` only follows a manual re-ingest.
- Discovery aborts on non-`IngestError` failures.
- API: `/api/releases` loads all rows before paging; the vintage kind is missing from `ReleaseAnalysis` and `CountriesOut`.
- Analysis: the citizenship chart title omits its period.
- Frontend: revision and chart data tables need `overflow-x-auto`; `/releases/abc` renders blank; the calendar month grid has
  no grid keyboard behaviour and the importance filter has no Low option; TanStack Table is installed but unused.
- Hygiene: the `.env.example` contact is a placeholder address; the shadcn CLI is a
  runtime dependency; add a Python lock file for reproducible images.
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
