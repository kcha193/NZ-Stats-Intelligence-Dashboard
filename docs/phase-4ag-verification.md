# Phase 4AG: verification record and readiness verdict

14 November 2026, Pacific/Auckland. Branch `feat/phase-4ag-bank-pilot` from main `e0fd037` (PR #59 merged).

**No live ingestion exists for any bank and no permission field was changed.** No bank was contacted and nothing was fetched
(neither the ANZ PDF nor the workbook); no hosted or local model was called; nothing was paid for, deployed, scheduled or
written to production data. The `PRE_APPROVAL_SHA256` pin is unchanged and `config/` has no diff.
`tests/research/test_phase_4ag_safety.py` pins all five real banks as denied and ANZ as having no approval of any kind.

## Verdict

| Question | Verdict |
|---|---|
| Technical implementation | **Verified** (results below), with the limits stated in the last section |
| Live ANZ pilot | **BLOCKED** at step 0: no ANZ right or owner permission is recorded, so the pilot was not started and nothing was ingested |
| Overall | **GO WITH CONDITIONS**: the conditions are non-technical: the owner's recorded decision on the [permissions package](phase-4ag-anz-permissions-package.md) (ideally ANZ's written reply), the reviewed registry change, then the [pilot procedure](phase-4ag-pilot-procedure.md) from step 1 |

Technical completion and live activation are separate: a clean build unlocks nothing.

## Results on the final tree

| Check | Result |
|---|---|
| Backend `pytest`, whole suite | 6894 passed, 5 skipped (previous baseline on `main`: 6341 passed at the 4AF merge) |
| Ruff `check` and `format --check` | clean |
| Frontend unit tests, `tsc -b`, build | 630 passed; types clean; build ok (frontend unchanged by this phase: no diff against `main`) |
| Playwright, live (desktop, tablet, mobile) | 204 passed |
| Playwright, synthetic research | 18 passed, 3 expected skips |
| Static site and parity (`scripts/e2e_static.sh`) | 315 passed, 54 expected skips |
| Offline replay (`test_table_e2e.py`) | passes in both drawing styles; run twice from empty directories with byte-identical answers on every route (the test asserts it); zero network and zero model calls (guards raise) |
| Isolation (`test_table_isolation.py`, `test_phase_4ag_safety.py`, `tests/publish/test_research_isolation.py`) | pdfminer imported only by `table_words.py`; table modules imported only inside `research/`; never by a public or private gate; not scheduled; snapshot unchanged by table rows; all five real banks denied |

`npm audit` and `npm run gen:api` were not re-run (no frontend or API-model change).

## What was added and how it is tested

- **Reader `pdf-words-2`** (`table_words.py`): glyph-level words from `pdfminer.six>=20251230`. 40 tests in
  `test_table_words_stream.py` use raw content streams: a row in one `BT..ET`; kerned `TJ`; numbers drawn in pieces; two
  figures one space or a third of an em apart; labels spaced by positioning; raised and text-rise footnote markers; rotated
  text and rotated pages; double-struck text at four offsets; scaled fonts; unmapped glyphs; hostile, truncated and timed-out
  input; page, character, word and content limits; isolated equals in-process.
- **Whole 4AF scenario suite under a second drawing style:** `conftest.py` re-runs nine table-pipeline test modules with every
  baseline in one `BT..ET` and `Tm`-positioned cells; results must equal the per-cell style (132 extra cases, all pass).
- **Real-layout page tests** (`test_table_real_layouts.py`): exact figures and exact rejection codes for kerned labels,
  split numbers, footnote markers, scaled fonts, prose beside rows (`mixed_layout`), a 12-column wide table, a scenario column
  and another forecaster's caption.
- **Comparison integrity** (`test_table_integrity.py`): one bank's report is never a consensus (mutation-checked: raising the
  threshold makes the test fail), no period is invented, every accepted figure keeps its cell, printed values are kept as
  printed, a financial year is not a calendar year.
- Interpreter `tables-11`; a held PDF read under `tables-9` or `tables-10` is read again and the old rows stay stored but unused.

## Independent review and what was done with it

