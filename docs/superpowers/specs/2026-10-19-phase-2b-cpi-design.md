# Phase 2B: CPI and inflation dashboard: design

Date: 2026-10-19. Branch: `feat/phase-2b-cpi`. Extends the verified Phase 1/2A architecture; nothing is rebuilt.
Requirements are the Phase 2B brief (already established). This records what recon found and the calls made.

## Intent

A release-ready CPI module. The "Consumers price index: September 2026 quarter" release (22 Oct 2026, 10:45
Auckland) must flow through discovery, polling, ingestion, validation, persistence, API and UI with no code
change. Priority is a correct, fail-closed pipeline; the dashboard follows it.

Non-goals: labour/GDP, notifications, monthly Selected Price Indexes, anything not in an official file,
an invented "core" inflation measure, an LLM. Anti-goals: a single wrong number on release day; old figures
shown as new; mixing monthly/annual or incompatible bases on one axis; a rounded contribution presented as official.

## Verified source facts (June 2026 release, fetched 19 Oct 2026 through the paced fetcher)

Release page `/information-releases/consumers-price-index-june-2026-quarter/`, published 2026-07-21 10:45 NZST.
Downloads (names in the page JSON, `Download-data/`):

| File | Rows | Use |
|---|---|---|
| `…-index-numbers.csv` | 22,701 | **Required.** All groups + 11 Level-1 groups + Level-2/3, unadjusted index. Cols `Series_reference, Period, Data_value, STATUS, UNITS, Subject, Group, Series_title_1, Series_title_2` |
| `…-tradeables-and-non-tradeables.csv` | 16,783 | **Required.** All groups (`CPIQ.SE9A`), `CPIQ.SE9NS6000` Tradable, `CPIQ.SE9NS6500` Non-tradable (1999.06 to date, 109 quarters), plus a tradable/non-tradable × group matrix (not used) |
| `…-seasonally-adjusted.csv` | 11,929 | **Required.** `CPIQ.SE9SA` all groups, SA tradable/non-tradable, Level-1/2/3 SA. Status `REVISED`/`FINAL`. Many Level-2/3 SA series end 2023.03 (discontinued) |
| `…-infoshare-data.csv` | 1,759 | Not used: weighted average prices of items (a different measure) |
| `.xlsx` ×2 | n/a | Not parsed at runtime. Workbook inspected once for base period and notes (Batch 1) |

Embedded chart CSVs on the page (already parsed by `parse_release_page`): quarterly % (17 quarters), annual %
for all groups, tradeables, non-tradeables (17 quarters), **quarterly and annual percentage-point contributions
by Level-1 group (latest quarter only)**, price-change distribution.

Reconciliation by hand from the index files: all groups 1359 / 1339 / 1306 gives 1.49% q, 4.06% a (published 1.5, 4.1);
tradables 1257/1224/1198 gives 2.70, 4.92 (2.7, 4.9); non-tradables 1438/1430/1391 gives 0.56, 3.38 (0.6, 3.4). All reconcile.

Findings that shape the design:

1. Missing values are encoded as `0` (pre-1999 Food/Alcohol) and `NA` (tradables file). Both mean missing, never zero.
2. Headline levels are published as integers, so computed changes carry rounding error (about +/-0.07 pp on a quarter).
   Stats NZ's own charts give the published percentages to cross-check, so tolerance is measured, not guessed.
3. Published contributions sum to 1.400 (quarterly) and 4.000 (annual) against 1.49/4.06 headline: they do not
   reconcile exactly. They are stored and shown as published, and the gap is disclosed, never absorbed.
4. Contributions exist only for the latest quarter of each release. Contribution history therefore accrues per vintage.
5. File names say "tradeables"; page text says "tradables". The classifier must accept both.
6. The base period is not in the CSVs. Recorded from the workbook notes; guarded at runtime by "index at the base quarter == 1000 for all groups and the 11 groups".
   A rebase makes that fail closed instead of silently mixing bases.
7. No official underlying/core inflation series exists in these files, so none is shown.

## Design

**Adapter** `adapters/cpi/` (`adapter.py`, `series.py`), `CpiAdapter`, slug `consumers-price-index`, registered in `runtime.py`.
`classify_download` gains `cpi_index_numbers`, `cpi_seasonally_adjusted`, `cpi_tradables` (regex tolerant of tradeables/tradables).
`required_downloads` = those three; `workbook`/infoshare are not fetched.

