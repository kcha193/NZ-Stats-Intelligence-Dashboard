# Phase 4AL PDF Parser Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether pdfplumber (PDF-skill guidance) or Camelot 2.x reads the forecast tables of ANZ version 4 (pages 5
and 8) more accurately than the existing `pdf-words-4` / `tables-14` pipeline, and recommend a parser on structural accuracy.

**Architecture:** A self-contained benchmark package outside the production tree (`benchmarks/pdf_tables/`) with its own venv
and pinned dependencies. Every parser is adapted to one neutral table model. Accuracy is scored against ground truth on
synthetic replicas of the two real layouts. The real document is scored only with truth-free structural invariants and
cross-parser agreement, emitted through a schema that admits only counts, booleans, durations and fixed codes.

**Tech Stack:** Python 3.12+, pdfplumber 0.11.10, camelot-py 2.0.0 (playa-pdf, opencv-python-headless), reportlab (synthetic
PDFs, per the PDF skill), existing `nzstats.research.table_words` / `table_grid`.

**Spec:** the Phase 4AL brief (owner, 2026-11-15) and `docs/phase-4ak-anz-pdf-compat.md` (layout facts of version 4).

## Global Constraints

- The genuine ANZ PDF stays local. No PDF text, image, figure or raw table enters the conversation, Git or any service.
- Real-document scripts print only masked structural diagnostics: integers, floats, booleans, fixed code strings.
- Agent-visible tests use synthetic PDFs only (`SYNTHETIC FIXTURE` text).
- No cloud PDF service, OCR API, or hosted or local model reads the real document. Camelot's lattice page render stays in memory.
- No production code, dependency or schema change (`backend/` untouched). No DB write; read-only `mode=ro`.
- Decide on structural accuracy, not extraction count. Economic validation (`table_forecast.interpret`) stays the gate.
- Pinned versions at least two weeks old: pdfplumber==0.11.10 (2026-06-15), camelot-py==2.0.0 (2026-06-04).
- No merge, push or deploy without the owner.

## Review Focus

1. A masked-output field that carries a string from the PDF (e.g. a header text used as a dict key) — must be refused by the
   output schema; test with canary words.
2. Superscript footnote digits fused into a value ("2.5" + "¹" read as "2.51") — scored as a false-positive numeric cell, not a match.
3. A borderless table where lattice/lines strategies find nothing — scored as a detection miss, never a crash.
4. Chart axis ticks near a table read as a table — counted as false-positive numeric cells.
5. Parser exception or timeout on one fixture — recorded as `error` for that parser and case, the run continues.

---

### Task 1: Benchmark scaffold, neutral model and synthetic fixtures with truth

**Files:**
- Create: `benchmarks/pdf_tables/requirements.txt`, `benchmarks/pdf_tables/README.md`, `benchmarks/pdf_tables/pdfbench/{__init__,model,synth}.py`
- Create: `benchmarks/pdf_tables/tests/test_synth.py`
- Modify: `.gitignore` (add `benchmarks/pdf_tables/.venv/`)

**Interfaces:**
- Produces: `BenchTable(page:int, bbox:tuple[float,float,float,float], grid:list[list[str]], header_rows:int|None, notes:list[str])`
  (`grid` rows top to bottom, cells left to right; `header_rows=None` when the parser has no header concept).
- Produces: `TruthTable(page, bbox, row_labels:list[str], col_headers:list[str], values:dict[tuple[int,int],str], stacked:list[int], markers:list[tuple[int,str]], notes:list[str])`.
- Produces: `Case(name:str, pdf:bytes, truth:list[TruthTable])`; `cases() -> list[Case]`.

Cases (all text synthetic): `p5_annual` (prose paragraph above "Table 1" caption, 5 unmarked + 3 `f` years, superscript
marker on one row label, a small-digit marker line, a "Source:" line naming a third party, no rules); `p8_stacked` (two
borderless tables, a "Current" header 0.59 em above and a date 0.61 em below the period line, 8 quarter columns, 6 and 4
rows); `ruled_control` (fully ruled grid, the lattice home case); `fused_superscript` (value with a raised small marker
directly after it); `axis_noise` (chart tick numbers beside a table); `tight_columns` (two value columns 0.5 em apart).

- [ ] Write `test_synth.py`: every case's PDF opens with pypdf, has the page count implied by its truth, and every truth value
  string occurs in the page's text exactly once per occurrence count; fixtures contain `SYNTHETIC FIXTURE`.
- [ ] Run, watch fail; implement with reportlab `canvas.drawString` at explicit coordinates and sizes; run, pass; commit.

