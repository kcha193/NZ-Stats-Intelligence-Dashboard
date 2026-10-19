# Consumers price index: source verification

Verified 19 October 2026 through the application's paced fetcher (10 s between requests, sequential, descriptive
User-Agent). Only official Stats NZ sources were used. The September 2026 quarter release (22 October 2026, 10:45 NZDT)
was not yet published, so nothing in this file describes it; the adapter was built and validated on three real releases.

Releases captured as fixtures (`backend/tests/fixtures/cpi_<YYYY-MM>_*`, regenerate with `scripts/capture_cpi_fixtures.py`):

| Release | Page | Published (Auckland) |
|---|---|---|
| [December 2025 quarter](https://www.stats.govt.nz/information-releases/consumers-price-index-december-2025-quarter/) | `cpi_2025-12_page.html` | 2026-01-23 10:45 NZDT |
| [March 2026 quarter](https://www.stats.govt.nz/information-releases/consumers-price-index-march-2026-quarter/) | `cpi_2026-03_page.html` | 2026-04-21 10:45 NZST |
| [June 2026 quarter](https://www.stats.govt.nz/information-releases/consumers-price-index-june-2026-quarter/) | `cpi_2026-06_page.html` | 2026-07-21 10:45 NZST |

## Downloads (June 2026 names; `Download-data/` under the release's asset folder)

| File | Used | Contents |
|---|---|---|
| `…-index-numbers.csv` | **required** | Unadjusted index: all groups, Level-1 groups, Level-2 subgroups, Level-3 classes |
| `…-tradeables-and-non-tradeables.csv` | **required** | `CPIQ.SE9A`, `CPIQ.SE9NS6000` tradeable and `CPIQ.SE9NS6500` non-tradeable all-groups, plus a tradeable/non-tradeable by group matrix (not used) |
| `…-seasonally-adjusted.csv` | **required** | Seasonally adjusted all groups, tradeable/non-tradeable, Level-1/2/3 |
| `…-infoshare-data.csv` | no | Weighted average prices of items (not an index) |
| `….xlsx` workbook | no (see below) | 27 sheets, see below |
| `…-central-and-local-government-charges.xlsx` | no | Supplementary |

Schema of the three required CSVs (identical across December 2025, March 2026 and June 2026): columns `Series_reference, Period,
Data_value, STATUS, UNITS, Subject, Group, Series_title_1, Series_title_2`; `UNITS` is always `Index`, `Subject` is `CPI`.
`Period` is `YYYY.MM` of the quarter-end month and must be read as text. `STATUS` is `FINAL` throughout the unadjusted files;
the seasonally adjusted file mixes `REVISED` and `FINAL`. File names say "tradeables"; page text and Stats NZ prose say
"tradables" in places. Official group names, as published: Food; Alcoholic beverages and tobacco; Clothing and footwear;
Housing and household utilities; Household contents and services; Health; Transport; Communication; Recreation and culture;
Education; Miscellaneous goods and services (the chart label "Housing contents and services" differs and is mapped).

Missing values are written `NA` or `0` (for example early Food and Alcohol history), never as a real zero; both are treated as
missing. Contiguous unbroken quarterly history (latest unbroken run, measured on the June 2026 release):

| Series | First stored quarter |
|---|---|
| All groups, unadjusted (also SA all groups) | 1925-09 (earlier points are annual-only or `NA`) |
| Tradables, non-tradables (unadjusted) | 1999-06 |
| SA tradables | 1999-06 |
| SA non-tradables | 2010-03 (has gaps before) |
| Level-1 groups (unadjusted) | 1925-09 for Food and Alcohol, 1999-06 for the others |
| SA Level-1 group `CPIQ.SE9S11` Miscellaneous | ends 2023-03 (discontinued): optional, warning only |

**Base period**: June 2017 quarter = 1000 (workbook tables 1 and 2.01; and verified in all three releases: the index at
2017-06 is exactly 1000 for all groups and each of the 11 Level-1 groups). The adapter fails closed if that stops being true.

## Embedded release-page charts

Chart titles are **not stable** across releases: December 2025 and March 2026 label the percentage charts only `Line` and
`Column`; June 2026 uses "Consumers price index, percentage change, June 2022–June 2026 – column/line". The adapter therefore matches
percentage charts by their **row labels** (`CPI all groups (quarterly)`, `CPI all groups (annual)`, `Tradeables (annual)`,
`Non-tradeables (annual)`), and contribution charts by title prefix (`Quarterly percentage point contribution to consumers price
index, by group` / `Annual percentage point…`), which were identical in all three releases. Quarter labels are `Jun-26`, `Sept-22`
(Stats NZ uses both `Sept` and `Sep`). Contribution charts hold the latest quarter only (one row, 11 groups).

## Workbook (June 2026): what it holds, what is used

Base statement: "Base: June 2017 quarter (=1000)". Tables: 1 tradeables/non-tradeables/all groups (index and % changes), 2 groups and
subgroups, 3 selected groupings ("All groups less food", "…less transport" and similar), 5/8 expenditure weights, 7.01/7.02
contributions (index point, percentage point and percentage contribution) with weight reference quarter, **10 trimmed means** (5 to 30 per cent
trim), **11 weighted percentiles** (10th, 25th, median, 75th, 90th), 12 distribution of item movements, 13/14 seasonally adjusted, 15
regional, 16 discounting, 17 regional all groups.

Footnotes that matter: "Official percentage changes calculated from rounded index numbers." Contributions are "supplementary
analytical information calculated from unrounded index numbers. May differ from the official all groups figures presented in the
percentage change column." Trimmed-mean and percentile measures are "calculated from unrounded index numbers". The CSVs contain none of
the trimmed-mean, percentile or selected-grouping series; those are workbook-only. See "Underlying measures" below.

## Measured tolerances (December 2025, March 2026, June 2026)

| Quantity | Measured | Constant used |
|---|---|---|
| Computed change from published (rounded) indexes vs the page charts: 68 points per release (17 quarters × quarterly all groups, annual all groups, tradeables, non-tradeables) | All 204 round to the published 1 d.p. value exactly; max absolute difference 0.0492 pp | `CHART_PCT_TOLERANCE = 0.05` (half a unit of the chart's 1 d.p.) |
| Sum of the 11 published group contributions vs computed headline change | Quarterly: Dec 0.008, Mar 0.004, Jun 0.094 pp. Annual: Dec 0.009, Mar −0.021, Jun 0.058 pp | `CONTRIBUTION_SUM_TOLERANCE_PP = 0.15`. Explained by the footnote above (unrounded vs rounded indexes; rounding alone allows about 0.075 pp); the gap is shown, never absorbed |
| Unadjusted index revisions between consecutive releases | None (0 changed values in all-groups and tradables across Dec→Mar→Jun) | Any change in a previously published unadjusted value is a genuine revision and is reported |
| SA index revisions between consecutive releases | Large and genuine: SA all groups, March→June, 71 of 403 common quarters differ, 17 by more than 0.05 index points, maximum 1.14; the rest differ at 1e-8 (floating-point noise) | `SA_REVISION_MATERIALITY = 0.05` index points: smaller differences are not reported as revisions (raw values are stored unchanged) |

Coverage: the three required files kept every previously published quarter of every core series between releases (nothing lost).

## September 2026 methodology update (published 8 October 2026)

[Price index methods – updates for the September 2026 quarter](https://www.stats.govt.nz/methods/price-index-methods-updates-for-the-september-2026-quarter/).
Items relevant to CPI: new water entities (Tiaki Wai, IAWAI, Selwyn Water) now charge separately; metered water stays in the water-rates item and
other charges are added back into local authority rates, so classification and weights are unchanged. Early childhood education index: the
FamilyBoost rebate estimate is unchanged (about $168 million), so no effect. Long-distance bus fares move to administrative data from the September
2026 quarter. Stats NZ also notes that a vehicle relicensing fee increase of 1 January 2025 was applied as a catch-up in June 2025, so annual CPI
inflation for the March 2026 quarter was higher than it would otherwise have been. **No rebasing, reclassification or file-layout change is announced**,
so no validation rule needs to change. The relicensing note is added to the dashboard's caveats. The page also records that quarterly CPI remains the
official measure while a monthly CPI is developed; the dashboard never presents Selected Price Indexes as monthly CPI.

## Underlying measures

No official core inflation series exists in the CSVs. The workbook publishes official trimmed means, weighted percentiles and "all groups less …"
groupings (series `CPIQ.SE9NS4000`–`SE9NS4025`, `SE9NS4100`–`SE9NS4120`, `SE9NS12xx`). These are official, not custom measures. The core
pipeline does not depend on them (the workbook is not required); an optional, warning-level extension reads the trimmed-mean and percentile
tables (see the implementation record). No custom exclusion metric is ever labelled "core inflation".

## Limitations

- Contributions are published only for the latest quarter of each release; history of contributions accrues one release at a time.
- Percentage contribution (share of total movement) is published only in the workbook (table 7.01) and is not used; the dashboard shows percentage change and percentage-point contribution only.
- Headline index values are rounded to integers, so computed quarterly changes carry up to about ±0.07 pp rounding error against unrounded values; official changes use the rounded indexes, as ours do.
- The index files hold roughly 200 series; only the core and an explicit allow-list (listed in `adapters/cpi/series.py`) are stored.
