# Data dictionary

All series are International migration, outcomes-based long-term migrants (a traveller counts as a migrant
if they spend 12 of the following 16 months in, or out of, New Zealand). Unit: people. Seasonal
adjustment: none. Definition id: `migration.outcomes_based_long_term`.

## Series keys

| Key | Frequency | Meaning |
|---|---|---|
| `mig.m.arrivals`, `mig.m.departures`, `mig.m.net` | monthly | Mean monthly estimate of migrant arrivals, departures, and net (arrivals minus departures) |
| `mig.m.arrivals.nz`, `mig.m.arrivals.nonnz` | monthly | Monthly arrivals by citizenship (NZ citizens, non-NZ citizens) |
| `mig.m.arrivals.country.<slug>` | monthly | Monthly arrivals by country of last permanent residence |
| `mig.m.arrivals.region.<slug>` | monthly | Same, for the five Stats NZ regions (Asia, Europe, The Americas, Africa and the Middle East, Oceania and Antarctica) |
| `mig.m.arrivals.country.not-stated` | monthly | "Not Stated" place of residence (series category `migration:unallocated`; never ranked as a country) |
| `mig.ry.arrivals`, `mig.ry.departures`, `mig.ry.net` | rolling annual | Year-ended totals as published by Stats NZ |
| `mig.ry.<arrivals\|departures\|net>.<nz\|nonnz>` | rolling annual | Year-ended totals by citizenship |

`<slug>` is the lower-case name with punctuation removed and spaces turned into hyphens (apostrophes are
dropped, e.g. `china-peoples-republic-of`).

## Semantics

- **Monthly vs year-ended**: a year-ended value for period `YYYY-MM` is the total for the twelve months
  ending in that month. It is never combined with, or plotted on the same axis as, a monthly value.
  Period labels read "Jul 2026" for monthly and "Year ended Jul 2026" for rolling annual.
- **Status**: `provisional` is read from the file's `status` column (latest sixteen months);
  `final` otherwise; `unknown` when a file gives no status. A year-ended total has no published status: it is
  derived as `provisional` when any of its twelve months is, `unknown` when a month's status is missing, `final`
  otherwise. Provisional values are drawn with a shaded band or lighter bars and flagged in tooltips, chart
  titles and exports; monthly and year-ended statuses are separate columns. The country ranking flags its
  prior window the same way (`prior_provisional`).
- **Standard error (SE)**: Stats NZ's published standard error for provisional estimates; zero for final.
  Labelled "SE" in the headline table. One standard error is not a 95 percent confidence interval or a
  range of possible future revisions. No confidence interval is inferred from it by this dashboard.
- **Net**: arrivals minus departures; wording is "net gain" or "net loss", never a sign alone.
- **Percentage change**: shown as "n/a" when the previous value is zero or negative, or the current value
  is negative, because a percentage of a non-positive base is misleading. Absolute change is always shown.
- **Revision**: revised value minus original, between two stored vintages. Percent only when meaningful.
  Releases before the oldest stored vintage cannot be compared, and the UI says so.
  Release analysis reports corrections within the same publication separately from revisions between
  publications, including changes to status or standard error and added/withdrawn observations.
- **Statistical identity**: new bundles use a `data-v1:` prefix plus a SHA-256 of parsed observations
  and measurement semantics. Editorial names, chart captions and file formatting are excluded. Legacy
  bundle identifiers and their observations remain intact; an equivalent legacy capture is reused.
- **Overview freshness**: `data_updated_at` is the selected migration bundle's ingestion/capture time.
  `generated_at` is only the API response time. Source checks have their own attempt/success timestamps.
- **Derived country ranking**: the sum of the published monthly arrivals by country over the requested
  window (the UI asks for the latest 12 months, `GET /api/migration/countries?months=&top=`). Country series are
  stored for the latest `country_window_months` (36, `config/sources.toml`) of each release. Months absent
  from the source are treated as zero. Regions and "Not Stated" are shown separately and never ranked.
  Lighter bars include provisional months.
- **Percentile or rank**: describes position within the published series only; it does not indicate
  economic significance.

## Release fields

| Field | Values |
|---|---|
| `status` | `scheduled`, `published`, `delayed`, `corrected`, `unavailable` |
| `category` | Migration, Tourism and travel, Population, Prices and inflation, Labour market, Economic growth, Housing and building, Retail, Trade, Other (from `catalog.py`) |
| `importance` | `high`, `medium`, `low`: an editorial choice for this dashboard, not a Stats NZ field |
| error class | `network`, `blocked`, `not_found`, `layout_changed`, `validation_failed`, `unexpected` |
