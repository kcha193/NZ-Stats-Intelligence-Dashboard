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
