# Phase 4AL: PDF parser benchmark (pdfplumber, Camelot 2.0, `tables-14`)

15 November 2026, Pacific/Auckland. Branch `bench/phase-4al-pdf-parser-benchmark` from `95be0ad` (Phase 4AK, branch
`feat/phase-4ak-anz-pdf-compat`, not yet merged). Document: the already-imported ANZ Quarterly Economic Outlook, **version 4**,
pages 5 and 8. Plan: [2026-11-15-phase-4al-pdf-parser-benchmark.md](superpowers/plans/2026-11-15-phase-4al-pdf-parser-benchmark.md).
Harness: [`benchmarks/pdf_tables/`](../benchmarks/pdf_tables/README.md).

**Verdict: keep the existing `pdf-words-4` / `tables-14` pipeline. No parser showed a structural improvement on the real
pages, so production extraction is unchanged.** Camelot 2.0 (`network` flavor) is the only competitive alternative. It
reproduces every page-8 cell that `tables-14` reads, but it merges page 8's two tables into one. It reads a different
(one word shorter) label for one page-5 row of 8 figures. It attaches no notes: on page 8 one source or note line sits
inside its grid as an ordinary cell, unlinked to any figure. On synthetic layouts it also fuses near-touching columns.
pdfplumber, as the PDF skill configures it, finds no borderless table. Its `lines` mode builds 27-column grids from the
pages' rectangles. Extraction counts were not the criterion. Most real-page measures use `tables-14`'s own reading as the
reference, so they show where Camelot departs from it, not who is right (§9). On the two reference-free measures
(figures fused into one cell, figure tokens left outside any cell), Camelot `network` ties `tables-14` at 0.

This record describes the document only by counts, grid indices and fixed codes. It holds no ANZ text or figure.

## 1. The official PDF skill

Inspected at `anthropics/skills/skills/pdf` (upstream, fetched 2026-11-15) and its synced local copy (identical files;
local `SKILL.md` SHA-256 `1c7caf5f35eb…`).

- **Licence:** Apache 2.0 (`LICENSE.txt`; the repository README lists the document skills as open source under Apache 2.0, and
  adds "provided for demonstration and educational purposes only"). pdfplumber is MIT. Camelot is MIT.
- **Requirements named:** pypdf, pdfplumber, pandas, reportlab, pypdfium2; pytesseract and pdf2image (OCR); poppler-utils,
  qpdf, pdftk (CLI); pdf-lib (JavaScript).
- **Scripts (8):** `check_bounding_boxes.py`, `check_fillable_fields.py`, `convert_pdf_to_images.py`,
  `create_validation_image.py`, `extract_form_field_info.py`, `extract_form_structure.py`, `fill_fillable_fields.py`,
  `fill_pdf_form_with_annotations.py`. All are for forms or page images. **None extracts tables**, so none was run.
- **Table guidance used:** `page.extract_tables()` with defaults (`plumber_default`) and the REFERENCE.md settings
  `lines`/`lines`, `snap_tolerance` 3, `intersection_tolerance` 15 (`plumber_lines`). pdfplumber's `text` strategy
  (`plumber_text`) was added for fairness on borderless tables; the skill does not name it.
- **Guidance not used:** the skill's visual debugging (`page.to_image`), OCR (pytesseract) and page-image conversion. Each one
  would render the document as an image, and OCR is barred by the brief. reportlab, which the skill recommends for creating
  PDFs, draws the synthetic fixtures.

## 2. Method and privacy boundary

- **Accuracy is measured against ground truth on synthetic replicas only.** These are reportlab PDFs with invented text and
  figures. They rebuild the page-5 and page-8 layout facts recorded in [Phase 4AK](phase-4ak-anz-pdf-compat.md): a prose
  paragraph above the caption, 5 unmarked plus 3 `f` years, a raised footnote marker on one row label, a small-digit marker
  line, a source line naming another forecaster, and a "Current" header stacked 0.59 em above and 0.61 em below the period
  line over 9 columns and 6 + 4 rows. The replicas reproduce the recorded `tables-14` outcomes exactly: page 5 gives 8 columns,
  4 rows, 2 notes and `scenario_table`; page 8 gives `actual_or_forecast_unstated` ×18, `unmapped_row` ×9 and
  `unit_unstated` ×1. Four control cases follow: a fully ruled grid, a value with a fused raised marker, chart axis ticks
  beside a table, and columns 0.5 em apart.
