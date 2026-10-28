# Phase 4C implementation plan: GDP, labour market, OCR, Outlook integration

Spec: [2026-10-28-phase-4c-macro-data-design.md](../specs/2026-10-28-phase-4c-macro-data-design.md).
Rule for every task: write the test, watch it fail, implement, watch it pass, `ruff check` and `ruff format --check`.
Fixtures are real excerpts (GDP, HLFS, LCI) or files named `SYNTHETIC` (OCR only).

## PR 1: `feat/phase-4c-gdp`

1. **Capture script** `scripts/capture_macro_fixtures.py`: paced `Fetcher`, skips files already in `RAW_DIR`, writes the
   two GDP pages and CSV excerpts (all rows of the pinned series) to `backend/tests/fixtures/gdp_<YYYY-MM>_*`.
2. **Classifier**: tests that `gdp_csv` matches the main CSV and its `-corrected` form and rejects `-visualisation.csv`
   and the workbooks; `-revised` wins like `-corrected` in `pick_downloads`. Existing classifier tests unchanged.
3. **Catalogue** `adapters/gdp/series.py`: pinned reference → key, definition, expected `UNITS`, `MAGNITUDE`, `Group`
   tokens, `Series_title_1`. Test: every pinned series is found in both real fixtures with that metadata.
4. **Parse**: tests on both fixtures (series count, first and last periods, latest values from the spec table); failure
   tests: header change, missing required series, metadata change, malformed period, duplicate period, period after
   publication, reference period mismatch, title mismatch, oversized file.
5. **Reconciliation**: `stats/gdp.py` pure functions (q/q, y/y, annual average from levels; round half away from zero).
   Measure the max |computed − published| on both files, fix tolerances with the measured figure in a comment, test
   pass on real data and failure on a perturbed published value.
6. **Page cross-check**: parse both chart label formats; test that June and March charts equal the published series;
   test that swapping the annual-average and y/y series fails (the mislabelling guard).
7. **Validate**: reference period, previous-vintage revision warnings; tests with the March vintage as "previous" for
   June: revisions found (March 2026 q/q 0.8 → 0.9) and recorded as warnings, not errors.
8. **Pipeline**: register in `runtime.build_adapters`; an ingest test through the existing pipeline with a fake fetcher
   serving the fixture page and CSV: vintage committed, active, definitions snapshotted; a failing file leaves the
   previous vintage active (last-known-good).
9. **Insights and API**: `insights/gdp.py`, `GdpDashboardOut`; `/api/gdp` 404 before ingestion, 200 after; headline
   texts name the measure; revision table from two stored vintages; `npm run gen:api` and commit the schema.
10. Docs: `docs/data-sources/gdp.md` (source facts, reconciliation evidence), `docs/data-sources.md` row.

## PR 2: `feat/phase-4c-labour`

1. Capture: labour zip excerpts (HLFS and LCI members with every row of the pinned series and the full header) as
   `labour_<YYYY-MM>.zip`, plus pages.
2. Classifier `labour_zip` incl. `-revised`. Archive reader: caps (archive, member size, member count, rows), member
   selection by pattern, streaming; tests with crafted oversized and malformed zips (structure only, no invented values).
3. Catalogue and parse: HLFS eight series, LCI three; metadata pinned; tests on both fixtures.
4. Identities: measure and fix tolerances; tests pass on real data, fail on perturbation.
5. Validate: reference period; page headline rate equals stored latest; revision of the previous quarter's rate
   recorded (March 2026: 5.3 first published → 5.4).
6. Pipeline registration and ingest test; insights `insights/labour.py`, `/api/labour-market`, generated types.
7. Docs: `docs/data-sources/labour-market.md`.

## PR 3: `feat/phase-4c-ocr`

1. `ocr/model.py`: `OcrDecision`, `rate_on`, `change_bp`, `month_end_series`, `monthly_average_series`; tests on a
   `SYNTHETIC` fixture, including a decision effective the day after announcement and a month with two decisions.
2. `ocr/parse.py`: CSV contract, strict validation; failure tests for each rule.
3. A test that no production module imports the synthetic fixture and that `ocr` has no network code.
4. `docs/data-sources/ocr.md`: access assessment, blocker, what the owner must decide.

## PR 4: `feat/phase-4c-integration`

1. Outcomes: GDP and unemployment matchers with tests per basis (matched, not matched with reason); existing CPI tests
   unchanged and passing; OCR unavailable reason. Accuracy: indicators extended only through the matcher; existing
   ranking and minimum tests unchanged.
2. Frontend: `/gdp`, `/labour-market`, `/ocr` pages with unit tests; chart builders in `src/charts/gdp.ts` and
   `labour.ts`; dataviz validator run for new colours; Outlook links; navigation.
3. Snapshot: contract entries and exporter for `gdp.json` and `labour-market.json`; `dump_frontend_fixtures.py`; parity
   spec covers both pages.
4. Playwright: live and static specs for the new pages (mobile and dark mode included), screenshots in `docs/screenshots`.
5. Verification run (below) and `docs/progress.md` entry.

## Verification (each PR, local)

Backend `pytest`, `ruff check .`, `ruff format --check .`; frontend `npm test`, `npm run typecheck`, `npm run build`
(PR 4: also `npx playwright test`, `scripts/e2e_static.sh`). Hosted CI and Docker are reported separately: CI is blocked
by billing and there is no container runtime here.
