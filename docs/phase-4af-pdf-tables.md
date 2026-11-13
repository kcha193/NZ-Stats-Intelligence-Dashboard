# Phase 4AF: deterministic PDF forecast tables

11 November 2026, Pacific/Auckland. Design: [spec](superpowers/specs/2026-11-11-phase-4af-bank-pdf-extraction-design.md);
plan: [plan](superpowers/plans/2026-11-11-phase-4af-bank-pdf-extraction.md).

**No live ingestion exists for any bank and no permission field was changed.** The capability is built and proven offline on
synthetic PDFs. It is dormant against the real registry: every bank is `needs_review`, so `research tables extract` refuses
all of them ([source readiness](phase-4af-source-readiness.md)).

## What it does

Reads the numeric forecast tables of a text-layer PDF that is already stored, on this machine, with no model and no request,
and keeps for every figure the printed text, the exact cell, its headers and its page. Figures then join the existing bank
analytics (comparison, consensus, revisions, divergence, evaluation) under the same rules as model-extracted claims.

```
PDF bytes (stored copy) -> table_words   positioned words, in an isolated child process
                        -> table_grid    lines, columns, merged headers, multi-page tables, or a refusal
                        -> table_forecast  indicator, unit, period, actual/forecast, value, or a fixed rejection code
                        -> table_store   migration 015, immutable rows, purge-aware
                        -> table_reconcile  against the checked model claims, fixed classes
                        -> table_view    the gate, then NormalizedForecast for bank_view / bank_analytics
```

## Rules (interpreter `tables-11`; `tables-10` is the Phase 4AF interpreter)

Earlier interpreter extractions remain immutable but are excluded from analytics. Re-extract the held PDF
to create a current interpretation before using its figures.

| Topic | Rule |
|---|---|
| Indicators | OCR, CPI inflation, GDP, unemployment, by fixed phrases in the row label. Two indicators in one label, or none, rejects the row (`ambiguous_indicator`, `unmapped_row`). "% of GDP" is not GDP. |
| Label | Kept as printed. Seasonal-adjustment wording is derived by the same functions as for model claims. |
| Period | From the column header: `Dec-26`, `Mar-27 yr`, `Q4 2026`, `2026`, `Year to March 2027`. A month-end alone does not say quarter or year, so the **row** must (annual / quarterly wording; OCR and unemployment are point-in-time). Anything else is `period_basis_unstated`. A header contradicting its group (e.g. `Mar 2026` under `Year to Dec`) is `contradictory_period`. Two columns for one period are both refused. |
| Actual or forecast | Only an explicit marker: a group header (`Actual`, `Forecast`, `Projections`) or a trailing `f`. No marker, `e` (estimate) or `p` (provisional) is `unknown` and the column is refused (`actual_or_forecast_unstated`). Actuals are stored as actuals and feed nothing. |
| Unit | From the row label, the caption or a `Unit` column: `%`, `% y/y`, `ppt`, `bps`, `% of GDP`. None is `unit_unstated`; two disagreeing statements are `contradictory_unit`; a unit this phase does not read (`000s`, `million`, `$`, `index`, `persons`, `hours`) is `unsupported_unit`, so a `(%)` caption never turns a count into a percentage. No conversion is ever made. |
| Values | The printed text is always kept. `-0.3` and `−0.3` are negative; `0.0` is zero; a lone dash, `n/a`, `..` or an empty cell is **missing** (never zero, never filled from a neighbour). `(0.3)` is `bracketed_value` and refused, because some reports bracket negatives and some do not. Anything else is `unrecognised_suffix`; a magnitude of one million or more is `value_out_of_range`. |
| Footnotes | Any footnote marker on a figure refuses that figure (`footnote_unresolved`): the note may change its basis and may sit further from the table than the reader looks. |
| Scope | Captions or column headers naming a recognised foreign or regional geography or population are refused (`unsupported_geography`, `unsupported_scope`); these fixed phrase lists are not general classifiers. Table notes and column headers are used for seasonal adjustment, with conflicting statements refused. |
| Context contract | One shared check (`table_context.context_rejection`) reads every statement around a figure: the document title (minus its publication name, e.g. "Quarterly Economic Overview"), the caption and any unnumbered heading lines above it, unmarked notes (wrapped lines joined), group and column headers, unit cells and the row label. Interpretation applies it before storing; `table_view` (normalization) and `table_reconcile` re-apply it to the stored evidence, so both identity paths use one definition. Context may repeat what the row says or add a dimension the identity carries (seasonal adjustment); any other qualifier (foreign geography, population, scenario, estimate, an unknown word) refuses the figure with a fixed code rather than being dropped. |
| Aggregation | The measurement basis comes from the row label only (`basis_of`). A label stating `annual average` (or `annual-average`) keeps `annual_average_change`; any other `average` in the label (`average annual`, a trailing `average`) is `period_basis_unstated`, never `annual_change`. Annual-average wording in a caption, note, header or title the label does not state is `period_basis_unstated`; annual-average beside through-the-year wording (`y/y`, `annual % change`) is `contradictory_period`. The same CPI rule applies to model claims. Column-header units must agree with the row's units. |
| Scenarios | A caption, nearby unnumbered scenario heading, row label or column header saying scenario, downside, upside, alternative, stress, sensitivity, illustrative or risk case refuses the table, row or column (`scenario_table`, `scenario_row`, `scenario_column`): a scenario is not the central forecast the analytics compare. |
| Author | The bank, unless a `Source:` line exists and does not name the bank, the caption names another forecaster and not the bank, or a column header names another forecaster (Treasury, RBNZ, the IMF, consensus, Stats NZ ...). These figures are third party and excluded from bank analytics. Names match as whole words. |
| Columns | A value belongs to a column only if it overlaps exactly one column by half its width. A value between two columns, past the last column, or a group header starting in a gap rejects the **whole table** (`ambiguous_columns`). |
| Multi-page | Joined only when the next page repeats the same header, or has no header, the table had no notes, **and the next page's block has no caption of its own** (or one saying "continued"). A captioned block is a new table; an explicit continuation that cannot join is refused (`unjoined_continuation`). A block without a usable header is refused (`no_header`). |

