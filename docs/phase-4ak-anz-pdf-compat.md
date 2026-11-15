# Phase 4AK: real ANZ PDF compatibility remediation

15 November 2026, Pacific/Auckland. Baseline: main `178ccd7` (Phase 4AJ, PR #63). Document: the already-imported ANZ Quarterly
Economic Outlook, **version 4** (dated 11 November 2026). Reader `pdf-words-4` (unchanged); interpreter `tables-13` → **`tables-14`**.

**Verdict: NO-GO for the pilot (0 accepted figures). The extractor improved, and nothing was accepted wrongly.** Page 8's two
tables are now read cell by cell instead of being refused for their layout. Every cell is still refused, for reasons the source
creates (no stated unit, no Actual/Forecast marker). Page 5 stays refused: each blocking rule was investigated, and no
structural change was safe. A latent attribution fail-open found during the work was fixed test-first.

This record describes the document only by codes, pages, counts and layout geometry. It holds no ANZ text or figure.

## Method and privacy boundary

Same as [Phase 4AJ](phase-4aj-anz-pilot.md): the Claude Code session did not read the PDF's text or images. It used a masked
layout skeleton: word positions and sizes, with numbers turned into digit shapes and every other word turned into a length
placeholder, except periods, units and a fixed list of generic structural words. Diagnosis scripts lived outside the repository
and printed codes, pages, counts and booleans. They also ran what-if checks: the current interpreter on a modified table object,
with nothing written. Every fixture in the repository is synthetic. Nothing was fetched, no model (hosted or local) read the
document, nothing was written to the database, and the document was not re-imported.

## Stage 1: page 8, a header stacked across the period line

**Original failure.** Page 8 holds two market tables (exchange rates; interest rates, including the OCR). Each has a "Current"
column whose header is set on two lines: "Current" 0.59 em above the quarter-end headers and a bracketed date 0.61 em below
them. `_columns` took the **lowest** header line (the date fragment alone) as the column base. It found one column and refused
the quarter headers as starting in a gap: `ambiguous_columns` ×2.

**Rule (`table_grid._stacked`).** It runs only when a header line other than the lowest has more cells. Otherwise the old path is
unchanged.

1. The period line is the **one** header line with the most cells. A tie is refused.
2. A header line less than one font size from the period line cannot be a row of its own, because its glyphs would collide. Its
   cells are fragments of stacked cells.
3. Fragments that all overlap one another horizontally form one stacked cell, with one fragment per line. The cell must have
   fragments both **above and below** the period line. Its text is the fragments top to bottom ("Current (date)").
4. A stacked cell that overlaps a period header is refused. So is a separate header line a full line or more below the period
   line (refused, never dropped).
5. Lines a full line or more above remain group headers, as before. A group over the quarters does not reach the stacked column.
6. `header_rows` keeps every original fragment with its own line, position and text (provenance).
7. No Actual/Forecast marker is inferred. The stacked column parses as no period and carries no marker, so it stays refused.

**Independent review** (no access to the document) found nothing blocking. Two findings were pre-existing and are now fixed
test-first, both as refusals:

- Two group headers starting over one column used to drop the first silently. They are now `ambiguous_columns`.
- On the old path, a line less than 1 em above the period line was accepted as a group header over every column. It is now refused.

**Tests** (`test_table_stacked_headers.py`, run under both PDF draw styles; 20 scenarios). Each new guard was mutation-checked:
removing it fails at least one test. The tie rule is defence in depth; the reviewer confirmed that the other rules already refuse
a tie.

**Result on version 4.** Both page-8 tables are read: 9 columns each, with 6 and 4 rows. No figure is accepted, because:

| Cells | Code | Why (from the masked layout) |
|---|---|---|
| all 9 columns of both tables | `actual_or_forecast_unstated` ×18 | Neither "Current" nor any quarter column carries an Actual/Forecast marker; "Forecasts" appears only in the first table's caption, which is not a column marker |
| OCR row | `unit_unstated` | No `%` or unit word in the label, caption, notes or headers |
| other 9 rows | `unmapped_row` | Exchange rates and other market rates: not indicators of interest |

**Valid OCR forecasts recovered: none.** Recovering them would mean assuming a unit and a forecast marker that the table does not
print. The brief rules both out.

## Stage 2: page 5, the key-forecast table, rule by rule

What-if checks (current interpreter, modified table object, nothing written): with the prose removed from the caption **and**
the title blanked, the table would give CPI 2026f–2028f. With either one present, it gives nothing. Page 5 therefore needs two
independent relaxations. Neither was made:

| | Original failure | Decision | Reason |
|---|---|---|---|
| A. Caption | `scenario_table`: the caption walk takes in a five-line paragraph about upside risks to the central forecast, which sits 4 em above "Table 1" | **Refusal kept** | A paragraph that introduces a scenario table ("the table below shows our downside scenario") has the same geometry as this one: same column, same leading, same gap. Its width, line count and gap cannot separate it from a scoping heading or scoping prose. Excluding prose would accept genuine scenario tables as central. `test_scenario_words_in_prose_above_a_labelled_caption_refuse_the_table` stays as the pin. |
| B. Title | `unsupported_context` on CPI: the PDF's `/Title` metadata (the `--title` option is only a fallback) is "publisher + publication phrase: headline". The part before the colon is fully neutral; the 7-word headline has 5 words outside the neutral vocabulary | **Refusal kept** | The only rule that passes this title exempts the headline after the colon from the unknown-word check. That check is the sole guard against unlisted qualifiers ("Nominal", "Median", "Adults", "Canterbury edition"), so the exemption would discard genuine scope. It is the general title bypass the brief rules out. The pins `test_unrepresented_document_title_is_refused` and `test_document_title_scope_is_not_discarded` stay. |
| C. Units | `unit_unstated` on unemployment and OCR | **Refusal kept** | Their labels, the caption, the notes and the headers print no `%` or unit word. GDP and CPI print `%` in their own labels. No traceable evidence for the other two. |
| D. GDP footnote | `footnote_unresolved` on the GDP row | **Refusal kept; the note walk was fixed** (below) | The footnote definition is two words in the source. Reading them would put report text in agent context, so only the owner can judge them. Even when understood, a footnote that qualifies how GDP is measured would need a fixed phrase map and an identity decision. GDP is also blocked by A and B. |
| E. Actuals | `actual_or_forecast_unstated` on the five unmarked years | **No change needed** | Unmarked historical columns stay excluded. The `f`-marked years are read when otherwise valid. Before the note fix, the what-if showed CPI 2026f–2028f passing every column rule. |

### D finding: notes under a small-digit footnote marker were never read (fixed)

**Original failure (latent fail-open).** Below the page-5 table, the footnote marker is set as a small plain digit on its own
line (size 5 against the table's 8.5). The note walk did not recognise that line, so it stopped there. It never read the source
line beneath, which names organisations other than the bank. A synthetic reproduction:

- a table with `Source: RBNZ` directly underneath is attributed `third_party`;
- the same table with a small-digit footnote between them is attributed to the **publisher**.

**Fix (`table_grid._small_marker`).** A footnote marker is a lone digit 1 to 99, at most 0.75 × the table's text size, set
directly under a table at the row-label column (within one em). It starts a footnote note, and its digit is written as the
superscript marker, as the word reader already writes a raised marker. The walk then continues to the definition, the source
and the lines beneath. A line continues the marker's note only when it starts right of the marker (a definition wrapping under
its own text). A line back under the marker starts a new, unmarked note, so any qualifier in it still counts.

This only adds evidence:

- Marker-specific notes still do not qualify unmarked cells.
- A footnoted label stays `footnote_unresolved`.
- A full-size digit, a small digit away from the row labels (a chart tick or page number) and `0` are not markers.

A second independent review found the position, `0` and margin-line cases; each was fixed test-first. Tests:
`test_table_footnote_notes.py` (9). Each guard is mutation-checked.

**Effect on version 4.** The page-5 table now carries 2 notes. Its refusal is unchanged (`scenario_table` is decided first).
The what-if confirms the evidence now counts: had A and B been relaxed, the CPI cells would no longer be three publisher-attributed
figures. The source line makes them third-party, and a dated sentence in the notes refuses two of the years as
`contradictory_period`.

## Stage 3: re-extraction (dry run only)

Checks before any write:

- Run from the repository root; database `./data/nzstats.db`.
- Backup `~/nzstats-backups/pre-anz-pilot-20261115` verified (schema 15, 53 raw artifacts).
- Registry and permissions unchanged (no diff; ANZ `ok`, the other four banks `permission_denied`).
- Version 4 present once; no table extraction stored.

| Code | Before (`tables-13`) | After (`tables-14`) | Classification |
|---|---|---|---|
| accepted figures | 0 | 0 | |
| `no_header` | 15 | 15 | unchanged (prose figures, chart axes, footers) |
| `mixed_layout` | 4 | 4 | unchanged |
| `ambiguous_columns` | 3 | 1 | −2: the page-8 tables are now read; the page-12 release calendar is unchanged |
| `scenario_table` | 1 | 1 | unchanged (page 5, decision A) |
| `actual_or_forecast_unstated` | 0 | 18 | new, correct: page 8, 9 unmarked columns × 2 tables |
| `unmapped_row` | 0 | 9 | new, correct: page-8 rows other than the OCR |
| `unit_unstated` | 0 | 1 | new, correct: page-8 OCR row |
| **total rejections** | **23** | **49** | more, finer-grained refusals; no page other than 8 changed its codes |

**Extraction was not run.** There is nothing to store, and a refusal-only extraction row is immutable and adds nothing (as in
4AJ). Historical evidence is unaffected: no extraction was stored under any interpreter. A held PDF extracted under `tables-13` or
earlier remains stored and stops feeding the analytics until it is re-extracted (`tables-13` was added to the legacy pins).

## Stage 4: acceptance

- **Human reconciliation:** nothing to reconcile (0 accepted values). For any future figure, the owner checks every accepted
  value against the PDF on these points: indicator, number, sign and decimals, unit, target period (calendar versus quarter-end),
  forecast versus actual, attribution to the bank (not a source, scenario or other forecaster), footnotes and scenarios, and
  publication vintage. Use the sheet in [phase-4ag-pilot-procedure.md](phase-4ag-pilot-procedure.md), step 7. Any wrong figure
  means NO-GO.
- **Bank Outlooks display:** unchanged from 4AJ (no figure stored; API, view and frontend untouched). There is no consensus from
  one bank, and the freshness rules are unchanged.
- **Isolation:** `export-snapshot` and `validate-snapshot --for-publish` gave a valid snapshot (250 files, origin production). The
  only "anz" text is Stats NZ's `ANZSIC06` code. `git status` shows only code and test files.
- **No network or model calls:** the dry runs read the stored copy only; the CLI says so on every run.

## Remaining correctness risks

1. **Notes can carry dates.** A dated sentence in a table's notes is read as period context and can refuse forecast years
   (`contradictory_period`). This fails closed, but it may refuse valid figures once notes are attached more often.
2. **Stacked headers allow several lines on one side.** A three-line stacked header is accepted when all its fragments overlap. No
   text is dropped, but the joined header text may read oddly.
3. **The old path's new 1 em rule.** A real table whose group header sits less than 1 em above its period headers (very tight
   leading) is now refused. This is safe, but it may refuse a layout that used to be read correctly. No current fixture or real
   layout was affected.
4. **Page 5 depends on the owner.** Its refusals rest on rules (A, B) that are correct by design. Any future acceptance there needs
   an owner decision, not a looser rule.

## Recommendation for Phase 4AL

Do not loosen A or B. Even with both relaxed, the attached notes now leave at most one page-5 CPI figure, and it would be marked third-party. So page 5 is unlikely to yield figures attributed to ANZ under the current rules. Options, each a separate owner decision:

1. **Owner title attestation** (decision B). For one version, the owner records that its PDF metadata title is editorial and
   does not scope the tables. Store it as a per-version record with the approver and date, carry it into the evidence, and have
   `stored_context_rejection` re-check it. It is a governance record, not a heuristic, and nothing is general.
2. **Wait for the next outlook** (February 2027). Its layout may differ. Run the dry run and diff the rejection map against this
   record.
3. **Unit evidence for the OCR path** would have to come from the source. A per-table unit note printed in the report would be
   read today. Nothing should assume `%`.
