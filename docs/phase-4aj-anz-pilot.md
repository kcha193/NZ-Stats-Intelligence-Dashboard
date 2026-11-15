# Phase 4AJ: first real ANZ forecast extraction pilot (one Quarterly Economic Outlook)

15 November 2026, Pacific/Auckland. Procedure: [phase-4ag-pilot-procedure.md](phase-4ag-pilot-procedure.md). Decision record for step 0:
[phase-4ai-authorization-assessment.md](phase-4ai-authorization-assessment.md) (PR #62).

**Follow-up: [Phase 4AK](phase-4ak-anz-pdf-compat.md) took option 2 (page-8 header geometry) and reviewed option 3 rule by rule. Page 8 is now read but still gives 0 figures (no marker, no unit); page 5 stays refused. Still NO-GO.**

**Verdict: NO-GO. The pilot is not accepted.** The deterministic extractor read this real ANZ layout safely: it stored nothing
wrong and refused every cell with a fixed code. But it yields **0 storable figures**, so steps 6 and 7 have nothing to extract
or reconcile. Nothing was fetched, no model read the document, and nothing reached a snapshot, Git or a public or private gate.

This record describes the document by codes, pages, counts and layout geometry only. It holds no ANZ text or figure.

## How the document was examined

The brief excluded any hosted or local model reading the bank document. The Claude Code session running the pilot is itself a
hosted model, so it did not read the PDF's text or images. The owner approved a **masked layout skeleton** instead: word
positions and font sizes, with each word replaced by a token class.

- Numbers become digit shapes (`9.9`).
- Only periods, units and a fixed list of generic economic terms (GDP, CPI, OCR, Actual, Forecast) were kept.
- Every other word became a length placeholder (`W5`).

Diagnosis scripts printed only codes, pages, counts and booleans, and were kept out of the repository. No reconciliation sheet
was produced, because no figure was extracted. The owner's by-eye reconciliation (step 7) remains the acceptance check for
any future figure.

## Steps

| Step | Result |
|---|---|
| 0 Preconditions | Met. The registry change was merged (PR #62); `auto_display` was on; `pdfminer.six` 20260107 was installed; no ANZ document was held (`bank-status`: `missing`). |
| 1 Backup | `~/nzstats-backups/pre-anz-pilot-20261115`, verified (schema 15, 53 raw artifacts). The first attempt ran from `backend/` and was refused: see finding F1. |
| 2 Import | `nzstats research import anz … --published-on 2026-11-11` gave publication 4, **version 4**, sha256 `52f22fc4f4d3…`. This matches the `shasum` of the saved file. |
| 3 Identity | The hash matches. The cover date is 11 November 2026 (boolean check on pages 1–2). The PDF has 15 pages and is 2.2 MB. `bank-status` reports ANZ `economic_outlook` `ok`, published 2026-11-11. |
| 4 Dry run | **0 figures, 23 rejections**: `no_header` ×15, `mixed_layout` ×4, `ambiguous_columns` ×3, `scenario_table` ×1. Reader `pdf-words-4`, interpreter `tables-13`. |
| 5 Rejections | Every rejection was reviewed by page (below). The tables of interest are all refused, which means stop under the procedure. No rule was loosened. |
| 6 Extract | Not run: there is nothing to store. A refusal-only extraction row is immutable and would add nothing. |
| 7 Reconcile | Not applicable: 0 figures. |
| 8 Bank Outlooks | Served offline on loopback from the repository root. The internal API showed the ANZ card `ok`, vintage `not_read`, 0 forecasts, 0 comparison rows, an empty consensus and no revisions; the other four banks showed `permission_denied`. The server log showed no outbound request. |
| 9 Isolation | `export-snapshot` + `validate-snapshot --for-publish` gave a valid snapshot: 250 files, origin production. It held no ANZ document, hash, URL, series or bank route. The only "anz" match was Stats NZ's `ANZSIC06` industry code. `git status` showed no document or data file. Before the fix, the export failed from the documented `.env` setup: see finding F2. |
| 10 Revocation | Not rehearsed (outside this brief). The import and the backup stay in place for the owner's decision. |

## Rejection map

| Page | What the layout is (masked) | Codes | Assessment |
|---|---|---|---|
| 5 | "Table 1" key-forecast summary: calendar years 2021–2025 (unmarked) and 2026f–2028f; rows: real GDP, unemployment rate, CPI inflation, OCR | `scenario_table` | **Correct by design.** See below. |
| 5, 12, 15 | prose sharing a baseline with figures | `mixed_layout` ×4 | Correct: not a table. |
| 8 | two financial-market tables (exchange rates; interest rates incl. OCR): a "Current" column and 8 quarter-end columns | `ambiguous_columns` ×2 | **Correct, a reader capability gap.** See below. |
| 12 | a release calendar | `ambiguous_columns` ×1, `no_header` | Correct: not a forecast table. |
| 2–4, 6–13 | figures in prose, chart axes and footers (pages 9–11 are chart pages) | `no_header` | Correct. |

**Page 5, the four indicators of interest.** The caption walk in `table_grid._candidates` climbs from the "Table 1" label
through the paragraph above it. That paragraph discusses upside risks and the central forecast, so the table is refused as a
scenario. The walk does this on purpose: a scope heading above a labelled caption ("Youth unemployment") cannot be told from a
paragraph by geometry, and `test_two_caption_lines_preserve_earlier_scope` pins that the heading still refuses.

A narrower walk was tried test-first and **reverted** when the full suite failed that pin. Even with the narrower walk, every
cell stayed refused under rules that are correct by design:

| Cells | Code | Why |
|---|---|---|
| CPI 2026f–2028f | `unsupported_context` | The stored document title has five words outside the neutral vocabulary (an editorial title). `test_unrepresented_document_title_is_refused` pins this. |
| Real GDP | `footnote_unresolved` | The row label carries a footnote marker. |
| Unemployment rate, OCR | `unit_unstated` | The labels state no unit. |
| 2021–2025 | `actual_or_forecast_unstated` | These columns carry no Actual or Forecast marker; 2026f–2028f do. |

A regression pin now records the lesson:
`test_scenario_words_in_prose_above_a_labelled_caption_refuse_the_table`.

**Page 8.** The "Current" column header is set on two lines: "Current" above a date. These two lines straddle the baseline of
the quarter headers (`Dec-26` … `Sep-28`), so the lowest header line holds only the date fragment. `_columns` takes that line
as the column base, finds one column, and refuses the quarter headers as starting in a gap.

This refusal is safe. Reading the table would need a new geometry rule: merging stacked header lines that straddle the period
line. That is a reader capability, not a loosening. It would start with a synthetic fixture and a failing test, and it would
need a new interpreter version. It is not done here.

## Findings

- **F1 (procedure defect, fixed in docs).** `.env` sets `NZSTATS_DATA_DIR=./data`, which resolves against the working directory.
  The pilot procedure's step 8 (`cd backend && … nzstats serve`) and any command run from `backend/` open a stale
  `backend/data/nzstats.db`. That file is from 8 November, schema 14, and lacks two migration-010 triggers. `nzstats backup`
  refused it correctly ("missing trigger research_claim_not_purged"). `scripts/run.sh` and every pilot command must run from the
  repository root. The procedure now says so. Deleting the stale file is the owner's decision; this phase did not touch it.
- **F2 (code defect, fixed test-first).** `export_snapshot` scrubbed `str(data_dir)`. For the documented relative data dir that
  string is the bare word `data`, so every export from the default setup failed ("contains forbidden text: 'data'"). The scrub now
  uses the resolved path. The new test `test_a_relative_data_dir_exports` failed before the change and passes after it.
- **F3 (layout lessons for the owner).** ANZ's key forecasts are annual (calendar-year) figures with an `f` suffix on forecast
  years; the quarterly path appears only for the OCR and market rates (page 8). The four indicators of interest sit in one
  five-line table directly under prose, and the document's own title is editorial.

## Options for the owner (none taken)

Each option is a separate, documented decision. None is a quiet loosening.

1. **Stop here.** The extractor stays as strict as it is. The next Quarterly Economic Outlook (February 2027) will probably give
   the same result.
2. **Page 8 header geometry.** Teach the grid to read a two-line header cell that straddles the period line. This is the most
   principled next step and would reach the quarterly OCR path. The "Current" column has no Actual/Forecast marker and would
   stay refused.
3. **Rule reviews**, one by one, each with its own evidence and tests:
   - an owner-supplied report title that overrides an editorial PDF title;
   - a unit for named rate indicators whose label states none;
   - footnote resolution for the GDP row.
   The caption walk should **not** be narrowed (see page 5).
4. **The ANZ forecasts workbook** is outside the Phase 4AI scope; using it would need a fresh scope decision.

## Verification

- Backend: full `pytest`, `ruff check`, `ruff format --check` (results in the PR).
- Real document after the change: the dry run is unchanged (0 figures, 23 rejections, `tables-13`).
- Snapshot: export and `--for-publish` validation passed from the absolute data dir. The relative case is covered by the new test.