- **The real document was measured only with counts.** Every parse runs in a child process whose stdout and stderr go to
  `/dev/null` with logging off, and the parent does the same (`safe_diagnose`). The review found that a pdfminer warning had
  quoted a synthetic canary to stderr before this fix (§11). The rerun after the fix wrote 0 bytes to stderr and gave the
  same non-timing values. `run_masked` opens `data/nzstats.db` read-only, applies the production
  gate (`table_ingest._VERSION` and `version_refusal`) and checks the stored SHA-256. Every value leaves through `emit`. `emit`
  refuses any key outside a fixed vocabulary, any number-like key except a page number directly under `pages`, and any
  string that is not a fixed code. Canary tests show that no word or figure of one synthetic canary document reaches the
  output under the current metric set. That is evidence for this set, not a proof for any future metric. Mutating the guard makes 3 tests fail per mutation. The database SHA-256 was the
  same before and after each run (`a44b929b1ef1…`).
- **No model, OCR or service touched the document.** Camelot's `ml` flavor (a Table Transformer model) is excluded. A test pins
  torch, transformers, timm, onnxruntime and pytesseract as absent from the benchmark venv. Camelot `lattice` renders pages in
  memory to find ruling lines; nothing is written or shown.
- **Cross-parser agreement is not truth.** On the real pages, `agreement_with_existing` counts the value cells that `tables-14`
  reads and that a parser reproduces under the same row label and column header (footnote markers on labels and values are
  ignored; a digit fused into a figure is not). On the page-5 and page-8 replicas this count equals the truth-scored alignment
  for every parser (network 32 and 90, stream 32 and 54, `plumber_text` 13 and 80). That validates it as a proxy on those
  layouts, not as ground truth.

Versions (exact pins, each released at least two weeks earlier): pdfplumber 0.11.10 (pins pdfminer.six 20260107),
camelot-py 2.0.0 (playa-pdf 1.1.0, opencv-python-headless 5.0.0.93), reportlab 5.1.0, pypdf 6.21.4; Python 3.12 venv.

## 3. Synthetic results (ground truth)

Totals over 8 cases (10 truth tables, 275 truth values, 4 stacked columns, 3 footnote markers, 5 notes). *Aligned* means the
exact text sits on its own row label and under its own column header, with no other column's header fragment above it.

| Parser | Tables found | Merged | Values aligned | Stacked joined | Markers kept | Notes kept | Numeric false positives | Seconds (median, sum) |
|---|---|---|---|---|---|---|---|---|
| **existing (`tables-14`)** | 9/10 | 0 | **271/275** | 4/4 | **3/3** | **5/5** | **0** | 1.20 |
| camelot_network | 10/10 | 2 | 266/275 | 4/4 | 0/3 | 0/5 | 4 | 3.30 |
| camelot_hybrid | 10/10 | 2 | 266/275 | 4/4 | 0/3 | 0/5 | 4 | 4.61 |
| camelot_stream | 8/10 | 0 | 194/275 | 2/4 | 0/3 | 0/5 | 6 | 3.18 |
| camelot_lattice | 1/10 | 0 | 4/275 | 0/4 | 0/3 | 0/5 | 0 | 4.56 |
| plumber_text | 7/10 | 2 | 190/275 | 0/4 | 0/3 | 0/5 | 20 | 0.38 |
| plumber_default (skill) | 1/10 | 0 | 4/275 | 0/4 | 0/3 | 0/5 | 0 | 0.34 |
| plumber_lines (skill) | 1/10 | 0 | 4/275 | 0/4 | 0/3 | 0/5 | 0 | 0.33 |

Per case (aligned / truth, false positives):

- **p5 replica (borderless and ruled):** existing 32/32, network and hybrid 32/32, stream 32/32 with 1 FP, `plumber_text`
  13/32 with 4 FP (it splits a figure across two cells, so `0.75 4` and `.25` appear). Lattice and both skill modes find nothing.
  Only existing keeps the label marker and both notes.
- **p8 replica:** existing 90/90 as two tables. Network and hybrid read 90/90 but as **one table spanning both**; the first
  table's caption, which carries "Forecasts", now heads the second table's rows. Stream 54/90 (misses the second table).
  `plumber_text` 80/90, also merged.