## Reconciliation with model claims

Per document, on the analytics' own identity (indicator, adjustment, basis, horizon), each group gets one class:
`exact_match`, `rounding_difference`, `units_mismatch`, `horizon_mismatch`, `attribution_mismatch`, `contradictory_value`,
`ambiguous_or_unsupported`, `no_counterpart`. Problems with *what is compared* are decided before the numbers. **Agreement is
recorded as agreement and never as proof of economic correctness**: two readings of one page can share a misreading, and
the class carries no "verified" flag.

What reaches the analytics: a figure with no counterpart; a contradiction (both
readings go in so the existing conflict rule leaves **both** out and does not show the bank's older figure in their place).
Not added: an exact match (the checked claim already states it, so it is one statement and counted once; it still shows in `table_reconciliation`). Not used: a rounding difference (the checked claim stays, the table figure is dropped, because a precise and a rounded
value of one number would be a spurious conflict), a unit, horizon or attribution difference, and anything not matched
one-to-one. An ambiguous group containing differently valued, same-unit, author-owned table figures retains those figures
so the analytics conflict rule can exclude the disagreement alongside any matching claim. Table figures appear only
when the owner's automatic internal view is on.

## Known limits

- Text-layer PDFs only. Scanned or image-only pages are `no_text_layer`; OCR of bank reports is not authorised.
- No real bank report has been read. The phrase maps are a starter set from the brief; the first pilot starts with a dry run
  and a person checking every cell ([pilot](phase-4af-first-bank-pilot.md)).
- Group headers must start over their first column (left-aligned or spanning from the left). A centred group header is
  refused, not guessed.
- A whole row shifted by exactly one column looks like a row with a missing first cell and cannot be detected geometrically.
- Text widths are estimated (no font file is read), so a very long row label that reaches the first column can hide that
  column's header and refuse the table. Refusal, never a wrong number.
- Footnoted and bracketed figures are refused rather than interpreted. Estimates (`e`) are not forecasts.
- Only the "table attributes it to someone else" direction of attribution is detected; a model claim attributed to a third
  party is excluded earlier and is not matched to a table row.
- Same-page interaction with the model-claim verifier: beside a table, the header's other periods make the horizon of a
  nearby sentence ambiguous to `verify-5`, which then fails that claim (correct and conservative). The synthetic replay puts
  the commentary on its own page for that reason.
- HTML tables are not parsed.
- Prose set beside a table's rows leaves the table unread and is reported as `mixed_layout` (Phase 4AG).
- **Resolved in Phase 4AG.** The word reader used to need each cell drawn as its own text operation (`pypdf` returned a whole
  `BT ... ET` baseline as one string). Since reader `pdf-words-2` it follows each glyph with `pdfminer.six`, so real reports
  that draw a row in one block are read cell by cell; the interpreter is now `tables-11`. See
  [phase-4ag-source-assessment.md](phase-4ag-source-assessment.md) and [phase-4ag-runbook.md](phase-4ag-runbook.md).
- There is no per-document owner withdrawal for table figures (the draft gate's withdrawal is per summary). To stop showing a
  document's figures: purge it, revoke its route, or turn `auto_display` off.
- `research purge` dry-run counts do not include table figures (they are deleted all the same). An extraction row keeps its
  words hash as a tombstone after a purge.
- If an extractor change ever produced words hash H2 and then reverted to H1, the store would report "unchanged" while reads
  return H2; a document's words only change with the extractor version, so this needs a deliberate downgrade.
- The conflict rule in the bank analytics now identifies "the same document" by document version rather than summary, which
  is what it meant; in explicit-list mode, two summaries of one version with different values now conflict.
