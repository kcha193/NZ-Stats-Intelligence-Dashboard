# Phase 4B: targeted dashboard UX and accessibility remediation

28 October 2026 NZDT. **Verdict: PASS** for the four scoped findings. Local changes only, ready for review.
This is a tested implementation result, not a real-world usability or WCAG conformance assessment.

## Isolation and preservation

| Checkout | Initial branch | Initial HEAD | Initial worktree |
| --- | --- | --- | --- |
| Dashboard original | `feat/phase-3d-a-research-pilot` | `f525ded5d47439b624f8ca725d91005df9bbcd81` | Clean |
| Vault | `main` | `217f76731a208b728c698f71498ac37a8011546a` | 6 tracked modifications, 27 individual untracked files (`status -uall`) |
| Remediation | `fix/phase-4b-dashboard-ux` | `93d114eb531a8d64c7bbe7dff90cb1c8ebd1693f` | Dedicated `.worktrees/phase-4b-dashboard-ux`, initially clean |

`git ls-remote origin refs/heads/main` matched the cached integration tip `93d114e`, the merge of PR #14.
Its frontend tree matches the evaluation checkout. No fetch, stash, reset, overwrite, commit, push, deployment,
publication, dependency installation or new service installation. Existing Node 20.20.2, node_modules and backend
venv were reused. The original research checkout remains on its original HEAD and branch with no changes; no
research source, permission, model, ingestion or statistical calculation was changed.

Vault changes are separate: one dated paragraph in the NZ Stats project status entry. All pre-existing vault file
hashes, including the capability registry and Phase 1–4 reports, are preserved after removing that exact paragraph.
No vault frontend guidance was edited: the adopted check belongs in the dashboard's established review guidance.

## Implementation evidence and measurements

| Finding | Before | Implemented and verified |
| --- | --- | --- |
| B1 | 58 plotted quarters, only latest 24 in table; range only disclosed to screen readers | Existing disclosure shows all 58 rows, Mar 2012–Jun 2026, with visible period/row count and date caption. No pagination. Full/3y/5y/10y filter changes yield 58/12/20/40 rows in supplied chart-series order; shorter and empty histories tested. Multi-series rows keep their series labels and input order. |
| B2 | Zero h1 elements during loading, 404 and 503 | Exactly one Inflation h1 in initial loading, 404, 503, pending retry and success. Header is outside QueryBoundary; KPI section has an h2 before its h3 tiles. Existing alerts, loading status and retry retained. |
| C1 | At 390px: segmented labels 24px high, exports 28px, select 34px | At 390px in light/dark: all three are 44px high; range labels 59.22–79.5px wide, exports 165.81/157.23px, select 303px. Disclosure targets 324×44px (previously 324×16px). Measured targets do not overlap. At 1440px, original 24/28/34px heights remain. |
| B3 | Raw headers, unformatted/left-aligned values, repetitive CSV provenance | CPI history display reduces 12 raw columns to five labelled columns: quarter ended, series, index with base, quarterly/annual percent. Index uses integer grouping, rates one decimal, contributions three decimals in percentage points; numbers right-aligned. Periods stay on one line. Missing is n/a, zero is 0.0. Source/capture remain in figure caption; omitted identifiers/adjustment/release metadata remain in CSV. |

ChartCard now accepts optional display columns. CSV download still calls `toCsv(csvRows)` without rounding,
filtering, reordering or removing metadata. Tests retain values such as `1.234567`, null's empty CSV cell and zero.
Unknown period strings are retained verbatim; valid YYYY-MM labels use the existing month formatter. Generic chart
callers retain their complete column set and now have humanised labels/all rows. Long tables remain in the existing
keyboard-focusable horizontal scroll region. No document overflow was observed at tested widths.

The existing `docs/progress.md` Chart and design review now contains one concise 44×44 mobile hit-region/non-overlap
check, including desktop density, keyboard focus and justified exceptions. No Make Interfaces Feel Better skill
was copied or installed. Existing dashboard design tokens, palette, components and motion rules remain in use.
No sizing exception was needed for the scoped controls; unrelated links/navigation/retry targets were not resized.

## Exact changed files

Dashboard worktree paths:

