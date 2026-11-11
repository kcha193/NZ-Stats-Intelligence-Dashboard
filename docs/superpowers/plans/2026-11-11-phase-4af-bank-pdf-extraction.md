# Phase 4AF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native) to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Deterministic, evidence-carrying PDF forecast-table extraction for the five-bank platform, reconciled against verified LLM claims, with 4AE defects fixed and source-readiness documented. Offline only.

**Architecture:** Positioned words from `pypdf` (isolated child) -> geometric table grid -> fixed-rule interpretation -> additive immutable store -> reconciliation -> gated `NormalizedForecast` feeding the unchanged 4AE analytics.

**Tech Stack:** Python 3.12, pypdf 6.21 (no new dependency), SQLite migration 015, FastAPI internal routes, React/TS (method label only), pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-11-phase-4af-bank-pdf-extraction-design.md`

## Global Constraints

- No bank contact, hosted/local model call, permission change, schedule, deployment, production write.
- Registry permission fields unchanged (`PRE_APPROVAL_SHA256` tripwire stays green).
- No migration alters an existing table or row. Table rows are immutable and purge-aware.
- Raw printed text is kept beside every parsed number; missing is never zero; nothing is guessed, filled, interpolated or carried forward.
- Bank text and values never enter committed frontend data, a snapshot, or the public/private gates.
- Timestamps UTC stored, Pacific/Auckland shown. Ruff line length per `pyproject.toml`. Python run with `PYTHONPATH=<worktree>/backend/src` (venv editable install points at main checkout); never `nohup` pytest.

## Review Focus

- A column shifted by one under a header must reject the table, not mis-assign values (Task 2, 4).
- `-`/`n/a` cells are missing, `0.0` is zero, `(0.3)` rejects, `−0.3` is negative (Task 3).
- An actual column beside a forecast column never yields a forecast for the actual period (Task 4).
- Same figure printed twice (table and prose) must not read as a conflict; different figures must (Task 8).
- Purging a version removes its table rows and blocks re-extraction (Task 5).

## Files

Create under `backend/src/nzstats/research/`: `table_words.py`, `table_grid.py`, `table_parse.py` (value, period, unit parsing), `table_forecast.py`, `table_store.py`, `table_reconcile.py`, `table_view.py`; `store/migrations/015_research_table_forecast.sql`. Tests under `backend/tests/research/`: `pdf_table_support.py`, `test_table_words.py`, `test_table_grid.py`, `test_table_parse.py`, `test_table_forecast.py`, `test_table_store.py`, `test_table_reconcile.py`, `test_table_view.py`, `test_table_e2e.py`, `test_table_isolation.py`, `test_phase4af_docs.py`. Modify: `bank_forecast.py`, `bank_view.py`, `bank_analytics.py`, `bank_models.py`, `bank_api.py`, `bank_status.py`, `cli.py`, `purge.py`, frontend `components/outlook/bank/*`. Docs listed in spec §8.

---

### Task 1: Positioned words and the synthetic table PDF builder

**Files:** Create `table_words.py`, `tests/research/pdf_table_support.py`, `tests/research/test_table_words.py`.

**Interfaces:**
- Produces `Word(page:int, x0:float, x1:float, y:float, size:float, text:str)` (frozen dataclass); `extract_words(body: bytes, limits: ExtractionLimits = ExtractionLimits(), *, isolate: bool | None = None, timeout: float = 60.0) -> tuple[Word, ...]` ordered by (page, -y, x0); raises `IngestError` exactly as `extract_pdf` does (too large, not pdf, encrypted, no pages, `no_text_layer`, limit).
- Produces `table_pdf(pages: list[list[tuple[float, float, str]]], *, size: float = 10) -> bytes`: each tuple is (x_left, y, text) drawn as its own `Tj` at that point; header comment `% SYNTHETIC FIXTURE`.

- [ ] Write `test_words_have_positions`: a one-page `table_pdf` with `(72, 700, "Table 1")`, `(72, 680, "OCR")`, `(300, 680, "3.25")` returns three words; `3.25` has `x0≈300`, `y≈680`, page 1; order is top-to-bottom, left-to-right.
- [ ] Write `test_word_boxes_do_not_overlap_for_adjacent_cells`, `test_encrypted_and_non_pdf_rejected`, `test_image_only_page_is_no_text_layer`, `test_isolated_equals_in_process`.
- [ ] Run: `PYTHONPATH=$PWD/src pytest tests/research/test_table_words.py` -> FAIL (module missing).
- [ ] Implement via `PdfReader.pages[i].extract_text(visitor_text=...)` using the combined `cm`×`tm` translation for x,y; estimate `x1 = x0 + width(text, size)` from a small Helvetica advance table (digits 0.556 em, `.` `,` 0.278, `-` 0.333, space 0.278, other 0.55). Reuse the child-process runner of `extract_pdf` by factoring the shared runner into a helper both call (no behaviour change; existing `test_extract_pdf.py` must stay green).
- [ ] Run tests -> PASS; run `tests/research/test_extract_pdf.py` -> PASS.
- [ ] Commit `feat: positioned word extraction for pdf tables`.

### Task 2: Table grid (rows, columns, multi-page, merged headers)

**Files:** Create `table_grid.py`, `tests/research/test_table_grid.py`.

**Interfaces:**
- Consumes `Word`.
- Produces `Cell(page, row, col, text, x0, x1, y)`; `GridTable(index:int, page_start:int, page_end:int, caption:str|None, header_rows: tuple[tuple[Cell,...],...], body_rows: tuple[tuple[Cell,...],...], column_anchors: tuple[float,...], notes: tuple[str,...])`; `Rejection(code:str, page:int|None, table:int|None, row:int|None, col:int|None)`; `find_tables(words) -> tuple[tuple[GridTable,...], tuple[Rejection,...]]`.

- [ ] Tests (each builds a PDF with `table_pdf`, runs `extract_words`, then `find_tables`): simple 1 label column + 4 period columns -> one table, 4 anchors, caption captured, notes after "Source:" captured; merged group header ("Actual" over two columns, "Forecast" over three) -> header_rows has two rows with spans recorded by x-overlap; table continued on page 2 with repeated header -> one table, `page_end == 2`, header not duplicated into body; page-2 table with a *different* header -> two tables; numeric cell overlapping two anchors -> `Rejection("ambiguous_columns")` and no table; body row with fewer numeric cells than anchors but each aligned -> kept (missing cells stay absent, not shifted); one row shifted right by a column width -> `ambiguous_columns`.
- [ ] Run -> FAIL.
- [ ] Implement: group words into lines by baseline (tolerance 0.4×size); a body line has a label chunk at the left and ≥1 numeric-looking chunks; header = contiguous non-numeric-dominated lines above the first body line; anchors from header chunk centres refined by body numeric right/centre edges; assignment by interval overlap with ≥50% of the narrower interval, else ambiguous.
- [ ] Run -> PASS. Commit `feat: geometric table grid with continuation and ambiguity rejection`.

### Task 3: Value, period and unit parsing

**Files:** Create `table_parse.py`, `tests/research/test_table_parse.py`.

**Interfaces:** Produces `parse_value(text:str) -> ParsedValue` where `ParsedValue(kind: Literal["number","missing","reject"], value: Decimal|None, raw: str, footnote: str|None, code: str|None)`; `canonical_horizon(group:str|None, header:str) -> tuple[str|None, str|None]` (horizon string accepted by `compare.horizon_of`, or `(None, code)` with `unparsed_period`/`contradictory_period`); `column_kind(group:str|None, header:str) -> Literal["actual","forecast","unknown"]`; `unit_of_text(*texts:str) -> tuple[str|None, str|None]` (`unit`, `code`: `contradictory_unit` or None).

- [ ] Tests pin: `"3.25"`→3.25; `"-0.3"`, `"−0.3"`→-0.3; `"0.0"`→Decimal 0 number; `"-"`, `"–"`, `"n/a"`, `".."`, `""`→missing; `"(0.3)"`→reject `bracketed_value`; `"1,234"`→1234; `"4.1*"`/`"4.1¹"`→4.1 with footnote; `"4.1x"`→reject `unrecognised_suffix`; `"Dec-26"` under group `"Forecast"` → `"December 2026 quarter"`; `"Mar-27 yr"` → `"year to March 2027"`; `"2026"` → `"calendar year 2026"`; `"Q4 2026"` → `"December 2026 quarter"`; `"Mar 2026"` under group `"Year to Dec"` → `contradictory_period`; `"2027f"`, `"Dec-27 (f)"`→forecast; `"Actual"` group→actual; no marker→unknown; `"p"` suffix→unknown; units `"% y/y"`, `"(%)"`, `"% pa"`→percent, `"ppt"`/`"percentage points"`→percentage_points, label `%` with caption `percentage points`→`contradictory_unit`.
- [ ] Run -> FAIL; implement with `Decimal` and fixed regexes; run -> PASS; commit.

### Task 4: Interpretation into forecasts and rejections

**Files:** Create `table_forecast.py`, `tests/research/test_table_forecast.py`.

**Interfaces:**
- Consumes `GridTable`, `parse_*`.
- Produces `TableForecast(table:int, page:int, row:int, col:int, indicator:str, label:str, period_text:str, horizon:str, kind:Literal["forecast","actual"], unit:str, raw_text:str, value:Decimal|None, missing:bool, author_role:Literal["author","third_party"], footnote:str|None, evidence: dict)` and `interpret(tables, *, publisher: str) -> tuple[tuple[TableForecast,...], tuple[Rejection,...]]`; constant `INTERPRETER_VERSION = "tables-1"`.
- `evidence` = `{page, table, row, col, bbox:[x0,x1,y], cell_text, row_label, header_texts:[...], caption}` (all from the PDF, untrusted).

- [ ] Tests (full PDFs through words→grid→interpret): OCR/CPI/GDP/unemployment rows each map; an "Actual" column and "Forecast" columns produce `kind` correctly and no forecast for an actual period; missing cell → `missing=True`, `value is None`, and *no* neighbouring value fills it; negative and zero preserved with raw text; two indicators in one label → `ambiguous_indicator`; unknown row ("Current account") → `unmapped_row` (a rejection, not an error); no unit → `unit_unstated`; "Source: RBNZ" caption → `author_role="third_party"`; row label "Annual CPI inflation (seasonally adjusted)" keeps the label verbatim; footnote that mentions a basis → `footnote_unresolved` rejection for that row; two columns with the same canonical horizon → `contradictory_period`; table with no actual/forecast markers → all columns `actual_or_forecast_unstated`.
- [ ] Run -> FAIL; implement with fixed phrase tables; run -> PASS; commit.

### Task 5: Migration 015, store, purge

**Files:** Create `015_research_table_forecast.sql`, `table_store.py`, `tests/research/test_table_store.py`; modify `purge.py`; extend `tests/research/test_migration.py`.

**Interfaces:** Produces `store_extraction(conn, version_id:int, extracted_at:datetime, forecasts, rejections, *, words_sha256:str) -> int | None` (returns extraction id; `None` if an identical `(version_id, interpreter_version, words_sha256)` extraction exists: idempotent); `load_forecasts(conn, version_id) -> list[StoredTableForecast]`; `load_rejections(conn, version_id)`.
Tables: `research_table_extraction(id, version_id FK, interpreter_version, words_sha256, extracted_at, forecast_count, rejection_count, UNIQUE(version_id, interpreter_version, words_sha256))`, `research_table_forecast(id, extraction_id FK, ordinal, ... , raw_text, value TEXT NULL, missing INTEGER, evidence TEXT)`, `research_table_rejection(id, extraction_id FK, code, page, tbl, row, col)`.

- [ ] Tests: migration applies on a database holding 4AE data without changing any existing table's rows (compare counts and a fingerprint of `research_*` pre-015 tables); stored value round-trips as exact decimal text; UPDATE and DELETE on forecast rows are refused; insert for a purged version refused; purge of a version deletes its table rows and later `store_extraction` refuses; second identical store returns `None`.
- [ ] Run -> FAIL; implement (triggers modelled on migration 010; extend purge's DB step to delete table rows in the same transaction, and have the delete trigger allow deletion only when the version is purged); run -> PASS; commit.

### Task 6: Extraction command

**Files:** Modify `cli.py`; create `research/table_ingest.py`, `tests/research/test_table_ingest.py`.

**Interfaces:** Produces `extract_version_tables(conn, version_id, store: ArtifactStore, registry, now) -> TableIngestResult(status: Literal["stored","unchanged","refused"], reason: str|None, forecasts:int, rejections:int)`; CLI `nzstats research tables extract VERSION_ID [--dry-run] [--json]` and `tables show VERSION_ID [--json]` (codes, counts, page/row/col; never cell text).

- [ ] Tests: refused with fixed reason when the institution's content policy is not `full_text` or the source is not permitted (synthetic registry cases) and for the five real bank keys; a stored synthetic version extracts and a rerun reports `unchanged`; `--dry-run` writes nothing; non-PDF version -> `refused: not_a_pdf`; CLI output contains no cell text; no network/provider use (socket guard fixture).
- [ ] Run -> FAIL; implement reading the raw artifact the way `summarise.load_sections` obtains stored data (use the stored raw file for the version, never a URL); run -> PASS; commit.

### Task 7: Reconciliation

**Files:** Create `table_reconcile.py`, `tests/research/test_table_reconcile.py`.

**Interfaces:** Consumes stored table forecasts and `NormalizedForecast` LLM claims. Produces `Reconciliation(table_id:int|None, claim_path:str|None, version_id:int, cls: Literal["exact_match","rounding_difference","units_mismatch","horizon_mismatch","attribution_mismatch","contradictory_value","ambiguous_or_unsupported","no_counterpart"], note_code:str)`; `reconcile(table: list[StoredTableForecast], claims: list[NormalizedForecast], rejections) -> list[Reconciliation]`; `summary_counts(rs) -> dict[str,int]`.

- [ ] Tests, one per class with exact values: 4.2 vs 4.2 exact; table 4.25 vs claim 4.3 and table 4.0 vs 4.0 handled (rounding: claim 4.3 equals 4.25 rounded half-up to one decimal -> `rounding_difference`); 4.2 vs 5.2 `contradictory_value`; table percent vs claim `percentage_points` `units_mismatch`; same label, horizons differ `horizon_mismatch`; claim issuer third party or table third party `attribution_mismatch`; two claims for one table row -> `ambiguous_or_unsupported`; table row with no claim and claim with no row -> `no_counterpart`; rejected table row paired by identity with a claim -> `ambiguous_or_unsupported`; agreement is never labelled verified (no such field).
- [ ] Implement matching by (version, indicator, canonical horizon, canonical label, adjustment); precedence as spec; run -> PASS; commit.

### Task 8: Table view and analytics integration

**Files:** Create `table_view.py`, `tests/research/test_table_view.py`; modify `bank_forecast.py` (`extraction_method: Literal["llm_verified","table"]`, `source_kind`), `bank_view.py` (merge), `bank_analytics.py` (same-document key `document_version_id`; exclusion codes), `bank_models.py` (REASONS for `table_*` codes).

**Interfaces:** Produces `table_forecasts(conn, registry, drafts_ctx, llm: list[NormalizedForecast]) -> tuple[list[NormalizedForecast], list[ExcludedClaim]]`; exclusion codes `table_unresolved_reconciliation`, `reconciliation_rounding`, `table_third_party`, `table_missing_value`, `table_actual`. `bank_view(...)` appends accepted table forecasts to `forecasts` and exclusions to `excluded`, without changing LLM handling.

- [ ] Tests: table-only value enters consensus with `extraction_method="table"`; table 4.2 equal to claim 4.2 counts the bank once (identical repeat); table 4.2 vs claim 5.2 -> both excluded `conflicting_forecasts`, older figure not substituted; rounding -> table excluded with `reconciliation_rounding`; actual/missing/third-party never enter; a bank not passing the draft gate's institution checks (policy not `full_text`) yields nothing; existing 4AE tests unchanged and green.
- [ ] Implement; run `tests/research -k "bank or table"` -> PASS; commit.

### Task 9: Internal API and UI method label

**Files:** Modify `bank_models.py`, `bank_api.py`, `frontend/src/components/outlook/bank/*`, regenerate `frontend/src/api/schema.d.ts`; tests `test_bank_api.py` additions and a frontend unit test.

- [ ] Backend test: `/forecasts` rows carry `extraction_method` (`"llm_verified"` or `"table"`) and a table row's evidence includes page and quote built from cell text (escaped by the client); frontend test: drawer shows "Table" or "AI" and escapes `<`.
- [ ] Implement; `npm run gen:api`; `npm test && npm run typecheck && npm run build`; commit.

### Task 10: Deferred 4AE defects (failing first, one commit each)

**Files:** `bank_forecast.py`, `bank_status.py`, `cli.py`, `bank_analytics.py`, frontend card; tests in existing `test_bank_forecast.py`, `test_bank_status.py`, `test_bank_view.py`, frontend tests.

- [ ] `derive_adjustment("Inflation, U.S.A. dollar", "")` and a lone `SA` (no parentheses, no "adjusted") must be `not_stated`; `(SA)` and "seasonally adjusted" stay adjusted.
- [ ] All-undated series: `bank_status` state not `ok` (new attention state `undated`, in `PRECEDENCE` between `missing` and `stale`, exit 1, rendered in CLI/JSON/UI).
- [ ] `bank-status` text output shows Pacific/Auckland times (JSON stays UTC ISO).
- [ ] Reproduce or refute `/freshness` exit-code claim; fix if reproduced.
- [ ] Failed-stance card: a failed claim's stance is collapsed with a "failed checks" label, not shown as the bank's view.
- [ ] Divergence ranks banks within a group (pure test); consensus explanation text states the contributor threshold rule.
- [ ] Measure gate re-evaluation per request with a fixture of N summaries; fix only if a request evaluates the gate more than once (share `drafts=`); otherwise record the measurement and defer.
- [ ] Document remaining deferrals in `docs/phase-4af-verification.md`.

### Task 11: End-to-end replay, determinism, isolation

**Files:** `tests/research/test_table_e2e.py`, `test_table_isolation.py`.

- [ ] Replay: synthetic registry; build PDFs for three banks (two report dates each) with simple, merged-header, multi-page and one bad table; manual import; `extract_version_tables`; also stored LLM claims via the 4AE scripted stand-in for the same documents where one disagrees; read `/forecasts`, `/consensus`, `/revisions`, `/evaluation`, `/freshness`; assert the exact table figures, reconciliation counts, exclusions with codes, and that a deliberately shifted table adds only rejections. Run twice from scratch -> byte-identical JSON. Socket and provider guards raise if touched. Real bank keys remain `permission_denied`.
- [ ] Isolation: no import of `table_*` outside `research/`; no table rows in snapshot/export; no public or private API exposes them; `PRE_APPROVAL_SHA256` unchanged; no scheduler/cron reference.
- [ ] Commit.

### Task 12: Documentation and project records

**Files:** `docs/phase-4af-source-readiness.md`, `phase-4af-pdf-tables.md`, `phase-4af-verification.md`, `phase-4af-runbook.md`, `phase-4af-first-bank-pilot.md`, `docs/progress.md`, `CLAUDE.md`, `tests/research/test_phase4af_docs.py` (names all five banks; links resolve; no registry permission claim of approval).

- [ ] Test first (links, banks named, "not examined" retained for BNZ/Kiwibank); write docs from registry evidence; commit.

### Task 13: Verification, review, PR

- [ ] Full backend (`run_in_background`, no nohup), ruff check/format, frontend test/typecheck/build/oxlint, `gen:api` clean, Playwright live + static, `git diff` inspected; independent code-review subagent on the branch; fix findings failing-first.
- [ ] Push branch, open PR (not merged, not deployed), update `current-projects.md` status line.

---

## Self-review

Spec coverage: §4 readiness -> Task 12; §5 modules -> Tasks 1-8; storage -> 5; reconciliation -> 7; analytics -> 8; §6 defects -> 10; §7 replay -> 11; §8 delivery -> 12-13. Types: `Word`, `Cell`, `GridTable`, `Rejection`, `TableForecast`, `StoredTableForecast`, `Reconciliation` are defined once and reused by name. Open: exact real-bank layouts are unknown by design (Task 4 phrase maps are a starter set).
