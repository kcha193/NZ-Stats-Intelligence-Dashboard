# Phase 4G: automatic refresh when the dashboard opens

Native, local operation only. Netlify, public hosting, research crawling, restricted RBNZ sources and paid LLM calls are
out of scope and unchanged.

> **In one sentence:** open the dashboard and you see your stored data at once; the local server checks Stats NZ once
> for releases you are missing, downloads and validates anything new, and the charts update. Otherwise the header says
> the data is already current.

There is no scheduler, timer, launchd or cron job. Opening the page is what asks for a check.

## Start it

```sh
scripts/run.sh                 # or double-click "Start Dashboard.command"; serves http://localhost:8000
```

The first run installs dependencies and builds the UI. Stop it with Ctrl+C or by closing the Terminal window.
`nzstats serve` now binds `127.0.0.1` by default (it was `0.0.0.0`); the container passes `--host 0.0.0.0 --refresh scheduler`
explicitly, so its behaviour is unchanged.

| You want | Do |
|---|---|
| Normal use | `scripts/run.sh`, then open http://localhost:8000 |
| Check again now | Click the refresh status in the header, then **Check now** |
| Never contact Stats NZ (testing, inspecting, travelling) | `scripts/run.sh --offline` (the same as `--no-scheduler`) |
| See what the last check did | The header panel, **Data health**, or `scripts/run.sh status` |

## What happens when you open it

1. The page renders the stored, validated data immediately. Nothing waits for the network.
2. The page reads `GET /api/refresh/status` first. Only a loopback dashboard with explicit `on_open` mode sends
   `POST /api/refresh` (once per page load, including under React StrictMode). Scheduler/offline modes stay hidden;
   tabs use Web Locks where available and the server always enforces single flight and recent-result reuse.
3. The server decides: if a check is already running (another tab, a reload) it reports that one; if the last check
   completed under 30 minutes ago it reuses that result; if the last check failed under 10 minutes ago it waits.
   Otherwise it starts one check in a short-lived background thread and answers straight away.
4. The check reads the Stats NZ release calendar (4 requests; after a long absence also the months since the last
   complete calendar refresh, at most 6 months back), then finds **missing releases**: a supported series (CPI, GDP,
   labour market, electronic card transactions, international migration) whose release has been published, has no
   stored vintage, and either is newer than the initial catch-up boundary or was attempted before and never stored.
   Before its first discovery, each series durably records its newest stored publication time (or seven days before
   the check if empty). That boundary survives newer ingestion and restarts: releases discovered on a recovered feed
   stay eligible. Existing stored releases are excluded and earlier history remains explicit backfill's job.
5. If there is anything to ingest, a verified backup is taken first (below). Then each missing release is downloaded,
   validated and committed in publication order, each in one transaction, through the existing ingestion pipeline.
6. The header follows the check: *Checking for updates…*, *Downloading latest release…*, *Validating statistics…*,
   then *Data is up to date*, *Updated with new data* or *Could not refresh — showing last verified data*. Pending
   releases are always named, never folded into "up to date".
7. When new data is committed, every page's data is refetched in the background; the charts update in place.

You can keep reading and navigating during a check. Closing the tab does not stop it: the check belongs to the server.

### Situations

| Situation | What you see |
|---|---|
| Nothing new | *Data is up to date*. Only the 4 calendar requests were made (about 40 seconds at 10 s apart) |
| A new release | *Updated with new data*; charts refresh by themselves |
| Release time passed but files not out yet | *1 release still pending* (files not out yet). The next check looks again |
| No internet / Stats NZ down | *Could not refresh — showing last verified data*. Retried no sooner than 10 minutes later |
| Stats NZ shows a block page | The check stops at once; every request waits 30 minutes (shared across processes) |
| A file fails validation | *Could not refresh — showing last verified data* (or *Updated with new data · 1 could not be verified* when others succeeded); nothing from it is stored. Retried once a day, not on every open, and reported as overdue even after a later release is stored. Needs a code review with the real file; never loosen a threshold |
| Not opened for weeks | The calendar is read back to the last complete refresh (up to 6 months), and the missed releases are fetched oldest first, **at most 6 per check and 40 logical GETs**. The rest are listed as pending and fetched by the next checks (Check now, or reopen after the window). Away for more than 6 months: run `scripts/run.sh discover`, then `backfill` for the gap |
| A brand-new install with no data | Only releases from the last 7 days are fetched. History is `backfill`'s job, never a page view's |
| Two tabs, a reload, or StrictMode | One check. The others show its progress |
| You stop the dashboard mid-check (Ctrl+C, closing Terminal) | Shutdown waits for the active HTTP operation and durable result, even beyond 15 s (the HTTP timeout is 120 s, with a 15 s connect timeout). Retry, redirect, pacing and lock waits honour cancellation; no further HTTP attempt starts. The pacing reservation is released and the check is recorded as interrupted. Existing block/Retry-After deadlines still apply |
| The process is killed or crashes mid-check | Recorded as interrupted on the next start; nothing partial is kept. If a request was in flight, the shared pacer's crash-safety rule holds all requests for 30 minutes |
| The laptop sleeps | The window uses wall-clock time, so after a night asleep the next opening (or returning to the tab after 5 minutes) checks again |

## Limits (config/sources.toml, `[refresh]`)

