# NZ Stats Intelligence Dashboard

A self-hosted dashboard that turns Stats NZ releases into explained statistics: what changed, how the
result compares with history, and whether earlier estimates were revised. It checks Stats NZ on a
release-aware schedule (Pacific/Auckland), stores every release's official data files as a dated
vintage, and generates deterministic, evidence-linked findings. No paid AI, no notifications.

**International migration and Phase 2A Electronic Card Transactions are implemented**: Economic overview,
Release analysis, Migration dashboard (trend, arrivals vs departures, monthly vs year-ended,
citizenship, country ranking, revisions), ECT spending dashboard (actual, adjusted, trend and official
quarterly series), Release calendar and Data health. Inflation, labour market, GDP, housing,
the Data Explorer and the Revision Explorer are Phase 2; see [docs/progress.md](docs/progress.md).

Source: Stats NZ (stats.govt.nz), licensed under Creative Commons Attribution 4.0. This project is
independent and is not endorsed by Stats NZ.

## Run it (Docker Compose)

Requires Docker with Compose v2.

```sh
cp .env.example .env          # then set NZSTATS_CONTACT (see below)
mkdir -p data && sudo chown 10001:10001 data   # Linux/Synology: the container user must own ./data
docker compose up -d --build
docker compose exec nzstats nzstats discover   # refresh the release calendar
docker compose exec nzstats nzstats backfill   # ingest historical releases (slow, see below)
```

Open http://localhost:8000. (On Docker Desktop for Mac or Windows the `chown` is not needed.) If the container restarts in a loop, check `docker compose logs nzstats` for a permission error on `/data`.

- `NZSTATS_CONTACT` is appended to the User-Agent so Stats NZ can reach the operator. Use an address you
  are happy to share with them; leave it blank to send no contact detail.
- Stats NZ's `robots.txt` asks for a 10 second crawl delay, which the app enforces
  (`NZSTATS_MIN_INTERVAL_SECONDS` cannot be set below 10). A backfill makes one request per release month
  plus three per release, so expect on the order of 15 to 25 minutes for the 2024-06 onward window.
  The app is usable while it runs; the Data health page shows progress.
- After the first backfill the container keeps itself current: the calendar refreshes daily, each
  release is polled shortly after its scheduled publication time (10:45 Auckland), and a catch-up job
  covers downtime.

### Start, stop, update

```sh
docker compose stop            # stop
docker compose up -d           # start
git pull && docker compose up -d --build   # update; the database migrates itself on start
docker compose logs -f nzstats
```

### Back up and restore

```sh
scripts/backup.sh              # consistent online copy -> data/backups/nzstats-<date>.db
```

`nzstats backup` checks its own copy. Before restoring, verify the file you will restore (read-only; it also checks
that the append-only research guards are present and, with `--raw-dir`, that every raw file it references exists):

```sh
docker compose exec nzstats nzstats verify-backup /data/backups/nzstats-<date>.db --raw-dir /data/raw --live /data/nzstats.db
```

To restore: `docker compose stop`, replace `data/nzstats.db` with the verified backup (delete any
`data/nzstats.db-wal` and `-shm` files), then `docker compose up -d` and run `verify-backup` on `data/nzstats.db`.
Raw Stats NZ files in `data/raw/` are content-addressed and can be re-fetched, but manually imported research documents
cannot: copy `data/raw/` with every backup.

### Public website (optional)

The dashboard can also be published as a static site on Netlify from validated JSON snapshots, without exposing the
database or the API. Nothing is published unless you enable it: see [docs/netlify-deployment.md](docs/netlify-deployment.md).

### Synology NAS

1. Install **Container Manager**, clone or upload this repository to a shared folder, and use SSH (or a
   Container Manager "Project") to run `docker compose up -d --build` in that folder.
2. The container runs as UID/GID 10001 by default and must be able to write `./data`. Either
   `chown 10001:10001 data` or set `NZSTATS_UID` and `NZSTATS_GID` in `.env` to the owner of the folder
   (`id <user>` over SSH).
3. Put it behind the DSM reverse proxy (Control Panel, Login Portal, Advanced, Reverse Proxy) with an
   HTTPS certificate rather than exposing port 8000.
