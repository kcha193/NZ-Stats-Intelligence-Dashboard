# Phase 4AP: ANZ forecasts workbook ingestion

Branch `feat/phase-4ap-anz-xlsx-ingestion` from main `597b16d` (PR #68 merged). This phase carries out the approved plan
[`2026-11-21-phase-4ao-anz-xlsx-adapter.md`](superpowers/plans/2026-11-21-phase-4ao-anz-xlsx-adapter.md). The spec
is [Phase 4AN §4](phase-4an-anz-workbook.md) with [Phase 4AO §1 to §3](phase-4ao-anz-workbook.md).

This is a personal research project, run on the owner's own computer. It has no connection to the owner's employer.

## 1. What was built

| Part | Where | What it does |
|---|---|---|
| Migration 016 | `store/migrations/016_research_xlsx_format.sql`, rollback `scripts/rollback/016_research_xlsx_format_down.sql` | Rebuilds `research_document_version` and `research_manual_import` so `format`/`file_format` accept `xlsx`. Every row, id, index and trigger is kept. The rollback runs under `.bail on` and refuses while any `xlsx` row exists. |
| Cell reader | `research/xlsx_cells.py` | Stdlib `zipfile` and `expat` only, in the hardened child process. It evaluates no formula and runs no macro. It refuses DTDs, entities, external links, ActiveX, embeddings, connections, macro content types and encrypted members. Archive, member, ratio, cell, merge, text, element and depth budgets are all bounded. |
| Mapping | `research/xlsx_anz.py`, interpreter `xlsx-anz-1` | Quarterly sheets with dates in column A, titles in row 1 and unit headers in row 2. Only a bold forecast tail is accepted, and only with exactly one legend note that names bold forecasts. GDP, CPI inflation and unemployment are mapped. **OCR is never mapped** because its unit is unverified. |
| Wiring | `manual_import.py`, `banks.py`, `table_ingest.py`, `table_view.py`, `bank_analytics.py`, `cli.py` | `research import anz FILE.xlsx` stores the workbook. `tables extract` reads it only for ANZ, and only at the forecasts workbook address. Storing requires the owner's reconciliation code. Figures reach only the internal loopback bank view. |

Every candidate keeps exact provenance: sheet position, A1 cell, printed and stored text, number format, bold flag,
block title, unit header, the legend and "as at" notes, and the workbook's SHA-256.

### 1.1 Fail-closed rules (unchanged from the plan)

- A cell that is not bold never becomes an ANZ forecast. A column refuses as a whole (`forecast_boundary_unclear`) when
  its bold tail has a gap, a non-bold cell after the first bold one, or no bold at all.
- Other refusals: a missing or ambiguous legend (`forecast_marker_missing`), any non-quarterly date column
  (`unsupported_period`), a formula cell (`formula_cell`), and a number format other than General (10 digits at most)
  or `0`, `0.0…` with optional `#,##` (`unsupported_number_format`). Hidden sheets are refused too.
- Indicators, units, horizons, scope, scenario and third-party wording go through the same rules as PDF tables
  (`_indicator`, `unit_of_text`, `_horizon`, `context_rejection`, `_third_party`).
- A GDP label must state its price basis ("real" or "nominal"). Without one, the figure is stored but held back from the
  comparison as `table_unresolved_reconciliation`. This is the existing Phase 4AF rule, unchanged.

### 1.2 Owner reconciliation (storage gate)

1. `nzstats research tables extract V --dry-run` prints counts, rejection codes and an 8-character **confirmation
   code**. It prints no values, so it is safe in any session.
2. The owner runs `nzstats research tables extract V --dry-run --list` **in their own terminal**. The command refuses
   unless both stdin and stdout are a terminal. It prints every candidate: sheet, cell, indicator, horizon, printed
   value, unit, role and label.
3. The owner opens the original workbook and checks every listed cell: the value, the period, the unit, and that it is
   bold and ANZ's.
4. Only when every candidate matches, the owner runs `nzstats research tables extract V --confirm CODE`. A missing or
   different code stores nothing. The code is a hash over exactly the candidates listed, so any change to the file,
   the interpreter or a candidate gives a new code.

`tables show V` on a workbook version also needs a real terminal, because it prints values.

### 1.3 History gate

Revisions and forecast evaluation leave out every `xlsx-anz-1` figure, with the fixed code `history_unverified`, until
the layout is shown stable across two releases. The current forecasts view and the freshness view are unaffected. One
bank never forms a consensus (existing rule).

### 1.4 Distinct series that name one indicator (found by the pilot)

When more than one distinct block title maps to the same indicator anywhere in the workbook, every column of those
blocks is refused as `ambiguous_indicator`. No block is picked as the headline. Examples are headline GDP beside
components or variants that also name GDP, or headline CPI beside a CPI variant. This rule tightens the mapping: it
can only remove candidates. Commit `4f5faf4`, tests `test_two_distinct_blocks_naming_one_indicator_*`,
`test_the_same_indicator_on_two_sheets_*` and `test_one_block_title_repeated_*`.

### 1.5 Review fixes for workbook identity and structural notes

New workbook versions (`xlsx-cells-2`) use `cells_sha256` in the existing version key. It covers the parsed cells,
including bold flags and number formats, plus sheet positions, names, visibility, merges, the date system and drawing
text. Repackaging the same parsed workbook reuses its version. Raw artifacts remain keyed by the SHA-256 of their exact
bytes. HTML and PDF continue to use the normalized text key. The manual import audit keeps the normalized text hash so
purge still blocks the same text under different workbook formatting or a different address.

Existing `xlsx-cells-1` rows retain their IDs, hashes and artifacts. Within the same publication, an import reuses a
legacy row when the bytes match or its verified local artifact has the same cell digest. If the stored bytes cannot
establish a match, the supplied workbook takes the semantic key. Existing publication links and audit rows stay intact.
The current schema supports both keys, so this requires no migration or replay.

Interpreter `xlsx-anz-2` checks qualifiers in the bold legend and vintage note during extraction and stored-evidence
revalidation. It keeps the original notes as evidence. Earlier extractions remain recorded. The internal view uses
the current interpreter and a new owner confirmation code is required to store its extraction. The two-release history
gate still applies.

## 2. Real workbook pilot, 21 November 2026

Every command ran from the repository root (`NZSTATS_DATA_DIR=./data`). The session printed counts, codes and hashes
only. No workbook value, sheet name, title or note entered the session.

| Step | Result |
|---|---|
| 1 Backup | `nzstats backup --bundle data/backups/pre-4ap-20261121T051826Z`: database plus 54 raw artifacts, schema 15. `verify-backup` ok |
| 2 Identity | `shasum -a 256 ANZ-Forecasts.xlsx` = `4c2d4b47…6da7358`, 178,346 bytes, matching Phase 4AO |
| 3 Address | Taken from the saved file's download provenance (`kMDItemWhereFroms`): `https://www.anz.co.nz/content/dam/anzconz/documents/economics-and-market-research/Latest-forecasts.xlsx`. Nothing was fetched |
| 4 Import | `research import anz … --title "ANZ Forecasts"`, no `--published-on`. Result: publication 5, **version 5**, sha256 `4c2d4b47cdf2`, warning `no_title`. This first open migrated the live database to **schema 16** |
| 5 Dry run | **0 figures, 97 rejections**: `ambiguous_indicator` ×52, `unmapped_row` ×42, `unsupported_period` ×2, `unit_unstated` ×1. Code `4f53cda1` covers 0 candidates |
| 6 Store gate | `tables extract 5` without `--confirm` was refused. Version 5 has **0 stored extractions** |
| 7 Rollback rehearsal | On a copy of the live database, the down script stops at the `xlsx` row and leaves schema 16 intact (integrity ok). On the restored pre-4AP bundle, 15 → 16 → 15 gives a schema identical to the bundle (99 objects) with every table's row count equal. `foreign_key_check` is empty and `integrity_check` ok |
| 8 Snapshot | `export-snapshot --now 2026-11-21T06:00:00Z` from the live database and from the pre-import copy: **byte-identical** (`513b53a8ea28`, 250 files) |
| 9 Status | `research bank-status`: ANZ `forecasts_workbook` is `undated`, because no publication date was guessed |

### 2.1 Why 0 figures (masked probes)

[`probe_rejections.py`](../benchmarks/xlsx_inspect/probes/phase_4ap/probe_rejections.py) and
[`probe_identity.py`](../benchmarks/xlsx_inspect/probes/phase_4ap/probe_identity.py) re-run the production rules part by
part and print only ints, booleans and production codes. Results:
[`phase-4ap-rejections.json`](../benchmarks/xlsx_inspect/results/phase-4ap-rejections.json) and
[`phase-4ap-identity.json`](../benchmarks/xlsx_inspect/results/phase-4ap-identity.json).

| Sheet | Finding |
|---|---|
| 1 | The cover. It has no cells and gives nothing |
| 2 | 14 distinct block titles. **10 map to GDP on their own, and all 10 state "real"**. 40 columns name GDP, so all are `ambiguous_indicator`. One column in every block of four has a unit header the reader does not support (`unsupported_unit`, a level or index). The sheet name has 2 words outside the neutral list, and neither appears in any title. Before the fix in §1.4, this gave `unsupported_context` on every percent column. Without the sheet name, those columns would have passed the context rule as 30 "GDP" columns from 10 different series. That is why the §1.4 fix was needed |
| 3 | 8 distinct titles. 3 map to CPI inflation (12 columns `ambiguous_indicator`). The one unemployment column has no unit header and its title states no unit, so it is `unit_unstated`. No unit is assumed. The sheet name has 1 word outside the neutral list |
| 4 | 4 blocks, none for the three indicators: 16 columns `unmapped_row` |
| 5, 6 | Monthly dates: `unsupported_period`. Sheet 5 holds the OCR, which stays excluded |

Every refusal follows the fail-closed rules. No rule was loosened to recover a figure.

### 2.2 Status: NO-GO for figures; owner decisions pending

The adapter, the storage gate and the isolation all work on the real file. The file gives **0 candidates**, so there is
nothing to reconcile and nothing was stored. Task 6 (dashboard check after owner-verified storage) did not run.

Any figure from this workbook first needs owner decisions. This branch does not implement any of them:

1. **Block selection.** Name the exact block titles for headline real GDP and headline CPI inflation, after checking
   the workbook. Every other GDP or CPI block stays refused.
2. **Unemployment unit.** The column states no unit. An explicit unit has to be shown from the workbook, not assumed.
3. **Sheet names.** The 1–2 non-neutral words in each sheet name block the context rule. Allowing them requires the
   owner to review those exact words. Each word would be added to a reviewed list with a regression test.
4. **Publication date.** Re-import the same file with `--published-on YYYY-MM-DD`, using the date the workbook states.
   This adds the date without a new version (`test_an_undated_import_takes_the_owners_date_*`) and clears `undated`.

After these decisions, the owner runs the reconciliation steps in §1.2 in their own terminal.

### 2.3 Restoring the pre-4AP state

The live database is at schema 16 with version 5 imported. `research purge` on version 5 removes the stored copy and
text, but keeps the version and audit rows (format `xlsx`). The rollback script therefore still refuses after a purge.
To return to schema 15, restore the step-1 bundle (`restore-backup`, then point `NZSTATS_DATA_DIR` at it). The rollback
script is for a database with no `xlsx` row. Run it with the sqlite3 shell, because it relies on `.bail on`.

## 3. Verification

- Synthetic tests: `test_xlsx_cells.py` 35, `test_xlsx_anz.py` 52, `test_xlsx_pipeline.py` 19, `test_migration_016.py` 7.
  Snapshot isolation gained a workbook case. The table isolation pins now also cover the `xlsx_*` modules
  (mutation-checked).
- Full backend suite before the §1.4 fix and the wording-pin update: 7,256 passed, 1 failed. The one failure was the
  expected wording pin, since updated. Research, store and publish suites after the fixes: see `docs/progress.md`.
  Ruff check and format clean.
- Privacy: only codes, counts, hashes and the provenance address entered the session. The probe outputs were checked
  mechanically: the only strings are production codes.