| Setting | Default | Meaning |
|---|---|---|
| `fresh_window_minutes` | 30 | A completed check this recent is reused. Override with `NZSTATS_REFRESH_WINDOW_MINUTES` |
| `failure_cooldown_minutes` | 10 | A failed check is retried no sooner than this, including by Check now |
| `manual_min_interval_seconds` | 60 | Check now still waits this long after the last check |
| `max_releases` | 6 | Releases ingested per check; the rest are reported pending |
| `max_requests` | 40 | Logical GETs per check, calendar included (at least 12). Each may include the fetcher's own bounded retries (3) and same-host redirect hops (5), all paced 10 s apart. A release is never started unless the budget can finish it |

The 10-second minimum request spacing, retry limits, `Retry-After` handling and the 30-minute block cooldown are the
existing shared fetcher's and apply unchanged, across processes.

On-open responses also have a 120-second body deadline checked on raw chunks, including compressed responses, so a
continuously trickling body cannot hold shutdown open. This is not a strict end-to-end 120-second limit: header
arrival and one outstanding read can extend it. HTTPX's existing connect/read timeouts still apply. Hard process
termination (including `SIGKILL`) cannot run graceful cleanup and retains the pacer's crash-recovery cooldown.

## What it will never do

- Download a release that already has a stored vintage. A corrected release is re-ingested by hand:
  `scripts/run.sh ingest --release-key <key>` (the command takes no reason and records none; keep your own note of why).
  Nothing detects that a correction exists: see `docs/repository-health-review-2026-11-09.md`. Revisions Stats NZ publishes *in later releases* arrive with those releases
  as new vintages; earlier vintages are never edited.
- Repeat the historical backfill or fetch unattempted history at/before the initial catch-up boundary.
- Contact anything other than stats.govt.nz. Research and RBNZ sources are a separate, permission-gated domain that this
  code does not import.
- Start because something read the server. Health checks, uptime probes, `GET` requests and server startup never start a
  check; only the dashboard's `POST` does.
- Run APScheduler. `--refresh scheduler` (the container's explicit setting) is the only way to start it.

Its ingestion attempts are ordinary `ingest_run` rows, shared with `nzstats ingest --due` and the scheduler. Those count
them as polling attempts, so after many "not published yet" answers `ingest --due` may mark a release unavailable; a
later calendar date or the catch-up puts it back.

## Security model

`POST /api/refresh` is accepted only when all of these hold; anything else gets 403 and starts nothing:

- the `Host` is a loopback name (`127.0.0.1`, `localhost`, `::1`), which also defeats DNS rebinding;
- `Origin` equals that same scheme and host (a page on any other site, a sandboxed frame or `file://` fails);
- `Sec-Fetch-Site`, when the browser sends it, is `same-origin`;
- the request carries `X-NZStats-Client: dashboard`. A cross-origin page cannot add that header without a CORS
  preflight, and the app answers no preflight (there is no CORS middleware).

`nzstats serve` refuses to start on-open mode on a non-loopback bind (exit 2). Responses carry error **classes** only,
never upstream text or exception messages. The worst a local page could do is ask for one more bounded, paced check.

## Data integrity

Unchanged from earlier phases, because the check calls the same `discover` and `ingest_release`: official-source pages
only, content hashes and raw-artifact provenance, first-published versus earliest-stored (a backfilled release keeps its
capture time), corrections as new vintages, one transaction per release, last-known-good kept on any failure, fail-closed
validation including the statistical identities, and source permissions.

**Backup before an update.** When a check has something to ingest, it first writes a verified backup bundle (database
plus every raw artifact, checksummed) to `data/backups/pre-refresh-<UTC time>`. Only one is kept: an older pre-refresh
bundle is removed after the new one verifies. No copy is made when nothing has been committed since the last one, so
retrying a not-yet-published release does not copy the database again. If the backup fails, nothing is ingested and the
check reports `backup_failed`. Manual backups (`scripts/run.sh backup --bundle <dir>`) are never touched.

## Monitoring

`nzstats status` and **Data health** show the collection mode and the last check:

| Mode | Meaning |
|---|---|
| `on_open` | Normal: checks when opened. Not judged by timers, so no "missed refresh" is ever reported |
| `disabled` | Offline by choice. Not a fault |
| `paused` | The dashboard is not running |
| `enabled` | The scheduler (container only) |

The last check is `running`, `completed`, `failed` (ATTENTION: `refresh:failed`) or `interrupted` (a note). A check
running over 20 minutes is `refresh:running_long`. Data is stale only when a **published release is missing**
(`release:overdue:<key>`), never merely because the newest reference period is old. Backups and alert-check are
unchanged.

## API

| Route | Method | Effect |
|---|---|---|
| `/api/refresh` | POST `{"manual": false}` | Start a check unless one is running or a recent result stands. Answers with the status and `started` |
| `/api/refresh/status` | GET | Read-only: mode, state, phase, counts, failures (classes), pending releases with reasons, last successful check, and the latest statistics held per series (reference period and publication time, distinct from the check time) |

Implementation: `backend/src/nzstats/pipeline/refresh.py` (selection, budget, single flight, backup, status),
`backend/src/nzstats/api/refresh.py` (routes and origin checks), `frontend/src/api/refresh.ts`,
`frontend/src/components/RefreshIndicator.tsx`. Migration 012 adds `refresh_run` and `ops_process.collection_mode`;
migration 013 adds the durable per-series `refresh_catch_up` boundary. Status-fetch failures say "Refresh status
unavailable" and offer a status retry; they do not imply ingestion failed or send an unapproved POST.
