# Phase 2B: CPI and inflation dashboard: implementation record

Branch `feat/phase-2b-cpi`. Design: [spec](superpowers/specs/2026-10-19-phase-2b-cpi-design.md). Plan:
[plan](superpowers/plans/2026-10-19-phase-2b-cpi.md). Sources and measured tolerances: [data-sources/cpi.md](data-sources/cpi.md).
Operating notes: [cpi-release-runbook.md](cpi-release-runbook.md).

## What was built

- **Adapter** `backend/src/nzstats/adapters/cpi/` (`series.py` identities, `adapter.py` parse/validate/reconcile,
  `workbook.py` stdlib reader), registered as `consumers-price-index`. It reuses discovery, scheduler, fetcher pacing, the
  ingest transaction, vintage definitions and revision logic unchanged, apart from two small shared additions:
  `ParsedBundle.warnings` and optional downloads/`-corrected` preference in `pipeline/ingest.py`.
- **Statistics** `stats/cpi.py`: quarterly and annual change from published (rounded) index numbers, contiguous-run trimming.
- **Insights/API** `insights/cpi.py`, `GET /api/cpi`, CPI branches in release detail and Overview; models in `models.py`.
- **Frontend** `/inflation` (`pages/Inflation.tsx`, `pages/inflation/Explorer.tsx`, `charts/cpi.ts`), nav entry, rate-aware
  KpiCard/ReleaseAnalysis (`lib/metric.ts`), Overview tile and link, Freshness name.
- **Tests**: real captured fixtures (Dec 2025, Mar 2026, Jun 2026 pages and CSV excerpts, June workbook); unit, adapter,
  pipeline, insights, API, scheduler rehearsal, vitest and Playwright (desktop/tablet/mobile).

## Decisions worth knowing

1. Percent changes are derived on read from index levels; Stats NZ's own charts are used as a reconciliation check, matched by row
   label (chart titles changed between releases).
2. Contributions are stored as published (percentage points, latest quarter per release). They do not sum exactly to the headline
   (Stats NZ computes them from unrounded indexes); the gap is shown. A missing contribution chart is a warning; a present but wrong one fails.
3. Official trimmed means and weighted percentiles exist only in the workbook (tables 10 and 11). They are read from the optional
   workbook (quarterly blocks only: the annual blocks splice two weight bases) and shown as official Stats NZ measures. The dashboard never
   defines core inflation.
4. Strict for core series, lenient for optional ones. The optional workbook is validated as a whole inside its own boundary (expected
   series set, quarter-end periods, finite numeric values within a sanity bound, enough unbroken history, reconciliation with the index
   that rejects NaN); anything wrong drops the optional series with a warning and never blocks required CPI.
   Required and optional series are compared separately on re-ingestion (`pipeline/ingest.py::_optional_match`):
   - optional data missing or invalid while a stored bundle has the same required statistics: the stored bundle stands (`unchanged`);
   - optional data arriving later: its vintages are added under the stored bundle's identity, core series are not copied, and the
     release status is not changed (it is enrichment, not a publication);
   - changed required statistics, or changed values of already stored optional measures: a new full bundle and `corrected`, as for any
     official correction; a revert reactivates the earlier bundle.
   Only adapters declaring `optional_series_prefixes` (CPI) use this rule; migration and ECT are unchanged.
5. Rate changes are percentage points between published 1 d.p. rates, never a percent of a percent.

## Verification (run 19 October 2026, on this branch)

| Command | Outcome |
|---|---|
| `cd backend && pytest` | 894 passed |
| `cd backend && ruff check . && ruff format --check .` | passed |
| `cd frontend && npx vitest run` | 161 passed (19 files) |
| `cd frontend && npm run typecheck`, `npm run lint`, `npm run build` | passed (lint: three existing Fast Refresh warnings; bundle-size warning as before) |
| `cd frontend && npx playwright test` (venv on PATH) | 48 passed (42 existing + 6 CPI across desktop, tablet, mobile) |

June 2026 benchmarks reconcile from the stored indexes: all groups 1.5% / 4.1%, tradables 2.7% / 4.9%, non-tradables 0.6% / 3.4%. Published
chart percentages match the computed values for all 204 charted points (68 per release, three releases). Existing migration and ECT tests
all pass unchanged.

## Review

One whole-branch review (Opus) found no Critical issues and eight Important/Minor findings; all eight were fixed test-first in a single
pass (commit "fix(cpi): reviewer findings"). No second review was run on the fix pass.

Codex review of PR #5 at `bb213be` raised two P2 findings, both reproduced with failing tests first: a non-finite optional workbook value
passed the optional boundary and blocked required CPI (#4312128553), and a workbook arriving after the first ingestion created new
vintages for every series and a false `corrected` status (#4312128556). Fixes and tests are described in decision 4 above.

## Limitations

- The September 2026 quarter release has **not** been ingested (not yet published on 19 October 2026); only the offline rehearsal exists.
- Contribution history accrues one release at a time; only March and June 2026 (and December 2025 as a fixture) were exercised. Earlier
  vintages were not backfilled.
- Percentage contribution (share of the total movement) is published only in the workbook and is not shown.
- Visual checks used Playwright screenshots at 1440, 768 and 390 px; the `design-taste-frontend` skill named in CLAUDE.md is not installed
  in this environment, so the design followed the existing ECT/migration styling and the dataviz skill.
- Fixtures are 2.6 MB because the real rows are kept whole.

## Recommended independent review

A second reviewer on the fix pass, and a live check of the real 22 October release against the official page text.

## Deployment

No new dependencies, environment variables or config. The CPI adapter is picked up automatically at start-up; an existing database
migrates as before. Run `nzstats discover` once so the September release is stored as scheduled before 22 October.
