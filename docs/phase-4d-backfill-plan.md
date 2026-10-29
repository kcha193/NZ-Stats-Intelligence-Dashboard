# Phase 4D official-data backfill dry run

Assessed **29 October 2026 (Pacific/Auckland)**. **Execution status: NOT AUTHORISED, NOT RUN.**
No Stats NZ or RBNZ request was made for this assessment. The evidence is the read-only production database,
previously captured official release pages/files, and offline parsing. This plan does not authorise collection.

## Existing production state

The read-only SQLite assessment found schema **10**, not schema 7 described in older readiness reports.
It contains 181 release registrations, 427 series, 523 series-vintages, 52,309 observations and 20 raw-artifact
records. All research tables are empty. GDP and labour have **zero stored series/vintages**.

| Release | Registered? | Own release vintage? | Action proposed |
|---|---|---|---|
| CPI December 2025 | No | No | Discover and ingest its own release |
| CPI March 2026 | No | No | Discover and ingest its own release |
| CPI June 2026 | No | No | Discover and ingest its own release |
| CPI September 2026 | Yes, published | Yes: 74 series-vintages | Preserve; use as the latest comparison, do not re-fetch in this plan |
| GDP March 2026 | No | No | Discover and ingest its own release |
| GDP June 2026 | Yes, published | No | Confirm metadata and ingest |
| Labour March 2026, HLFS and LCI | No | No | Discover and ingest; revised-source restriction below |
| Labour June 2026, HLFS and LCI | No | No | Discover and ingest |
| Labour September 2026 | Yes, scheduled for 4 November 2026 10:45 NZDT | No | Future release; excluded |
| GDP September 2026 | Yes, scheduled for 17 December 2026 10:45 NZDT | No | Future release; excluded |

Earlier GDP/labour releases are also absent. The bounded activation batch covers the March and June 2026
releases already represented by approved official captures. It does **not** claim a complete historical release
archive. An earlier quarter's observation in a later release is historical coverage, not that quarter's original
release vintage. Extending the batch before March 2026 requires a separately enumerated plan and approval.

## Exact proposed batch and dates

The dates below are read from each captured page's `PublicationDate`; none is a schedule inference.
Reference periods are quarter-end months. Local time is always **10:45**.

