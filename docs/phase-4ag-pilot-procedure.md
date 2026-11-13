# Phase 4AG: operating procedure for the first ANZ pilot (one Quarterly Economic Outlook)

14 November 2026, Pacific/Auckland.

**Status: BLOCKED at step 0.** No ANZ right or owner permission is recorded, so nothing below has been run against ANZ
material and no live ingestion exists. Do not start step 1 until step 0 is complete and written down. A pilot that is
not run is reported as blocked, never as a success.

Scope: **one** owner-saved ANZ Quarterly Economic Outlook PDF; table parsing only; internal loopback dashboard only. Out of
scope: scheduling, the crawler, a second bank, HTML or workbook tables, any model (local or hosted), anything public.

Manual reconciliation here is a **one-time quality acceptance check** of the extractor on a real layout. It is not an approval
step that every later internal summary needs.

## Step 0: preconditions (owner; all must be true)

| # | Condition | Evidence to record |
|---|---|---|
| 0.1 | The owner has re-read the ANZ terms in a browser and recorded date, URL and the clauses | note in the registry change |
| 0.2 | ANZ's written reply, or the owner's recorded decision, covers [decisions 1 to 6](phase-4ag-anz-permissions-package.md) | reply reference |
| 0.3 | One reviewed change sets, for `anz` only, `manual_import = approved` (approver, date, note) and `content_policy = full_text`; `review_status`, `llm_processing`, `public_display` and `private_display` unchanged | the diff |
| 0.4 | `PRE_APPROVAL_SHA256` in `test_phase_4x_readiness.py` and the pins in `test_phase_4ag_safety.py` are updated in the same change, with the key-by-key diff | the diff |
| 0.5 | `data/internal-drafts.json` has `auto_display` on (the owner's own file; ignored by Git) | the file |
| 0.6 | `nzstats --help` runs from an environment installed with the research extra (`pip install -e 'backend[research]'`) so `pdfminer.six>=20251230` is present | `pip list` line |

If any row is not true: **stop and report BLOCKED**.

## Step 1: back up (before anything is written)

```sh
nzstats backup --bundle ~/nzstats-backups/pre-anz-pilot-$(date +%Y%m%d)
nzstats verify-backup ~/nzstats-backups/pre-anz-pilot-$(date +%Y%m%d)
```

Stop if verification fails. The backup is the rollback.

## Step 2: import one owner-saved document

The owner saves the PDF in a browser (a normal visit; no script fetches anything). Then:

```sh
shasum -a 256 ~/Downloads/ANZ-QEO-YYYYMMDD.pdf        # record this hash
nzstats research import anz ~/Downloads/ANZ-QEO-YYYYMMDD.pdf \
  --url https://www.anz.co.nz/content/dam/anzconz/documents/economics-and-market-research/YYYY/ANZ-QEO-YYYYMMDD.pdf \
  --importer "<owner>" --note "saved from a browser on <date>; pilot 4AG" --published-on YYYY-MM-DD
```

The URL must match the registry's `economic_outlook` pattern (`/economics-and-market-research/YYYY/ANZ-QEO-YYYYMMDD.pdf`); that is how the
document is placed in its series. `--series` is not used.

Never bypass a refusal, challenge or error page; if the browser cannot save the document, stop.

## Step 3: validate identity, dates and hashes

- The import line's `sha256` prefix equals the `shasum` recorded in step 2.
- The title and cover date of the PDF match `--published-on` and the date in the file name.
- `nzstats research bank-status` lists the document under ANZ, not "undated".
- The page count and size are plausible (a quarterly outlook is tens of pages).

Stop on any mismatch; fix the import metadata through a new import, never by editing the database.

## Step 4: deterministic extraction, dry run

```sh
nzstats research tables extract <VERSION> --dry-run
```

Read: figure count, rejection tally by code, reader (`pdf-words-2`) and interpreter (`tables-11`). Nothing is written.

## Step 5: examine the rejected and ambiguous tables

For every rejection code, open the PDF at the page and decide whether the refusal was right. Common codes are listed in the
[runbook](phase-4ag-runbook.md). A rejection is information, not a failure.

- **Stop (pilot is not accepted yet)** if the tables of interest (OCR, CPI, GDP, unemployment) are all rejected or `no_text_layer`
  / `rotated_text_only` appears. The fix is a documented extractor change: a synthetic fixture that reproduces the layout,
  a failing test, then the change. **Never loosen a rule to get more values.**
- `mixed_layout` means prose shares a baseline with table rows; the table was not read, by design.

## Step 6: extract the supported figures

```sh
nzstats research tables extract <VERSION>
nzstats research tables show <VERSION> --json > pilot-figures.json   # codes and numbers only; keep out of Git
```

## Step 7: reconcile every figure by eye against the PDF

For each stored figure, open the PDF at its page and complete a sheet (keep it out of Git; it describes ANZ's content):

| page, table, row, col | indicator | target period | unit | printed text | stored value | actual or forecast | correct? |
|---|---|---|---|---|---|---|---|

Check **indicator, value, unit, target period** (calendar versus financial year; quarter versus year-ended), **attribution**
(ANZ's own forecast, not another forecaster's or a scenario), **actual versus forecast status**, and that no footnoted or
bracketed figure was read. Also confirm no figure that is in the table is missing without a rejection code explaining why.
**Any wrong figure stops the pilot.** It becomes a failing synthetic test before anything else changes.

## Step 8: check the displayed result

```sh
cd backend && NZSTATS_STATIC_DIR=../frontend/dist nzstats serve --no-scheduler   # loopback only
```

Open the dashboard, "Bank outlooks": the ANZ figures match the sheet; the evidence drawer shows "Read directly from a table in
the report. No AI was used." with the right page and row. One bank is shown as "Insufficient banks": **no consensus** appears.
Confirm opening the page made no request to ANZ and no model call (the server log shows none; `serve` never fetches).

## Step 9: confirm public and static isolation

```sh
nzstats export-snapshot ./snapshot && nzstats validate-snapshot ./snapshot --for-publish
grep -ril "anz" ./snapshot || echo "no bank content in the snapshot"
git status --short                      # no ANZ document, no data/ file, no figure staged or modified
```

The snapshot must contain no bank text or figure; `git status` must show no document or data file.

## Step 10: rehearse revocation and rollback

```sh
nzstats research purge anz --version <VERSION>                       # a dry run: the plan only; review it
nzstats restore-backup ~/nzstats-backups/pre-anz-pilot-<date> ~/nzstats-restore-rehearsal   # into a NEW directory
```

Rehearse revocation in order of weight: turn `auto_display` off (the dashboard shows nothing); revert the registry change
(the route is refused again, `tables extract` refuses); `purge ... --apply` removes the text and the figures (the extraction
row remains as a hash-only tombstone). Do not apply the purge unless revoking. The restore goes to a **new** directory; it never
overwrites live data.

## Step 11: record the outcome

Write the date, version id, hash, counts, rejection tally, the reconciliation result and any layout lesson into
`docs/progress.md`. If it passed, the next pilot step is a second quarterly outlook (to exercise revisions and the
staleness note in the [verification record](phase-4ag-verification.md)); a model reading ANZ text remains a separate decision.

## What the pilot never does

It never fetches, never lowers the 10-second delay, never works around a 403, robots rule or challenge, never sends text to a
model, never schedules, never adds a bank's text or figures to Git, a snapshot, or the public or private gates.
