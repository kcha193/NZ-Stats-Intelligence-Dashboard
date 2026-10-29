# Phase 4D statistical reconciliation

Assessed 29 October 2026 (Pacific/Auckland). This is an offline independent check of previously authorised Stats NZ
captures. It made no upstream requests and changed no production observations. Release readiness and the production
backfill inventory are separate deliverables.

## Evidence and independence

The calculations below use Python standard-library CSV/ZIP readers and `Decimal` arithmetic directly on official
rows. They do not call the application's adapter, growth, identity, rounding or insight helpers. The portable
regression record is `backend/tests/test_phase4d_reconciliation.py` (20 cases).

The cached full GDP CSVs and labour ZIPs in the ignored `data/capture-4c/` directory were also streamed to compare
every retained row, including metadata and blanks, with the committed excerpts. The comparisons were exact:

| Release | GDP excerpt | HLFS excerpt | LCI excerpt |
|---|---:|---:|---:|
| March 2026 | 12 series, 1,855 rows | 8 series, 1,216 rows | 3 series, 397 rows |
| June 2026 | 12 series, 1,867 rows | 8 series, 1,224 rows | 3 series, 400 rows |

These excerpts preserve the **complete available histories of the selected series**, rather than only the latest
quarter. This does not validate omitted industries, demographic groups, earnings or other unselected series.

SHA-256 of the full official captures used in that comparison:

| Cached source file | SHA-256 |
|---|---|
| `gross-domestic-product-march-2026-quarter.csv` | `1576eb1443c1fad22ee260a0f5ec690b26d84aa2c673533f3b22c0a5c5f66fda` |
| `gross-domestic-product-june-2026-quarter.csv` | `4e88dc85c4406665bcbbb6f3c8e851f38a968a76550772b85cedac4f7d95eab3` |
| `labour-market-statistics-march-2026-quarter-revised.zip` | `53d702b134b416b81735eb2a0c5a1253a7fd1b6b2a2e3bb021c557c22b1e545e` |
| `labour-market-statistics-june-2026-quarter.zip` | `f7f867ab76b6bae2177ba1c3960f9a4ca7f7fb01a8325b5cdd7ee37b5cecab26` |

## GDP definitions and price basis

The CSV distinguishes production/expenditure, chain-volume/current-price, seasonally adjusted/actual and
total/per-person series. The published percentage rows are used as observations; independent calculations check
their consistency with rounded levels, rather than replace published percentages.

For quarter `t`, the checks are:

- Quarterly growth: `100 × (SA[t] / SA[t−1 quarter] − 1)`.
- Annual change of the quarter: `100 × (SA[t] / SA[t−4 quarters] − 1)`.
- Annual average growth: `100 × (sum(actual[t…t−3 quarters]) / sum(actual[t−4…t−7 quarters]) − 1)`.

The annual average calculation requires all eight quarters. It is neither the quarterly rate multiplied by four nor
an average of four growth percentages. Independent parsing of the captured GDP page charts confirms that all 15
quarters of each page's “Annual growth” series equal the **annual average** CSV series; its 15 quarterly-chart
figures also equal their matching CSV series (60 page/CSV comparisons across the two releases).

| Release | Measure | Numerator / denominator | Independently calculated % | Published % |
|---|---|---|---:|---:|
| March 2026 | Production quarterly, SA | 71,471 / 70,904 | 0.799673 | 0.8 |
| March 2026 | Production annual change, SA | 71,471 / 70,435 | 1.470860 | 1.5 |
| March 2026 | Production annual average, actual | 282,969 / 280,703 | 0.807259 | 0.8 |
| March 2026 | Expenditure quarterly, SA | 73,699 / 72,963 | 1.008730 | 1.0 |
| June 2026 | Production quarterly, SA | 71,805 / 71,628 | 0.247110 | 0.2 |
| June 2026 | Production annual change, SA | 71,805 / 70,019 | 2.550736 | 2.6 |
| June 2026 | Production annual average, actual | 285,049 / 280,164 | 1.743622 | 1.7 |
| June 2026 | Expenditure quarterly, SA | 74,135 / 73,869 | 0.360097 | 0.4 |

