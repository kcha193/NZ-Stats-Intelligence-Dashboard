# Phase 4D release validation plan

**Goal:** Reconcile the Phase 4C stack and prepare an evidence-backed Stats NZ-only release candidate.

**Scope:** The owner's Phase 4D mission is the approved scope. Work proceeds in this session. No merge to main, deployment, source permission change or live statistical collection is authorised.

**Approach:** Preserve branch ancestry and existing source-specific ingestion, validation and publication gates. Test populated views using captured official test excerpts in an isolated fixture database; assess production through a read-only connection and disposable copies. Never turn test excerpts into production data.

- [x] Inspect PRs #19–#22 and full ancestry. Integrate both completed tips (`origin/feat/phase-4c-gdp` and `origin/feat/phase-4c-ocr`) on `feat/phase-4d-release`; preserve both progress records.
- [x] Independently reconcile official captured GDP/HLFS/LCI values, periods, definitions, dates and vintages; investigate material discrepancies before release.
- [x] Inventory production releases and raw artifacts read-only; specify exact missing vintages, URLs, bounded requests, restore verification and gated execution in `docs/phase-4d-backfill-plan.md`.
- [x] Run backend, frontend, live/static/research browser suites; inspect populated desktop/tablet/mobile/light/dark views and CSVs; preserve screenshots with explicit fixture provenance.
- [x] Verify migrated production copy, restore integrity, Stats NZ-only snapshot and local static release candidate. Inspect canonical URLs, headers, freshness and private-data exclusion. Recheck Actions and Docker availability.
- [x] Fix only demonstrated integration/release issues with focused regression coverage, inspect final diff, obtain independent review and open a draft PR into main with exact commit/test evidence and owner gates.

**Review focus:** earliest stored is not necessarily first published; corrected files must not silently become originals; forecast dates must precede outcomes; failed updates preserve last-known-good; fixtures and research must never enter a public production snapshot.

**Deliverables:** `docs/phase-4d-release.md`, statistical reconciliation, backfill plan, operations evidence and screenshots. Report NO-GO where required evidence or authorisation is absent; distinguish integration readiness from populated production readiness.
