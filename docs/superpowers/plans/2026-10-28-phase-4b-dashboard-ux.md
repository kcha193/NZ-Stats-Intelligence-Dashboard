# Phase 4B dashboard remediation implementation plan

Goal: address B1–B3 and C1 from the completed Phase 4 report with the existing React, Tailwind and chart components.

Scope: dedicated `fix/phase-4b-dashboard-ux` worktree from verified `origin/main` 93d114e. No research, statistics, ingestion, CSV schema/precision, dependencies, commits or publication changes. Execute inline; at most two correction cycles.

- [x] Add failing regression tests for full/short/filtered table ranges, display formatting, raw CSV retention and Inflation heading across loading/404/error/retry/success.
- [x] In ChartCard, disclose the entire selected range with a visible count/date caption. Add optional display column definitions; supply CPI labels, units, precision and missing-value display in the existing inflation formatting module. Keep CSV rows untouched and ordered as supplied.
- [x] Keep Inflation identity outside QueryBoundary and give the KPI section a level-two heading. Preserve announcements and retry.
- [x] Size segmented labels, chart exports, table disclosure and component select to at least 44×44 on mobile; retain compact desktop sizes. Measure controls and non-overlap with Playwright, including shared segmented callers.
- [x] Add one sizing/non-overlap item to the existing docs/progress.md chart/design review. Verify typecheck, lint, all frontend unit tests, production build, relevant existing E2E and synthetic browser checks at 390/1440 in both themes. Inspect final diff and preserve original checkouts.

Review focus: multi-series row ordering; missing values versus zero; filter changes; CSV precision and provenance; long select labels and control wrapping; persistent identity while retry is pending. Browser tests use approved synthetic evaluation responses or the project’s established offline fixtures, never production requests.

Execution evidence: 423 unit tests, 126 live and 51 static/parity browser checks passed; typecheck, lint and builds passed. One focused correction pass guarded generic period formatting after a failing regression demonstrated unsupported labels. New tests first reproduced the 24-row cap, absent h1 and 24px mobile range targets. Initial harness adjustments corrected JSON import attributes and the component-select locator. Independent source review found no critical/important issues; its minor fallback issue is covered by the added regression. No unresolved findings or second correction pass required.
