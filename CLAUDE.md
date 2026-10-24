# NZ Stats Intelligence Dashboard: project instructions

Self-hosted dashboard that ingests Stats NZ releases and explains them. Phase 1 (International migration)
is built; Phases 2 and 3 are in the spec. Resume from [docs/progress.md](docs/progress.md).

## Stack and layout

- `backend/src/nzstats/`: Python 3.12 (3.11+ works), FastAPI, Pydantic, pandas, httpx, SQLite (WAL), APScheduler.
  `sources/` (calendar, release page, throttled fetcher) · `adapters/` (file layouts, one per category: migration, ect, cpi) ·
  `validate/` · `stats/` (pure number functions) · `insights/` (deterministic findings with evidence) ·
  `store/` (SQL migrations, repositories) · `pipeline/` (discover, ingest, backfill) · `scheduler/` ·
  `api/` (read-only, serves the built SPA) · `cli.py`.
- `frontend/`: React 19, TypeScript, Vite, Tailwind 4, shadcn/ui (Base UI flavour), ECharts, TanStack Query.
  `src/charts/` holds option builders; pages in `src/pages/`; API types are generated.
- `config/sources.toml`: Stats NZ endpoints, polling offsets, backfill window. `scripts/`: seed, fixtures, backup.
- Spec: `docs/superpowers/specs/`. Plan: `docs/superpowers/plans/`. Source registry: `docs/data-sources.md`.

## Commands

```sh
cd backend && . .venv/bin/activate
pytest && ruff check . && ruff format --check .
nzstats serve --no-scheduler        # API + built UI (set NZSTATS_STATIC_DIR=../frontend/dist)
cd frontend
npm test && npm run typecheck && npm run build
npm run gen:api                     # regenerate src/api/schema.d.ts after any API model change
cd backend && python ../scripts/dump_frontend_fixtures.py   # regenerate frontend fixtures, review the diff
cd frontend && npx playwright test  # needs the venv on PATH and a fresh build
scripts/e2e_static.sh               # public Netlify build: fixture snapshot, static site, browser specs incl. visual parity
nzstats export-snapshot ./snapshot && nzstats validate-snapshot ./snapshot --for-publish   # public JSON from the real DB
```

## Rules

- The 10 second crawl delay on stats.govt.nz is a hard constraint. Never lower it, never add parallel requests,
  and never run real-site checks except the deliberate, throttled integration check.
- No synthetic values in production code paths. Test fixtures are real excerpts from official files.
- Store timestamps in UTC; present them in Pacific/Auckland.
- Never plot or compare monthly and year-ended series on one axis. They are different series.
- Regions and "Not Stated" are not countries; the country ranking is a derived total and says so.
- Last-known-good data must survive any failed update. Success means downloaded, parsed, validated and
  committed in one transaction, not "the HTTP request returned 200".
- Never loosen a validation threshold without evidence from the real file, and add a regression test.
- Error text stored or served by the API must not include raw exception messages (log them instead).
- Anything built from upstream text (tooltips, CSV export) must escape it: see `escapeHtml` and `toCsv`.
- Public site: never publish fixture data (`FIXTURE_DATA` marker; the exporter refuses it), never put the database, the
  ingestion log or error text in a snapshot, and never deploy without `PUBLISH_ENABLED=1`. Static mode must render exactly
  what live mode does (the parity spec). See `docs/netlify-deployment.md`.
- Prefer small, TDD-driven changes. Watch each new test fail first.

## Design

Frontend work follows the installed `design-taste-frontend` skill and the `dataviz` skill. The skill is
aimed at landing pages and declares dashboards out of scope, so spec §9 wins on conflicts: dials are
DESIGN_VARIANCE 5, MOTION_INTENSITY 2, VISUAL_DENSITY 7; one accent; neutral palette; dark mode follows
`prefers-color-scheme`. Chart colours are validated with the dataviz validator (record in `docs/progress.md`).
Never edit the skill's own files.
