# CPI release-day runbook

For the "Consumers price index: September 2026 quarter" release (22 October 2026, 10:45 NZDT) and every later
quarter. Nothing here needs a code change: the calendar, the per-minute release watch and the daily catch-up already
cover the `consumers-price-index` series. Never hand-edit the database and never lower the 10 second request delay.

## What should happen on its own

1. The daily 06:00 NZ calendar refresh has already stored the scheduled release (`status = scheduled`).
2. From 10:45 NZDT the watch polls at +0, 1, 2, 5, 10, 15, 30, 60, 120 and 180 minutes. A 404 means "not published yet"
   and costs nothing; the release stays `scheduled`.
3. When the page and files exist: page, three CSVs and the optional workbook are fetched sequentially (10 s apart),
   parsed, validated, and committed in one transaction. The release becomes `published`, the previous quarter's
   vintage is kept, and `/inflation`, Overview, Latest Releases and the release analysis switch to the new quarter.
4. The 07:30 NZ catch-up covers a missed window (for example if the process was down).

## How to confirm it worked

- Data health shows `release:consumers-price-index` as OK with a recent last success, and the newest ingestion run for
  `consumers-price-index:september 2026 quarter` has outcome `ingested`. Warnings (for example "official underlying
  measures unavailable") are listed in the run detail and do not mean failure.
- `/inflation` shows "Latest reference quarter: September 2026". Check the headline against the page text on the
  official release (`https://www.stats.govt.nz/information-releases/consumers-price-index-september-2026-quarter/`).
- Until a real ingestion has happened, the dashboard shows the June 2026 quarter. That is correct, not stale data.

## If it did not ingest

| Data health / run shows | Meaning | Action |
|---|---|---|
| `not_available` after the polling window | Stats NZ files not up yet (delayed) | Nothing; the daily catch-up retries. Check the official calendar. |
| `blocked` | The site challenged us; a 30 minute cooldown applies | Wait. Do not retry by hand in a loop. |
| `layout_changed` | A required file, header, series or chart changed shape | Last-known-good (June) stays on screen. Save the page and files (raw artifacts are kept under the data directory), compare with `docs/data-sources/cpi.md`, add the new real file as a fixture with a failing test, then change the adapter. |
| `validation_failed` | The data failed a check (base quarter, chart percentage reconciliation, contribution sum, ordering, missing core series) | Read the message in the run detail. Do not widen a tolerance without measuring the real file and recording it in `docs/data-sources/cpi.md`. |

Manual run (one paced attempt, safe to repeat):

```sh
cd backend && . .venv/bin/activate
nzstats discover
nzstats ingest --release-key "consumers-price-index:september 2026 quarter"
# or, for a stored published release:
nzstats backfill --series-slug consumers-price-index --since 2026-09 --until 2026-09
nzstats health
```

## Fallback behaviour to expect

- A failed update never overwrites data. Last-known-good observations, vintages and the previous analysis stay served.
- The failure is shown in Data health and in the run list; the old figures are never presented as new.
- Optional items (selected Level-2/3 series, seasonally adjusted Level-1 groups, the workbook's trimmed means and
  percentiles) are dropped with a warning if they change; headline CPI still ingests. A *core* series change (all
  groups, tradables, non-tradables, the 11 groups, SA all groups) fails the whole bundle.
- Group contributions that are missing from the page produce a warning and a "not published" message on the page;
  contributions that are present but wrong fail the bundle.

## What happened on 22 October 2026

The September release was discovered and polled correctly, but every ingestion failed with `layout_changed` ("CPI percentage chart
rows are missing or renamed") because the quarterly chart's first header cell changed from `Quarter` to `Category`. That is a code
defect, not a scheduling or deployment problem; it is fixed on `fix/cpi-september-chart-header` (see `docs/progress.md`). Until that
fix runs, a database that never ingested an earlier CPI quarter shows "CPI data has not been ingested yet" at `/api/cpi`; the June
figures are only "last known good" where June was ingested before.

Recovery once the fixed code is running (one paced attempt; the release is already `published`, so the daily catch-up also retries it):

```sh
cp data/nzstats.db data/nzstats.db.bak-$(date +%Y%m%d)   # or: nzstats backup, with the server running
cd backend && . .venv/bin/activate
nzstats ingest --release-key "consumers-price-index:september 2026 quarter"
nzstats health
```

Restart `nzstats serve` after pulling the fix; a running process keeps the old adapter in memory.

## Not yet proven

The offline rehearsal (`backend/tests/scheduler/test_cpi_release_day.py`) replays the real June release; the September regression
tests (`backend/tests/pipeline/test_cpi_september_2026.py`) replay the captured September files. Neither is a live ingestion of
the September quarter into the running database. After the recovery above, check Data health and `/inflation`, and record the
outcome in `docs/progress.md`.