The June rolling annual production level `SNEA.SG00RAC00B01J` in the full official CSV independently equals the
four-quarter actual sum, 285,049. This rolling annual series is not one of the stored dashboard series.

Across all 1,226 overlapping growth/level comparisons, the largest absolute difference is **0.053341 pp**
(expenditure quarterly change, March 1989). Counts for March/June captures are 155/156 production quarterly,
152/153 annual change, 149/150 annual average and 155/156 expenditure quarterly. The existing **0.06 pp**
tolerance is supported by the captured evidence. No threshold was loosened.

**Reference-year correction:** the earlier implementation labelled chain-volume levels “2009/10 prices”. Neither
the captured CSV metadata nor captured release pages supplies that reference year. Phase 4D removes the unsupported
year from production definitions, units, caveats and the page header, preserving `chain_volume` versus
`current_prices`. Units are now `NZD million (chain volume)`. No alternative year is guessed. Exact reference-year
verification needs an approved primary-source metadata/worksheet capture before a year can be shown. A common scale
factor does not change the growth ratios checked here. The current-price series is never used to calculate real
growth. Per-capita values remain dollars per person; inconsistent official magnitude fields are not used as a scale.

## Labour identities, categories and reference periods

HLFS is seasonally adjusted, quarterly, total both sexes, age 15 and over. Levels are thousands of people. The LCI is
the all-sector, all-industry, all salary and wage rates index (including overtime), **unadjusted**, with June 2009
quarter = 1000. Its source metadata explicitly states that base; it is distinct from the unsubstantiated GDP year.
HLFS (`labour:hlfs`) and LCI (`labour:lci`) are separate categories. QES average earnings and filled jobs are not
stored. The LCI measures wage rates for work of the same quality, rather than workforce-composition-driven earnings.

| June 2026 check | Independent calculation | Published |
|---|---|---:|
| Labour force identity | 2,905 employed + 171 unemployed = 3,076 | 3,076 thousand |
| Unemployment | 100 × 171 / 3,076 = 5.559168% | 5.6% |
| Employment | 100 × 2,905 / 4,353 = 66.735585% | 66.7% |
| Participation | 100 × 3,076 / 4,353 = 70.663910% | 70.7% |
| LCI quarterly change | 100 × (1459 / 1450 − 1) = 0.620690% | 0.6% |
| LCI annual change | 100 × (1459 / 1431 − 1) = 1.956674% | 2.0% |

All 323 quarter-level labour-force identities (161 March-capture quarters and 162 June-capture quarters) and all 969
corresponding rate/level checks pass. The maximum force discrepancy is **1 thousand**, within the existing 1.5
tolerance. The maximum rate discrepancy is **0.070642 pp** (employment, June 2003), within 0.08 pp. March 2026
employment illustrates why exact rounding from rounded levels is inappropriate: 100 × 2,889 / 4,335 = 66.643599%,
whereas the official rate is 66.7%; official rates use unrounded underlying levels.

All 528 overlapping LCI growth/index comparisons pass (March/June quarterly counts 133/134; annual counts 130/131).
The maximum difference is **0.049955 pp**, within 0.06 pp. Underutilisation is not independently reconstructed:
the stored headline set lacks all extended-labour-force components required for its identity. Its published value
and pinned definition are checked, without inventing components.

## Dates, revisions and historical provenance

Publication times come from `PageDate` in the captured official pages. These four dates fall in NZST (UTC+12).