A separate reviewer read the diff without this session's context and ran demonstrations. No hard-rule violation (no network,
no permission change, no bank content, no raw error text leaked). Findings and dispositions:

| Finding | Disposition |
|---|---|
| **High:** the overprint filter used rounding buckets, so a row drawn twice with a 0.05 pt offset was stored as `44.225`, `33.775`, ... with no rejection | **Fixed**, failing test first: overprints are matched by distance (same character and size, within 0.1 em vertically and half a glyph width horizontally); tests at offsets 0, 0.05, 0.3 and 0.45 and through the table pipeline |
| Medium: two figures about a point apart merged into one number at token level (docs overclaimed) | **Fixed**: two figure characters more than 0.03 em apart are two cells; docs corrected. Cells closer than that cannot be told apart and are refused downstream |
| Medium: month-only headers (`Dec Mar Jun Sep`) merged into one header | **Fixed**: two month or quarter names are two headers |
| Medium: memory bound not enforced on macOS (a 1.5 million glyph string reached 1.5 GB before the character count applied; `RLIMIT_AS` is refused on macOS) | **Mitigated**: a per-page decompressed content-stream cap (300,000 bytes) is checked before layout; the docs now say the address-space limit applies on Linux only and that macOS relies on the timeout and the bounds |
| Medium: the overprint filter can delete a legitimate repeated character drawn with a negative character spacing equal to its width | **Documented, accepted**: contrived (the text would be unreadable to a person) and fails closed in the usual case |
| Low: `research tables show` could display `tables-10` figures with no label | **Fixed**: it names the interpreter and prints `NOT CURRENT` for an older one (JSON: `interpreter`, `current`) |
| Low: docs overclaimed ANZ's terms ("silent on machine analysis") and the workbook | **Fixed**: now states only what the registry records |
| Low: a test asserted only `_finite()`; `text_width` in test support measures with the reader under test; some modules run twice without drawing PDFs | **Accepted**: a direct test of dropping a non-finite glyph needs a real pdfminer object; the circular helper only places fixtures and no assertion depends on it; the doubled runs are cheap |
| Not verified by the reviewer (and not by me): Linux `RLIMIT_AS` behaviour, real-world frequency of double-struck PDFs | **Stated below** |

## Limits stated plainly

- **No real ANZ document was read.** Everything is proven on synthetic PDFs. Real layouts may still refuse tables the reader
  cannot place; that is what the pilot's dry run is for, and refusal is the safe outcome.
- **Staleness gap (found, not fixed).** If a newer document's figure for a horizon is refused (a footnote, say), an older
  document's figure for that horizon still appears as that bank's latest, labelled with its own publication date. A refused
  table cell stores only a code, not an identity, so the analytics cannot hide the older figure the way they do for an unusable
  model claim. It is visible (each row carries its publication date) and the first pilot has no older vintage; **check it at the
  second quarterly report**. A fix needs a schema change and its own phase.
- Agreement of two readings is not proof of economic correctness; a person checks every figure at the pilot.
- The reader does not detect invisible, clipped or white-on-white text, does not read scanned pages or HTML tables, and leaves
  a table unread when prose shares its baselines (reported as `mixed_layout`).
- The XLSX route was assessed, not built: it is unauthorised and unevidenced ([assessment](phase-4ag-source-assessment.md)).
- Numbers for the PDF-library comparison (0.84 s and 45 MB for pdfminer, 1.14 s and 206 MB for pdfplumber on one synthetic
  40-page file) come from one local run; the CVE facts come from the public advisories for pdfminer.six.

## Recommended next phase

The evidence says the limiting factor is no longer extraction code but rights and a real layout. Recommended, in order:

1. **Owner action, no code:** decide on and, if wanted, send the ANZ request; record a decision.
2. **Phase 4AH, only after step 1:** run the single-document ANZ pilot exactly as written, and let what the real PDF refuses drive
   any further extractor work (synthetic fixture and failing test first).
3. **Then** a second quarterly report to exercise revisions and close the staleness gap above.

Do not build an XLSX adapter, a second bank or model reading of bank text before that evidence exists.
