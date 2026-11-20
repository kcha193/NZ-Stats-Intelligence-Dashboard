# Phase 4AO ANZ Forecasts Workbook Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read ANZ's own forecasts from one manually imported forecasts workbook (XLSX) into the existing table-figure
store, with cell provenance, so they reach the internal Bank Outlooks view under the existing gates and nowhere else.

**Architecture:** A bounded stdlib XLSX cell reader (`xlsx_cells.py`, run in the existing hardened child process) feeds
one ANZ-specific mapping (`xlsx_anz.py`) that emits the same `TableForecast`/`Rejection` records as the PDF interpreter,
stored through `table_store.store_extraction` (migration 015, unchanged). Migration 016 widens the two `format` CHECKs
to admit `xlsx`. Storing a workbook extraction requires the owner's reconciliation hash.

**Tech Stack:** Python 3.12 stdlib (`zipfile`, `xml.parsers.expat`), SQLite, existing `nzstats.research.table_*`.
No new dependency (`openpyxl` stays benchmark-only).

**Spec:** `docs/phase-4an-anz-workbook.md` §4 (design) and `docs/phase-4ao-anz-workbook.md` §1 to §3 (the masked
structure this mapping is shaped by).

## Global Constraints

- Never evaluate a formula or follow an external reference. Any formula cell in a read block is rejected `formula_cell`.
- Never infer a unit, a period, an actual/forecast status or an author. Reject with a fixed code.
- Rejection and refusal text is fixed wording: never workbook text or an exception message.
- Store forecasts only: non-bold (historical) cells are neither stored nor shown; workbook actuals are never official data.
- Tests use synthetic workbooks only ("Fictional" names, invented figures). No ANZ text, value or sheet name in Git.
- Interpreter version string: `xlsx-anz-1`. Reader limits: the CPI reader's (16 MB archive, 64 MB unpacked, 200 members,
  ratio 250) plus the inspector's cell budget (100,000 cells).
- No crawler, model, schedule, snapshot, public or private-research route. Display only through `table_view` behind the
  internal loopback gate. No single-bank consensus.
- Ruff line length and format per `backend/pyproject.toml`; `pytest && ruff check . && ruff format --check .` green.

## Review Focus

1. **A second workbook vintage with a moved boundary** (next release): must be a new document version and a new
   extraction; the older version's figures are never overwritten or inferred. Test in Task 4.
2. **A cell that is bold inside the historical block, or a non-bold cell inside the forecast block:** the whole column is
   refused `forecast_boundary_unclear`, never split. Test in Task 3.
3. **A float artefact in the stored value** (`2.0999999999999996` under format `0.0`): the figure is the printed text
   (`2.1`), with the stored text kept in evidence. Test in Task 3.
4. **Migration 016 on a populated database** (versions referenced by summaries, table extractions, imports, purges):
   no row, id, trigger or foreign key lost; `foreign_key_check` and `integrity_check` clean; rollback restores the old
   CHECKs. Test in Task 1.
5. **Storing without reconciliation:** a non-dry-run extraction of an `xlsx` version without the matching `--confirm`
   hash stores nothing. Test in Task 4.

---

### Task 1: Migration 016, `xlsx` format

**Files:**
- Create: `backend/src/nzstats/store/migrations/016_research_xlsx_format.sql`
- Create: `scripts/rollback/016_research_xlsx_format_down.sql`
- Test: `backend/tests/store/test_migration_016.py`

**Interfaces:**
- Produces: `research_document_version.format` and `research_manual_import.file_format` accept `'xlsx'`.

