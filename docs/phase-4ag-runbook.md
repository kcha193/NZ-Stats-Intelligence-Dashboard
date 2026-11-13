# Phase 4AG runbook: the glyph-level PDF reader and the first-bank pilot

14 November 2026, Pacific/Auckland. Companion to the [Phase 4AF runbook](phase-4af-runbook.md), which still applies.

**No live ingestion exists for any bank and no permission field was changed.** Every command below is local and offline.
Today all five banks refuse them ([permissions package](phase-4ag-anz-permissions-package.md)).

## What changed for an operator

| Before (4AF) | Now (4AG) |
|---|---|
| word reader `pdf-words-1` (`pypdf`), a `BT..ET` row came back as one string | `pdf-words-4` (`pdfminer.six>=20251230`), every cell is its own word with its true right edge; unresolved glyph overlays refuse the PDF |
| interpreter `tables-10` | `tables-13`; older extractions, including `tables-11` and `tables-12`, stay stored and stop feeding the analytics, so a held PDF is re-extracted once to appear again |
| dry run printed counts | dry run also prints each rejection code with its count, the reader and the interpreter version |
| prose beside table rows made the table vanish without a code | reported as `mixed_layout` |
| `Mar-26` and `Jun-26` in a narrow gutter could merge into one header | period headers, month-only headers and figures are separate cells; double-struck (fake bold) text is read once |

Install the research extra so the reader exists: `pip install -e 'backend[research]'` (or the `dev` extra). Without it,
extraction refuses with `pdf_support_not_installed`.

## Commands

```sh
nzstats research tables extract VERSION --dry-run   # counts, rejection tally, reader and interpreter versions; writes nothing
nzstats research tables extract VERSION             # store (rerunning with the same reader and interpreter is a no-op)
nzstats research tables show VERSION [--json]       # stored figures and rejection codes; names the interpreter and says NOT CURRENT for an older one
nzstats research bank-status [--json]               # state of each bank source
```

A held PDF extracted under an older reader or interpreter is read again and stored as a **new** extraction; the previous rows
are not changed. Reads use the latest extraction, and analytics use only the current interpreter.

## Rejection codes you may see (new and unchanged)

| Code | Meaning | Usual cause on a real report |
|---|---|---|
| `mixed_layout` (new) | a would-be table row shares its baseline with text | prose or a note set in a column beside the table |
| `ambiguous_columns` | a value or header straddles columns, or headers overlap | very narrow gutters, centred headers, a row shifted by a column |
| `footnote_unresolved` | a footnote marker sits on the figure (including a raised marker the reader kept) | superscript marker after a figure |
| `scenario_table`, `scenario_row`, `scenario_column` | a scenario, downside or sensitivity | alternative-scenario tables |
| `actual_or_forecast_unstated` | a column with no Actual or Forecast marker | table that does not say |
| `no_header`, `unjoined_continuation` | a body with no usable header, or a continuation that cannot join | page break without a repeated header |
| `unmapped_row`, `ambiguous_indicator`, `unit_unstated`, `contradictory_unit`, `unsupported_unit`, `period_basis_unstated`, `contradictory_period`, `unparsed_period`, `bracketed_value`, `unrecognised_suffix`, `value_out_of_range` | as in [phase-4af-pdf-tables.md](phase-4af-pdf-tables.md) | |

Reader refusals (fixed wording, shown as `pdf could not be read (...)`): `no_text_layer` (no extractable text),
`rotated_text_only` (the only text is sideways), `pdf_extraction_limit (words|characters|content|layout depth)`, `pdf has too many pages`,
`pdf is encrypted`, `pdf_support_not_installed`, `unreadable pdf (ErrorType)`,
`ambiguous_glyph_overlap` (overlapping glyphs beyond recognised overprints and normal kerning; the whole PDF is refused).

## Reading a result that gave nothing

1. `no_text_layer`: the PDF is scanned or image-only. OCR of bank reports is not authorised. Stop.
2. `rotated_text_only`: the page text is sideways in display. Not read, by design.
3. Zero figures and `mixed_layout`: prose shares the table's baselines. Not read, by design; open the PDF to confirm.
4. Zero figures with `ambiguous_columns` on the table of interest: a layout the grid will not guess. Reproduce the layout with a
   **synthetic** fixture and a failing test before any code changes. Never loosen a rule to extract more.
5. A figure present in the PDF but absent without any code: that is a defect; stop and add a failing synthetic test.
6. `ambiguous_glyph_overlap`: unresolved glyph geometry; stop and reproduce with a synthetic fixture. No figure is accepted.

## Rollback

Code: revert the Phase 4AG commits; `pdfminer.six` can stay installed. Data: nothing was migrated (no schema change), so there
is nothing to roll back; stored extractions are removed only by `research purge`. To stop showing figures:
turn `auto_display` off, or revoke the route, or purge ([pilot step 10](phase-4ag-pilot-procedure.md)).

## What this phase never does

It never fetches, never lowers the 10-second delay, never works around a 403, robots rule or challenge, never sends text to a
model, never schedules, and never adds bank text or figures to Git, a snapshot, or the public or private gates.
