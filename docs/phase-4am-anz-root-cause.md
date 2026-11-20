# Phase 4AM: ANZ forecast extraction root-cause audit

20 November 2026, Pacific/Auckland. Branch `audit/phase-4am-anz-root-cause` from main `aba4e4e` (Phase 4AL, PR #65 merged).
Document: the already-imported ANZ Quarterly Economic Outlook, **version 4** (dated 11 November 2026). Reader `pdf-words-4`,
interpreter `tables-14`, both unchanged.

**Verdict: NO-GO. No production change. 0 accepted figures, and no defensible deterministic rule produces any.** Every
blocker was traced to the text that causes it. The tables are read correctly. The refusals come from what the report prints
(no forecast marker, no unit) and from evidence that really is ambiguous (scenario prose, an editorial title, a dated source
line, a source line that names another forecaster beside ANZ).

On page 5, three relaxations together (caption prose, title, source-line date) would accept 3 CPI figures. All 3 would still be
attributed to a third party, so none would count as an ANZ forecast: `table_view` keeps third-party figures out of the bank
comparison (`table_third_party`). A fourth relaxation, on attribution, would be needed to make them ANZ's. On page 8, printed
markers and units would not be enough either: caption and title context still refuse every cell. PyMuPDF was not tried,
because no layout defect was found.

This record describes the document only by counts, indices, booleans and fixed codes. It holds no ANZ text or figure.

## Method and privacy boundary

- The Claude Code session did not read the PDF's text or images, and no model read the document. Two things touched the
  real document: the masked probes and the CLI dry-run tally (§4).
- The probes are in [`benchmarks/pdf_tables/probes/phase_4am/`](../benchmarks/pdf_tables/probes/phase_4am/), and their outputs
  in `benchmarks/pdf_tables/results/phase-4am/`. They ran on the owner's machine. Each probe:
  - opens `data/nzstats.db` read-only and passes the same registry gate and SHA-256 check as `tables extract`;
  - runs the production reader and grid with every stream silenced;
  - prints only ints, booleans and production codes, through a guard that refuses any other string.
- `probe_attribution.py` classifies the institutions a source line names. Its committed output (`--collapse`) shows only a
  count. The class split was printed on the owner's terminal and kept out of this record.
- What-if checks ran `table_forecast.interpret` on modified `GridTable` copies. Nothing was written, fetched or re-imported.
- Database SHA-256 was unchanged before and after every run. stderr was 0 bytes on every run.

## 1. Phase 4AL benchmark verification

PR #65 is merged (`aba4e4e`, 20 November 2026). The owner re-run that §12 of the
[Phase 4AL record](phase-4al-pdf-parser-benchmark.md) asked for was done: `run_masked 4 --pages 5 8` under the final scoring and
agreement rules. All non-timing values were compared with the committed result, and 4 changed. All 4 are `plumber_text` on page 8:

| Metric | Before | After | Cause |
|---|---|---|---|
| `numeric_cells` | 108 | 116 | leading-decimal tokens (`.25`) now count as numeric |
| `multi_number_cells` | 4 | 8 | the same |
| `unreproduced_reasons.header_mismatch` | 19 | 0 | reasons now judged one-to-one on unused cells, with the foreign-header rule |
| `unreproduced_reasons.value_missing` | 21 | 40 | the same 19 cells, reclassified |

`agreement_with_existing` did not change for any parser. `tables-14`, Camelot (all flavours) and the pdfplumber skill modes
are unchanged. The Phase 4AL recommendation stands. `results/masked-v4-pages-5-8.json` now holds this run.

### The disputed page-5 row label (8 cells)

The row is `tables-14` body row 0 of the page-5 table (grid row 1 in the harness). It holds 8 figures, and its label has
6 words. Camelot `network` puts the same 8 figures on one row whose label also has 6 words (`results/phase-4am/label.json`).
Word by word:

| Label word | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| exact match | yes | **no** | yes | yes | yes | yes |
| match after mapping a superscript to a plain digit | yes | **yes** | yes | yes | yes | yes |

Word 1 carries a raised footnote marker fused to it. `tables-14` keeps the marker as a superscript. Camelot reads it as an
ordinary digit glued to the word. So the dispute is **probably a footnote-marker encoding difference, not a wording difference**.
Phase 4AL said "not a footnote effect" because it checked only for a marker at the end of a label. Agreement is not truth, so
this stays probable until the owner confirms it:

**Owner check (local only; do not paste any text into a hosted session):**

1. Open the stored PDF in a local viewer.
2. Go to page 5, Table 1, first data row (the row with a footnote marker).
3. Check that the label has six words.
4. Check that the second word ends in a raised footnote marker, not a full-size digit.
5. Report only yes or no for each check.

## 2. Semantic blocker root-cause matrix

What-if results (`results/phase-4am/semantics.json`; accepted figures; `interpret` on modified copies, nothing written):

| Variant | Accepted | Page-5 codes |
|---|---|---|
| baseline | 0 | `scenario_table` ×1 |
| caption cut at the `Table N` text | 0 | `actual_or_forecast_unstated` ×5, `unit_unstated` ×2, `contradictory_period` ×2, `footnote_unresolved` ×1, `unsupported_context` ×1 |
| + document title blanked | 1 (CPI, `third_party`) | the same, without `unsupported_context` |
| + source-line years removed | 3 (CPI, `third_party`) | no `contradictory_period` |
| + source line removed | 3 (CPI, `author`) | no `contradictory_period` |
| title blanked only | 0 | `scenario_table` ×1 |

Page 8 gives 0 in all of these. Its own what-if (`results/phase-4am/page8.json`) supplied an `f` on every month-end column and a
`%` on the OCR label. The OCR cells are still `unsupported_context` ×8, with the title or without it. They pass only when the
caption is also removed and the title blanked, and then all 8 are `third_party`. The 2 "Current" columns stay
`actual_or_forecast_unstated` throughout.

| | Root cause | Evidence (masked) | Component | Safe fix? | Remaining uncertainty |
|---|---|---|---|---|---|
| **A. Scenario contamination** | The caption walk (`table_grid`: lines up to 5 em apart) climbs past the `Table N` line into the paragraph above. That paragraph carries the scenario words, the unknown words and an institution name. | Page-5 caption: the `Table N` part has 8 words, with 0 scenario words, 0 unknown words, no years and no institution. The 67-word prose part has 2 scenario words, 34 unknown words and 1 institution from the fixed list of other forecasters, so `_third_party` is true. | `table_grid` caption walk → `interpret` (`scenario_table`), `context_rejection`, `_author_role` | **No.** A heading that scopes the table can sit above the `Table N` line, and geometry cannot tell it from prose (`test_scenario_words_in_prose_above_a_labelled_caption_refuse_the_table`). So the walk must keep reading it. Separating the prose's scenario words from its other content would need its wording judged, which is semantic. The boundary alone gains 0 figures. | Whether this paragraph scopes the table. 4AK: it discusses upside risks to the central forecast. Owner judgement. |
| **B. Document metadata** | `context_rejection` applies the PDF `/Title` as context. The publisher and publication phrase are neutral. The headline after the colon has 5 words outside the neutral vocabulary. | Title: 0 unknown words before the colon, 5 after; 0 scenario words; names the publisher only. | `table_context.context_rejection` (`unsupported_context`) | **No.** Exempting the headline drops the only guard against unlisted qualifiers (4AK decision B). | Owner title attestation (4AK option 1) is a governance record, not a rule. |
| **C. Attribution** | The page-5 source line names ANZ, Stats NZ and one institution from the fixed list of other forecasters. By design, naming the publisher beside another forecaster does not make the figures the publisher's. The page-8 interest-rate source line names ANZ and one institution from the same list. | Page-5 source line: names the publisher and the statistics agency, plus 1 listed other forecaster, so `_third_party` is true. Page-8 table 2 source line: publisher plus 1 listed other forecaster. | `table_forecast._author_role` / `_third_party` | **No.** This sets the role, not acceptance. Third-party figures are stored but kept out of the bank comparison. Whether the named institution supplied history or the forecasts is not stated in a form a rule can read. | Owner: for each table, does the named institution supply only historical or current data? Figures are not assigned to ANZ without that evidence. |
| **D. Markers, units and table context** | Not printed. Page-8 columns carry no Actual/Forecast marker (no group header, no `f`, no notes on table 1). "Forecasts" is only in table 1's caption, which also covers a "Current" column. The OCR row prints no `%`. Page 5: unemployment and OCR print no unit, and the first 5 years carry no marker. Even with markers and units, each page-8 caption has 2 words outside the neutral vocabulary, and those words, with the title, refuse the cells. | Page 8: 9 + 9 columns `kind=unknown`, 0 group headers, no `%` in any header, caption or label. Page 5: 3 `f` columns read as `forecast`, 5 `unknown`. Unemployment and OCR labels `unit=none`; CPI and the footnoted row print `%`. Page-8 what-if: `unsupported_context` ×8. | `table_parse.column_kind`, `unit_of_text`; `context_rejection` | **No.** Inferring `%` or forecast status is ruled out, and the caption words are unrepresented context. | None for markers and units: these are source facts. |
| **E. Footnotes and periods** | The footnote is applied to the correct cells. The marker-specific note (3 words) is excluded from unmarked cells, and the footnoted row is `footnote_unresolved`. The page-5 source line holds a date (1 month, 1 year, in its first sentence). The year matches exactly one column year. `_columns` passes the caption and unmarked notes to `period_of` as group headers, so that year refuses every column with a different year. | In production the 5 unmarked columns are refused first (`actual_or_forecast_unstated`). Of the 3 `f` columns, the 2 whose year differs are `contradictory_period`. On pages 5 and 8, no column's period was changed by context (`redefined=false` for every column): here a date only refused. | `table_forecast._columns` → `table_parse.period_of` | **No change now.** It fails closed in this document. In general, caption or note text can recast a month-end period as a quarter or a year-to period, through the group-header rules (`period_of`). That is intended for real group headers, and it applies to notes too. A candidate rule, "a source line is attribution evidence, not period evidence", is general. But it removes a check and gains 0 figures on its own (A, B and C still block). Recorded, not implemented. | Whether any bank prints a real period constraint inside a source line. |

Further findings, all fail-closed with no change:

- The footnoted row's indicator reads as `none`, because a superscript glued to the indicator word defeats `\bgdp\b`
  (superscripts count as word characters). `footnote_unresolved` is decided first, so nothing changes today. A future footnote
  resolver must strip the marker before matching the indicator.
- Page-8 table 1's six rows are exchange rates (`unsupported_unit` from their currency labels). Table 2's non-OCR rows are
  market rates (`unmapped_row`).

## 3. Implementation decision

None of A to E meets all five conditions in the brief. A and C need a semantic or ownership judgement. B and D would bypass
`unsupported_context` or assign missing units and markers. E is a real over-refusal but not a correctness defect: nothing wrong
is accepted, and fixing it alone yields nothing.

**No production code, test or interpreter version changed.** The brief's code-change verification (TDD, review, backup and
rollback, snapshot isolation) therefore does not apply. Checks run on this branch:

