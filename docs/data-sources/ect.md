# Electronic Card Transactions: source verification

Verified 18 October 2026 using the application's shared, sequential 10-second request pacing.
Only official Stats NZ sources were used. No statistical API endpoint was invented or assumed.

- [September 2026 release](https://www.stats.govt.nz/information-releases/electronic-card-transactions-september-2026/), published 16 October 2026, 10:45 NZDT.
- [September CSV ZIP](https://www.stats.govt.nz/assets/Uploads/Electronic-card-transactions/Electronic-card-transactions-September-2026/Download-data/electronic-card-transactions-september-2026.zip).
- [September workbook](https://www.stats.govt.nz/assets/Uploads/Electronic-card-transactions/Electronic-card-transactions-September-2026/Download-data/electronic-card-transactions-september-2026.xlsx).
- [August 2026 release](https://www.stats.govt.nz/information-releases/electronic-card-transactions-august-2026/), published 15 September 2026.
- [DataInfo+ methodology](https://datainfoplus.stats.govt.nz/item/nz.govt.stats/3d0dfc89-6bf5-4677-8cef-3befc36f5b90), linked by the release. The implementation uses the release downloads; no DataInfo+ or ADE API access is needed.

## Choice and coverage

Primary: the downloadable CSV ZIP. It has one UTF-8 CSV table, 14 named columns and 22,575 rows
in September. Rows identify series, period, value, status, units, magnitude, subject, group,
adjustment and industry. Monthly ECTM and quarterly ECTQ are separate official series. Annual
ECTA, population-based ratios and card proportions are outside this feature's scope.

Secondary: embedded chart CSVs cross-check the retail levels (dollars) and industry movements
(percent). The charts alone cannot supply a complete historical/quarterly bundle, so loss or
corruption of the primary file fails closed and retains last-known-good data. Narrative rounded
headlines are reconciliation benchmarks in fixture tests, never production constants.

The Excel workbook was downloaded and inspected: Contents and Tables 1–8; actual, adjusted,
trend, monthly and quarterly tables. Table notes confirm nominal GST-inclusive values, independently
adjusted aggregates and percentage changes calculated from unrounded values. Its presentation
layout adds no coverage needed here, so there is no Excel runtime parser or dependency.

The adapter retains 96 monthly/quarterly spending, transaction-count, mean-value and published
aggregate-change series. September actual retail history has 321 months (January 2000–September
2026); adjusted/trend retail has 288 months (October 2002–September 2026). Adjusted quarterly
retail has 96 quarters (December 2002–September 2026). Missing confidential early observations
are omitted, never replaced by zero. Counts are individual transactions, values NZD millions,
and means NZD. The CSV's revised `R` status maps conservatively to `unknown`, with an explicit
methodology caveat; `F` and `P` map to final/provisional. Raw artifacts retain original statuses.

ZIP extraction stays in memory: 16 MiB compressed, 32 MiB total uncompressed, at most 8 members,
one CSV, maximum 250:1 compression ratio, 150,000 rows; unsafe paths/encrypted members are rejected.
Schema, official identities, units, magnitude, adjustment, industry, dates, duplicates, finite and
nonnegative levels, continuity and retained historical coverage are checked before commit.

## September reconciliation

Differences below use the CSV's published levels, rounded to NZD 0.1 million. Stats NZ calculates
headline changes from unrounded data. The tests allow 0.065 percentage points for published
one-decimal rates, 0.55 million for whole-million movements (including rounding at both endpoints),
and 0.051 million for the embedded chart's unrounded dollar levels. These tolerances do not
impose an exact identity on independently adjusted components.

| Measure | Calculated from CSV | Published benchmark |
|---|---:|---:|
| Retail monthly, adjusted | −0.4282%; −$30.0m | −0.4%; −$30m |
| Core retail monthly, adjusted | −0.6534%; −$41.2m | −0.7%; −$41m |
| Total ECT monthly, adjusted | −0.5291%; −$51.5m | −0.5%; −$51m |
| Hospitality / apparel / durables | −2.3% / −2.0% / −0.4% (one decimal) | Same |
| Consumables / vehicles excl. fuel / fuel | +0.3% / +0.6% / +2.9% (one decimal) | Same |
| Actual total | $9.1906b | Approximately $9.2b |
| Actual count | 166,814,173 | Approximately 167 million |
| Actual mean | $55.1 | Approximately $55 |
| Retail quarter, adjusted | +0.0669%; +$14.1m | +0.1%; +$14m |
| Core retail quarter, adjusted | +0.4186%; +$79.1m | +0.4%; +$79m |

Both August and September were ingested through the real pipeline into the local ignored
`data/nzstats.db`, preserving page and ZIP artifacts. The September retail adjusted vintage has
110 changed observations against August. A single September history file is one vintage;
no publication vintages were inferred from its historical rows.

ZIP SHA-256: September `a89b02ba61b127baf3894bb333961710e4b4d6486dfcdc012d18c0655aa970c2`;
August `ade397fbeffa1f01ccaafb98f7f2a91d537c829ccbd8aa4982e1eb56087ab88c`.
Captured pages/ZIPs/workbook live under `backend/tests/fixtures/ect_*`. Frontend fixture points
are real observations from September 2021 onward, generated from the two captured releases.

## Operation and limits

The existing adapter registry enables discovery, release-watch, catch-up, health and analysis.
The official month calendar currently lists October data for 12 November 2026, 10:45 NZDT;
this is observed calendar data, never a production constant. A running scheduler is required
to fetch future releases. Existing post-publication corrections still require explicit re-ingestion.

To load the latest complete history only:

```sh
nzstats backfill --series-slug electronic-card-transactions --since 2026-09 --until 2026-09
```

Start from `2026-08` instead to capture the verified previous publication and genuine revisions.
The default backfill retains its existing behaviour across all registered adapters.

Schema migration 003 snapshots definitions per vintage, including source, units, frequency,
adjustment and methodology identity. Upgrade seeds pre-existing vintages with metadata available
at upgrade time; previously overwritten historical definitions cannot be recovered. Subsequent
metadata changes and older backfills cannot relabel retained vintages. Incompatible revision
definitions are withheld. Back up the SQLite database before rollout; migrations run on startup.

ECT represents participating providers' electronic transactions, not all retail sales, real
consumption or all household spending. Provider coverage and classifications can change.
Source-layout changes intentionally fail closed. No merge, deployment or public hosting is part
of this feature. Independent statistical and code review is recommended before rollout.
