# Phase 4AF design: bank activation readiness and deterministic PDF forecast tables

11 November 2026, Pacific/Auckland. Baseline `main` `a3a5449` (Phase 4AE merged, PR #58).
Status: written from the owner's brief; scope is the offline subset below. The "my calls" are mine and cheap to reverse.

## 1. Intent and why

Phase 4AE built a five-bank comparison that can only be fed by model-extracted claims, and proved it offline. Two things stand
between it and a first real bank: (a) nobody has recorded, per bank and per decision, what evidence the owner still has to
gather; (b) the most numeric part of a bank outlook, the forecast table, is read by a model from flattened text, which is the
riskiest way to read a table. This phase prepares both, without touching a bank.

## 2. Goals, non-goals, anti-goals

Goals
- A source-readiness matrix and a per-bank approval checklist (documentation only, from the registry's recorded evidence).
- A deterministic PDF table layer: word positions, rows and columns, table assembly across pages and merged headings,
  interpretation of OCR, CPI inflation, GDP growth and unemployment rows, with cell-level evidence.
- Storage of table-derived forecasts in a new, additive, immutable store, tied to the document version.
- Reconciliation against existing verified LLM claims with fixed classes.
- Only sufficiently evidenced, comparable table figures reach the existing bank analytics (consensus, revisions, divergence).
- Fix demonstrated 4AE defects that touch correctness, evidence, privacy or operations, failing test first.
- A full offline replay from synthetic PDF to the internal dashboard, run twice, byte-identical.

Non-goals
- Any bank contact, crawl, permission change, registry permission edit, hosted or local model call, schedule or deployment.
- OCR of scanned PDFs (an image-only page is reported as `no_text_layer`; the 4AE rule that OCR stays synthetic is unchanged).
- Charts and text-box forecasts; only tables with a text layer.
- A general PDF table library or a new third-party dependency.

Anti-goals (a pass that would still be a failure)
- A table figure that is plausible but guessed: a shifted column, a mislabelled period, an actual read as a forecast, a missing
  cell filled from a neighbour, a bracketed negative read as positive.
- Two methods agreeing being shown as "verified". Agreement is recorded as agreement and nothing more.
- Bank text or values in committed frontend data, a snapshot, the public or private gates, or the Stats NZ pipeline.

## 3. Constraints (unchanged boundaries)

All 4AE rules stand. Every bank stays `needs_review`; `manual_import`, `llm_processing` and `private_display` stay denied, so
the new code is dormant against the real registry and proven on a synthetic registry. Table forecasts are shown only through
the internal draft gate's institution checks (loopback, `source_permitted`, `content_policy = full_text`, internal display).
Table text is untrusted data: it is never executed, never sent to a model, escaped wherever rendered. Purge covers it.

## 4. Source readiness (Workstream A, documentation)

`docs/phase-4af-source-readiness.md` holds: per-decision evidence gaps (discovery, acquisition, full-text storage, manual
import, local model, hosted model, internal display), a bank-by-bank checklist (exact source terms to read, evidence to record,
the owner's pending decision), the report formats and ingestion paths each bank could offer after approval, and the
recommended first-bank pilot. It is derived from `config/research_sources.toml` and the 4AE matrix. No new web read is made;
anything the registry marks unexamined stays "not examined". A test pins that the matrix names all five banks and that no
registry permission field changed (the existing `PRE_APPROVAL_SHA256` tripwire already does the second).

Table extraction is a local, deterministic operation on a document already held, so it needs the same permissions as holding
and showing it, and no model permission. This is my reading of the registry's separate decisions; the matrix says so, and the
owner decides whether *table parsing of a manually imported owner copy* needs its own flag (my call: it does not, because it
adds no processing destination, but the owner may require one).

## 5. Architecture (Workstream B)

Reuse `extract_pdf`'s hardened child-process pattern (isolated `python -I`, wall-clock, CPU and memory limits, JSON only
back). New modules in `backend/src/nzstats/research/`:

| Module | Job | Pure? |
|---|---|---|
| `table_words.py` | `pypdf` `visitor_text` -> words with page, x, y, font size; isolated child; bounded | I/O, isolated |
| `table_grid.py` | words -> lines (y clustering) -> column anchors -> `GridTable` (cells with bbox, page, row, col); joins a table continued over pages only when column anchors, header text and unit agree | pure |
| `table_forecast.py` | `GridTable` -> `TableForecast` records or `TableRejection` records; fixed phrase maps; no guessing | pure |
| `table_store.py` | persist extraction runs, forecasts and rejections; idempotent; purge | SQL |
| `table_reconcile.py` | table forecast vs LLM claim: fixed classes | pure |
| `table_view.py` | gated, evidenced table forecasts -> `NormalizedForecast` for the existing analytics | read-only |

`pypdf` gives positioned text, not table lines, so detection is geometric: rows are words sharing a baseline within a tolerance,
columns are x anchors recurring over rows, and a numeric cell belongs to the column whose anchor it overlaps (right-aligned
numbers are compared by right edge). A cell that overlaps two anchors, or a row whose numeric count differs from the header
period count, makes the *table* ambiguous and it is rejected whole (`ambiguous_columns`), never repaired.

### Interpretation rules (fixed, versioned `tables-1`)

- Indicator from the row label by fixed phrases: OCR ("official cash rate", "OCR"), CPI inflation ("CPI", "consumer price",
  "inflation" with annual / quarterly cadence kept in the label), GDP ("GDP", "real gross domestic product" with
  "growth" or "% change"), unemployment ("unemployment rate"). Two indicators matched, or none, rejects the row
  (`ambiguous_indicator`, `unmapped_row`). The stated label is kept; adjustment wording is derived by the existing
  `bank_forecast` functions, not re-implemented.
- Period from the column header, canonicalised to a form `compare.horizon_of` accepts ("year to March 2027", "June 2026
  quarter", "calendar year 2026"). Header text that cannot be canonicalised, or two headers claiming the same period, or a
  header period that contradicts its group label (e.g. "Dec 2026" under "Year to March"), rejects the column
  (`contradictory_period`, `unparsed_period`). Fiscal vs calendar year follows the stated wording only.
- Actual vs forecast from an explicit marker: a group header ("Actual", "Forecast", "Projection") or a per-column suffix
  ("f", "F", "(f)", "e", "p" is *not* accepted). No marker means `unknown` and the column is rejected (`actual_or_forecast_unstated`).
  Actuals are stored as `actual` rows and are never forecasts; they feed nothing.
- Unit from the table caption, a unit column, or a bracket in the row label ("%", "% y/y", "% q/q", "% pa", "percentage points").
  Mixed units in one table are allowed if each row states its own; a row with none is rejected (`unit_unstated`). A unit that
  disagrees between the label and the table caption rejects the row (`contradictory_unit`).
- Values: kept as original text (`raw_text`) beside the parsed decimal. `-`, unicode minus and `−` are negative signs only when
  attached to digits; a lone dash, `n/a`, `..` or empty is **missing** (stored as missing, never zero, never filled). `0`, `0.0` are
  zero. A value in brackets is ambiguous (some reports bracket negatives) and rejects the cell (`bracketed_value`) unless the table
  note states the convention (not implemented; it stays rejected). Thousands separators and footnote markers are handled by one
  tested function; an unrecognised suffix rejects the cell.
- Footnotes: a footnote marker on a figure is recorded in the evidence and does not change the value; a footnote that states
  a different basis cannot be applied automatically, so the row is flagged `footnote_unresolved` and is not used by analytics.
- Forecast author: the document's publishing bank, unless the table or its caption names another source ("Source: RBNZ",
  "Treasury", "Consensus"), in which case the forecast is `third_party` and excluded from bank analytics like any other
  third-party claim (`attribution` tests).

### Storage (backward compatible, migration `015_research_table_forecast.sql`)

Additive only; no existing table or row is altered. `research_table_extraction` (one row per version, extractor
version and input hash; status; counts; unique so a rerun is idempotent), `research_table_forecast` (one row per accepted
forecast or actual: indicator, label, period text as printed and canonical horizon, kind `forecast|actual`, unit, `raw_text`,
`value` (NULL when missing), `missing`, author role, evidence JSON of `{version_id, page, table, row, col, bbox, cell_text,
header_texts}`), and `research_table_rejection` (code, page, table, optional cell, no free text). Rows are immutable;
triggers refuse a row for a purged version, and a purge deletes the version's table rows in its transaction. Existing documents
and summaries are untouched; a version with no extraction row simply has no table forecasts.

### Integration with the analytics (Workstream C)

`table_view` produces a `NormalizedForecast` with `extraction_method = "table"` only when all of: the version is current and
passes the draft gate's institution checks; the forecast is `kind = forecast`; the row has a value; the mapping carried no
rejection; the author is the bank; no `footnote_unresolved`; reconciliation class is `exact`, `no_counterpart`.
Everything else is listed by a fixed exclusion code, never by text. The existing identity rules then do the rest: a table value
that differs from a verified LLM claim for the same bank, document and measure is a *conflict* and both are left out, which is
the behaviour we want from `contradictory_value`.

Reconciliation classes (fixed, in this precedence): `exact_match`; `rounding_difference` (the more precise value, rounded
half-up to the other's printed precision, equals it); `units_mismatch`; `horizon_mismatch` (same row identity, different
canonical horizon); `attribution_mismatch` (one side third party or a different author); `contradictory_value`;
`ambiguous_or_unsupported` (a side rejected, or the LLM claim is not matched by a table row, or the match is not one-to-one);
`no_counterpart` (table row with no LLM claim, or the reverse). Matching is by institution, version, indicator, canonical
horizon and the existing `canonical_label`/adjustment identity, and must be one-to-one or it is `ambiguous_or_unsupported`.
The report states counts only and each pair's evidence references; agreement is reported as "two extraction methods agree",
never "verified". `rounding_difference` keeps the LLM claim and leaves the table figure out of analytics
(`reconciliation_rounding`; my call: a rounded and a precise value would otherwise be a spurious conflict).

`NormalizedForecast` gains `source_kind` (`llm` / `table`); table forecasts use a negative `forecast.summary_id`
(`-extraction_id`, a documented sentinel, so no public model changes) and the analytics' same-document test is keyed on
`document_version_id` instead of `summary_id`, which is what "same document" meant. Internal API responses gain
`extraction_method`; the UI shows "Table" or "AI" beside the source in the evidence drawer and escapes all text.

## 6. Existing 4AE defects (Workstream D)

Triage rule: fix what produces a wrong number, a wrong state, a privacy leak or a misleading operational signal; defer wording.

| Item | Decision |
|---|---|
| `derive_adjustment`: "U.S.A.", lone "SA" read as seasonally adjusted | fix (changes a figure's partition) |
| all-undated series reports `ok` | fix (an unreadable freshness is not ok) |
| `bank-status` prints UTC | fix (project rule: present Pacific/Auckland) |
| `/freshness` exit code 0 on unreadable registry | fix if reproduced in `bank-status` (operational) |
| failed stance shown in full on the card | fix (a failed claim must not read as the bank's view) |
| consensus/divergence explanation | fix only if a stated rule is not shown; add banks' rank within group (small, pure) |
| gate re-evaluated per route | measure first; fix only with a measured cost (one evaluation shared per request is already supported by `drafts=`) |
| empty-state wording, revisions "Unchanged" copy, `UNIT_LABELS` import, three loose tests | defer, recorded |

## 7. Tests and the end-to-end replay (Workstream E)

TDD throughout: write the test, watch it fail for the right reason. A synthetic PDF builder with explicit coordinates
(`tests/research/pdf_table_support.py`, text marked SYNTHETIC) produces: simple table; merged group headers; a table continued
on page 2 with a repeated header; contradictory period labels; incomplete rows (missing cells); several units; a shifted
column layout (one row offset by a column); right-aligned and left-aligned numbers; footnotes; bracketed values; third-party
source captions; an image-only page. The replay: synthetic PDF -> manual import (synthetic registry) -> table extraction ->
store -> reconciliation -> bank view -> analytics -> internal routes -> UI strings, twice from scratch, byte-identical;
real bank keys remain permission-denied; zero network and zero model calls (a socket guard and a provider guard in the test).

## 8. Delivery

Spec (this), plan, `docs/phase-4af-source-readiness.md`, `docs/phase-4af-pdf-tables.md` (architecture and limits),
`docs/phase-4af-verification.md`, `docs/phase-4af-runbook.md`, `docs/phase-4af-first-bank-pilot.md`, progress and project
`CLAUDE.md` updates, a pull request that is not merged or deployed.

## 9. My calls, in one list

1. Skipped the interview and the subagent builder-check; the owner's brief served as the full description.
2. No new dependency: `pypdf`'s `visitor_text` provides positions.
3. Rounding differences keep the LLM claim and drop the table figure from analytics.
4. Bracketed values and missing period/actual markers reject rather than infer.
5. Table parsing of an already-held copy needs no new registry flag (owner may overrule).
6. Negative `summary_id` sentinel for table forecasts instead of widening a public model.
7. Mixed shifted layouts reject the whole table.

## 10. Known limits (stated up front)

Text-layer PDFs with ruled or aligned tables only; real bank layouts are unknown and untested (no real report was read), so the
extractor's phrase maps are a starting set built from the owner's brief, and the first-bank pilot must begin with a dry
extraction on an owner-supplied copy and a human check of every cell before any figure reaches analytics.