- backend `pytest -k table`: 1,161 passed;
- benchmark suite: 155 passed;
- the dry run below matches Phase 4AK.

Accepting the three CPI figures as ANZ's would take four per-version owner attestations:

1. the prose is not a scenario;
2. the title is editorial;
3. the source-line date is an as-at date;
4. the named institution supplied only history.

That would be manual forecast entry under another name, which the brief rules out.

## 4. Real-document dry run (`nzstats research tables extract 4 --dry-run`, repository root)

`0 figures, 49 rejections`: `no_header` ×15, `mixed_layout` ×4, `ambiguous_columns` ×1, `scenario_table` ×1,
`actual_or_forecast_unstated` ×18, `unmapped_row` ×9, `unit_unstated` ×1. This is identical to the Phase 4AK `tables-14` tally.
Nothing was requested, no model was used, and nothing was stored.

## 5. Optional PyMuPDF check: not run

The brief allows it only for a specific layout defect PyMuPDF could fix. None was found. `tables-14` reads the page-5 table and
both page-8 tables cell by cell, and the one disagreement (§1) is probably Camelot's marker encoding. So the AGPL review was not
needed.

## 6. Recommendation for the next milestone

1. **Stop work on version 4.** Its refusals are correct, and more rules would be ANZ-shaped heuristics.
2. **February 2027 outlook:** run the dry run and `run_masked` first, then the phase-4am probes. Diff the rejection map
   against §4 and the blocker matrix. Accepted ANZ figures need all of these at once: printed `f` markers and units on the rows
   of interest, caption and title wording inside the neutral vocabulary, and a source line that names no other forecaster.
