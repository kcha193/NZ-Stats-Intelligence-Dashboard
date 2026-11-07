# Phase 4Y: ECT live release acceptance and statistical verification

8 November 2026, Pacific/Auckland. Baseline main `181a19e7fe210981760ee2e133a5476f2bfcc26f`;
clean checkout, equal to remote main. PR #52 is merged; no newer PR existed at inspection.

**OFFLINE READY — LIVE ACCEPTANCE PENDING.** Full Phase 4Y remains incomplete.
No October publication, download, official figure or successful live ingestion is claimed.

## Release and live gate

Target: **Electronic card transactions: October 2026**. The stored official calendar record
has reference `2026-10`, scheduled `2026-11-11T21:45:00Z`, **12 November 2026, 10:45 am NZDT**,
with no publication URL and no vintage. This agrees with the calendar observation recorded in
[ECT source verification](data-sources/ect.md#operation-and-limits) on 18 October. The small
committed ICS excerpt covers migration, not ECT: it is not independent evidence for this date.
The original ECT calendar response is not retained among the raw artifacts. The schedule is
stored evidence, not a fresh verification of an unchanged schedule or of publication.

On 8 November the expected time is still in the future. **No live Stats NZ request was made
for this work.** No polling, task, scheduler or unattended check was installed. Genuine
publication and the actual downloadable source must be established after publication; the
owner must separately authorise one bounded refresh before any live ingestion.

The existing on-open check is a batch, not an ECT-only command. September migration is
scheduled for the same time. Approval must name the actual eligible Stats NZ batch (up to
six supported releases), or the operator must stop before opening the live dashboard. An
ECT-only approval does not silently authorise other releases.

## Read-only production baseline

Private evidence is under ignored `data/phase-4y/` (directories 0700, files 0600). The
baseline was captured with SQLite `mode=ro`, a read transaction and `query_only=ON`;
no runtime, migration, discovery or ingestion command was used on production.

| Item | Observed baseline |
|---|---|
| Schema / database checks | 14; 33 tables; 80,503 rows; `integrity_check=ok`; zero foreign-key violations |
| Current ECT | September 2026; published 16 October 2026, 10:45 NZDT |
| ECT vintages | August: 96, IDs 258–353; September: 96, IDs 354–449; October: zero |
| ECT observations | 36,756 across 192 vintages |
| Retail history revisions | 110 changed common monthly adjusted retail values between the August and September vintages |
| Raw artifacts | 48 referenced artifacts, all present and SHA-256 verified; full URLs, capture times, sizes and hashes in private evidence |
| Last refresh | Run 20, 8 November 09:41:14–09:42:05 NZDT; completed; four calendar requests; zero discovered or ingested, failures and pending empty |
| Read-only operational health | `nzstats status --json --deep`: `ok` |

`baseline.json` records every vintage's identity, observation count, definition identity,
publication and capture time; all table counts and content hashes; schema hash; database
and WAL hashes; raw-artifact hashes; refresh status and catch-up boundaries. Future scheduled
releases are distinct from pending/overdue attempted releases. October is scheduled, not overdue.

The dashboard process stopped during inspection. The first baseline-to-backup comparison
differed only in `ops_process`; its heartbeat/clean-stop record changed. The subsequent
backup, restored copy and live database agree on **all 33 tables**. Statistical history,
raw artifacts and research tables did not change. File-byte equality alone is not the test
for a WAL-backed online backup; compare the consistent snapshot's logical rows as well.

## Backup and rollback evidence

The existing [Phase 4X backup and restore evidence](phase-4x-operational-readiness.md#2-backup-restore-rehearsal-migration)
was retained. This phase also made `baseline-backup` and restored it to the new, separate
`baseline-restore` directory, using shipped `create_bundle`, `verify_bundle` and
`restore_bundle` directly with a read-only source connection. Both verifications pass:
schema 14, 48 artifacts, every table content-identical between backup and restore.

Do not use `nzstats backup` as a supposedly read-only inspection: it migrates its source
database before copying. `serve`, `health` and `alert-check` can also migrate/write. The
backup below reuses shipped functionality without building a runtime or migrating production:

```sh
# Repository root; choose NEW names for each live attempt. This performs no network access.
umask 077
backend/.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path
from nzstats.store.backup_bundle import create_bundle, restore_bundle, verify_bundle

root = Path('data/phase-4y')
dest = root / 'pre-live-backup'          # must not already exist
restore = root / 'pre-live-restore'      # must be new/empty
conn = sqlite3.connect(Path('data/nzstats.db').resolve().as_uri() + '?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
try:
    report = create_bundle(conn, Path('data/raw'), dest)
finally:
    conn.close()
assert report.ok and verify_bundle(dest).ok
assert restore_bundle(dest, restore).ok
print('Backup and separate restore verified:', report.schema_version, report.raw_artifacts)
PY
```

Before live use, quiesce the owner's dashboard normally and recapture the baseline against
the **current** database. Inspect schema version before any command that might migrate it.
Compare every table and raw hash in the fresh backup and restore, not just counts. The
8 November bundle is rehearsal evidence, not a substitute for the fresh release-day backup.
Rollback means stop the server, retain the failed post-state as evidence, restore to a NEW
directory, verify it, then deliberately switch the data directory. Do not overwrite the
live database, delete historical vintages, or use the rollback SQL for an ingestion failure.

## Reproducible offline harness

The only code additions are test helpers and acceptance tests. Product code, source
permissions, statistical tolerances and the on-open architecture are unchanged.

| Acceptance area | Evidence and required behaviour |
|---|---|
| A–C: identity, time, provenance | Synthetic publication has an explicit mock-only URL; real parser/pipeline promotes its October identity, correct NZDT publication time, one consistent bundle and source URL. Genuine publication, source URL and acquisition provenance remain live gates |
| D–F: ZIP, definitions, frequency | Existing adapter tests cover archive limits, unsafe members, decoding, schema, units/magnitude, duplicates, statuses, missing/confidential values, continuity and metadata. October monthly extension retains September ECTQ; stale quarters and changed magnitude fail closed. Genuine archive CRC is a live gate |
| G: arithmetic | Separate stdlib CSV/Decimal oracle compares source observations, units, adjustment, frequency and statuses against dashboard payload; recomputes adjacent monthly/quarterly changes and mean/value/count consistency; checks published aggregate percentage rows within the existing allowance |
| H: vintages | 192 old vintages retained byte-for-value; 96 new synthetic vintages; a quarterly count revision is identifiable; repeat ingestion adds none; later refresh downloads no stored release |
| I: backup/rollback | Real rolling bundle verifies before the first release request; restore of the pre-refresh bundle retains the original vintages/observations/definitions and passes SQLite checks; failed backup prevents download |
| J: browser/cache | ECT and refresh suites plus synthetic October acceptance run desktop 1440×900, tablet 768×1024 and mobile 390×844; committed data version refetches ECT without reload; exports carry the new month, release key, units and provisional status |

`backend/tests/ect_acceptance.py` generates **synthetic October**, by extending September
monthly rows unchanged, keeping September quarterly rows, and revising one quarterly count
by one. New monthly statuses are provisional. Its page is labelled synthetic and is served
only by `httpx.MockTransport`; no real October figure or download URL is invented. Browser
responses are separately labelled synthetic; neither fixture is written into production.

Negative oracle tests corrupt period, units, scale, change percentage, comparison period and
status and require rejection. The September oracle also checks five official narrative
rate/dollar benchmarks directly from CSV numbers. Existing tests supply the industry
headlines, August/September actual identities and confidential-value checks. Initial harness
failures were fixture date/API-shape and browser-selector/import mistakes; they were corrected
in test code. They are not evidence of a product defect.

Run from the repository root (the browser server uses only its isolated fixture database):

```sh
cd backend
.venv/bin/python -m pytest tests/adapters/test_ect.py tests/pipeline/test_ect_ingest.py \
  tests/pipeline/test_ect_acceptance.py tests/pipeline/test_refresh.py \
  tests/pipeline/test_refresh_coordinator.py tests/store/test_vintage_definitions.py \
  tests/store/test_backup_bundle.py tests/store/test_backup_check.py tests/sources tests/api
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
cd ../frontend
npm test
npm run typecheck
npm run lint
npm run build
PATH="$PWD/../backend/.venv/bin:$PATH" E2E_DATA_DIR="$PWD/../data/phase-4y/e2e" \
  E2E_PORT=8775 npx playwright test e2e/ect.spec.ts e2e/refresh.spec.ts \
  e2e/ect-acceptance.spec.ts --workers=3
```

Existing coordinator/fetcher/API tests cover single flight, the 30-minute reuse window,
10-minute failure cooldown, 10-second shared pacing, three retries, request/release budgets,
block cooldown, interrupted recovery, pending/overdue releases, no duplicate downloads and
loopback/same-origin guards. No institutional crawler or paid provider is involved.

### Verification results

Results are populated from this phase's logs, not earlier phase counts:

| Check | Result |
|---|---|
| Focused backend | 529 passed, one existing Starlette/httpx deprecation warning; final oracle and vintage assertions included |
| Full pytest | 5,854 passed on Python 3.14, one existing Starlette/httpx warning; 8 min 1 s. The final tightened oracle is also covered by the focused run |
| Ruff lint / format | Both pass; 377 files formatted |
| Frontend unit / types / lint / build | 557 passed; types and lint pass; six existing React fast-refresh lint warnings; build succeeds with existing chunk-size advisory |
| API schema / npm audit | Regenerated API types unchanged; zero npm vulnerabilities |
| ECT / refresh / October browser | 39 passed across desktop/tablet/mobile; final October suite rerun 12 passed after adding monthly screenshots. No console errors or unintended external requests in the new flows |
| Static network/security isolation | 27 passed, 21 expected on-open skips; fixture snapshot, no deployment. ECT, offline refresh, same-origin networking, CSP/security headers and failure states included |
| Hosted CI on baseline main | Run `42413647418`: billing/spending-limit failure before backend/frontend/static job steps; Docker skipped. Separate from local outcomes |

The monthly and quarterly synthetic screenshots were retained privately; the monthly views
were visually inspected at all three sizes. No ECT-specific functional or chart-layout defect
was found. One existing cosmetic limit remains: the shared footer's source attribution wraps
into a narrow column at tablet width. Content remains present and there is no page overflow;
shared footer redesign is outside this release acceptance change.

Independent read-only review of the tests and runbook found no actionable issue. GitHub Codex
review is requested on the delivery PR; its outcome must be recorded separately from local
verification. The full dashboard/research/static parity suites and Docker were not repeated:
product, API and public-build code are unchanged, and the required focused browser/static
checks above passed. No deployment or genuine October browser result is implied.

## Genuine-release statistical reconciliation

Use the actual October publication, its own CSV ZIP and its own narrative/chart/workbook
benchmarks. Never compare October source levels against September-vintage dashboard values.
The independent reader does not import adapter identities or change-calculation functions.

1. Record the observed title, reference month, publication timestamp (including timezone),
   actual page and download URLs, capture times, HTTP/acquisition outcome and SHA-256. A
   scheduled calendar row alone is insufficient. A 200 response containing a block page is
   not a release. Stop on an access block; never switch transport to bypass it.
2. Record archive member names, CRC result, sizes, CSV schema/row counts and distinct series
   identities. Check units: spending `Dollars`/magnitude 6 → NZD million; counts `Number`/0
   → individual transactions; mean `Dollars`/0 → NZD. Keep actual, adjusted and trend separate.
3. For adjusted retail, core and total and all eight industries, recompute October versus
   September **within the October file**. Recompute September quarter versus June quarter
   from ECTQ; October is not a new completed quarter. Check quarterly revisions independently.
4. For rates use `100 × (current / prior − 1)`; dollar movement is `current − prior` in NZD
   millions. Compare unrounded recomputations first, then the published one-decimal rate and
   whole-million dollar benchmark. Keep the original lexical/source values in private evidence.
5. Apply existing source-supported allowances: 0.065 percentage points for rounded published
   rates; 0.55 million for whole-million movements; 0.051 million for embedded dollar chart
   levels after conversion. Exact CSV-to-stored values must agree (the oracle allows only
   1e−8 for binary arithmetic in derived changes, not a statistical discrepancy). Coarse
   actual quarterly aggregation checks are scale guards, not evidence of headline agreement;
   see the [source tolerance rationale](data-sources/ect.md#actual-value-consistency-checks).
6. Recompute actual transaction value/count and average value from the same month and vintage.
   Preserve `P` as provisional and `F` as final; `R` remains unknown with the revision caveat.
   Publication status and observation finality are different. Confidential/missing observations
   are absent, never zero. Do not force independently adjusted components to sum to aggregates.
7. Classify every discrepancy: confirmed agreement, legitimate source rounding, official
   revision, missing/confidential, definition change, or genuine defect. Record observed and
   expected values, prior period/vintage, units, residual, tolerance and source evidence. A
   new definition or unexplained residual is NO-GO, not a reason to widen a tolerance.

After authorised ingestion, save the local API's unwrapped JSON to `data/phase-4y/live-ect.json`
and copy the exact content-addressed ingested ZIP to `live-ect.zip`. Run this offline cross-check:

```sh
cd backend
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from tests.ect_acceptance import reconcile_archive

root = Path('../data/phase-4y')
n = reconcile_archive((root / 'live-ect.zip').read_bytes(),
                      json.loads((root / 'live-ect.json').read_text()), '2026-10')
print('Source observations reconciled:', n)
PY
```

This checks selected acceptance series over their complete retained histories, including
all adjusted industries and actual total/count/mean, with literal independent source-code
mappings. It is not an independent licence/provenance check or a narrative extractor. Manually
transcribe the genuine release benchmarks and apply steps 3–7; record those results separately.
Run without Python optimisation (`-O`), because this test helper uses assertions.

## Original/new vintage comparison

Use the verified pre-live database as the old state and a fresh read-only post-state snapshot.
All pre-existing `vintage`, `observation` and `vintage_series_definition` rows must remain
identical by primary key and row-content hash, including statuses and capture timestamps.
For the new release, record each new vintage ID, series key, bundle digest, activation,
definition identity and observation count. Normally 96 series are expected; a changed set
needs an explicit definition/coverage review. New monthly maxima must be October; quarterly
maxima September. Different captures of one history file are not multiple publication vintages.

Join new and previous publication observations on matching series key/period and compatible
unit, frequency, adjustment and definition identity. Record value/status changes and added or
missing periods; identify prior-period official revisions separately from October's new month.
Recompute revision counts, including adjusted retail, from SQL/source values rather than only
the dashboard's revision panel. Compare all original raw file hashes before/after; new files
must match their content-addressed names. Failed validation may retain raw evidence and an
ingest attempt, but must not change any last-known-good measurement or current bundle.

Do not repeat a live download just to test idempotency. The synthetic harness proves repeated
ingestion is unchanged; after live success, inspect the stored release and its exclusion from
the next eligible set read-only. Any same-publication correction needs separate review.

## Remaining live steps and decision

1. After the expected release, the owner establishes the genuine publication and downloadable
   source, and confirms the actual eligible batch. Do not infer URLs from naming conventions.
2. Quiesce the dashboard, capture a fresh read-only baseline, and verify a fresh database/raw
   bundle and separate restore, including logical table equality and all artifact hashes.
3. Obtain explicit, recorded owner authorisation for **one** normal bounded on-open check.
   Record the target, eligible batch, time/window and existing limits. No retries beyond the
   existing mechanism and no unattended follow-up are authorised by this runbook.
4. Start the loopback dashboard in existing on-open mode, open it once and record the resulting
   refresh ID. Preserve 10-second pacing, six-release/40-logical-GET budgets, retries and source
   blocking. A recent result may be reused; do not clear history or bypass cooldowns to force it.
5. Record actual acquisition/validation/commit outcomes. Missing files stay pending. Failure
   keeps last-known-good data and must never display “up to date”. No extra check without approval.
6. Run the independent ZIP/API and narrative reconciliation above. Compare before/after vintage,
   observation, definition and raw hashes; confirm the new publication is current without losing history.
7. Check the genuine ECT page at desktop/tablet/mobile sizes: newest month, units, adjustment,
   monthly/quarterly labels and comparisons, revision information, attribution/publication time,
   provisional status in exports/table, loading/failure states and chart refresh without reload.
   Record console errors and requests; opening source links is distinct from automatic acquisition.
8. Record GO / GO WITH CONDITIONS / NO-GO and replace the pending status only with actual evidence.

**Decision:** GO WITH CONDITIONS for the prepared offline procedure. **NO-GO for live execution now.** October's
availability, real figures, actual new vintages, source acquisition and production browser
presentation remain unverified. Full phase completion requires all of those live steps.

No product defect was confirmed, so no production or UX change was made. Treasury/RBNZ
permissions, OpenRouter configuration/ceilings, private research, loopback controls and public
static isolation remain unchanged. No merge or deployment is authorised by this phase.
