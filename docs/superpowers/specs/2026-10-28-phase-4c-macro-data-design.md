# Phase 4C: official NZ macroeconomic data (GDP, labour market, OCR): design

Date: 2026-10-28. Base: `main` at `5ad5f34` (Phases 3A to 3F and 4B merged). Extends the existing release pipeline;
nothing is rebuilt. Plan: [2026-10-28-phase-4c-macro-data.md](../plans/2026-10-28-phase-4c-macro-data.md).

## Intent

Add quarterly GDP and the Household Labour Force Survey (with the Labour Cost Index as the one wage indicator) as
release-aware Stats NZ categories, assess the Reserve Bank's OCR data, and connect the new official outcomes to the
Economic Outlook's forecast evaluation where the definitions genuinely match.

Anti-goals: a wrong growth rate on release day; annual-average growth shown as "annual growth" of a quarter; seasonally
adjusted and unadjusted figures, or chain-volume and current-price figures, on one axis; HLFS, LCI and QES measures
mixed; an OCR figure from an unapproved source; a forecast scored against an outcome with a different definition.

## Audit (28 October 2026)

- `main` is clean at `5ad5f34`; no open PRs. Hosted CI is still blocked by account billing (Phase 3D-A to 3F), so all
  verification is local and reported as such.
- The generic schema (`release`, `series`, `vintage`, `observation`, `vintage_series_definition`) already holds any
  quarterly Stats NZ series with full vintages and definition snapshots. **GDP and HLFS need no migration.**
- A category is: an adapter (`adapters/<cat>/`: `series.py` catalogue, `adapter.py` parse and validate), registration in
  `runtime.build_adapters`, a download classifier in `sources/release_page.py`, an insights builder, an `/api/<cat>`
  dashboard model, a snapshot contract entry and a frontend page. CPI (Phase 2B) is the template.
- Research already names `gdp`, `unemployment` and `ocr` as indicators, and `research/compare.basis_of` already separates
  their bases (annual average, quarterly, end-of-period). Only CPI outcomes are evaluated (`research/outcomes.py`,
  `research/accuracy.EVALUATED_INDICATORS`).
- RBNZ is `restricted` in `config/research_sources.toml`: robots.txt and pages returned 403 to the Phase 3A probe; its
  terms (read via a search summary only) restrict automated access without written permission.

## Verified source facts

Captured on 28 October 2026 under owner authorisation (Kevin, this session) through the application's paced
`Fetcher` (10 s between requests, sequential, project User-Agent): four release pages, two GDP CSVs and two labour
market zips, 8 requests in total. Raw files are under `data/capture-4c/` (git-ignored). Nothing else was requested.

### GDP (`gross-domestic-product-june-2026-quarter`, published 2026-09-17 10:45 NZST; March 2026 quarter, 2026-06-18)

Downloads: `…-quarter.csv` (21 MB, 98,547 rows, 1,004 series), `…-quarter.xlsx`, `…-current-price-income-and-expenditure.xlsx`,
`…-supplementary-tables.xlsx`, `…-visualisation.csv`. Only the main CSV is read.

Columns: `Series_reference, Period, Data_value, STATUS, UNITS, MAGNITUDE, Subject, Group, Series_title_1..5`. `Period`
is `YYYY.MM` (quarter-end month); `SNEQ.*` series are quarterly, `SNEA.*` annual (March years and rolling annuals).
`STATUS` is `FINAL` for quarterly rows; `REVISED` appears in annual rows. Chain-volume series are in 2009/10 prices.

Headline series (June 2026 values, $ million unless stated):

| Series | Meaning | Latest |
|---|---|---|
| `SNEQ.SG01RSC00B01` | GDP, production measure, chain volume, seasonally adjusted | 71,805 |
| `SNEQ.SG01RAC00B01` | GDP, production measure, chain volume, actual (unadjusted) | 70,642 |
| `SNEQ.SG02RSC00B15` | GDP, expenditure measure, chain volume, seasonally adjusted | 74,135 |
| `SNEQ.SG02RAC00B15` | GDP, expenditure measure, chain volume, actual | 73,906 |
| `SNEQ.SG02NSC00B15` | GDP, expenditure measure, current prices, seasonally adjusted | 115,798 |
| `SNEQ.SG02NAC00B15Z` | GDP, expenditure measure, current prices, actual | 114,916 |
| `SNEQ.SG09RSC00B01NZ` | GDP per capita, production, chain volume, SA (NZ$ per person) | 13,410 |
| `SNEQ.SG09NSC00B15NZ` | GDP per capita, expenditure, current prices, SA (NZ$ per person) | 21,626 |
| `SNEQ.SG01RSC01B01PC` | Production GDP, SA, % change from previous quarter | 0.2 |
| `SNEQ.SG01RSC01B01AC` | Production GDP, SA, % change from same quarter a year earlier | 2.6 |
| `SNEQ.SG01RAC01B01AC` | Production GDP, rolling annual (annual average) % change | 1.7 |
| `SNEQ.SG02RSC31B15PC` | Expenditure GDP, SA, % change from previous quarter | 0.4 |

