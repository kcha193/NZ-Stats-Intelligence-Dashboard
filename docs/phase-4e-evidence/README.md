# Phase 4E evidence index

Assessed 29 October 2026 (Pacific/Auckland) against merged main `3ac92addea52908d926a93e4015c217cf6cde125`. **Approved data activation passed; production deployment remains NO-GO.** No Netlify draft or production URL exists for this phase.

| Artifact | Contents |
|---|---|
| [Reconciliation](reconciliation.json) | Production counts, preserved old-row hashes, raw source identities, per-release vintage/bundle/capture identities, independent macro arithmetic, CPI workbook fidelity, provenance/forecast checks, snapshot equality, schema and fresh backup evidence |
| [Actual backfill results](backfill-results.json) | All 30 actual request URLs/times/statuses/body hashes, calendar agreement, seven sequential results, warnings and reconciliations |
| [Verification](verification.json) | Fresh local counts and versions, exact-head hosted billing failure/job evidence, Docker checks explicitly not run |
| [Snapshot manifest](snapshot-manifest.json) · [Complete site inventory](candidate-files.json) | Exact undeployed data snapshot and all 301 built site file hashes |
| [Publication](publication.json) | Local production snapshot ID, generated/data timestamps, canonical/header/route checks, latest API health, six browser views and twelve exports; actual deployments and rollback reference are null |
| [Screenshots and hashes](screenshots.json) | Seven screenshots tied to the final snapshot |
| [Screenshot gallery](../screenshots/phase-4e/README.md) | Production-data desktop/mobile views, their scope and provenance |

The complete pre-activation DB/raw archive and independent restore remain in the private ignored directory named by the backup record. The full row-level CPI report is retained locally at `data/phase-4e/cpi-reconciliation-final.json`; the tracked reconciliation records its eight vintages, 1,607 outcomes and zero discrepancies. Full official response bodies and operational logs are private ignored audit artifacts, never static-site assets.

## Reproduce offline

Use an installed `backend[dev]` environment. Run from the repository root. No command below contacts Stats NZ. The full-source checks require the already authorised GDP/labour captures under `data/capture-4c/`, with the hashes recorded in the reconciliation report. Restore supplied local artifacts rather than fetching replacements without approval.

```sh
python docs/phase-4e-evidence/reproduce_offline.py
python -m pytest backend/tests/test_phase4d_reconciliation.py
```

The script revalidates the seven captured pages, selected download URLs/dates, adapter validation/counts, request budget and registration excerpt syntax. Its independent CSV/ZIP/Decimal calculations use no application growth/identity helpers. It compares selected metadata/blanks/rows with the exact HLFS/LCI archive members, excluding the combined LMS file's duplicate series. Socket creation is disabled during this audit.

To repeat the live-capture worksheet checks and preserved-production/provenance checks **without collection**, retain `data/phase-4e/activation-results.json`, `backfill-offline.json`, `approved-backup.json`, all `live-captures/` bodies, the named private pre-activation backup and raw tree, and the unchanged reconciled production database:

```sh
python docs/phase-4e-evidence/reproduce_workbooks.py
PYTHONPATH=backend python docs/phase-4e-evidence/reproduce_production.py
NZSTATS_DATA_DIR=data/phase-4e/post-backfill-copy nzstats research cpi-reconcile
nzstats verify-backup data/phase-4e/post-backfill-copy/nzstats.db --live data/nzstats.db --raw-dir data/phase-4e/post-backfill-copy/raw
```

These audit scripts write only ignored local reports/copies; production connections are read-only. `reproduce_production.py` asserts this exact completed batch and counts; it is a release evidence replay, not a general ingestion command. Do not run it over a later-changing production database and interpret changed counts as a parser regression. Workbook checks compare exact SQLite REAL conversions and exact published one-decimal figures, explicitly reporting the tiny decimal representation differences.

Local CI-equivalent commands are the commands in `.github/workflows/ci.yml`: Python 3.12 backend pytest/Ruff; Node 20 `npm ci`, audit, API schema generation/diff, types, lint, tests/build and Playwright; then `scripts/e2e_static.sh`. Research Playwright uses its dedicated synthetic loopback configuration. Isolate fixture directories and ports. Docker has its own pending gates in [the operations runbook](../phase-4e-operations.md).

## Interpretation

Machine reports distinguish local production-data evidence from a deployed production system. HTTP 200 and source state `ok` do not prove category completeness or freshness. Actual Netlify edge behaviour, final canonical origin, deployed snapshot/deploy IDs, hosted CI, container runtime, external alerts and a real rollback reference remain unverified. No report grants an outstanding owner approval.