- **fused_superscript:** existing reads `2.5` with the marker kept separately (`2.5¹`). Camelot reads `2.5` but moves the marker
  into a row of its own under the period header, where a lone `1` reads as a figure (1 FP). The link between the footnote and
  its value is lost.
- **tight_columns:** existing 9/9. All three Camelot text flavors put three figures in one cell (`12.35 13.40 14.65`): 0/9
  with 3 FP.
- **axis_noise:** no parser except `plumber_text` reads the chart ticks as a table (10 FP).
- **ruled_control:** every other parser 4/4. **Existing 0/4:** a stub heading over the label column ("Indicator 2026 2027")
  reads as a body line, so the table has no header (`no_header`). This is a real `tables-14` gap. It fails closed. See §7.

## 4. Real document, version 4 (masked counts)

Page facts: **neither page has a ruling line or curve.** Page 5 has 104 rectangles and page 8 has 343 (pdfplumber `rects`,
which counts filled and stroked rectangles alike; which kind was not measured). Page 5 has 1
footnote marker set after a word (a row label) and none after a figure. Page 8 has none.

| Parser | p5 tables (rows × cols) | p5 cells reproduced | p8 tables (rows × cols) | p8 cells reproduced | Merged | Multi-figure cells | Notes attached |
|---|---|---|---|---|---|---|---|
| **existing** | 1 (5×9) | 32/32 | 2 (7×10, 5×10) | 90/90 | 0 | 0 | p5: 2, p8: 1 |
| camelot_network | 1 (11×9) | 24/32 | 2 (18×10, 28×2) | 90/90 | **1** | 0 | 0 |
| camelot_hybrid | 1 (11×9) | 24/32 | 2 (18×10, 28×2) | 90/90 | **1** | 0 | 0 |
| camelot_stream | 1 (8×9) | 24/32 | 1 (46×2) | 0/90 | 1 | 10 | 0 |
| camelot_lattice | 0 | 0/32 | 0 | 0/90 | 0 | 0 | 0 |
| plumber_text | 1 (29×12) | 0/32 | 1 (83×16) | 50/90 | 1 | 4 | 0 |
| plumber_lines (skill) | 1 (2×11) | 0/32 | 2 (5×27, 6×27) | 2/90 | 0 | 0 | 0 |
| plumber_default (skill) | 1 (1×11) | 0/32 | 2 (2×10, 2×10) | 0/90 | 0 | 0 | 0 |

Why cells were not reproduced (fixed reason codes):

- **Camelot network, hybrid and stream, page 5:** the 8 missing cells are all of grid row 1, one per year column. Each is
  `label_mismatch`: the figure sits under its correct column header, but the row label differs. A follow-up probe (ints
  only, printed through `emit`, not committed) found that the `tables-14` label for that row has 6 words. Camelot's label on the same 8 figures is non-empty and holds 5 of
  them, and no Camelot row holds the full 6-word label. The label does not end in a footnote marker in the `tables-14` reading,
  so this is a label-reading difference, not a footnote effect. One of the two readings is wrong about the identity of 8
  figures. **Owner check:** only the PDF can settle which label is printed. The agent did not read it.
- **Camelot network and hybrid, page 8:** every cell reproduced, but the two market tables come back as one 18-row table (the
  same merge as the replica), plus a 28×2 table that holds 0 figures (the same uncommitted probe). Its grid also holds 1 source or note line
  (`source_lines_in_grid`), as an ordinary cell. Stream reads 0/90 (`value_missing` ×90): it fuses the page
  into two columns and puts several figures in one cell (10 cells).
