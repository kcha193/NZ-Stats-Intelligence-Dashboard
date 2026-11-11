# Phase 4AF: bank table extraction runbook

**No live ingestion exists for any bank and no permission field was changed.** Every command below is local and offline:
none contacts a bank, calls a model or schedules anything. Today all five banks refuse them (see the
[readiness matrix](phase-4af-source-readiness.md)); the runbook is what to do once the owner has approved a source.

## Read the state (safe any time)

```sh
nzstats research bank-status              # per bank and series; times shown in Pacific/Auckland
nzstats research bank-status --json       # the same, machine-readable, times in UTC
nzstats research tables show 12 --json    # stored figures and rejection codes for version 12 (no label or cell text)
```

`bank-status` reports `undated` when reports are held but none states a publication date (freshness cannot be judged; exit
code 1). `tables show` refuses a version whose source is no longer permitted, and prints codes, positions and numbers only.

## Extract the tables of one stored PDF

```sh
nzstats research import SOURCE FILE --url URL --importer NAME --note NOTE   # an owner-saved copy (needs manual_import approved)
nzstats research tables extract 12 --dry-run                                # count figures and rejections; write nothing
nzstats research tables extract 12                                          # store them (rerunning is a no-op)
```

Refusals use fixed wording: `unknown version`, `purged`, `unknown institution`, `source not permitted`, `content policy does
not allow full text`, `not a pdf`, `raw copy unavailable`, `raw copy does not match the stored version`, `pdf could not be
read (...)`. A refused run writes nothing. Rejection codes you may see in `tables show`: `ambiguous_columns`, `no_header`,
`unmapped_row`, `ambiguous_indicator`, `unit_unstated`, `contradictory_unit`, `period_basis_unstated`,
`contradictory_period`, `unparsed_period`, `actual_or_forecast_unstated`, `bracketed_value`, `unrecognised_suffix`,
`footnote_unresolved`, `unsupported_unit`, `value_out_of_range`, `scenario_table`, `scenario_row`, `scenario_column`. A rejection is information, not an error: nothing was guessed.

## What the dashboard shows

Table figures appear in "Bank outlooks" only on the loopback dashboard, only with the owner's automatic internal view on, and
only for a bank whose route is still permitted and whose content policy is `full_text`. The evidence drawer says "Read directly
from a table in the report. No AI was used." with the page, the row and the header. The forecasts response carries
`table_reconciliation`, counts by class. A figure left out appears under "Left out" with a fixed reason.

## Revocation and removal

```sh
nzstats research purge SOURCE --version 12            # plan (dry run); add --reason --by --note --apply to do it
nzstats backup --bundle DEST                          # database, raw files and a checksum manifest
```

A purge removes the version's table figures and rejections in the same transaction as its text; the extraction row stays as
a tombstone (hashes and counts, no content) and the text cannot be extracted again. Migration 015 is rolled back with
`scripts/rollback/015_research_table_forecast_down.sql` (back up first); the 004 and 010 rollbacks also drop its tables.

## What this phase never does

It never fetches, never lowers the 10 second crawl delay, never works around a 403, robots rule or challenge, never sends text
to a model, never adds bank text or values to committed frontend data, a snapshot, or the public or private gates.
