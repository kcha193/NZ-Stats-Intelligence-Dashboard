# Phase 3D-B: historical forecast intelligence

Date: 2026-10-28. Overview and audit: [2026-10-28-phase-3d-design.md](2026-10-28-phase-3d-design.md) (on the 3D-A
branch). Everything here is deterministic, derived on request from immutable stored rows (claims, summaries,
publication decisions, Stats NZ vintages), and built only from summaries that pass the public gate. No migration.

## Inputs and what is not used

- Forecasts: the claims of summaries that `research/public.py` would show now (verified, reviewed, publication-approved,
  current document version, display level `summary` or above). Nothing unpublished, no document text.
- Actuals: Stats NZ CPI vintages already stored (`cpi.index.nsa.all_groups`, `cpi.index.sa.all_groups`). No other
  official series is ingested, so GDP, unemployment and the OCR are never evaluated, and nothing is invented for them.

## A. Forecast history

- **Identity** = institution + indicator + unit + statistical basis + horizon + kind (central, or the normalised scenario
  name). The basis is the Phase 3C one (`compare.basis_of`), unchanged: nothing is converted or inferred.
- **Vintage** = one published summary's claim: its publication's `published_on`, the summary id, the value as stated,
  the label, horizon and qualification as written, and its evidence locations. Vintages are ordered by publication date,
  then summary id. The newest is current; older ones are kept and marked superseded.
- **Revision** = a change of value between consecutive vintages of the same identity (`value - previous value`).
- **Measure change** = the same institution, indicator, horizon and kind in consecutive vintages, but with disjoint
  bases (for example "annual average" then "through the year"). Reported as a change of measure, never as a revision.
- **Within-document conflict** = one summary states two different values for one identity. Both are withheld from
  history, comparison, evaluation and consensus, and listed with the reason. Identical repeats (text and table) are one
  claim. This also fixes Phase 3C comparison, which listed a same-document repeat as an "earlier vintage".

## B. Standardisation

Only the Phase 3C rules decide equivalence: indicator, unit, basis (cadence, price basis, timing, the measure, the part of
the series), horizon and kind. Fiscal "2026/27" stays a split year "as stated" and never becomes a June year; real and
nominal GDP never meet; quarterly and annual CPI never meet. A qualification is shown, never parsed into a definition.

## C. Outcome matching (CPI)

| Claim basis | Official measure | Series | Formula (official rounding) |
|---|---|---|---|
| `annual_change` | annual % change, through the year | unadjusted all groups | `round(100 × (I_q / I_{q-4} − 1), 1)` |
| `annual_average_change` | annual average % change | unadjusted all groups | `round(100 × (ΣI_{q-3..q} / ΣI_{q-7..q-4} − 1), 1)` |
| `quarterly_change`, label says seasonally adjusted | quarterly % change, SA | seasonally adjusted all groups | `round(100 × (I_q / I_{q-1} − 1), 1)` |
| `quarterly_change`, label says unadjusted | quarterly % change | unadjusted all groups | same |

- Rounding is half away from zero on exact decimals of the published index numbers (Stats NZ computes its percentage
  changes from the rounded published index). The annual and quarterly formulas reproduce all 204 published chart
  values in the CPI fixtures (`docs/data-sources/cpi.md`); the annual average formula is standard but was not checked
  against a published figure, so it is labelled "derived from the published index".
- Not matched, with a reason: a quarterly change that does not say whether it is seasonally adjusted; a basis with a
  qualifier (a region, a population); core, trimmed or excluding measures (Phase 3C already refuses them); horizons that
  do not name a quarter (`calendar:`, `split:`, a non-quarter-end month); `year_to:` with a quarterly change.
- **First-published actual** = the value in the stored vintage of the release whose reference period is the target
  quarter. If that release is not stored, the earliest stored vintage containing the target is used and labelled
  "earliest stored release", not "first published". **Latest actual** = the newest stored release. Both are reported
  with their release names and dates; the revision between them is shown separately.
