# Phase 4D operational evidence

Checked **29 October 2026 (Pacific/Auckland)**. All database work below used a read-only live connection and
isolated local copies. No statistical collection, production migration, deployment or source-permission change ran.

## Backup recovery and migrations

The current live database is already **schema 10**. Older Phase 3E/3F reports describing schema 7 are historical
evidence, not current instructions to migrate production. Phase 4C adds no migration beyond 010.

SQLite's online backup API read the live database with `mode=ro`, including its WAL, and wrote a new isolated copy.
The complete raw directory was copied alongside it. The retained restore copy passed:

- `PRAGMA integrity_check` and `foreign_key_check` through `verify-backup`.
- Full expected table/index/append-only-trigger inventory for schema 10.
- **54,014 rows in 26 tables**, with no row-count differences against the read-only live database.
- All **20 referenced raw artifacts present**, with independently matching SHA-256 and byte size; 44,075,525
  referenced bytes, zero missing files and zero hash/size mismatches.
- `migrate(copy)` returned 10 and left the restored schema current.

The main live database's SHA-256 before/after this audit was unchanged:
`398b0f1e99cb90eecb4ae74588a6f4762852979d19e3d8028123741042897af1`.
The restored copy hash was `ae1fb49cdc5960a938e2135e2b06f6f7601651089cec39bbabdce47a8ec85d0a`.
The live file had a nonempty WAL; a main-file hash alone is therefore not proof of a consistent backup.
The online backup, row-count checks, raw hashes and restore checks provide that evidence.

The copy and raw tree are local, ignored audit artifacts under `data/phase-4d-operations/`; neither belongs in
Git, snapshots or a deployment. They establish an offline restore rehearsal, **not** the fresh pre-backfill
backup required immediately before approved production writes. That backup is still pending authorisation.

Verification commands on the correctly named audit copy:

```sh
NZSTATS_DATA_DIR=data/phase-4d-operations backend/.venv/bin/python -m nzstats.cli verify-backup data/phase-4d-operations/restored.db --live data/nzstats.db --raw-dir data/phase-4d-operations/raw
NZSTATS_DATA_DIR=data/phase-4d-operations backend/.venv/bin/python -m nzstats.cli research cpi-reconcile
cd backend
.venv/bin/pytest tests/store/test_backup_check.py tests/store/test_db.py tests/store/test_concurrent_migrations.py tests/research/test_migration.py
```

Results: restore **OK**; existing CPI reconciliation reproduced both stored all-groups vintages from retained
official files, checked **1,607 outcomes**, and reported **no discrepancies**. Only the September 2026 own release
vintage exists. The targeted backup/database/migration suite passed **33 tests** in 3.61 seconds, with one existing
Starlette/httpx deprecation warning. Final full backend verification passed **2,785 tests on both Python 3.14
and a clean Python 3.12 environment**, with Ruff clean on both. The latter installed `backend[dev]` from the
declared dependencies. Hosted CI specifies Python 3.12 but has not supplied execution evidence.

An initial diagnostic pointed `NZSTATS_DATA_DIR` at the restore directory while its backup was named `restored.db`;
the CLI created a new empty scratch `nzstats.db` there and correctly reported no CPI data. The scratch file was
replaced through SQLite backup from `restored.db`, then the successful 1,607-outcome check above ran. Production
was never opened for writing or changed by this correction.

## GitHub Actions and billing

The connected GitHub tools provide workflow/job metadata but no billing settings or check annotations. Those
read-only gaps were checked using authenticated `gh api`; no account settings were changed.

| Existing head | Run | Current result |
|---|---|---|
| Main `8f9f2a0d0932173020815bedab389048664a4f5e` | [40804674662](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/40804674662) | Backend, frontend and static-site failed **before execution**; zero steps and empty runner names. Docker skipped. |
| PR #20 `a9c76f2b601536bc603e87794e958a3e7e456033` | [40807221672](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/40807221672) | Same pre-execution failure; zero steps. Docker skipped. |
| PR #22 `33091a94b125a07bfc181729bbb3be3864caa21f` | [40805826557](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/40805826557) | Same pre-execution failure; zero steps. Docker skipped. |

The backend check annotations for all three runs state that the job did not start because account payments failed
or the spending limit must be increased. This is an account billing block, **not a green CI result or an executed
test failure**. Account billing usage endpoints returned 404 to this credential, so the exact balance/limit is
unavailable and is not inferred. The repository self-hosted-runner endpoint returned **zero registered runners**;
the workflow requests `ubuntu-latest` hosted runners.

Owner action: restore billing/hosted runner eligibility and run CI on the final Phase 4D PR head. Existing runs do
not verify the new integrated commit. Final-head run status must be recorded in the release report after the PR
exists; no prior green result can substitute for it.

## Docker

The Docker CLI is installed, but `docker info` cannot connect to `/var/run/docker.sock` because no daemon socket
exists. Docker image builds and `scripts/smoke_docker.sh` are **NOT RUN**; there is no container-runtime success claim.
The separate `docker-compose` executable is available (the `docker compose` subcommand is unavailable here).

```sh
docker-compose config --quiet
docker-compose -f docker-compose.publisher.yml config --no-env-resolution --quiet
```

Both configuration checks passed. Normal publisher config resolution fails because `.env.publisher` does not
exist; `--no-env-resolution` checks configuration syntax without loading it. No configuration, secret or permission
was created to bypass that absence.

On an available runtime, the outstanding offline checks are the existing CI commands:

```sh
docker build -t nzstats:phase-4d .
bash scripts/smoke_docker.sh nzstats:phase-4d
docker build -f Dockerfile.publisher -t nzstats-publisher:phase-4d .
```

The smoke script uses `--network none`, checks API health, persistence across restart/recreation, online backup,
research refusal without a provider, and scheduler job registration. It does not collect official data.

## Publication configuration and source restrictions

There is **no configured canonical site URL** in `.env` or `.env.publisher`; the publisher file does not exist.
Only `.env.publisher.example` has `PUBLISH_SITE_URL=https://your-site.netlify.app`, which is a placeholder.
An offline candidate may be checked with a clearly stated provisional HTTPS origin. A real draft upload needs the
owner's confirmed canonical URL/site ID and separate deployment approval; credentials must remain private.

The production database has no institutional research rows. Registry permissions remain unchanged: RBNZ restricted,
other institutions awaiting review, LLM processing denied and public display defaulting to none. The OCR module
has no acquisition/API/snapshot path, and its unavailable UI must remain accurate. No approval for a Stats NZ
backfill implies approval to enable RBNZ or research publishing.

Production release is **NO-GO** until the authorised official-data batch, provenance reconciliation and fresh
snapshot/dashboard checks are complete, final-head hosted CI runs, an available Docker runtime supplies its checks,
and the owner approves merge and deployment. Local verification can support code review while these blockers
remain explicit.
