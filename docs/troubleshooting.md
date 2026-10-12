# Troubleshooting

Start with the **Data health** page (or `curl localhost:8000/api/health`). It lists each source's state,
last check and last success, and the most recent ingestion runs with their error class. Container logs:
`docker compose logs -f nzstats`. Inspect runs directly:
`docker compose exec nzstats nzstats health`.

Whatever fails, the last good data stays on screen: a failed run never overwrites stored vintages.

## By error class

| Class | Symptom | Where to look | Likely cause and fix |
|---|---|---|---|
| `network` | Run failed, source "Degraded", detail mentions timeout or connection | Data health, logs | Temporary outage or no internet from the container. Retries with backoff happen automatically. Check DNS and outbound HTTPS; re-run with `nzstats ingest --due`. |
| `blocked` | Detail mentions a block or challenge page | Logs | Stats NZ bot protection rejected the request. Do not lower the 10 s delay. Set `NZSTATS_CONTACT`, wait, and try later. Persistent blocking from a data-centre address may need a different network. |
| `not_found` | Release marked "scheduled" or "unavailable" after its time | Calendar, `ingest_run` | The files are not published yet (normal for a few minutes after 10:45) or the polling window (3 hours) expired. Run `nzstats ingest --release-key "<key>"` once the page is live. |
| `layout_changed` | Detail names a missing column or embedded JSON | `ingest_run.detail`, saved artifacts in `data/raw/` | Stats NZ changed a file. Nothing was stored. Compare the new file with the fixtures, add a new layout version to the adapter with a regression test using a real excerpt. |
| `validation_failed` | Detail starts with a rule name such as `[continuity]` | Data health, `ingest_run` | The data parsed but looks wrong (missing months, implausible jump, latest period not matching the title). Open the release page and compare with the official figures. Fix the cause; loosen a threshold only with evidence from the real file, plus a test. |
| `unexpected` | Detail reads "unexpected <ExceptionType>; see server log" | Container logs (full traceback) | A bug. The message is deliberately not stored or shown. Find the traceback in the logs, reproduce with the saved artifact, fix with a test. |

## Common problems

**The calendar looks stale.** The Release calendar page shows the last successful check. The calendar refreshes
daily at 06:00 Auckland time; force it with `nzstats discover`. If the month listing is failing but the ICS
works, upcoming releases still appear while history stops updating (the month endpoint is undocumented).

**A release did not appear at 10:45.** Polling starts at the scheduled time and continues at 0, 1, 2, 5, 10, 15,
30, 60, 120 and 180 minutes. Stats NZ sometimes publishes a few minutes late. Check Data health for the run. After
the window the release shows as unavailable; the daily catch-up job (07:30) and `nzstats ingest --due` retry it.

**Re-run a release.** `docker compose exec nzstats nzstats ingest --release-key "international-migration:august 2026"`.
This downloads the release page and its files again (three requests, 10 s apart). If the files are
byte-identical to a stored vintage the run reports `unchanged` and adds nothing, so it is safe to repeat.
If Stats NZ republished corrected files, the run stores a new vintage and the release status becomes
`corrected`.

**Reprocess after a parser fix (limitation).** Phase 1 has no re-parse command. Downloaded files are kept in
`data/raw/`, but ingest decides "unchanged" from the files' hashes alone, so a fixed parser will not
re-process a release whose files were already stored. Workaround: stop the server, take a backup
(`scripts/backup.sh`), delete that release's rows from `vintage` (and their `observation` rows) with
`sqlite3 data/nzstats.db`, then run the ingest command above. A proper `--reparse` option is listed as
remaining work in [progress.md](progress.md).

**"database is locked".** SQLite allows one writer at a time. Running `docker compose exec nzstats nzstats
discover` beside the server is supported: network requests from every process sharing `data/` are serialised and
kept at least 10 s apart through a lock file (`data/.request-pace`), and a writer waits for the other. Avoid
pointing a second container at the same `data/` directory.

**Wrong times.** Timestamps are stored in UTC and shown in Pacific/Auckland. The container sets
`TZ=Pacific/Auckland`; if times are off by hours, check that `TZ` was not overridden in `.env`.

**Permission denied on `/data`.** The container user must own `./data`. Run `chown 10001:10001 data` or set
`NZSTATS_UID` and `NZSTATS_GID` in `.env` to the folder owner (`id <user>`), then `docker compose up -d`.

**The page is blank or shows "could not be loaded".** Open the browser console. If `/api/*` returns errors,
check `docker compose ps` for the healthcheck and `docker compose logs`. A 404 for `/api/...` returns JSON;
anything else is served as the app.

**Start fresh.** Stop the container and move `data/` aside (do not delete it until you have confirmed the new
database works), then `docker compose up -d`, `nzstats discover` and `nzstats backfill`.