- **Look-ahead**: a forecast published on or after the Auckland date of the target's first release is excluded. When
  the release date is unknown, only forecasts published by the end of the target quarter are kept. A forecast with no
  publication date is excluded. A target whose release is not yet stored is `pending`, never matched to the latest
  available quarter.
- **Horizon** = quarters from the quarter containing the publication date to the target quarter (0 = current quarter;
  negative = published after the quarter ended, before the release).

## D. Accuracy

- Central forecasts only: a scenario is conditional on its own assumptions and is never scored.
- Error = forecast − actual (positive means the forecast was too high), against the first-published actual by default
  and the latest actual as a second column.
- Per institution and horizon band (≤0, 1–2, 3–4, 5–8, 9+ quarters): count, mean error, MAE, RMSE. MAE, RMSE and mean
  error are reported only from **4** outcomes; below that the count is shown with "insufficient".
- **Ranking** only on a matched sample: the targets and exact horizons that every institution with a matched forecast
  forecast (latest vintage per institution within a cell). At least **8** matched cells, or no ranking and the reason.
  No significance test is run, and the page says so.
- Coverage: matched, pending and excluded counts per institution, the vintage date range and the newest CPI release used.
- Thresholds (4 and 8) are judgement for a descriptive display, not statistical power calculations.

## E. Consensus

- Per Phase 3C comparison group, central forecasts only: each institution's latest vintage, at most one per institution.
- Excluded with a reason: scenarios (always), a document whose title says it is a consensus or survey of other
  forecasters (not independent), and vintages more than **180 days** older than the newest contribution.
- Two or more institutions: mean, median, minimum, maximum, range. Three or more: sample standard deviation. Five or
  more: outliers beyond median ± 3 × 1.4826 × MAD (when MAD > 0).
- Always labelled: a descriptive summary of the latest published central forecasts, not statistically calibrated and not
  an independent forecast.

## API (read-only, behind `NZSTATS_PUBLIC_RESEARCH=1`, built from `public_summaries` only)

- `GET /api/research/forecast-history?indicator=&institution=`
- `GET /api/research/forecast-evaluation?indicator=` (CPI is the only indicator with outcomes; others return an
  explicit `no_official_series` state)
- `GET /api/research/consensus?indicator=`

Nothing enters the static snapshot; the static site shows the same "not published" state as the live app with research
off.

## Frontend

- Forecast comparison: the official "latest observation" line is drawn only for a target ending after the observed
  quarter (Phase 3C drew it on every annual CPI group, so a "year to March 2026" group showed the June 2026 figure);
  an earlier target points to the track record instead. The consensus line (institutions, median, range; spread and outliers when supported) under each
  central group; a dot-plot axis that need not start at zero, with a minimum span and an explicit note when it does not.
- Forecast history: pick a target (indicator, basis, horizon); one line per institution across vintages, the official
  first-published outcome as a reference line when it exists; revisions, measure changes and conflicts listed.
- Forecast track record (CPI): errors by horizon as dots, the summary table with counts, the ranking state, and the
  matched, pending and excluded lists. Explicit states for "no official series", "nothing to evaluate yet" and
  "insufficient".

## Chart colours

A line per institution would need a categorical palette, and the site's navy and violet tokens fail the colour-vision
check together (validator: worst all-pairs CVD ΔE 2.7 light, 0.7 dark; normal-vision 11.5 and 9.5, below 15). Revision
charts are therefore small multiples, one panel per institution on shared axes, in the validated navy (forecasts) and
amber (official outcome) pair. Error dots are one series in navy, one row per institution.

## Verification

Synthetic, hand-counted fixtures for history, conflicts, measure changes, consensus and accuracy arithmetic; real Stats
NZ CPI fixture releases (December 2025 to September 2026) for outcome matching, first-release versus later vintages and
look-ahead; leak tests that unpublished summaries never reach the new routes; the routes are 404 while off.