- `frontend/src/charts/ChartCard.tsx`
- `frontend/src/charts/ChartCard.test.tsx`
- `frontend/src/components/Segmented.tsx`
- `frontend/src/pages/Inflation.tsx`
- `frontend/src/pages/Inflation.test.tsx`
- `frontend/src/pages/inflation/Explorer.tsx`
- `frontend/src/pages/inflation/format.ts`
- `frontend/e2e/cpi-ux.spec.ts` (new)
- `docs/progress.md`
- `docs/superpowers/plans/2026-10-28-phase-4b-dashboard-ux.md` (new)
- `docs/phase-4b-dashboard-ux.md` (this report, new)

Separate vault change: `AI_Context/Memory/Durable_Facts/Kevin/current-projects.md`, NZ Stats entry only.

## Verification

All commands use existing installed tools; no package acquisition. Frontend commands run in `frontend/`.

| Check | Final result |
| --- | --- |
| `npm run typecheck` | Pass |
| `npm run lint` | Pass, three existing Fast Refresh warnings in badge/toggle/button |
| `npm test` | 42 files, 423 tests pass |
| `npm run build` | Pass; existing >500kB chart chunk warning |
| `scripts/build_static_site.sh --snapshot frontend/.e2e-snapshot --site-url https://nzstats.test --allow-fixture --skip-install` | Pass; fixture snapshot is non-indexable, not published |
| `playwright test -c playwright.config.ts --workers=3` | 126/126 pass, no skipped/flaky tests |
| `playwright test -c playwright.static.config.ts e2e/cpi.spec.ts e2e/cpi-ux.spec.ts e2e-static/parity.spec.ts --workers=3` | 51/51 pass, no skipped/flaky tests |
| Vault `check_ai_context.py`, `check_second_brain.py` | Pass |
| Whitespace, isolated local Gitleaks scan and final diff/preservation review | Pass |

Playwright used isolated temporary fixture databases with the scheduler disabled. The new CPI suite supplies
synthetic observations following the approved Phase 4 evaluation pattern, in both live/static modes; it blocks
external requests and records none. Established E2E tests use the project's offline seed fixtures. No production
Stats NZ, research or provider requests were made. Only Git remote ref verification used the network.

Browser projects: 390×844, 768×1024, 1440×900. New scenarios run in light/dark with reduced motion: loading,
404, persistent 503, keyboard retry to success, heading order, native radio ArrowRight/focus outline, native select,
Enter disclosure, history filters, CSV/PNG download, document width and pairwise hit-region overlap. Existing live
suite also exercises shared migration/ECT/story callers. Screenshots were visually inspected for mobile/desktop
controls, tables, themes and loading/error identity. Static visual parity checks pass.

Initial test invocations exposed harness issues (working directory, JSON import attribute, component-select exact
label, waiting for data now that h1 is immediate, and Sep/Sept expectation); these were corrected. New regressions
first reproduced missing h1, table truncation and 24px mobile ranges. One focused correction pass fixed the generic
period fallback identified by independent review, with a failing regression followed by a green full suite.
Independent review found no critical/important issue; no unresolved failure is masked. No second correction pass
was needed. Existing backend HTTPX deprecation and stale fixture-calendar warnings remain.

Local temporary evidence: `/tmp/phase4b-e2e-final.json`, `/tmp/phase4b-static-e2e-final.json`,
`/tmp/phase4b-mobile-before.json`, `/tmp/phase4b-units-final.log`, build/check logs with the same prefix, and
`frontend/test-results/` plus `/tmp/phase4b-static-results-final/` screenshots. These are disposable diagnostics,
not durable memory; the measurements/results above remain the record.

## Limitations and next action

Chromium emulation and DOM/CSS measurements do not test a physical touch device, assistive technology or actual
mis-taps. No screen-reader audit, new contrast audit, Lighthouse/performance benchmark or WCAG conformance claim.
No statistical accuracy claim is derived from synthetic observations. Very large future histories can make the
expanded disclosure long; no pagination infrastructure was added. Non-CPI generic tables keep all provenance columns.
Backend tests were not rerun because no backend/API/statistical code changed. The full static suite was not rerun;
targeted CPI plus visual parity and the complete live suite cover the changed UI.

Next action: review the isolated uncommitted diff and, before broader accessibility claims, check a physical mobile
device and screen reader. Keep research source activation and deployment under their existing separate workflows.
