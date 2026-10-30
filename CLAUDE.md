# NZ Stats Intelligence Dashboard: project instructions

Self-hosted dashboard that ingests Stats NZ releases and explains them. Migration, card spending and CPI are built;
Phase 4D integrates GDP, labour and the Outlook stack on main. Phase 4E has activated and reconciled the approved
seven-release official backfill; production deployment remains gated. Phase 4G replaces native scheduled collection with
a bounded on-open refresh (`docs/phase-4g-on-open-refresh.md`); `--offline` never contacts Stats NZ. OCR remains synthetic-only
and institutional research publishing remains permission-gated. Resume from [docs/progress.md](docs/progress.md);
current release gates and evidence are in [docs/phase-4e-release.md](docs/phase-4e-release.md).

## Stack and layout

- `backend/src/nzstats/`: Python 3.12 (3.11+ works), FastAPI, Pydantic, pandas, httpx, SQLite (WAL), APScheduler.
  `sources/` (calendar, release page, throttled fetcher) · `adapters/` (file layouts, one per category: migration, ect, cpi,
  gdp, labour) · `ocr/` (OCR domain model on synthetic data only; source not approved, see `docs/data-sources/ocr.md`) ·
  `validate/` · `stats/` (pure number functions) · `insights/` (deterministic findings with evidence) ·
  `store/` (SQL migrations, repositories) · `pipeline/` (discover, ingest, backfill) · `scheduler/` ·
  `api/` (read-only, serves the built SPA) · `cli.py` · `research/` (Phase 3A institutional commentary and Phase 3B
  evidence-grounded LLM summaries; Phase 3C public research API, `api.py`, off unless `NZSTATS_PUBLIC_RESEARCH=1` and
  wired by `cli.py` only: a separate domain that no Stats NZ package imports; LLM processing and public display are
  disabled by default and gated per source; see `docs/data-sources/research.md`).
- `frontend/`: React 19, TypeScript, Vite, Tailwind 4, shadcn/ui (Base UI flavour), ECharts, TanStack Query.
  `src/charts/` holds option builders; pages in `src/pages/`; API types are generated.
- `config/sources.toml`: Stats NZ endpoints, polling offsets, backfill window. `scripts/`: seed, fixtures, backup.
- Spec: `docs/superpowers/specs/`. Plan: `docs/superpowers/plans/`. Source registry: `docs/data-sources.md`.

## Commands

```sh
cd backend && . .venv/bin/activate
pytest && ruff check . && ruff format --check .
nzstats serve --no-scheduler        # API + built UI (set NZSTATS_STATIC_DIR=../frontend/dist)
nzstats status [--json] [--deep]    # read-only operational health; exit 0 OK / 1 ATTENTION / 2 CRITICAL / 3 failed to run
nzstats alert-check                 # local alerts only (log + data/ops/alerts.jsonl); never a network channel
nzstats backup --bundle DEST        # database + raw files + checksum manifest; verify-backup DIR; restore-backup SRC NEWDIR
cd frontend
npm test && npm run typecheck && npm run build
npm run gen:api                     # regenerate src/api/schema.d.ts after any API model change
cd backend && python ../scripts/dump_frontend_fixtures.py   # regenerate frontend fixtures, review the diff
cd frontend && npx playwright test  # needs the venv on PATH and a fresh build
npx playwright test -c playwright.research.config.ts   # /economic-outlook with SYNTHETIC published research
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
- Research is shown publicly only through `research/public.py` (one gate). Never change a source's access, LLM or
  `public_display` settings without a documented, authorised review, and never add research to a snapshot.
- Operational monitoring (`nzstats/ops/`) is read-only and offline: `status` opens the database `mode=ro`, never builds a
  runtime or scheduler, and alert payloads are built only from structured fields (never upstream text). Spec and runbook:
  `docs/phase-4f-operational-health.md`, `docs/phase-4f-runbook.md`. A scheduler switched off by choice is not a fault.
- Prefer small, TDD-driven changes. Watch each new test fail first.

## Design

Frontend work follows the installed `design-taste-frontend` skill and the `dataviz` skill. The skill is
aimed at landing pages and declares dashboards out of scope, so spec §9 wins on conflicts: dials are
DESIGN_VARIANCE 5, MOTION_INTENSITY 2, VISUAL_DENSITY 7; one accent; neutral palette; dark mode follows
`prefers-color-scheme`. Chart colours are validated with the dataviz validator (record in `docs/progress.md`).
Never edit the skill's own files.
