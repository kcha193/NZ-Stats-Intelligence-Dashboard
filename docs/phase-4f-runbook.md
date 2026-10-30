# Monitoring and recovery runbook (native operation)

For one operator running the dashboard on their own machine. Design and thresholds:
[phase-4f-operational-health.md](phase-4f-operational-health.md). Commands run from the repository root. `scripts/run.sh`
passes subcommands to `nzstats` using `backend/.venv`, after loading `.env` and changing to the repository root (calling the `nzstats` binary directly skips both, and a relative `NZSTATS_DATA_DIR` then points at the wrong place).

Nothing here schedules anything or contacts anyone. Commands marked **contacts Stats NZ** make requests (one at a time,
10 seconds apart) and are only for when you decide to run them.

## 1. Choose how you run it

```sh
scripts/run.sh                  # normal use: serve; each time you open the dashboard it checks Stats NZ once (on-open)
scripts/run.sh --offline        # serve stored data only. Makes no requests to stats.govt.nz. Collection: "off by choice"
```

The on-open refresh (Phase 4G) replaced the scheduler for native use: nothing runs on a timer, and opening the page is
what asks for a check. How it works, its limits and what it does after a long absence:
[phase-4g-on-open-refresh.md](phase-4g-on-open-refresh.md). `--refresh scheduler` still exists for the container.

Closing the terminal window is a clean stop. Killing the process or losing power is not, and the next start records an
"unexpected restart" for 24 hours.

## 2. The daily check (30 seconds)

```sh
scripts/run.sh status
```

or open **Data health** in the dashboard (it refreshes every 30 s). It does not start anything, write anything or use the
network, so it is safe at any time, including while the dashboard runs.

| Exit | State | Meaning |
|---|---|---|
| 0 | OK | Every check is within its limit |
| 1 | ATTENTION | Look at it today |
| 2 | CRITICAL | The dashboard is not doing its job, or its data may be wrong |
| 3 | Could not run | The monitor itself failed; read the message. Not the same as OK |

Read the top block first: **Collection** (on / off by choice / paused), **Process** (running, stopped, lost), **Calendar**,
**Next release**, **Backup**. Then **Issues**; each says what to do. `--json` gives the full report.

"Current" in the freshness table means no published release is waiting to be ingested. A reference period that is months
old is normal until Stats NZ publishes again.

## 3. What to do about each issue

| Issue | Do this |
|---|---|
| `process:lost` | Start it again (`scripts/run.sh`). If you did not expect it, read the terminal output it was running in for a crash |
| `process:stalled` | The process is alive but silent. Look at its terminal. If unresponsive, Ctrl+C (or `kill <pid>`), then start it again. Interrupted ingestion rolls back; last-known-good data is kept |
| `scheduler:no_progress`, `scheduler:job_running_long` | Same: restart. Then check `status` again after 5 minutes |
| `calendar:missed` | The laptop slept through 06:00, or the dashboard was off. Restart (it refreshes the calendar on start), or **contacts Stats NZ**: `scripts/run.sh discover` |
| `calendar:stale` / `calendar:never` | On-open: open the dashboard, or press **Check now** in its header. Offline: **contacts Stats NZ**: `scripts/run.sh discover` |
| `refresh:failed` | The last on-open check failed; the dashboard shows the last verified data. Press **Check now** after 10 minutes. `blocked`: do nothing for 30 minutes. `backup_failed`: free disk space |
| `refresh:running_long` | A check is taking too long: restart the dashboard. Interrupted ingestion rolls back |
| `release:overdue:<key>` and collection is on-open | Open the dashboard or press **Check now**. A check fetches a few releases at a time; the rest are listed as pending |
| `release:overdue:<key>` and collection is off | **Contacts Stats NZ**: `scripts/run.sh ingest --due`, or for one release `scripts/run.sh ingest --release-key <key>` |
| `release:overdue:<key>` with `validation_failed` / `layout_changed` | Stats NZ published but the file was rejected. Last-known-good data is still shown. Do **not** retry in a loop and do **not** loosen a validation threshold; this needs a code review with the real file |
| `source:blocked` | Do nothing. Polling pauses 30 minutes. If it persists for a day, check `NZSTATS_CONTACT` and that `NZSTATS_MIN_INTERVAL_SECONDS` is not below 10 |
| `source:degraded:<source>` | Open Data health; the error class says whether it is `network` (usually clears), `blocked`, or a parser/validation problem |
| `database:schema_behind` | `scripts/run.sh migrate` (local, no network), or start the dashboard |
| `database:unreadable` / `database:integrity` | Stop the dashboard. Restore into a **new** directory (section 5). Keep the damaged file |
| `backup:*` | Take a bundle (section 4) |