4. Keep the instance private (LAN or VPN). Stats NZ's terms-and-conditions page could not be machine-read,
   so review it before making the dashboard public.
5. Leave `NZSTATS_PUBLIC_RESEARCH` unset here. The research routes have no login, so with it set `nzstats serve`
   refuses to start on any address but loopback, which the container's `0.0.0.0` is not. A private research preview
   runs on the owner's machine (`nzstats serve --host 127.0.0.1`); see `docs/data-sources/research.md`.

## Local development

Quick start without Docker: `scripts/run.sh` (or double-click `Start Dashboard.command`). The first run installs
dependencies and builds the UI, then serves on http://localhost:8000. Each time you open the dashboard it checks Stats NZ
once for missing releases and updates the charts; `scripts/run.sh --offline` never contacts Stats NZ. See
[docs/phase-4g-on-open-refresh.md](docs/phase-4g-on-open-refresh.md).

```sh
python3 -m venv backend/.venv && . backend/.venv/bin/activate
pip install -e 'backend[dev]'
cd backend && pytest && ruff check . && ruff format --check .

cd ../frontend && npm ci
npm run dev                    # Vite on :5173, proxies /api to :8000
nzstats serve --offline        # in another shell: API on stored data, never contacts Stats NZ
```

Test and build commands:

| What | Command |
|---|---|
| Backend tests, lint, format | `cd backend && pytest && ruff check . && ruff format --check .` |
| Frontend unit tests | `cd frontend && npm test` |
| Frontend types and build | `cd frontend && npm run typecheck && npm run build` |
| Regenerate API types | `cd frontend && npm run gen:api` (needs the backend venv active) |
| Regenerate frontend fixtures | `cd backend && python ../scripts/dump_frontend_fixtures.py` |
| End-to-end (desktop and mobile) | `cd frontend && npm run build && npx playwright install chromium && npx playwright test` |

The end-to-end suite seeds a database from real Stats NZ fixture files (`scripts/seed_e2e_db.py`) and
serves the built app; it never contacts stats.govt.nz.

## Known limitations

- International migration and Electronic Card Transactions are active. Other categories appear on
  the Overview as "not yet active"
  until a verified, maintainable source is wired in.
- Reprocessing: every ingest parses and validates the source, then compares canonical statistical data.
  Editorial titles and file formatting do not create corrections. Parser fixes that change the parsed
  statistics create a new vintage while preserving existing history; identical statistics are unchanged.
  Nothing re-checks a release once it has data, so later corrections require manual re-ingestion or backfill.
- Revision history only covers releases captured since the oldest backfilled vintage. Stats NZ's older
  migration files (before 2024-06) are missing or use a different layout for many months; see
  [docs/data-sources/migration-vintage-depth.md](docs/data-sources/migration-vintage-depth.md). The UI
  states this wherever revisions are shown.
- Release discovery uses an ICS export (official) and the month listing endpoint behind the Stats NZ
  site's own calendar. The latter is undocumented and may change without notice.
- Country rankings are derived (sums of the published monthly estimates); regions and "Not Stated" are
  never ranked as countries.
- The Stats NZ API Portal (ADE) needs registration and a key and has no vintage history; it is not used.

## Documentation

ECT source verification, rounding reconciliation and bounded backfill commands:
[Electronic Card Transactions](docs/data-sources/ect.md). The dashboard is at
`/electronic-card-transactions`. To capture the latest full history and a genuine previous vintage:

```sh
nzstats backfill --series-slug electronic-card-transactions --since 2026-08 --until 2026-09
```

Future ECT releases use the existing official-calendar scheduler. Database migration 003 preserves
measurement definitions per vintage; back up the database before updating an existing installation.

[Architecture](docs/architecture.md) · [Data-source registry](docs/data-sources.md) ·
[Data dictionary](docs/data-dictionary.md) · [Troubleshooting](docs/troubleshooting.md) ·
[Progress and verification record](docs/progress.md) · [Design spec](docs/superpowers/specs/2026-10-11-nz-stats-dashboard-design.md) ·
[Phase 1 plan](docs/superpowers/plans/2026-10-11-nz-stats-dashboard-phase-1.md)