| Reference quarter and release | Published Pacific/Auckland | Stored UTC equivalent |
|---|---|---|
| [GDP March 2026](https://www.stats.govt.nz/information-releases/gross-domestic-product-march-2026-quarter/) | 18 June 2026, 10:45 | 17 June 2026, 22:45Z |
| [GDP June 2026](https://www.stats.govt.nz/information-releases/gross-domestic-product-june-2026-quarter/) | 17 September 2026, 10:45 | 16 September 2026, 22:45Z |
| [Labour March 2026](https://www.stats.govt.nz/information-releases/labour-market-statistics-march-2026-quarter/) | 6 May 2026, 10:45 | 5 May 2026, 22:45Z |
| [Labour June 2026](https://www.stats.govt.nz/information-releases/labour-market-statistics-june-2026-quarter/) | 5 August 2026, 10:45 | 4 August 2026, 22:45Z |

The official captured March GDP headline corroborates 0.8% for March quarterly growth; the June CSV records 0.9%
for that same quarter. The March labour page headline independently corroborates 5.3% unemployment; June page and
CSV both record 5.4% for March, alongside 5.6% for June. These are different observations of the same quarter across
release histories and must remain distinct.

**Important provenance limit:** March labour's captured download is a `-revised.zip`; its retained members are dated
28 July, after the 6 May publication. The captured page's 5 August error note names `HLFQ.SVE` and `LCIQ.SG33Z9`,
neither of which is pinned by this adapter. That supports the scope of the documented correction and the original
headline, but it does not prove possession of the original complete ZIP. More generally, an October capture of an
old release is not proof that every byte/value was present on the original publication day. A release title, quarter,
old publication timestamp, or low insertion ID alone cannot establish first publication.

Consequently the backfill must preserve “earliest stored” versus proven first-publication status. Page-corroborated
headlines above are source evidence, not a blanket attestation of an entire historical vintage. The Phase 4D
provenance guard deliberately takes the conservative path: late captures and corrected/revised source artifacts do
not become first-publication baselines merely because their quarter matches the release's reference quarter.
Reactivating an old bundle must also retain the earliest inserted observation rather than rewrite history.

## Forecast evaluation

GDP matching distinguishes quarterly real SA growth, real annual average growth from actual values, and annual
change of a single quarter. Annual change requires an explicit SA label. Nominal growth, unsupported GDP parts,
unsupported adjustment bases and ambiguous horizons remain unmatched. Unemployment matching uses the HLFS headline
quarterly SA total rate; period averages, end-of-period values, monthly horizons and demographic parts are rejected.
CPI matching remains a separate path.

The look-ahead check excludes a forecast dated **on or after** the original official release day in Auckland.
Date-only forecasts on release day are therefore conservatively excluded. The release registry's own-quarter date
is used where available, so ingesting a newer release first does not permit forecasts published after the original
outcome. Later revised actuals are explicitly latest-vintage comparisons, not contemporaneously available outcomes
or predictor inputs. Unverified first-publication baselines must be excluded from first-error summaries/rankings;
late backfill must not manufacture a valid first-release score.

OCR remains unavailable. Its synthetic domain-model tests provide no official rate, ingestion authority or forecast
outcome. No RBNZ request or research-source permission change was made.

## Verification and release implication

```sh
backend/.venv/bin/python -m pytest backend/tests/test_phase4d_reconciliation.py
backend/.venv/bin/python -m pytest backend/tests/insights/test_gdp_dashboard.py backend/tests/pipeline/test_gdp_ingest.py backend/tests/adapters/test_gdp.py
cd frontend && npm test -- src/pages/MacroDashboards.test.tsx
```

The 20 independent checks, targeted GDP backend suites and seven dashboard frontend cases passed locally. The new
backend and frontend regression assertions were observed failing on the unsubstantiated GDP year before its removal;
they then passed. Ruff lint/format checks for the changed Python files and `git diff --check` passed. The test run
reported the existing Starlette/httpx deprecation warning. Final integrated-suite/CI/browser evidence is recorded in
the Phase 4D release report, not inferred from this targeted run.

Arithmetic and selected-series identity checks support integration. **Production data activation remains conditional**
on authorised, restorable-backup-protected backfill and per-release reconciliation. Original historical vintages
that are absent remain absent; neither later vintages nor corroborating headlines reconstruct an entire original
dataset. Production first-release forecast scoring remains unavailable where original-vintage evidence is absent.
