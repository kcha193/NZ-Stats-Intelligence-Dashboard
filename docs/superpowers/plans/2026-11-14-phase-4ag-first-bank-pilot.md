# Phase 4AG implementation plan

Spec: [design](../specs/2026-11-14-phase-4ag-first-bank-pilot-design.md). Branch `feat/phase-4ag-bank-pilot` (worktree
`.worktrees/phase-4ag`). Every code task is test first: write the test, watch it fail for the stated reason, then implement.
Run backend tests with `PYTHONPATH=<worktree>/backend/src` (the venv's editable install points at the main checkout), never
with `nohup`.

## Task 1: Dependency and fixtures
- Add `pdfminer.six>=20251230` to the `research` and `dev` extras in `backend/pyproject.toml`; install into `backend/.venv`.
- New `tests/research/pdf_stream_support.py`: builds PDFs from **raw content-stream operators** (one `BT..ET` per row, `TJ`
  kerning arrays, `Tm` positioning, raised small digits, rotated text, scaled fonts, doubled text, an unmapped-glyph font).
- Failing test: a row drawn in one `BT..ET` yields separate words with their own positions (today: one string).

## Task 2: Word reader `pdf-words-2`
- Tests (each fails first): separate cells in one block; `TJ` kerning does not split a number; split number token (`3.` + `25`)
  is one word; two numbers separated by a space glyph or a 0.3 em gap stay two words; a label with spaces stays one phrase; a
  raised footnote digit is never glued (`3.25` and `1`, not `3.251`); rotated text dropped; fake bold read once; an unmapped
  glyph keeps `(cid:` in the text; real `x1` equals the glyph edge; scaled font (`Tm` scale) gives the true size; page
  `/Rotate`; blank page is `no_text_layer`; encrypted blocked; page, word and char limits; isolated equals in-process.
- Implement in `table_words.py`; remove the `pypdf` visitor path, `make_word`, `text_width` (replace their tests with the new
  ones, same assertions where still meaningful). Bump `EXTRACTOR_VERSION`.

## Task 3: Interpreter version and reprocessing
- Bump `INTERPRETER_VERSION` to `tables-11`; update the pinned strings in tests. Test: a version extracted under
  `tables-10` and again under `tables-11` has two extraction rows, the latest feeds `load_forecasts`, analytics ignore
  `tables-10`.

## Task 4: Real-world-like end to end tables
- Fixtures: a three-page ANZ-style outlook (fictitious bank name in tests) drawn the way real PDFs are (one `BT..ET` per row),
  covering multi-column page, repeated header, wide table with year-ended and quarterly columns, group headers, negative,
  zero, empty cell, scenario column, misleading caption, multi-page continuation, other-forecaster attribution, footnote.
- Tests assert exact figures and exact rejection codes for each; run through `extract_version_tables` and the analytics.

## Task 5: Forecast comparison integrity
- Tests: one bank's report yields no consensus; no extrapolation of missing periods; calendar versus financial year not mixed;
  rounded printed value kept as printed; a same-report contradiction excludes both; a newer unusable claim does not
  resurrect or hide the older figure; forecast versus actual; duplicate exclusion; evidence reachable for every figure.

## Task 6: Isolation and safety
- Tests: registry pin unchanged and ANZ stays `needs_review`/`manual_import = denied`/`llm_processing = denied`; extraction
  makes no network or model call (guards raise); words module imports nothing network-capable; child limits still bound output.

## Task 7: Documents
Source assessment; ANZ permissions package with the unsent request; pilot procedure; runbook; verification record; update
`docs/progress.md`, `CLAUDE.md`, the 4AF docs' "known limit" lines, and the vault `current-projects.md`.

## Task 8: Verification, review, PR
Full backend, ruff, frontend tests/typecheck/build, Playwright (live, research), static parity, offline replay twice;
independent code review; fix Critical and High; push the branch and open a PR (not merged).

## Task 9: PR #60 numeric-integrity remediation

**Goal:** Refuse unresolved overlapping glyphs before they can become accepted figures.
**Spec:** The design's anti-goal forbids accepting a wrong number by guessing a boundary.
**Files:** `table_words.py`, `table_forecast.py`, the stream/ingestion/version regression tests,
and the existing verification record. No dependency, permission, registry pin or schema change.
**Interfaces:** `extract_words(...)` keeps its signature and raises the existing `IngestError`;
`extract_version_tables(...)` returns its existing fixed refusal without storing forecasts.

**Root cause:** At 10 pt, overprint deduplication accepts a vertical offset up to 1 pt,
but token assembly joins through 1.5 pt and imposes no lower bound on horizontal gaps.
The reproduced 0.05 pt horizontal / 1.1 pt vertical shadow becomes `44`; `parse_value`
accepts that valid integer. Raising the deduplication tolerance would guess away ambiguity.

**Review focus:** residual identical/different glyph overlays; mixed sizes/fonts and text rise;
normal repeated digits and modest kerning; neighbouring narrow cells; stale accepted extractions.

- [x] RED: Add stream tests for the reported shadow and overprint boundaries, conflicting overlays,
  and mixed sizes/fonts. Test both child-process and direct extraction. Preserve exact repeats,
  decimals, negatives, modest kerning, raised markers and narrow cells with explicit expected text.
- [x] RED: Add ingestion tests asserting `refused`, zero accepted figures and zero extraction writes
  for ambiguous synthetic PDFs, including dry runs. Add `tables-11` to legacy-version tests.
- [x] GREEN: After recognised duplicates are removed, check remaining nonblank glyph rectangles
  before line/token assembly. Reject overlapping numeric glyphs beyond the existing 0.03 em
  kerning allowance, capped by half the narrower glyph's width under horizontal scaling;
  permit ordinary text kerning below half the narrower glyph's width.
  Use actual `y0` and size for vertical overlap, so shifted baselines/text rise cannot evade it.
  Raise `LAYOUT_CHANGED` with fixed code `ambiguous_glyph_overlap`; refuse the whole PDF.
- [x] GREEN: Advance reader to `pdf-words-3` and interpreter to `tables-12`, excluding older
  accepted extractions from analytics without modifying immutable history.
- [x] REFACTOR/VERIFY: Run focused stream, table, ingestion, isolation and deterministic replay
  tests; full backend and Ruff; frontend tests/types/lint/build and relevant browser integration.
  Backend type checking is not configured. Inspect the diff and obtain independent code review.
- [ ] Commit and push to `feat/phase-4ag-bank-pilot`; answer and resolve genuinely fixed threads.
  Request `@codex review` only when none is pending, at most three new cycles. Verify current-head
  review coverage and CI before declaring REVIEW CLEAN. ANZ remains BLOCKED.

Execution: native, sequential TDD under the owner's explicit instruction to proceed autonomously.
Verification evidence and review outcomes belong in `docs/phase-4ag-verification.md`.

## Task 10: Review cycle 1 — refuse truncated Form XObject traversal

Root cause: `_walk()` stops visiting iterable layout nodes at depth 8 without an error.
A depth-8 form's minus sign disappears while shallow digits survive; the June forecast
reproduces as `4` instead of `-4`. A nested footnote can disappear the same way.

- [x] RED: Add synthetic nested-Form support in `pdf_stream_support.py`. Stream tests
  must refuse signs/markers at form depths 8 and 9 in both isolation paths; depth 7
  must retain `-4`. Ingestion must refuse deep signs/markers without writes, including
  dry runs; supported-depth signs and footnotes must retain their numerical meaning.
- [x] GREEN: In `table_words._walk(node, depth=0)`, raise the existing
  `VALIDATION_FAILED / pdf_extraction_limit (layout depth)` at the iterable-node limit.
  Keep the depth bound unchanged. Advance reader/interpreter to `pdf-words-4` / `tables-13`
  and add `tables-12` to legacy-extraction tests so partial historical readings stay excluded.
- [x] VERIFY: Run focused stream/ingestion/view tests, full backend, Ruff, and final diff
  checks. Frontend has no code changes; the preceding 630 unit and 204/18/315 browser
  results remain applicable. Update current version labels and the existing verification record.
- [ ] Commit/push the existing branch, reply/resolve the new P2, then inspect review cycle 2
  and CI. Do not duplicate a review already triggered by the push. Maximum remains three cycles.
