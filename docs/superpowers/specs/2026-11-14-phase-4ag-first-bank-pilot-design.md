# Phase 4AG design: first real bank research pilot (preparation)

14 November 2026, Pacific/Auckland. Baseline `main` `e0fd037` (PR #59 merged). Status: approved by the owner's Phase 4AG brief
(the brief fixes scope, constraints and deliverables; the calls below are the implementer's and are marked as such).

## Intent and why

Phase 4AF can read forecast tables from stored text-layer PDFs, but only proven on synthetic PDFs that draw every cell in its
own text operation. Two things stop a first genuine bank pilot: (1) the word reader (`pypdf` visitor) merges everything drawn in
one `BT..ET` block into one string, which is how most real reports are written, so real reports would yield nothing; (2) no
bank has recorded permission, so nothing may be fetched, saved or parsed. This phase removes the technical blocker, prepares the
owner's permission decision for ANZ New Zealand, and writes the pilot procedure, **without unlocking anything**.

## Goals

1. A positioned-word reader that follows the PDF content stream faithfully (real glyph positions and widths), replacing the
   `pypdf` visitor for tables, behind the existing hardened child process.
2. A reasoned PDF-versus-XLSX source decision for ANZ, with a decision matrix, without fetching either.
3. Real-world-like synthetic fixtures (text in one `BT..ET`, `TJ` kerning, `Tm` positioning, split tokens, superscripts, rotated
   text, scaled fonts, fake bold, unmapped glyphs, multi-column pages, wide and multi-page tables) and regression tests that
   prove figures are extracted correctly and ambiguity still fails closed.
4. An owner decision package and an unsent permission request for ANZ.
5. A single-document pilot procedure with stop conditions; the pilot is reported BLOCKED until rights are recorded.
6. Verification that extracted figures still integrate correctly with the 4AE/4AF analytics (one report is not a consensus).

## Non-goals

No live ingestion, fetch, scheduling, hosted or local model call, paid inference, public display, snapshot content, production
database change, change to any registry permission field or to the `PRE_APPROVAL_SHA256` pin, change to Stats NZ data, OCR,
HTML tables, or a second bank. No relaxing of any validation threshold to obtain more values.

## Anti-goals (a failure even if tests pass)

A wrong number accepted because the reader guessed a cell boundary; any path that makes a bank request or model call on open;
bank text or figures in Git; a build step that flips a permission; a looser rule justified only by "more values extracted".

## Constraints

Existing 4AE/4AF modules keep working (`table_grid`, `table_forecast`, `table_store`, `table_reconcile`, `table_view`,
`bank_view`, `bank_analytics`). Immutable evidence store and safe reprocessing: a changed reader yields a new extraction row
(words hash differs); older rows stay but are excluded from analytics by the interpreter version. All PDF bytes are untrusted:
child process, wall-clock, CPU, memory, output bounds. New dependency must be maintained, permissively licensed and free of
unfixed advisories.

## Approaches considered

### PDF word reader

| Option | For | Against |
|---|---|---|
| A. Keep `pypdf` visitor | no new dependency | merges a `BT..ET` row into one string (reproduced); estimated widths; cannot be fixed from outside |
| B. **`pdfminer.six` at character level, own word assembly** | maintained, MIT, real positions and advances, `laparams=None` skips layout analysis, 0.8 s and 45 MB for 40 dense pages | new dependency (`charset-normalizer`, `cryptography`); had pickle-CMap advisories CVE-2025-64512 and CVE-2025-70559, fixed in 20251230 |
| C. `pdfplumber` | convenient `extract_words` | wraps pdfminer.six with an **exact pin**, which blocks the security floor; adds Pillow and `pypdfium2` binaries; 4x peak memory in the benchmark; its word grouping is a tolerance guess we would still have to audit |
| D. Custom content-stream interpreter | no dependency | reimplements fonts, CMaps and encodings; the brief says prefer a maintained library |

**Chosen: B**, with `pdfminer.six>=20251230`. Spike evidence: on a PDF with three rows drawn in one `BT..ET` each,
`pypdf` returned `'OCR 3.25 3.00'` as one string at one position; pdfminer returned every glyph with its own box.

### Source route

PDF (quarterly Economic Outlook) versus the published forecasts XLSX workbook: see
[phase-4ag-source-assessment.md](../../phase-4ag-source-assessment.md). **Chosen: PDF stays the pilot route; no XLSX adapter is
built.** The workbook's existence, structure, terms and permitted use are unverified (not fetched), the registry has no
workbook route, and the brief forbids building both unless the workbook is demonstrably better *and* independently authorised.
The assessment lists the conditions under which a workbook adapter should be built later.

## Design of the reader (`pdf-words-2`)

1. In the existing child process: `pypdf` pre-checks (encrypted → blocked, page count within `max_pages`), then
   `pdfminer.high_level.extract_pages(laparams=None)`; only upright `LTChar` objects are read; blank glyphs are separators.
2. Characters are bounded (`_MAX_CHARS`, `_MAX_WORDS`) and a char drawn twice at the same spot (fake bold) is read once.
3. Per page and baseline, characters become **tokens** (split at a space glyph or a gap above 0.15 em; split wherever the
   baseline moves more than 0.15 em or the font size changes by more than 15%, so a raised footnote digit is never glued to a
   figure), then tokens become **phrases**: neighbours join unless the gap exceeds 0.45 em or both sides are value-like (numbers
   are never merged across a space or gap; a split number token with no gap, such as `3.` + `25`, is one token).
4. `Word.x1` is the real right edge of the last glyph (the old estimate is removed), so column overlap is geometric.
5. Version `pdf-words-2`; the table interpreter becomes `tables-11` because geometry input changed. Re-extraction of a held PDF
   creates a new immutable extraction; `tables-10` rows stay in the database but no longer feed analytics.
6. Fail closed: unmapped glyphs (`(cid:N)`) stay in the word text and so fail the value pattern; rotated text is dropped and a
   count is logged; no text layer is still `no_text_layer`. Invisible text (render mode 3) is **not** detected (documented limit).

## Parts left to the builder (implementer's calls, marked)

Exact gap constants (0.15 em and 0.45 em: implementer's call, covered by boundary tests); module split (one new function group
inside `table_words.py`); whether rotated-page `/Rotate` is honoured (it is, via pdfminer).

## Verification and acceptance

All suites green (backend, frontend, Playwright live and research, static parity); offline replay twice, byte-identical;
independent review with Critical and High findings fixed; the registry pin unchanged; no permission field changed.
Verdict wording: technical completion is separate from live activation.