3. **If a later document is blocked only by E or attribution,** add a rule then, test-first and under a new interpreter
   version, with real-document evidence that it gains correctly attributed figures. The candidates are "source lines are not
   period evidence" and an exemption for a supplier of actuals.
4. **Generic `tables-14` gap from 4AL:** the stub-headed `no_header` refusal. It is independent of ANZ and has a synthetic
   regression case ready.
5. The owner check in §1 closes the Phase 4AL dispute. No code depends on it.

## 7. Probe limitations

- The "caption cut" what-if slices the joined caption at the last `Table N` match. Production's caption test (`_CAPTION`)
  matches at the start of a line. The two are equivalent here (one match, at the start of a line), but not in general.
- `probe_semantics.py`'s `with_context` column calls `period_of` whatever the column's kind. Production refuses unmarked
  columns earlier, so §2 E quotes production counts (2 `contradictory_period`), not the probe's 7.
- The first probe run counted no column years for `f`-suffixed headers (a regex word-boundary bug). It was fixed and
  re-run. Every other value and every what-if was identical.

## 8. Independent review

A fresh-context reviewer read the code, this record and the masked outputs. It was barred from `data/` and from running anything
on the document. It found no Critical issue and agreed with the NO-GO: it found no deterministic, general, safe rule that the
audit missed. Fixed from its findings:

- Page 8 was overclaimed. A what-if was added (§2), and §6 corrected.
- "Four safeguards" was overstated. Three relaxations give third-party figures; a fourth is needed for ANZ attribution.
- The label conclusion is now marked probable until the owner check.
- The probes and their outputs are kept in the repository.
- Institution class names were collapsed out of this record.
- Probe bugs fixed: `BaseException`, and the year regex on `f`-suffixed headers.
- The scope of the "no redefinition" claim is now stated.
- The stale Phase 4AL lines now point here.