## 4. Backups

A native backup set holds the database **and** every raw file it references, with checksums.

```sh
scripts/run.sh backup --bundle data/backups/nzstats-$(date +%F-%H%M)
scripts/run.sh verify-backup data/backups/nzstats-2026-10-30-0900
```

`backup --bundle` refuses to overwrite, refuses to finish if a referenced raw file is missing or damaged (nothing is
written), and verifies the set before it appears. `verify-backup` on a directory re-hashes every file; run it before you
rely on a backup. Taking a backup is safe while the dashboard runs. Take one before any `ingest`, `backfill` or upgrade.

`scripts/run.sh backup <file.db>` still writes the database alone; it is counted, but marked "not verified" and does not
protect the raw files.

Never delete or edit anything in `data/backups/` to silence an alert.

## 5. Restore (always into a new directory)

Restore never overwrites a database. You switch over deliberately.

```sh
scripts/run.sh verify-backup data/backups/nzstats-2026-10-30-0900
scripts/run.sh restore-backup data/backups/nzstats-2026-10-30-0900 data-restored
NZSTATS_DATA_DIR=data-restored scripts/run.sh migrate         # only if it reports a schema older than the code
NZSTATS_DATA_DIR=data-restored scripts/run.sh --no-scheduler  # look at it; run `nzstats status` against it
```

When satisfied, stop the dashboard, rename `data` to `data-damaged-<date>` (keep it), rename `data-restored` to `data`, and
start again. `NZSTATS_DATA_DIR=... scripts/run.sh` now takes precedence over `.env`, so an isolated copy can never fall
back to `./data`.

## 6. Local alerts (optional, no network)

```sh
scripts/run.sh alert-check                   # log + data/ops/alerts.jsonl
scripts/run.sh alert-check --channels file
```

It runs the same checks as `status` and delivers only **new or changed** problems: once when opened, again if it
worsens, a reminder after 12 h (CRITICAL) or 72 h (ATTENTION), and once when resolved. Repeats are suppressed, at most 6
are delivered per hour, and more than 3 at once become one digest. Its exit code is the dashboard's state (as `status`);
a problem delivering is printed separately and recorded, and never turns a healthy dashboard red.

To run it periodically you would use launchd or cron. **That creates an unattended process and needs the owner's
approval; it is not installed.** Remote channels (Telegram and similar) are not implemented and need approval and a
credential decision first.

## 7. When the laptop sleeps

Sleep is detected and recorded, not treated as a fault. With the on-open refresh there is nothing to miss: returning
to a dashboard tab after more than 5 minutes asks for a check, and the server runs one if the last was over 30 minutes
ago (wall-clock time, so a night asleep always counts). A check interrupted by sleep carries on when the machine wakes;
one interrupted by a restart is recorded as interrupted and the next opening checks again.

With `--refresh scheduler`, the scheduler gets 10 minutes to catch up after waking. A sleep across 06:00 drops that day's
calendar refresh; `status` reports `calendar:missed` with the fix (restart or `discover`). A release that came due while
asleep is recovered by the startup catch-up within 7 days, and reported as overdue until then.

## 8. Do not

- Run the scheduler, `discover`, `ingest` or `backfill` against `data/` for testing, or open a test server in on-open
  mode on `data/`. Use an isolated copy, or `--offline`.
- Lower the 10-second crawl delay or add parallel requests.
- Copy `data/nzstats.db` with `cp` while the dashboard is running (use `backup`).
- Delete `data/`, `data/backups/` or any `-wal` file by hand.
