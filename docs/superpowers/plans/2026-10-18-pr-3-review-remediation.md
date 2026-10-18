# PR #3 ECT Revision Comparison Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ECT release analysis compare revisions and decomposition against the same preceding distinct publication, while retaining within-publication corrections separately.

**Architecture:** Keep the generic revision API unchanged. Resolve the preceding distinct publication once in the ECT analysis layer with the existing storage ordering, pass that release explicitly to `revision_view()`, and reuse the resulting vintage for decomposition.

**Tech Stack:** Python 3.11+, SQLite, pytest, Ruff; existing React checks for regression verification only.

**Spec:** `docs/superpowers/specs/2026-10-11-nz-stats-dashboard-design.md`; PR review discussion `#discussion_r4304534495` supplies the defect-specific acceptance criteria.

## Global Constraints

- Preserve historical vintages, SQLite migrations, measurement metadata, statistical units, frequencies and seasonal-adjustment definitions.
- Keep within-publication corrections distinct from inter-publication revisions and new-period movements.
- Use captured official fixtures only; routine tests must not contact Stats NZ.
- Do not change shared revision APIs unless the ECT layer cannot select the correct pair explicitly.
- Do not merge, force-push or deploy.

## Review Focus

- A corrected current release must still compare revisions with the preceding publication.
- Multiple current-release corrections must not alter the inter-publication comparison base.
- A corrected preceding publication must contribute its latest active valid vintage.
- Historical and out-of-order ingestion must follow publication chronology, not insertion order.
- Incompatible vintage definitions must withhold both revision statistics and decomposition.

---

### Task 1: Pin ECT publication boundaries and reconciliation

**Files:**
- Create: `backend/tests/insights/test_ect_revisions.py`
- Modify: `backend/src/nzstats/insights/ect.py`

**Interfaces:**
- Consumes: `repo.previous_vintage(conn, series_key, published_before_utc)` and `revision_view(..., base_release_key=..., compare_release_key=...)`.
- Produces: ECT `RevisionBlock` and `PreviousComparison` values derived from one preceding-publication vintage.

- [x] **Step 1: Write failing high-level ECT regression tests**

Add deterministic cases for consecutive publications, corrected current publications, multiple corrections, a corrected prior publication, first publication, historical selection, out-of-order backfills, incompatible definitions and numerical decomposition reconciliation. Run the existing migration correction-separation test as the cross-category guard.

- [x] **Step 2: Run the focused tests and verify RED**

Run: `cd backend && .venv/bin/pytest tests/insights/test_ect_revisions.py -q`

Expected: corrected-release cases fail because the revision base title/key is the current publication while decomposition uses the prior publication.

- [x] **Step 3: Implement the smallest ECT-layer fix**

Resolve `previous = repo.previous_vintage(...)` before calling `revision_view()`. Call the revision view only when `previous` exists, with `base_release_key=previous.release_key` and the selected current release key; reuse `previous` for decomposition and give the no-prior-publication state an explicit note.

- [x] **Step 4: Run focused tests and verify GREEN**

Run: `cd backend && .venv/bin/pytest tests/insights/test_ect_revisions.py tests/insights/test_corrections.py::test_same_publication_correction_keeps_earlier_publication_revisions_separate -q`

Expected: all selected tests pass.

- [x] **Step 5: Commit the verified fix**

Commit the plan, regression tests and minimal ECT implementation together with a conventional `fix:` message.

### Task 2: Verify, publish and close the review loop

**Files:**
- Modify only if a genuine test, CI or subsequent review finding requires it.

**Interfaces:**
- Consumes: Task 1's verified branch HEAD and GitHub PR #3 review/check state.
- Produces: pushed commits, replies on original actionable threads, resolved verified threads and a completed fresh Codex review round.

- [ ] **Step 1: Run repository verification**

Run backend pytest, Ruff lint and Ruff format; run frontend unit tests, typecheck, lint and build. Run Playwright only if the API/dashboard contract or visual behaviour changes.

- [ ] **Step 2: Inspect the final diff and commit any verification-only correction**

Expected: no unrelated changes, no migration or frontend contract changes, and a clean working tree after commit.

- [ ] **Step 3: Push and update the original review thread**

Push without force, reply with root cause/change/tests/commit, then resolve the verified thread.

- [ ] **Step 4: Request and observe a fresh Codex review**

Post `@codex review` once for the substantive new HEAD, wait for completion and inspect new threads and required checks. Repeat only for genuine new findings, to a maximum of four new rounds.

- [ ] **Step 5: Record the final status**

Update `docs/progress.md` and the canonical project status only if the PR's status or current focus materially changed; do not merge or deploy.