Findings that shape the design:

1. **Three different "annual" figures exist.** The release page chart titled "Annual growth" (June 2026: 1.7) is the
   *annual average* change (`SG01RAC01B01AC`: year ended June 2026 against year ended June 2025, from actual values).
   The seasonally adjusted change from the same quarter a year earlier is a different series (2.6). Quarterly growth is
   0.2. Each is stored and labelled separately; none is called plain "annual growth".
2. **Real revisions between the two captured releases** (page charts): March 2026 quarterly growth 0.8 first published,
   0.9 in June; March 2025 0.9 to 0.8; June 2025 -0.7 to -0.6; June 2023 1.0 to 0.9; annual average Sept 2024 0.5 to 0.4,
   Sept 2025 -0.6 to -0.5, March 2026 0.8 to 0.9. Revisions are the norm in national accounts, so a revision is recorded
   and shown, never treated as an error.
3. **Per-capita metadata is inconsistent**: `SNEQ.SG09RAC00B01NZ` (actual) declares `MAGNITUDE` 6 (millions) while its
   values (13,193) are dollars per person; the SA per-capita series declare 0. The adapter pins the expected metadata per
   series as observed and stores the unit as "NZ$ per person"; it never multiplies by a declared magnitude.
4. Page chart period labels changed format between releases (`Dec 2022` in June, `Sept-22` in March). The chart
   cross-check parses both and fails closed on anything else.
5. Values are integers in $ million, so a change computed from levels carries at most ±0.0008 pp of rounding error,
   far below the 1 d.p. publication. Tolerances are measured on both real files before being fixed.

### Labour market (`labour-market-statistics-june-2026-quarter`, published 2026-08-05 10:45 NZST; March 2026, 2026-05-06)

Downloads: `labour-market-statistics-june-2026-quarter.zip` (18.6 MB packed, **756 MB unpacked**), plus HLFS, LCI and
QES workbooks. The March 2026 page lists only `…-march-2026-quarter-revised.zip`, whose folder is named "…updated" and
whose members are dated 28 July 2026, i.e. **the March release was republished after first publication**.

Zip members: `hlfs-<qtr>-csv.csv` (423 MB, 1,278,057 rows, 61 columns), `lci-…csv` (6.7 MB), `qes-…csv` (40 MB),
`lms-…-tables.csv` (286 MB: HLFS+LCI+QES combined). Member names differ by release (`-csv.csv` in June, `-tables.csv`
in the revised March zip). Only the HLFS and LCI members are read, streamed row by row.

HLFS headline (seasonally adjusted, total both sexes, June 2026): unemployment rate `HLFQ.S1F3S` 5.6%, employment rate
`HLFQ.S1H3S` 66.7%, participation rate `HLFQ.S1E3S` 70.7%, underutilisation rate `HLFQ.SXJ3UZS` 13.8%; employed
`HLFQ.S1A3S` 2,905 thousand, unemployed `HLFQ.S1B3S` 171 thousand, labour force `HLFQ.S1Z3S` 3,076 thousand,
working-age population `HLFQ.S1D3S` 4,353 thousand. Rates from 1986 (underutilisation from 2004).

LCI headline: `LCIQ.SG53Z9` all salary and wage rates (including overtime), all sectors, all industries, index (base
June 2009 quarter = 1000); published changes `LCIQ.SG53Z9PC` 0.6% quarterly and `LCIQ.SG53Z9AC` 2.0% annual. The LCI
measures the price of labour for the same job at the same quality; it is not average earnings (that is QES).

Findings:

6. **A real revision of the headline rate**: the March 2026 release reported unemployment of 5.3%; the June 2026
   release states 5.4% for March 2026. Seasonal adjustment revises the SA history every quarter.
7. `STATUS` is `FINAL` on every HLFS row, including revised seasonally adjusted history, so revisions are found only by
   comparing stored vintages.
