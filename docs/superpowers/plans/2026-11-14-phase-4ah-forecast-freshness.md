# Phase 4AH forecast freshness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A bank's older forecast is never shown as current, or used in the consensus, while the bank has a newer outlook report that was not fully read and does not restate that measure.

**Architecture:** Read-only document states computed in `research/table_view.py`, carried on `BankView.documents`, applied in `research/bank_analytics._prepare` for current views only; an additive `vintages` list on the internal forecasts API. No migration.

**Tech Stack:** Python 3.12, SQLite, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-phase-4ah-forecast-freshness-design.md`

Execution: native (three coupled tasks), then one independent whole-branch review.

## Global Constraints

- No schema migration, no permission/registry change, no network, no model call, no change to extraction rules.
- Fixed exclusion codes: `newer_report_incomplete`, `newer_report_not_read`; reasons exactly as in the spec.
- Scenario-only rejections (`scenario_table`, `scenario_row`, `scenario_column`) affect scenario groups only.
- Revisions and evaluation keep every accepted vintage (`current=False`).
- Stored rows are not changed; immutable triggers stay.

## Review Focus

- Undated newer report: must not trigger (test in Task 2).
- Newer weekly (non-outlook) report: must not trigger (Task 2).
- Named (non-auto) mode: table extractions do not count; an unnamed newer report is `not_read` (Task 1).
- Older-interpreter extraction only: `not_read`, never `read` (Task 1).
- Restating figure from a still newer report: older figure stays an earlier vintage (Task 2).

---

### Task 1: Document states

**Files:**
- Modify: `backend/src/nzstats/research/table_view.py`, `backend/src/nzstats/research/bank_view.py`
- Test: `backend/tests/research/test_table_freshness.py` (new)

**Interfaces:**
- Produces: `DocumentState(institution_key: str, version_id: int, published_on: str, state: Literal["read","incomplete","incomplete_scenario","not_read"])` (frozen dataclass, in `table_view.py`); `document_states(conn, registry, allowlist, read_versions: set[int], adapters=ADAPTERS) -> list[DocumentState]`; `BankView.documents: list[DocumentState] = []`, filled by `bank_view` with `read_versions` = version ids of admitted bank drafts.

- [ ] Step 1: tests (fail first): clean extraction -> `read`; footnote/`ambiguous_columns` rejection -> `incomplete`; dash in an own forecast cell -> `incomplete`; scenario-only -> `incomplete_scenario`; held PDF never extracted -> `not_read`; legacy interpreter only -> `not_read`; not auto mode -> `not_read`; superseded, duplicate, purged, undated, weekly, route revoked -> no state.
- [ ] Step 2: run `PYTHONPATH=src python -m pytest tests/research/test_table_freshness.py`; expect import failure.
- [ ] Step 3: implement; reuse `_shown` and `report_kind_of`; query current versions of bank publications with `published_on`.
- [ ] Step 4: rerun; pass. Commit `feat: Phase 4AH document freshness states for bank reports`.

### Task 2: The rule in the analytics

**Files:**
- Modify: `backend/src/nzstats/research/bank_analytics.py`, `backend/src/nzstats/research/bank_api.py`
- Test: `backend/tests/research/test_table_freshness.py`

**Interfaces:**
- Consumes: `BankView.documents`.
- Produces: `_prepare(view, *, outlook_only, dated_only, current)`; `bank_exclusions(view, *, outlook_only, dated_only, current=True)`; `REASONS` gains the two codes. `bank_comparison`/`bank_consensus` use `current=True`; `bank_revisions`/`bank_evaluation` use `current=False`; revisions endpoint passes `current=False`.

- [ ] Step 1: tests through `bank_view` on stored synthetic PDFs (two vintages, `published` 2026-08-01 and 2026-11-01): newer valid -> newer current, older earlier vintage; newer footnote cell -> older excluded `newer_report_incomplete` in comparison and consensus, present in revisions; ambiguous cell -> same; newer held unextracted -> `newer_report_not_read`; duplicate newer -> no exclusion; corrected newer (new version, unextracted) -> `not_read`; purged newer -> no exclusion; dash -> excluded; two horizons, one restated -> only the unrestated one excluded; scenario-only -> central kept.
- [ ] Step 2: run; fail.
- [ ] Step 3: implement in `_prepare` after `eligible` is built: newest blocking date per (bank, scope), restated set = identities with an eligible figure dated >= that date.
- [ ] Step 4: rerun focused + `tests/research/test_bank_*.py tests/research/test_table_*.py`; pass. Commit.

### Task 3: Latest published versus latest accepted

**Files:**
- Modify: `backend/src/nzstats/research/bank_models.py`, `backend/src/nzstats/research/bank_api.py`
- Test: `backend/tests/research/test_table_freshness.py`

**Interfaces:**
- Produces: `BankVintageOut(institution_key: str, latest_published_on: str, latest_accepted_on: str | None, state: str, current: bool)`; `BankForecastsOut.vintages: list[BankVintageOut] = []`; `bank_vintages(view) -> list[BankVintageOut]` in `bank_analytics.py`.

- [ ] Step 1: tests: incomplete newer report -> `latest_published_on=2026-11-01`, `latest_accepted_on=2026-11-01` or older as applicable, `current=False`; clean -> `current=True`; API returns `vintages` and the exclusion with its reason.
- [ ] Step 2-4: fail, implement, pass. Commit.

### Task 4: Docs, review, verification, PR

- [ ] Phase docs: `docs/phase-4ah-forecast-freshness.md` (design summary, ANZ decision summary, BLOCKED verdict, verification, review record); runbook addendum; `docs/progress.md` entry; CLAUDE.md one-line phase note.
- [ ] Independent review (fresh reviewer, concise `file:line | severity | finding | fix`); fix confirmed critical/high.
- [ ] Full gates: backend pytest, ruff check/format, frontend test/typecheck/build, Playwright (dashboard, research, static), gitleaks on diff.
- [ ] Push branch, open PR; do not merge.