| Order | Official release page | Publication in Auckland | Publication UTC | Minimum release requests |
|---|---|---|---|---|
| 1 | [CPI December 2025](https://www.stats.govt.nz/information-releases/consumers-price-index-december-2025-quarter/) | 23 January 2026 NZDT | 22 January 2026 21:45Z | Page + 3 required CSVs + listed optional workbook = 5 |
| 2 | [CPI March 2026](https://www.stats.govt.nz/information-releases/consumers-price-index-march-2026-quarter/) | 21 April 2026 NZST | 20 April 2026 22:45Z | 5 |
| 3 | [Labour March 2026](https://www.stats.govt.nz/information-releases/labour-market-statistics-march-2026-quarter/) | 6 May 2026 NZST | 5 May 2026 22:45Z | Page + one ZIP = 2 |
| 4 | [GDP March 2026](https://www.stats.govt.nz/information-releases/gross-domestic-product-march-2026-quarter/) | 18 June 2026 NZST | 17 June 2026 22:45Z | Page + one CSV = 2 |
| 5 | [CPI June 2026](https://www.stats.govt.nz/information-releases/consumers-price-index-june-2026-quarter/) | 21 July 2026 NZST | 20 July 2026 22:45Z | 5 |
| 6 | [Labour June 2026](https://www.stats.govt.nz/information-releases/labour-market-statistics-june-2026-quarter/) | 5 August 2026 NZST | 4 August 2026 22:45Z | 2 |
| 7 | [GDP June 2026](https://www.stats.govt.nz/information-releases/gross-domestic-product-june-2026-quarter/) | 17 September 2026 NZST | 16 September 2026 22:45Z | 2 |

HLFS and LCI share a labour-release ZIP. They are not fetched or counted as two releases; the parser separates
`labour:hlfs` and `labour:lci`. It does not activate the QES files in the archive.

## Request budget and exact source URLs

**Preferred bounded sequence: 30 logical GETs**, assuming the captured download listings still apply:

- Seven calendar-month GETs, one per publication month: `https://www.stats.govt.nz/api/v1/releaseCalendarMonth/2026-01`,
  `…/2026-04`, `…/2026-05`, `…/2026-06`, `…/2026-07`, `…/2026-08`, `…/2026-09`.
- Seven page GETs from the table above.
- Four GDP/labour file GETs and twelve CPI file GETs (nine required CSVs, three optional workbooks).

Use the existing `fetch_release_month` parser, shared `Runtime.fetcher`, and transactional `repo.upsert_release`
to register **only the seven target references**, after checking title, reference period, published status and
publication date. The known June GDP registration is checked against September's calendar rather than silently
trusted. Stop if a target is missing or differs. Do not crawl the ICS feed or unrelated calendar months.
The reviewable operator command below uses those existing functions; it has not run.

The normal `backfill` CLI scans every month from `since` through the current Auckland month, even if `until`
is earlier, then ingests all matching releases. Consequently it is **not** the 30-request plan. Running seven
single-release bounded backfills instead would make 50 calendar GETs plus the 23 page/file GETs: **73 logical
GETs** in October 2026. Prefer targeted registration followed by one explicit `ingest --release-key` at a time.

Logical GET counts exclude conditional retries and redirects: `Fetcher` allows three retries after the first
attempt and at most five redirect hops. Every attempt/hop is paced. Stop and review unexpected redirects,
changed listings or extra requests rather than treating 30 as a guaranteed network-attempt count.
All requests must use the existing descriptive User-Agent, shared `.request-pace` lock/journal, **at least 10 seconds**
between requests, source block detection, 30-minute block cooldown and `Retry-After` handling. Never reset the
pacing journal, lower the interval, parallelise downloads or use unpaced browser/search requests as a fallback.

The captured page selects these macro URLs:

```text
https://www.stats.govt.nz/assets/Uploads/Gross-domestic-product/Gross-domestic-product-March-2026-quarter/Download-data/gross-domestic-product-march-2026-quarter.csv
https://www.stats.govt.nz/assets/Uploads/Gross-domestic-product/Gross-domestic-product-June-2026-quarter/Download-data/gross-domestic-product-june-2026-quarter.csv
https://www.stats.govt.nz/assets/Uploads/Labour-market-statistics/Labour-market-statistics-March-2026-quarter/Download-data/labour-market-statistics-march-2026-quarter-revised.zip
https://www.stats.govt.nz/assets/Uploads/Labour-market-statistics/Labour-market-statistics-June-2026-quarter/Download-data/labour-market-statistics-june-2026-quarter.zip
```

For CPI, these exact directory/filename pairs define the twelve selected URLs. Concatenate the directory and
each filename; do not substitute a guessed URL if the live page no longer lists it.

| Directory | Required filenames | Optional filename |
|---|---|---|
| `https://www.stats.govt.nz/assets/Uploads/Consumers-price-index/Consumers-price-index-December-2025-quarter/Download-data/` | `consumers-price-index-december-2025-quarter-index-numbers.csv`; `consumers-price-index-december-2025-quarter-seasonally-adjusted.csv`; `consumers-price-index-december-2025-quarter-tradeables-and-non-tradeables.csv` | `consumers-price-index-december-2025-quarter-corrected.xlsx` |
| `https://www.stats.govt.nz/assets/Uploads/Consumers-price-index/Consumers-price-index-March-2026-quarter/Download-data/` | `consumers-price-index-march-2026-quarter-index-numbers.csv`; `consumers-price-index-march-2026-quarter-seasonally-adjusted.csv`; `consumers-price-index-march-2026-quarter-tradeables-and-non-tradeables.csv` | `consumers-price-index-march-2026-quarter.xlsx` |
| `https://www.stats.govt.nz/assets/Uploads/Consumers-price-index/Consumers-price-index-June-2026-quarter/Download-data/` | `consumers-price-index-june-2026-quarter-index-numbers.csv`; `consumers-price-index-june-2026-quarter-seasonally-adjusted.csv`; `consumers-price-index-june-2026-quarter-tradeables-and-non-tradeables.csv` | `consumers-price-index-june-2026-quarter.xlsx` |

## Expected changes and first-publication restrictions

Offline parsing of the captured pinned-series excerpts gives this comparison baseline. These counts are
**not** a promise that current downloads are byte-identical. Changed metadata/structure/statistics must fail closed.

| Release | New series-vintages in offline baseline | Observations in offline baseline |
|---|---:|---:|
| CPI December 2025, required files only | 63 | 5,497 |
| CPI March 2026, required files only | 63 | 5,531 |
| CPI June 2026, including captured workbook | 74 | 5,763 |
| Labour March 2026 | 11 | 1,613 |
| GDP March 2026 | 12 | 1,845 |
| Labour June 2026 | 11 | 1,624 |
| GDP June 2026 | 12 | 1,857 |
| Baseline total | 246 | 23,730 |

Expected new registrations: six; June GDP already exists. Expected new series keys: 23 (12 GDP + eight HLFS +
three LCI), giving 450 keys if all existing definitions remain compatible. CPI keys already exist. With the
baseline only, totals would be 187 release registrations, 769 series-vintages and 76,039 observations.
December/March CPI optional workbooks were not captured as fixtures; their supported underlying measures may
add up to eleven further series-vintages per release, with observation counts to be measured, not invented.
Page/file artifacts are content-addressed; reused hashes may reduce new raw records. Calendar responses are
parsed into registrations rather than stored as raw-artifact rows by the existing discovery implementation.

The June release contains historical observations, but it cannot recover the March release's own first value.
Preserve all old vintage rows and values, never overwrite the September CPI bundle, and keep publication time
separate from the present acquisition/capture time.

**Provenance restriction:** the March labour archive is explicitly `-revised.zip`, and its captured members are
dated 28 July 2026. The page also records a later correction. The December CPI workbook is explicitly corrected.
These are genuine official data, but acquisition today does not establish an untouched first-publication bundle.
Use earliest-stored terminology and exclude uncertain first-published scoring unless original per-measure evidence
has been independently established. Do not backdate acquisition or silently substitute later revised figures for
initial values. If preservation of genuine original bundles is mandatory, this part remains blocked until an
approved official archive/source is identified; do not guess an unsuffixed filename or use a third-party archive.

## Execution runbook after a separate owner approval

1. Record the approved seven-release scope, request budget, chosen integrated commit, operator and maintenance
   window. Pause competing ingestion/scheduler and publisher processes; retain the shared pacing state.
2. Take a **fresh** SQLite online backup from a `mode=ro` source connection, plus the entire raw-artifact tree,
   current source configuration and content hash manifest into private backup storage. Do not copy only the live
   main `.db` file: uncheckpointed WAL changes are part of its state. Do not put backups in a public snapshot.
3. Restore that backup into an isolated directory. Run `verify-backup` with `--live` and `--raw-dir`, independently
   check every raw SHA-256/size, SQLite integrity and foreign keys, migration objects and row counts. Confirm the
   current schema before permitting any upgrade. A failed or incomplete restore is a stop condition.
4. Perform the seven bounded calendar checks and register only the seven target releases. Reconcile exact dates
   and identities against the captured pages above. Stop on disagreement.
5. Process in the table's chronological order, **one release at a time**, using the existing CLI:
   `scripts/run.sh ingest --release-key 'consumers-price-index:december 2025 quarter'`, then equivalent explicit
   keys for March CPI, March labour, March GDP, June CPI, June labour and June GDP. Inspect the exit code and report
   before starting the next command. Do not use `--due` or an unattended all-category backfill.
6. For every release compare page/file identity, capture hash, reference/publication time, selected series, price
   base/adjustment/unit, row coverage, statistical identities and validation warnings with the independent baseline.
   Check GDP quarterly/annual/annual-average distinctions, HLFS/LCI separation, raw and API values. Structural or
   statistical mismatch rejects the bundle and leaves last-known-good observations active. Review warnings before
   continuing; an optional workbook failure remains an explicit limitation, never fabricated data.
7. Record before/after raw hashes, counts, vintage IDs, capture and publication times, active bundle, first/latest
   values and revisions for each release. Recheck all older vintage values and the latest September CPI values.
   Run `research cpi-vintages`, `research cpi-reconcile`, macro reconciliation, forecast look-ahead exclusions,
   dashboard/API equality and a new production snapshot validation. Confirm no research/OCR source activation.
8. Produce and review the reconciliation report before resuming ingestion or proposing deployment. A failed update
   is not a reason to delete old data or weaken validation. If recovery is required, restore the verified matching
   database **and raw tree** with writers stopped; verify again before restarting. Never reset the pacing journal.

## Bounded registration command for the authorised maintenance window

This command is **prepared only, not executed**. It makes the seven calendar GETs and registers only the seven
checked releases. It does not ingest any release. Run from the repository root with the approved integrated
environment and an explicitly configured `NZSTATS_DATA_DIR`, after steps 1–3 above. A different calendar date,
reference period, page URL or status stops registration. Only after all seven checks pass is the registration
transaction committed. Then use the seven separate `ingest --release-key` commands in step 5, reviewing each result.

```python
from nzstats.clock import to_utc_iso, utc_now
from nzstats.config import load_settings
from nzstats.domain import ReleaseStatus
from nzstats.runtime import build_runtime
from nzstats.sources.calendar import fetch_release_month
from nzstats.store import repo
from nzstats.store.db import transaction

# Publication month, exact release key, reference quarter, official publication UTC.
targets = [
    ("2026-01", "consumers-price-index:december 2025 quarter", "2025-12", "2026-01-22T21:45:00Z"),
    ("2026-04", "consumers-price-index:march 2026 quarter", "2026-03", "2026-04-20T22:45:00Z"),
    ("2026-05", "labour-market-statistics:march 2026 quarter", "2026-03", "2026-05-05T22:45:00Z"),
    ("2026-06", "gross-domestic-product:march 2026 quarter", "2026-03", "2026-06-17T22:45:00Z"),
    ("2026-07", "consumers-price-index:june 2026 quarter", "2026-06", "2026-07-20T22:45:00Z"),
    ("2026-08", "labour-market-statistics:june 2026 quarter", "2026-06", "2026-08-04T22:45:00Z"),
    ("2026-09", "gross-domestic-product:june 2026 quarter", "2026-06", "2026-09-16T22:45:00Z"),
]
settings = load_settings()
rt = build_runtime(settings)
checked = []
try:
    for month, key, quarter, published in targets:
        refs = fetch_release_month(rt.fetcher, settings.base_url, settings.release_month_path, month)
        matches = [ref for ref in refs if ref.release_key == key]
        if len(matches) != 1:
            raise RuntimeError(f"Expected exactly one approved release: {key}")
        ref = matches[0]
        slug, period = key.split(":", 1)
        page = f"https://www.stats.govt.nz/information-releases/{slug}-{period.replace(' ', '-')}/"
        if (ref.reference_period != quarter or to_utc_iso(ref.published_at) != published
                or ref.page_url != page
                or ref.status not in (ReleaseStatus.PUBLISHED, ReleaseStatus.CORRECTED)):
            raise RuntimeError(f"Official metadata differs from approved plan: {key}")
        checked.append(ref)
    with transaction(rt.conn):
        for ref in checked:
            repo.upsert_release(rt.conn, ref, utc_now())
finally:
    rt.conn.close()
```

The excerpt is syntax-checked offline; its imports/signatures and expected metadata were checked against the current
repository and retained pages. No live calendar request or production registration was made to test it. Live source
agreement is deliberately a future stop/go check, not assumed from offline evidence.

## Required owner decisions

- Authorise this exact official-data collection batch and its maintenance/backup procedure; it has not run.
- Decide whether revised/corrected historical releases may be retained as earliest-stored observations with
  uncertain first-publication evaluation withheld, or require an approved original official archive first.
- Any expansion beyond these seven releases needs its own enumerated source/request plan.
- Merge, Netlify upload and research/RBNZ permissions remain separate approvals. None follows from backfill approval.
