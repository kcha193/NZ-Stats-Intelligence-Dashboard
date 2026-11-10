# Phase 4AE: bank research runbook

Operating the bank comparison safely. **Today there is no live ingestion for any bank: all five are permission-denied**, so
every acquisition command below refuses. The runbook is what to do once the owner has independently approved a source.
See [phase-4ae-permissions-matrix.md](phase-4ae-permissions-matrix.md) for the state and prerequisites.

Opening the dashboard fetches nothing and calls no model. Nothing is scheduled; there is no cron entry, scheduler job or
on-open refresh for banks, and one institution's failure cannot affect another's or the Stats NZ pipeline.

## Read-only checks (safe any time)

```sh
nzstats research sources                  # every institution and why access is allowed or refused
nzstats research bank-status              # each bank, by report series: state and four separate dates
nzstats research bank-status --json       # the same, machine-readable (exit 0 ok / 1 attention / 3 cannot run)
nzstats research health --json            # pipeline health, plus per-bank metrics for the last 30 days
```

`bank-status` never creates or migrates a database. States, worst first: `permission_denied` (every bank today; expected, not
a fault), `unsupported` (permitted but no report series defined), `blocked` (the source refused the last request),
`missing` (permitted, nothing received), `stale` (a series is older than its cadence), `ok`. Staleness is judged per series,
so a fresh weekly note cannot hide a missing quarterly outlook. Dates shown: newest report published, ingested, analysed,
last checked. Metrics (`research health --json`, key `bank_metrics`): discovery ok/failed, new documents, updated versions,
blocked runs, extraction failures, verification failures, missing expected releases. Output holds ids, states, dates and
counts only, never document text.

## Discovery and ingestion (refused until approved)

```sh
nzstats research discover anz             # discovery-only dry run
nzstats research ingest anz --dry-run     # what an ingest would do
nzstats research ingest anz               # one bounded, throttled run for one institution
```

Each is refused with a fixed reason while the source is `needs_review`. Never lower the 10 second crawl delay, add parallel
requests, or work around a 403, robots rule or challenge.

## Manual import (refused until `manual_import = approved`)

```sh
nzstats research import anz --help        # an owner-saved copy of one report, with importer and note
```

## Summaries and reprocessing

```sh
nzstats research summarise --help         # needs the source's `llm_processing` and, if hosted, a version-scoped consent
nzstats research summaries                # list stored summaries
```

No bank is in any hosted policy; the Treasury authorization is not widened. Reprocessing a stored version is deterministic and
idempotent. A claim enters bank comparisons only if it passes every automated check with no warning.

## Permission failures and revocation

A refused command writes nothing. To revoke a source, set its registry state back, then withdraw what it let in
(`nzstats research purge --help`); each route (crawler, manual import) is revoked independently and the dashboard stops showing
that source's material on the next read.

## Backup and restore

```sh
nzstats backup --bundle DEST              # database, raw files and a checksum manifest
nzstats verify-backup DIR
nzstats restore-backup SRC NEWDIR
```

## What the dashboard may and may not do

Bank content is shown only on the loopback dashboard, only when internal AI analysis is on, labelled as AI-generated and not
independently reviewed. It never reaches the public API, the private preview, the static snapshot or the Netlify build.