8. Levels are in thousands, rounded; rates are published to 1 d.p. Identity checks (labour force = employed +
   unemployed; rate = unemployed / labour force) therefore need measured tolerances.
9. HLFS is a sample survey: the file carries sampling-error series. Quarterly movements of 0.1 to 0.2 points are
   within sampling error; the dashboard says so instead of narrating them as trends.

### OCR (Reserve Bank of New Zealand)

No request was made to RBNZ. The existing evidence (Phase 3A) is that robots.txt and pages returned 403 to the probe and
the terms, read through a search summary only, restrict automated access without prior written permission. There is no
documented access decision for the OCR statistical tables. See "OCR" below.

## Design

### Shared

- `sources/release_page.classify_download` gains `gdp_csv` (`gross-domestic-product-<period>-quarter(-corrected)?.csv`,
  excluding `-visualisation`) and `labour_zip` (`labour-market-statistics-<period>-quarter(-revised|-corrected)?.zip`).
  `pick_downloads` treats `-revised` like `-corrected` (a republication wins).
- Both adapters follow CPI's fail-closed rules: exact header check, pinned metadata per series, period format, every
  required series present, reference period equals the release's, no period after publication, no duplicate period.
  Optional series are dropped with a warning, never blocking the headline.
- Last-known-good: unchanged. A failed parse or validation leaves the previous active vintage in place.
- No synthetic values in production paths. Fixtures are real excerpts (every row of each pinned series), regenerated by
  `scripts/capture_macro_fixtures.py`, which uses the paced `Fetcher` and skips files already captured.

### GDP: `adapters/gdp/`, slug `gross-domestic-product`

Stored series (quarterly, period `YYYY-MM`): the twelve in the table above. Keys:

| Key | Unit |
|---|---|
| `gdp.production.cv.sa`, `gdp.production.cv.nsa`, `gdp.expenditure.cv.sa`, `gdp.expenditure.cv.nsa` | NZ$ million (2009/10 prices) |
| `gdp.expenditure.cp.sa`, `gdp.expenditure.cp.nsa` | NZ$ million (current prices) |
| `gdp.per_capita.production.cv.sa`, `gdp.per_capita.expenditure.cp.sa` | NZ$ per person |
| `gdp.production.cv.sa.pct_qoq`, `gdp.production.cv.sa.pct_yoy`, `gdp.production.cv.nsa.pct_annual_avg`, `gdp.expenditure.cv.sa.pct_qoq` | percent, as published |

Validation (errors block; warnings record):

- Official percentages reconcile with the levels: each published change against the change computed from the stored
  levels (q/q and y/y on SA levels; annual average on the sums of four unadjusted quarters). Error above a tolerance
  measured on both releases (see the plan); the levels and the percentages must come from the same file.
- Page cross-check: the release page's "Quarterly growth" and "Annual growth" charts must equal the published series at
  every common quarter (exact to 1 d.p.). This is the guard against mislabelling annual average as annual change.
- Reference period: the latest quarter of every headline series equals the release's reference period.
- Revisions against the previous vintage: recorded; a quarterly growth revision above 1.0 pp is a warning, never an error.

Dashboard `/api/gdp` (`insights/gdp.py`): headline metrics (quarterly growth SA, annual average growth, annual change SA,
each named for what it is), level charts kept apart by price basis and adjustment, production versus expenditure growth,
per capita, a revision table (first published versus latest for each recent quarter, from stored vintages, with the
earliest-stored caveat CPI already uses), sources and caveats. Text is deterministic and states the measure every time.

### Labour market: `adapters/labour/`, slug `labour-market-statistics`

Stored series: the eight HLFS headline series above (keys `hlfs.rate.unemployment.sa`, `hlfs.rate.employment.sa`,
`hlfs.rate.participation.sa`, `hlfs.rate.underutilisation.sa`, `hlfs.level.employed.sa`, `hlfs.level.unemployed.sa`,
`hlfs.level.labour_force.sa`, `hlfs.level.working_age_population.sa`) and the LCI headline (`lci.all_wages.index`,
`lci.all_wages.pct_qoq`, `lci.all_wages.pct_yoy`). Series definitions name the survey (HLFS or LCI). QES is not stored in
Phase 4C; it is listed as a follow-up so earnings are never presented as wage rates.