**Stored series** (quarterly, period = quarter-end month `YYYY-MM`): index level for all groups, tradables, non-tradables, 11 Level-1 groups
(unadjusted), SA all groups, SA tradables/non-tradables, SA Level-1 groups, and an allow-list of Level-2/3 series for housing, energy and food
(household energy, electricity, gas, petrol, actual rentals, purchase of housing, fruit and vegetables, meat/poultry/fish, grocery food, restaurant
meals; exact IDs fixed in the plan from the file). Published contributions are stored as `pp` series (quarterly and annual, per group) for the
reference quarter. Percent changes are **derived on read** in a pure `stats/cpi.py` from index levels
(`(I_t/I_{t-1}-1)*100`, `(I_t/I_{t-4}-1)*100`, only for consecutive quarters of one definition), not stored as separate series.
Stored history starts at the first quarter of the contiguous quarterly run per series. Early annual-only history (all groups pre-1925) is dropped and documented.

**Series identity.** `definition_id` includes measure, classification level and adjustment; units are `index`, `pp`.
Base period is part of the definition text; the base-quarter == 1000 check is the runtime rebasing guard. Vintage definition snapshots (migration 003) are reused unchanged.

**Validation** (errors reject the whole bundle atomically; last-known-good survives):
schema/header and title match; reference quarter is a quarter end not after publication; period regex and quarter-end months; duplicates;
finite, positive indexes; `0`/`NA` treated as missing; no gaps inside a series' stored run; `STATUS`/`UNITS`/`Subject`/`Group` match the expected
identity for each series; all 11 Level-1 groups, all groups, tradables, non-tradables and SA all groups present at the reference quarter
(and every previously observed core series keeps its periods, per the ECT coverage rule); base-quarter == 1000; computed q/a changes for
all groups, tradables and non-tradables equal the page's embedded chart percentages for all 17 charted quarters within a measured rounding
tolerance; all-groups change lies between tradables and non-tradables changes (plus rounding); contribution tables, **when present**, have exactly the 11 groups,
finite values, correct period and a sum within a measured tolerance of the headline change.
Level-2/3 optional series: problems produce warnings, not errors, so a lower-level reclassification cannot block headline CPI.
Contribution charts **absent**: ingest succeeds with a recorded warning and the UI says "not published in this release" (my call, see below).
Contribution charts **present but wrong**: fail.

**Revisions.** Existing vintage/revision machinery compares compatible vintages (mainly SA series; unadjusted CPI is not normally revised).
Only genuine publications are compared; no vintages are fabricated. Backfill depth is set by a short paced probe of March 2026 and December 2025
(and earlier only if files are complete), recorded in `docs/data-sources/cpi.md`, as was done for migration.

**Calendar/scheduler.** `parse_title` already maps "September 2026 quarter" to 2026-09 and slug `consumers-price-index`, and the catalog already lists it as high importance. Registering the adapter makes
the existing planner poll it. Batch 3 proves this offline with a simulated-release rehearsal; it is not evidence the live release was processed.

**API/insights.** `GET /api/cpi` returns one release bundle (like `/api/ect`): headline, tradables/non-tradables, groups, contributions, histories, source/vintage metadata,
caveats. `insights/cpi.py` builds the dashboard and rule-based Release Analysis (headline, change vs previous quarter, annual vs prior release,
tradables vs non-tradables, driving groups, revisions, caveats). Overview KPI and `INACTIVE_CATEGORIES` ("Prices and inflation") follow the ECT pattern: active only when a verified bundle exists. Calendar, Latest Releases and Data Health
recognise the slug. Generated `schema.d.ts` updated; existing contracts untouched.

**Frontend.** `/inflation` page (`pages/Inflation.tsx`, `charts/cpi.ts`), nav entry, sections A to G from the brief. Annual and quarterly inflation charts with zero line,
optional 1 to 3% band (labelled as the RBNZ target band, a reference only), 3/5/10-year/full ranges, gaps not connected; tradables vs non-tradables;
signed ranked contribution bars with quarterly/annual toggle, labelled "percentage points"; component explorer; analysis; methodology with Stats NZ links. Existing CSV/PNG export, escape helpers and
the validated palette are reused. Taste/dataviz skills guide styling within spec §9 dials.

## Calls I made (change any)

1. Absent contribution chart is a warning, not a failure (headline CPI must not be blocked on release day); a present but invalid one fails the bundle.
2. Percent changes are derived on read, with embedded chart percentages used only as a validation cross-check.
3. Level-2/3 series limited to an allow-list; the full set of ~200 is not stored.
4. No official core measure exists in the files, so none is shown; the page says so rather than offering a lookalike.
5. No builder-check subagent (token budget); I read this as that builder.
6. Unfetched items to verify in Batch 1: base period (workbook), the 8 Oct 2026 methodology update, March/December fixtures.

## Out of scope / risks

Live September layout may differ: the adapter fails closed and keeps March/June data. First-ingestion coverage and March/June vintage depth are measured, not assumed.
