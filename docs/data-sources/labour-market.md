# Labour market statistics: source verification

Captured 28 October 2026 under owner authorisation, through the application's paced fetcher (10 s between requests,
sequential, project User-Agent). Only official Stats NZ sources were used. Design: [Phase 4C spec](../superpowers/specs/2026-10-28-phase-4c-macro-data-design.md).

| Release | Page fixture | Zip | Published (Auckland) |
|---|---|---|---|
| [March 2026 quarter](https://www.stats.govt.nz/information-releases/labour-market-statistics-march-2026-quarter/) | `labour_2026-03_page.html` | `…-march-2026-quarter-revised.zip` (republished; members dated 28 July 2026) | 2026-05-06 10:45 NZST |
| [June 2026 quarter](https://www.stats.govt.nz/information-releases/labour-market-statistics-june-2026-quarter/) | `labour_2026-06_page.html` | `…-june-2026-quarter.zip` | 2026-08-05 10:45 NZST |

Fixtures `labour_<YYYY-MM>.zip` keep the original member names and timestamps; the HLFS and LCI members keep every row
of the eleven stored series with the original header, the QES and combined members only their header row
(`scripts/capture_macro_fixtures.py`). Nothing is edited.

## The zip

18.6 MB packed, about 756 MB unpacked: `hlfs-…csv` (423 MB, 1,278,057 rows, 58 columns), `lci-…csv` (6.7 MB, 13
columns), `qes-…csv` (40 MB) and `lms-…-tables.csv` (286 MB, HLFS+LCI+QES combined). Member names differ by release
(`hlfs-jun26qtr-csv.csv`, `hlfs-mar26qtr-tables.csv`), and the March zip's folder is "labour market statistics march
2026 quarter updated". The adapter selects members by pattern, requires exactly one HLFS and one LCI member, and streams
them without extracting: caps are 64 MB archive, 1 GB declared member size, 8 members, 2.5 million rows per member. The
release page also lists HLFS, LCI and QES workbooks; they are not read.

The HLFS CSV has one column per classification (age, sex, region, ethnicity and so on), `NA` where it does not apply.
Each stored series is pinned by every field that is not empty or `NA`, so a classification newly set on a stored series
fails ingestion while unrelated new columns do not. The column is spelt `MAGNTUDE` in both HLFS and LCI files.
`STATUS` mixes `FINAL` and `REVISED` (stored as `final` and `unknown`).

## Stored series

| Key | Reference | June 2026 |
|---|---|---|
| `hlfs.rate.unemployment.sa` | `HLFQ.S1F3S` | 5.6% |
| `hlfs.rate.employment.sa` | `HLFQ.S1H3S` | 66.7% |
| `hlfs.rate.participation.sa` | `HLFQ.S1E3S` | 70.7% |
| `hlfs.rate.underutilisation.sa` | `HLFQ.SXJ3UZS` | 13.8% (from March 2004) |
| `hlfs.level.employed.sa` | `HLFQ.S1A3S` | 2,905 thousand |
| `hlfs.level.unemployed.sa` | `HLFQ.S1B3S` | 171 thousand |
| `hlfs.level.labour_force.sa` | `HLFQ.S1Z3S` | 3,076 thousand |
| `hlfs.level.working_age_population.sa` | `HLFQ.S1D3S` | 4,353 thousand |
| `lci.all_wages.index` | `LCIQ.SG53Z9` | 1459 (June 2009 quarter = 1000) |
| `lci.all_wages.pct_qoq` | `LCIQ.SG53Z9PC` | 0.6% |
| `lci.all_wages.pct_yoy` | `LCIQ.SG53Z9AC` | 2.0% (published as `2`) |

HLFS series are seasonally adjusted totals for both sexes, category `labour:hlfs`. The LCI is all salary and wage rates
including overtime, all sectors, all industries, not seasonally adjusted, category `labour:lci`. The LCI measures the
price of labour for the same work; it is not average earnings. The Quarterly Employment Survey (earnings, filled jobs)
is not stored, so no earnings figure can be mistaken for a wage rate.

## Reconciliation

Independent computation from the full official files (plain arithmetic, not the adapter's code):

| Quarter (release) | Check | Computed | Published |
|---|---|---|---|
| June 2026 | Labour force vs employed + unemployed | 2,905 + 171 = 3,076 | 3,076 |
| June 2026 | Unemployment rate | 171 / 3,076 = 5.559% | 5.6 |
| June 2026 | Employment rate | 2,905 / 4,353 = 66.736% | 66.7 |
| June 2026 | Participation rate | 3,076 / 4,353 = 70.664% | 70.7 |
| June 2026 | LCI quarterly | 1459 / 1450 = 0.621% | 0.6 |
| June 2026 | LCI annual | 1459 / 1431 = 1.957% | 2.0 |
| March 2026 | Unemployment rate | 163 / 3,052 = 5.341% | 5.3 |
| March 2026 | Employment rate | 2,889 / 4,335 = 66.644% | 66.7 |
| March 2026 | LCI quarterly | 1450 / 1443 = 0.485% | 0.5 |

The March employment rate shows why the checks use tolerances, not exact rounding: Stats NZ computes rates from
unrounded levels, so 66.644% from the rounded levels is published as 66.7. Over the whole history of both files: labour
force identity max 1.0 thousand (tolerance 1.5), rates max 0.0706 pp (tolerance 0.08), LCI changes max 0.0500 pp
(tolerance 0.06). The release page headline ("The unemployment rate was 5.6 percent in the June 2026 quarter, compared
with 5.4 percent in the March 2026 quarter") is parsed and must match the file; unfamiliar wording only warns.

Both full official archives parse and validate with no error, in about 3.2 s each.

## Revisions

The March 2026 release published an unemployment rate of 5.3%; the June 2026 release states 5.4% for March 2026, in its
headline and its file. Seasonal adjustment re-estimates history every quarter. The dashboard shows the latest figure and
says when the previous quarter was first published differently.

## Limitations

- Headline national totals only: no breakdown by sex, age, region or ethnicity, no trend series, no sampling errors
  (the file has them; the dashboard says only that small movements may not be significant).
- QES earnings and filled jobs are not stored.
- First-published rates exist only from the earliest stored release.
