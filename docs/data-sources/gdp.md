# Gross domestic product: source verification

Captured 28 October 2026 under owner authorisation, through the application's paced fetcher (10 s between requests,
sequential, project User-Agent). Only official Stats NZ sources were used. Design: [Phase 4C spec](../superpowers/specs/2026-10-28-phase-4c-macro-data-design.md).

Releases captured as fixtures (`backend/tests/fixtures/gdp_<YYYY-MM>*`, regenerate with `scripts/capture_macro_fixtures.py`):

| Release | Page fixture | Published (Auckland) |
|---|---|---|
| [March 2026 quarter](https://www.stats.govt.nz/information-releases/gross-domestic-product-march-2026-quarter/) | `gdp_2026-03_page.html` | 2026-06-18 10:45 NZST |
| [June 2026 quarter](https://www.stats.govt.nz/information-releases/gross-domestic-product-june-2026-quarter/) | `gdp_2026-06_page.html` | 2026-09-17 10:45 NZST |

The CSV fixtures (`gdp_<YYYY-MM>.csv`) keep the original header and every row of the twelve stored series; all other
series in the 21 MB file are omitted. Nothing is edited.

## Downloads

| File | Used | Contents |
|---|---|---|
| `gross-domestic-product-<month>-<year>-quarter.csv` | **required** (`gdp_csv`) | 98,547 rows, 1,004 series: `SNEQ.*` quarterly, `SNEA.*` annual and rolling annual |
| `…-quarter.xlsx`, `…-current-price-income-and-expenditure.xlsx`, `…-supplementary-tables.xlsx` | no | Workbooks |
| `…-quarter-visualisation.csv` | no | Chart data for Stats NZ's visualisation tool |

A `-corrected` or `-revised` republication of the CSV wins over the original (`pick_downloads`).

Schema: `Series_reference, Period, Data_value, STATUS, UNITS, MAGNITUDE, Subject, Group, Series_title_1..5` (identical
in both releases). `Period` is `YYYY.MM`, the quarter-end month. Missing values are an empty `Data_value`; in the stored
series they occur only before a series starts (for example the percentage series' first quarters) and are skipped. A
blank after a series starts is a gap and fails validation. `STATUS` is `FINAL` or `REVISED`; `REVISED` is stored as
`unknown`, as for CPI. Metadata of every stored series is identical across both releases and is pinned in
`adapters/gdp/series.py`.

**Per-capita magnitude.** `SNEQ.SG09NSC00B15NZ` (nominal, SA) and `SNEQ.SG09RAC00B01NZ` (real, actual) declare
`MAGNITUDE` 6 although their values are dollars per person (21,626 and 13,193); `SNEQ.SG09RSC00B01NZ` declares 0. The
adapter checks the declared value as observed and never scales by it.

## Stored series

See the table in the spec. Levels are NZ$ million (chain volume in 2009/10 prices, or current prices) or NZ$ per
person; the four percentage series are stored exactly as published (1 d.p.).

## Three "annual" measures

| Measure | Series | June 2026 |
|---|---|---|
| Quarterly growth (SA) | `SNEQ.SG01RSC01B01PC` | 0.2 |
| Annual change of the quarter (SA, same quarter a year earlier) | `SNEQ.SG01RSC01B01AC` | 2.6 |
| Annual average growth (year ended the quarter, actual values) | `SNEQ.SG01RAC01B01AC` | 1.7 |

The release page's "Annual growth" chart equals the annual average series at all 15 quarters it shows, in both releases
(`check_page_charts`), so the page headline "annual growth" is annual average growth. Swapping the two series fails
ingestion (`test_annual_growth_chart_is_annual_average_not_annual_change_of_the_quarter`).

## Reconciliation

Independent hand computation from the raw CSV (plain arithmetic, not the adapter's code):

| Release | Measure | Computed from levels | Published |
|---|---|---|---|
| June 2026 | Quarterly, production SA | 71,805 / 71,628 → 0.2471% | 0.2 |
| June 2026 | Annual change of the quarter, production SA | 71,805 / 70,019 → 2.5507% | 2.6 |
| June 2026 | Annual average, production actual | 285,049 / 280,164 → 1.7436% | 1.7 |
| June 2026 | Quarterly, expenditure SA | 74,135 / 73,869 → 0.3601% | 0.4 |
| March 2026 | Quarterly, production SA | 71,471 / 70,904 → 0.7997% | 0.8 |
| March 2026 | Annual change of the quarter, production SA | 71,471 / 70,435 → 1.4709% | 1.5 |
| March 2026 | Annual average, production actual | 282,969 / 280,703 → 0.8073% | 0.8 |
| March 2026 | Quarterly, expenditure SA | 73,699 / 72,963 → 1.0087% | 1.0 |

The June 2026 four-quarter sum (285,049) also equals Stats NZ's published rolling annual level `SNEA.SG00RAC00B01J`.

Over the whole history of both files (150 to 156 quarters per measure), the largest |computed − published| is 0.0533 pp
(expenditure quarterly growth, March 1989 quarter); production quarterly 0.0499, annual change 0.0501, annual average
0.0499. Integer levels in the late 1980s explain the excess over 0.05. No quarter since 2016 differs after rounding to
1 d.p. **Tolerance: 0.06 pp** (`RECONCILE_TOLERANCE_PP`). A published value outside it fails ingestion.

## Revisions between the two releases

From the release pages and the stored series, March release → June release:

| Quarter | Measure | First published | June 2026 release |
|---|---|---|---|
| March 2026 | Quarterly growth | 0.8 | 0.9 |
| March 2025 | Quarterly growth | 0.9 | 0.8 |
| June 2025 | Quarterly growth | -0.7 | -0.6 |
| June 2023 | Quarterly growth | 1.0 | 0.9 |
| March 2026 | Annual average | 0.8 | 0.9 |
| September 2025 | Annual average | -0.6 | -0.5 |
| September 2024 | Annual average | 0.5 | 0.4 |
| March 2026 | SA production level ($m) | 71,471 | 71,628 |

Revisions are recorded as warnings at ingestion and shown on the dashboard; a quarterly growth revision above 1.0 pp is
flagged for review, never blocked.

## Limitations

- Only quarterly national totals are stored: no industries, expenditure components or income measure.
- First-published figures exist only from the earliest stored release; older quarters are labelled "earliest stored".
- Real GDP per person is published by Stats NZ; its quarterly change on the dashboard is calculated from two published
  values and says so.