### Task 2: Parser adapters

**Files:** Create `pdfbench/adapters.py`, `tests/test_adapters.py`.

**Interfaces:**
- Consumes: `BenchTable`, `cases()`.
- Produces: `PARSERS: dict[str, Callable[[bytes, list[int]], list[BenchTable]]]` with keys `existing` (extract_words +
  find_tables, header rows = `len(header_rows)`, notes kept), `plumber_default` (skill: `page.extract_tables()`),
  `plumber_lines` (skill REFERENCE settings: lines/lines, snap 3, intersection 15), `plumber_text` (text/text, beyond the skill,
  for fairness), `camelot_lattice`, `camelot_stream`, `camelot_network`, `camelot_hybrid`. Pages are 1-based.
- Produces: `run(parser:str, pdf:bytes, pages:list[int], timeout:float=60) -> tuple[list[BenchTable]|None, str|None, float]`
  (tables, error code `error`/`timeout`, seconds); runs in a child process.

- [ ] Tests: on `ruled_control` every parser returns ≥1 table except none is required of `existing`; on a blank page every
  parser returns `[]`; a parser that raises yields `(None, "error", t)` (inject a fake parser).
- [ ] Fail, implement, pass, commit.

### Task 3: Truth scoring

**Files:** Create `pdfbench/metrics.py`, `tests/test_metrics.py`.

**Interfaces:** `score(truth:list[TruthTable], got:list[BenchTable]) -> Score` with integer fields: `tables_truth`,
`tables_found` (IoU ≥ 0.5), `tables_extra`, `values_truth`, `values_present` (exact text anywhere), `values_aligned` (exact
text, same grid row holds the row label, same grid column holds the column header above it), `stacked_joined` (both
fragments in one column), `markers_kept` (marker separable from the value and present), `notes_kept`,
`numeric_false_positive` (numeric-looking cells that are not a truth value, header or label, incl. fused and merged numbers).

- [ ] Tests on hand-built `BenchTable`s: perfect grid scores all; a shifted column scores present but not aligned; "2.51" for
  truth "2.5" + marker "1" counts 1 false positive and 0 present; "1.2 3.4" in one cell counts 1 false positive.
- [ ] Fail, implement, pass, commit.

### Task 4: Synthetic benchmark run

**Files:** Create `pdfbench/run_synthetic.py` (prints a Markdown table per case × parser, plus timings), `tests/test_run_synthetic.py`.

- [ ] Test: output has one row per (case, parser) and no exception escapes. Fail, implement, pass, commit. Run it; keep output.

### Task 5: Masked real-document diagnostics

**Files:** Create `pdfbench/masked.py`, `pdfbench/run_masked.py`, `tests/test_masked.py`.

**Interfaces:** `diagnose(pdf:bytes, pages:list[int]) -> dict` and `emit(d:dict) -> str`. `emit` refuses any value that is not
int, float, bool, None, or a code from a fixed allow-list, and any key not in a fixed allow-list. Per parser and page:
`tables`, `shapes` (rows, cols), `numeric_cells`, `multi_number_cells`, `fused_small_glyph_cells` (a numeric cell whose
glyphs, looked up in pdfplumber `chars`, mix sizes below 0.75 × the largest), `uncovered_numeric_tokens` (numeric glyph runs
inside the table bbox in no cell), `agreement_with_existing` (share of the existing pipeline's value cells reproduced at the
same row-label/column-header position, compared by in-memory equality only), `seconds`. Page facts: ruling `lines`, `rects`, `curves`.
`run_masked.py VERSION_ID`: opens `data/nzstats.db` with `mode=ro`, resolves the raw path, refuses on SHA mismatch, never prints paths.

- [ ] Tests: canary run on a synthetic PDF whose words are canaries; `emit` output contains no canary and no digit sequence
  from the fixture's values; `emit` refuses a string value and an unknown key.
- [ ] Fail, implement, pass, commit. Run on version 4, pages 5 and 8; keep the masked output.

### Task 6: Record, recommendation, integration and migration plan

**Files:** Create `docs/phase-4al-pdf-parser-benchmark.md`; modify `docs/progress.md`, `CLAUDE.md` (one phase sentence).

- [ ] Write results (synthetic truth table, masked real-document table, speed and dependency table), recommendation, integration
  architecture (parser behind the `Word`/`GridTable` boundary, `interpret()` unchanged), tests and migration plan. Commit.

### Task 7: Independent review

- [ ] Dispatch a reviewer (no access to `data/`) on the branch diff and the record; fix findings test-first; record the outcome.
