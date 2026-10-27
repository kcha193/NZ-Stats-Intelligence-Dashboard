# Phase 3C implementation plan: Economic Outlook

Spec: [2026-10-27-phase-3c-economic-outlook-design.md](../specs/2026-10-27-phase-3c-economic-outlook-design.md).
Each task is test-first (watch the new test fail), then `pytest`, `ruff check .`, `ruff format --check .` (backend) or
`npm test`, `npm run typecheck` (frontend), then one commit.

## Backend

1. **Registry: public display permission.** Add the `summary` level and the `public_display_approved_by/on/note`
   fields to `research/registry.py`; loader refuses a level without approval fields, `summary`/`excerpt` without
   `full_text`. Add `Institution.display_level` and `display_refusal()`. Tests in `test_registry.py`. No change to
   `config/research_sources.toml` values; document the fields in its header comment.
2. **Migration 007 + publication store.** `research_summary_publication` (append-only, triggers), rollback script,
   `summary_store.publish_decision()` and `latest_publication()`; full research rollback drops 007 first.
   Tests: `test_migration.py`, `test_summary_store.py`.
3. **CLI publish / withdraw.** `research publish|withdraw ID --approver --note`; `research summaries` shows the
   publication state. Tests: `test_cli.py`.
4. **Comparability.** `research/compare.py`: unit, basis, horizon normalisation and grouping. Tests:
   `test_compare.py` (table-driven).
5. **Eligibility.** `research/public.py`: `eligible_summaries(conn, registry)` returns parsed, re-verified,
   permission-filtered items; one function used by every endpoint. Tests: `test_public.py`, one per rule.
6. **API.** `research/api_models.py` (response models), `research/api.py` (router, disabled = 404, filters, pagination,
   search, detail, forecasts). `create_app(routers=...)`; `cli.py` wires the router for `serve` and `openapi`.
   Tests: `test_api.py` (TestClient over a synthetic registry), leak checks, isolation unchanged, snapshot unchanged.

## Frontend

7. **API types and hooks.** `npm run gen:api`; `useResearchFeed`, `useResearchSummary`, `useForecasts` map a 404 to
   "not published". Static reader unchanged (research paths are already "not published").
8. **Pulse.** `lib/pulse.ts` (interpretation sentence, freshness status) and `components/outlook/Pulse.tsx`.
9. **Research feed.** Filters, search, sort, group-by, expandable items, processing badges, empty state.
10. **Forecast comparison.** `charts/forecasts.ts` (dot plot option, escaped tooltips, zero baseline), the comparison
    section with selectors, table and "not comparable" list; dataviz validator run recorded.
11. **Research detail page** and routing, navigation, route metadata, Netlify redirects.

## End-to-end and docs

12. **Playwright.** Live: empty state and navigation. Research-enabled config (`playwright.research.config.ts`):
    synthetic registry and seeded database, feed, filters, comparison, detail, keyboard, no horizontal scroll,
    screenshots at 1440, 768 and 390 wide. Static: parity, site and scroll lists include `/economic-outlook`.
13. **Docs.** `docs/data-sources/research.md` (public display runbook), `docs/progress.md`, `CLAUDE.md` layout line,
    architecture note.

## Risks

- A permission bug leaks restricted material: mitigated by one eligibility function, tests per rule, disabled by
  default, and no change to source settings.
- Comparing unlike forecasts: grouping is conservative; anything unrecognised is shown as not comparable.
- Static and live drift: the parity spec covers `/economic-outlook`.