- **pdfplumber `lines` (the skill's settings):** the filled rectangles become cell edges, so page 8 becomes two 27-column grids
  (25 `header_mismatch`, 63 `value_missing`). Page 5 gives a 2-row fragment. `default` finds 1- and 2-row fragments.
- **pdfplumber `text`:** 0/32 on page 5 (28 `label_mismatch`, 4 `header_mismatch`) and 50/90 on page 8 (21 missing, 19 under
  the wrong header; 41 figure tokens inside its table box are in no cell).
- **No parser** produced a fused footnote figure on these pages: neither page has a marker after a figure.

## 5. Criteria (brief)

| Criterion | existing `tables-14` | Camelot 2.0 network | pdfplumber (skill) |
|---|---|---|---|
| Table detection | p5 1, p8 2; refuses stub-headed tables (synthetic) | p8 tables merged into 1 (real and synthetic) | Skill modes: borderless none; rectangles give false 27-column grids. `text` (not in the skill): 1 table per page, merged |
| Cell and column alignment | 122/122 real (reference); 271/275 synthetic | 114/122 real; 266/275 synthetic; fuses columns 0.5 em apart | Skill modes ≤ 2/122 real, 4/275 synthetic; `text` 50/122 real, 190/275 synthetic |
| Merged and stacked headers | Stacked "Current" joined (4/4) | Stacked joined (4/4), but table boundaries lost | Not joined (0/4) |
| Footnote preservation | Marker kept on its cell (3/3); notes walked past small-digit markers | Marker detached into its own row (0/3); a lone digit can read as a figure | Not kept |
| Source attribution evidence | Notes attached to the table (5/5 synthetic; real p5 2, p8 1) | No notes attached (0/5 synthetic); real p8: 1 source or note line inside the grid as a plain cell | Skill modes none; `text`: 1 such line per real page, inside the grid |
| Extraction completeness | Complete on the read tables | Complete on p8 values; p5 row 1 read with a different label (owner check) | Low |
| False-positive numeric cells | 0 | 4 synthetic (fused columns, detached marker) | Skill modes 0 (they read almost nothing); `text` 20 synthetic |
| Speed | 1.20 s for 8 synthetic cases; real 2.51 s for the **whole document** (words for every page; 2.5 to 3.4 s across runs) | 3.30 s synthetic; real 0.41 s for **2 pages** (hybrid 0.73, stream 0.38) | 0.33 to 0.34 s synthetic; real 0.13 to 0.21 s for 2 pages |
| Dependencies | pdfminer.six (already required) | +13 packages, about 278 MB (numpy, pandas, OpenCV, pypdfium2, playa-pdf) | +8 packages, about 47 MB; pins pdfminer.six **exactly** (`==20260107`), against our floor `>=20251230` |

## 6. Recommendation

**Keep `pdfminer.six` + `tables-14` as the production parser.** Adopt neither pdfplumber nor Camelot.

- pdfplumber, as the PDF skill guides it, is built for ruled tables. These bank pages are borderless with filled
  backgrounds, so it misses every table or invents grids. Its exact pdfminer pin would also freeze our reader's version.
- Camelot `network` comes closest on figures alone. Its structural failures hit the exact rules our economic validation relies
  on. A merged table puts two tables under one caption scope; on page 8 only the first caption says "Forecasts" (Phase 4AK),
  so forecast status would spread to the second. Unattached notes lose attribution, which is the Phase 4AK fail-open class:
  a source line left as a plain grid cell is not linked to the figures it qualifies. A footnote marker detached into its own row (synthetic) loses its link to the figure. Each one would need new repair
  logic, which is the custom engine we already have, plus about 278 MB of dependencies. The page-5 label difference is open
  until the owner checks it. Even if Camelot's label is the right one, that single row would not outweigh the failures above.
- The economic validation (`table_forecast.interpret`: units, dates, attribution, forecast status) stays the gate for any
  parser. Nothing in this benchmark relaxes it.

The benchmark does give production two inputs. They need separate phases:

1. A `tables-14` gap: stub-headed tables are refused (`no_header`). The fix belongs in `table_grid`, test-first, with the
   ruled control as its regression case. It is not a parser swap.
2. The masked harness can be reused: run it on the next outlook (February 2027) before trusting a new layout.

## 7. Integration architecture (if a future document shows a clear win)

The seam is `find_tables(words) -> (GridTable…, Rejection…)` in `table_grid.py`. Everything after it (`table_forecast.interpret`,
`table_store`, migration 015's immutable tables, `table_view`, the freshness rules) consumes `GridTable` and stays unchanged.

```
stored PDF bytes ─► table_words.extract_words (pdf-words-4, child process) ─► Word[]
                    └─► table_grid.find_tables ─► GridTable[] ─► interpret() ─► forecasts / rejections ─► store
alternative:        <parser>_grid.find_tables(pdf bytes) ─► GridTable[]  (same type, same Rejection codes)
```

- **Adapter contract:** an alternative must emit `GridTable` with real `Cell` positions, `Column.headers` (group then own),
  `header_rows` provenance and `notes`. A parser that cannot supply notes (Camelot, pdfplumber) needs a separate note walk over
  `Word`s below the table. Without one it cannot pass attribution, so it fails closed.
- **Versioning:** a new interpreter string (for example `tables-15-camelot`) in the existing extraction row. Older extractions
  stay immutable and stop feeding analytics, as with `tables-13`.
- **Isolation:** the parser runs in the same child-process sandbox as `table_words` (time, memory and size limits). Its
  dependencies go in an optional extra, never in the base install. No `ml` flavor and no page images leave the process.
- **Shadow mode first:** run both parsers, store only `tables-14`, and log the masked disagreement codes from this harness. No
  output changes until the gate below passes.

## 8. Tests and migration plan

Tests now (benchmark only, `benchmarks/pdf_tables/tests`, 108 passing): replica fidelity (`test_synth.py`), adapters and
failure isolation (`test_adapters.py`), truth scoring with mutation-checked guards (`test_metrics.py`), the run table
(`test_run_synthetic.py`), and the privacy schema, canaries, production gate and reason codes (`test_masked.py`). The backend
suite is unchanged; no production file changed.

Migration plan: **none now.** If a later document shows a win, adopt only when all of these hold:

1. Synthetic: aligned ≥ `tables-14` on every case, 0 numeric false positives, markers and notes kept, 0 merged tables.
2. Real (masked): 100% of `tables-14` cells reproduced with 0 `label_mismatch` and 0 merges, on every held bank PDF.
3. End to end: the same `interpret()` outcome, with **zero accepted figures that `tables-14` refuses**, unless the owner
   reconciles each one against the PDF (procedure step 7).
4. Shadow mode for at least one new release, a new interpreter version, then switch, with `tables-14` kept as the fallback.

## 9. Limitations

- The replicas follow the recorded geometry, not the real pages' filled rectangles; only the real run measured those.
- On the real document, "reproduced" means agreement with `tables-14`, not truth. A parser could be right where `tables-14`
  is wrong; only the page-5 row 1 label case is open, and it is an owner check.
- The timings measure different scopes (whole document against 2 pages), include no process start, and vary between runs.
- The replicas were judged faithful because they reproduce `tables-14`'s recorded outcomes. They did not reproduce Camelot's
  real page-5 label difference or `plumber_text`'s real page-5 0/32 (13/32 on the replica). So the synthetic numbers measure
  each parser on these layout facts, not a prediction of its real-page result.
- Markers kept and notes kept score features of the `tables-14` pipeline. Under §7's adapter contract, a separate note walk
  would supply them for any parser. So 5/5 against 0/5 is evidence about today's adapters, not about grid structure. The
  grid-structure evidence is alignment, merges and false positives.
- The 6-word label and the empty 28×2 table come from an ints-only probe printed through `emit` that is not committed.

## 10. Independent review

An independent reviewer (fresh context, Opus; barred from `data/` and from running anything on the real document) checked the
whole branch. Its verdict was "with fixes": no Critical findings, and the recommendation is supported. It re-ran the
synthetic benchmark (all 64 rows match `results/synthetic.md`) and checked §3 and §4 against the committed results.

## 11. Review findings and fixes

Fixed test-first (each test watched fail, then pass; suite 102 passing):

- `emit` accepted number-like keys at any depth, so a year header used as a metric key would pass. Now a number is a key only
  as a page number directly under `pages` (`test_digit_keys_are_allowed_only_as_page_numbers`).
- **Side channel:** child processes and the parent could write library warnings, native output and tracebacks to the
  terminal. The test reproduced a pdfminer warning quoting a synthetic canary on stderr. Now every child sends fd 1 and 2 to
  `/dev/null` with logging off; `safe_diagnose` does the same in the parent; `main` turns any exception into the fixed code
  `error` (`test_a_broken_document_prints_nothing_on_either_stream`, `test_parser_children_print_nothing_on_either_stream`).
  The version 4 rerun after the fix gave identical non-timing values and 0 bytes on stderr. The earlier real runs used the
  old path; no stderr content from them was shown in the session, and no record or committed file holds any.
- A child that died without reporting was recorded as `timeout` after the full wait. It is now `error`
  (`test_a_child_that_dies_without_reporting_is_an_error_not_a_timeout`); the timeout path now has a test.
- The agreement proxy now ignores a value's footnote marker as it already ignored a label's
  (`test_a_value_marker_does_not_block_agreement_but_a_fused_digit_does`). Version 4 has no value markers, so its results are
  unchanged.
- The README's synthetic commands lacked `PYTHONPATH`, so `existing` would score every case as `error`.

Record corrections: Camelot's page-8 grid holds 1 source or note line (it was described as dropping them); timings now match
the committed run; the proxy claim is limited to the p5 and p8 replicas; "filled" rectangles was not measured; the canary
claim is evidence, not proof; the headline now says most real measures use `tables-14` as the reference; §5 separates the
skill modes from `text`; §9 adds the replica-fidelity and notes caveats and the uncommitted probe.

Deferred minor: two contradictory comments on the tight-columns pitch in `synth.py`.

Declined to judge (reviewer), with the owner's position: which page-5 label is right (owner check against the PDF); whether
the masked JSON reads version 4 correctly and the database checksums (both under `data/`, barred); dependency sizes,
licence and upstream facts (measured and fetched by the implementer, §1 and §5); the guard mutations (re-run by the
implementer: each failed 3 tests); whether 0.5 em column gaps occur in bank PDFs (a domain judgement; the case stays a
control); the §7 design detail (to be settled if a future phase adopts a parser).

## 12. PR review: leading-decimal fragments (PR #65)

Finding (P2, automated PR review): `numeric()` required an initial digit, so a parser cell such as `.25` (a figure split
from its leading digits) was not numeric and was never counted as a numeric false positive.

Fix, test-first: a numeric token may now be `.` followed by digits, with the same optional sign, parentheses and `%` as
before (`.25`, `-.25`, `−.25`, `(.25)`, `.25%`, `.25 2.5`). `.`, `.abc`, `..25`, `.25.`, `2..5` and words stay non-numeric.
New tests in `test_metrics.py` cover both `numeric()` and `score()`: truth `4.25` read as `.25` scores 0 present, 0 aligned
and 1 numeric false positive. The leading-decimal `numeric()` test and the `score()` test failed before the fix; the
other two (existing forms stay numeric, non-numbers stay non-numeric) are regression guards that pass on both patterns.

Effect on the synthetic run (regenerated; only these cells changed apart from timings): `plumber_text` on `p5_annual` and
`p5_annual_hrules` goes from 3 to 4 numeric false positives, so its total goes from 18 to 20. No other parser or metric
changed, `tables-14` stays at 0, and the recommendation (§6) is unchanged.

Not re-run: `masked.py` uses the same `numeric()` for its real-document counts: `numeric_cells`, `multi_number_cells`,
`existing_value_cells`, `agreement_with_existing`, `unreproduced_existing_cells`, `unreproduced_reasons`,
`bbox_numeric_tokens` and `bbox_numeric_tokens_uncovered`. `results/masked-v4-pages-5-8.json` and §4 were
produced with the earlier classifier. They change only if version 4 has a leading-decimal cell or word, which was not checked:
re-running the masked diagnostics on the real document needs the owner's approval. **Owner action:** re-run
`run_masked 4 --pages 5 8` and compare the non-timing values.

The §10 statement that all 64 rows matched `results/synthetic.md` refers to the run before this fix; the regenerated file
differs from it only in the two `plumber_text` cells above and in timings. Pre-existing behaviour left unchanged: an
unbalanced parenthesis (`(2.5`, now also `(.25`) still reads as numeric, and a label-column cell equal to any marker digit
on its page is not counted as a false positive.

Second finding (P2, automated PR review of the fix): `score()` rebuilt its pool of parsed cells for each truth table, so one
parsed cell could count as present for the same text in two truth tables on one page. The pool is now shared by all truth
tables of a page (`test_a_parsed_cell_is_consumed_once_across_truth_tables_on_a_page` failed before the fix: 2 present
instead of 1). Sharing the pool made consumption order matter: a value with a footnote marker took the plain cell first
and starved a later duplicate without one. A value now tries its marked forms before its plain text
(`test_a_marked_truth_takes_its_marked_cell_before_a_plain_one`, both orders). The regenerated synthetic run has the same
non-timing values, so `results/synthetic.md` is unchanged. The suite is 108 passing. Pre-existing and left unchanged:
*aligned* does not consume cells, so two identical truth cells (same label, header and value) can both align to one
parsed cell.