Archive reading: the zip is opened from memory; only members matching `hlfs-…\.csv` and `lci-…\.csv` are read, streamed
through `csv` with a cap on archive size (64 MB), member size (1 GB), member count (8) and rows (2.5 million). A member
that exceeds a cap fails closed. Nothing is extracted to disk.

Validation: identity checks on the published figures (labour force against employed plus unemployed; each rate against
its numerator and denominator), with tolerances measured on both releases; LCI published changes against the index;
reference period; the release page headline rate equals the stored latest rate.

Dashboard `/api/labour-market`: headline rates, rate trends on one percent axis (rates only), levels on their own axis,
revision of the previous quarter's rate (first published versus latest), the LCI as a separately labelled wage panel,
sampling-error and survey caveats, sources.

### OCR: `ocr/` (domain module, synthetic fixtures only)

Access decision: **not supported.** There is no documented permission for automated access to RBNZ's statistics, and
the only evidence on file is restrictive. Live acquisition is therefore not implemented. Built instead:

- A typed model for OCR decisions (announcement date, effective date, new rate, change in basis points, decision kind)
  and pure functions: the rate in force on a date, the change in basis points, month-end and monthly-average
  observations, and the distinction between decision date, effective date and monthly observation.
- A parser for a documented CSV contract that the owner could supply from an approved source, with strict validation
  (ordering, duplicates, effective date not before announcement, basis-point change equal to the rate difference).
- Tests on fixtures marked `SYNTHETIC` in their name and header. Nothing reads them outside tests; no API, snapshot or
  page shows an OCR value. The dashboard's OCR page states that the source is not yet approved and why.

Unblocking needs a human: read RBNZ's terms of use and statistics licence directly, decide on the access method (manual
download, written permission or an official API), and record the decision in `docs/data-sources/ocr.md`.

### Economic Outlook integration

`research/outcomes.py` keeps the CPI rules byte for byte (existing tests unchanged) and gains matchers that run only for
`gdp` and `unemployment` forecasts with a clearly stated basis and a single quarter:

- GDP quarterly growth (seasonally adjusted, real, production unless "expenditure" is stated) → `pct_qoq`; annual average
  growth → `pct_annual_avg`; annual change of a quarter → `pct_yoy` only when the label says seasonally adjusted,
  otherwise not matched (Stats NZ's annual change of a quarter is on actual values; that series is not stored). Nominal
  GDP and GDP levels are not matched in 4C.
- Unemployment rate for a quarter → `hlfs.rate.unemployment.sa`; an annual average or a month is not matched.
- OCR → "No official OCR series is ingested; RBNZ access is not approved", an explicit unavailable state.
- First-published: from the release whose reference period is the target quarter (else the earliest stored, labelled);
  latest: the newest stored release. Look-ahead exclusion and horizon bands are reused unchanged.
- Accuracy summaries include GDP and unemployment only where matched outcomes exist; minimums and ranking rules unchanged.

### User experience

Pages `/gdp` and `/labour-market` in the editorial system already used by `/inflation`: a headline band with the three
named measures, one primary trend chart, a revision-aware chart (first-published against latest), a compact data table,
plain-English findings generated from the figures, source attribution with release and reference dates in Pacific/
Auckland, CSV export. `/ocr` explains the unavailable state. Economic Outlook links each indicator's comparison to its
official page. Mobile, dark mode and keyboard behaviour follow Phase 4B. Chart colours are validated with the dataviz
validator and recorded in `docs/progress.md`.

### Publication

The snapshot contract gains `gdp.json` and `labour-market.json` (official Stats NZ data only, never OCR). The exporter's
fixture refusal, URL allow-list and parity spec apply unchanged.

## Delivery

Stacked PRs, none merged or deployed automatically:

1. `feat/phase-4c-gdp`: this spec, the plan, the capture script, GDP adapter, validation, `/api/gdp`.
2. `feat/phase-4c-labour`: HLFS and LCI adapter, validation, `/api/labour-market`.
3. `feat/phase-4c-ocr`: OCR domain module on synthetic fixtures and the access assessment.
4. `feat/phase-4c-integration`: Outlook outcome matching, pages, snapshot and static site.

## Risks

- The 423 MB HLFS member makes labour ingestion slower (about 10 s to stream) and memory-sensitive; streaming and caps
  bound it. A future Stats NZ layout split would fail closed, not partially load.
- National accounts revise heavily; first-published GDP for quarters before the earliest stored release is unknown, and
  the dashboard says "earliest stored" rather than "first published" for them.
- OCR stays unavailable until a human access decision; the Outlook shows that state explicitly.