Method (inside the runner's transaction, foreign keys on): `PRAGMA defer_foreign_keys=ON`; copy each table to a plain
backup table; drop its triggers; drop the table; recreate it with the identical column list and the wider CHECK; re-insert
from the backup (this clears the deferred violations); drop the backup; recreate indexes and triggers verbatim. The down
script does the reverse and first refuses (via a failing CHECK) when any `xlsx` row exists.

- [ ] Step 1: tests: `test_016_accepts_xlsx_versions_and_imports`, `test_016_keeps_every_row_id_trigger_and_index`
  (populate every research table referencing versions, migrate 15 to 16, compare row counts, ids, `sqlite_master`
  names and SQL other than the two CHECKs), `test_016_fk_and_integrity_checks_are_clean`,
  `test_016_purge_triggers_still_fire`, `test_016_rollback_restores_the_old_checks` and
  `test_016_rollback_refuses_while_xlsx_rows_exist`.
- [ ] Step 2: run, expect failures. Step 3: write both scripts. Step 4: run, pass; run the full store and research suites.
- [ ] Step 5: commit `feat(store): migration 016 admits xlsx research documents`.

### Task 2: `xlsx_cells.py`, bounded stdlib cell reader

**Files:**
- Create: `backend/src/nzstats/research/xlsx_cells.py`
- Test: `backend/tests/research/test_xlsx_cells.py`, `backend/tests/research/xlsx_support.py` (synthetic builder:
  writes OOXML parts directly with `zipfile`, no openpyxl)

**Interfaces:**
- Produces:
  - `XCell(row: int, col: int, kind: Literal["number", "text", "bool", "error", "formula"], text: str, bold: bool,
    number_format: str, is_date: bool)`: `text` is the stored `<v>` text (or shared string); `is_date` from the
    number format.
  - `XSheet(position: int, name: str, state: Literal["visible", "hidden", "very_hidden"], cells: Mapping[tuple[int, int], XCell], merges: tuple[tuple[int, int, int, int], ...])`
  - `WorkbookCells(sheets: tuple[XSheet, ...], drawing_texts: tuple[str, ...], date1904: bool)`
  - `read_cells(body: bytes, *, isolate: bool | None = None) -> WorkbookCells` (raises `IngestError`, fixed text)
  - `cells_sha256(wb: WorkbookCells) -> str` (the extraction's `words_sha256`)
  - `render_text(wb: WorkbookCells) -> str` (sheet name, then one line per row of cell texts, tab-separated: the
    document text that manual import stores and validates)
  - `serial_date(text: str, date1904: bool) -> date | None`

- [ ] Step 1: tests (synthetic): reads numbers, shared strings, inline strings, bold via `cellXfs`/`fonts`, number
  formats (built-in id 14 and custom `d/mm/yyyy` are dates; `0.0` is not), merges, sheet state, drawing `<a:t>` runs,
  `date1904`. Refusals with fixed text: not a zip, over size/members/ratio/cell budget, encrypted member, unsafe path,
  `vbaProject.bin`, `externalLinks/`, `activeX/`, `embeddings/`, `connections.xml`, macro content type, DOCTYPE/ENTITY
  in any member (UTF-8 and UTF-16), missing sheet target. A formula cell is read as kind `formula` and never evaluated.
  Isolated and in-process results are equal.
- [ ] Step 2: fail. Step 3: implement with `expat` (DTD/entity handlers refuse); child process via the helpers
  `table_words` uses (`_apply_child_limits`, `_child_env`), JSON reply capped. Step 4: pass. Step 5: commit
  `feat(research): bounded stdlib XLSX cell reader`.

### Task 3: `xlsx_anz.py`, the ANZ mapping

**Files:**
- Create: `backend/src/nzstats/research/xlsx_anz.py`
- Test: `backend/tests/research/test_xlsx_anz.py` (uses `xlsx_support` to build a fictional vertical workbook shaped
  like §1: cover sheet, data sheets with dates in column A from row 3, titles merged over 4-column blocks in row 1, unit
  headers in row 2, a bold forecast tail, a legend note and an "as at" note below)

**Interfaces:**
- Consumes: Task 2 types; `table_parse.Period`, `parse_value`, `unit_of_text`; `table_forecast.TableForecast`,
  `_INDICATORS`, `_horizon`, `_third_party`; `table_context.context_rejection`; `table_grid.Rejection`.
- Produces: `INTERPRETER_VERSION = "xlsx-anz-1"`;
  `interpret_anz_workbook(wb: WorkbookCells, *, publisher_names: Sequence[str], document_title: str, workbook_sha256: str) -> tuple[tuple[TableForecast, ...], tuple[Rejection, ...]]`

Rules, each with its fixed code (sheet-level and column-level codes are recorded once, not per cell):

| Condition | Code |
|---|---|
| sheet not visible | `hidden_sheet` |
| no column-A date run, or dates not all on the 1st of Mar/Jun/Sep/Dec, 3 months apart, increasing | `unsupported_period` (monthly sheets included) |
| no note below the table matching `column_kind == "forecast"`-style wording and "bold" | `forecast_marker_missing` |
| column's bold cells are not one contiguous block ending at the last date row | `forecast_boundary_unclear` |
| title + header name no or several of the four indicators | `unmapped_row` / `ambiguous_indicator` |
| `unit_of_text(title, header, sheet name)` gives no unit / a conflicting or unsupported one | `unit_unstated` / `contradictory_unit` / `unsupported_unit` |
| `_horizon(Period("month_end", y, m), label, indicator)` fails | its code |
| `context_rejection` | its code |
| a forecast cell is a formula | `formula_cell` |
| number format not General, `0`, `0.0…`, `#,##0.0…` (optional negative section) | `unsupported_number_format` |
| `parse_value(display)` rejects | its code |

Value: `display` is the stored text rendered to the format's decimal places (General: `repr(float(text))`); `raw_text`
is `display`. Label: `f"{title}: {header}"`. Evidence: `sheet_position`, `cell` (A1), `stored_text`, `number_format`,
`bold`, `workbook_sha256`, `caption` (sheet name), `header_texts` `[title, header]`, `unit_texts` `[header]`, `notes`
(the notes below the table), `document_title`, `publisher_names`. `page` = sheet position, `table` = block number,
`row`/`col` = the cell. Author role: `third_party` when `_third_party(label + notes + headers)` holds, else `author`.

- [ ] Step 1: tests: normal block gives forecasts for the bold tail only, with exact evidence;
  `test_historical_cells_are_never_emitted`; wrong unit (`$m` level column) `unsupported_unit`; OCR without a unit
  `unit_unstated`; monthly sheet `unsupported_period`; missing legend `forecast_marker_missing`; bold gap
  `forecast_boundary_unclear` (Review Focus 2); formula in tail `formula_cell`; float artefact gives `2.1`
  (Review Focus 3); a note naming another forecaster gives `third_party`; hidden sheet `hidden_sheet`;
  `q/q` header gives `Mmm YYYY quarter`, `annual % change` gives `year to Mmm YYYY`, unemployment gives a quarter horizon.
- [ ] Step 2: fail. Step 3: implement. Step 4: pass. Step 5: commit `feat(research): ANZ forecasts workbook mapping`.

### Task 4: import, ingest, view and CLI wiring

**Files:**
- Modify: `backend/src/nzstats/research/manual_import.py` (`FORMATS["xlsx"]`, `_extract` for xlsx via `read_cells` and
  `render_text`; refuse a body that is not a zip)
- Modify: `backend/src/nzstats/research/banks.py` (ANZ `Series("forecasts_workbook", "ANZ Forecasts", "outlook", 100, url_pattern=<owner-supplied address form>)`)
- Modify: `backend/src/nzstats/research/table_ingest.py` (route `format == "xlsx"` to Task 3; `candidate_hash8(forecasts) -> str`; storing an xlsx extraction requires `confirm == candidate_hash8`)
- Modify: `backend/src/nzstats/research/table_view.py` (`_VERSIONS` reads the latest extraction for `tables-14` or `xlsx-anz-1`)
- Modify: `backend/src/nzstats/research/cli.py` (`.xlsx` import suffix; `tables extract VERSION --dry-run --list` prints candidates for the owner's terminal; `--confirm HASH8`)
- Test: `backend/tests/research/test_xlsx_pipeline.py`

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces: `extract_version_tables(..., confirm: str | None = None)`; `TableIngestResult.candidate_hash8: str | None`.

- [ ] Step 1: tests (real registry, synthetic workbook at an ANZ-shaped address): import xlsx, dry run gives counts,
  codes and a hash; store without or with a wrong hash refuses (Review Focus 5); store with the hash stores; figures
  appear in `table_forecasts` under `auto_display` and nowhere in `/api/research/feed`, `/api/private/research/items`
  or `export-snapshot`; a second, revised workbook is a new version whose figures replace the view's but leave the
  first extraction intact (Review Focus 1); a duplicate import is `unchanged`; purge removes the figures.
- [ ] Step 2: fail. Step 3: implement. Step 4: pass; full backend suite and ruff. Step 5: commit
  `feat(research): wire the ANZ workbook through import, tables and the internal view`.

### Task 5: record, pilot and review

**Files:** `docs/phase-4ao-anz-workbook.md`, `docs/progress.md`, `CLAUDE.md`, `docs/data-sources/research.md` if it lists formats.

- [ ] Real pilot per Stage 5: `nzstats backup --bundle` and `verify-backup`; import the owner's file; hash check;
  dry run (codes and counts only in the session); the owner runs `--list` in their own terminal and reconciles every
  candidate; store with `--confirm`; check the internal view and snapshot isolation; rehearse rollback on a restored copy.
- [ ] Independent review (Superpowers `requesting-code-review` and Caveman review), fixes test-first.
- [ ] Commit, push branch, open PR. No merge.
