# Phase 1 audit remediation — 16 October 2026

Scope: remediate findings F01–F10 from the independent Phase 1 audit, against baseline
`9deca776d69df30ec064fbaea2d9ec19a593d694`. Work is grouped into four logical batches below.
This record covers local evidence and the successful implementation CI run for
[PR #2](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/2).
No merge, deployment or Phase 2 implementation is authorised by this record.

## 1. Findings F01–F10 resolution matrix

| Finding | Disposition | Resolution and evidence |
|---|---|---|
| F01 — incomplete citizenship and component validation | Fixed | All six annual citizenship flow series reconcile with totals; each group's net identity, available 12-month arrivals, and component bounds are checked. Required measurement semantics, duplicate periods, nonnegative counts and standard errors, and chart shape are validated. Official rounding tolerance and negative net migration remain supported. `test_rules_citizenship.py`, `test_ingest_citizenship.py`, and parser regressions prove rejection preserves the previous bundle. |
| F02 — invisible same-publication corrections | Fixed | An additive `corrections` API block and Release analysis panel show value, status and standard-error changes, additions and withdrawals between captures of the same publication. Earlier-publication revisions remain a separate comparison. First captures, corrections without an earlier publication, and A → B → A reactivation are covered. |
| F03 — response generation presented as freshness | Fixed | Overview exposes `data_updated_at` from the selected stored bundle's capture time; its label uses that value. `generated_at` remains response-generation time. Empty databases have no data-update timestamp. |
| F04 — ambiguous uncertainty units | Fixed | The headline metrics table labels uncertainty as `SE` under its “Value (people)” heading, replacing ambiguous ± notation and retaining zero standard errors. Frontend and browser regressions verify the wording. |
| F05 — pacing durability and Retry-After gaps | Fixed, with operational limits in §7 | Non-finite crawl intervals fail configuration. A shared, append-only journal reserves and fsyncs pacing state before HTTP; persistence failures refuse requests. Unfinished or damaged records impose a fixed recovery cooldown. Numeric and HTTP-date `Retry-After` values are shared across processes; long waits defer promptly. Failure injection and process tests cover short writes, fsync, corruption, restart and shared deadlines. |
| F06 — concurrent schema initialization | Fixed | A stable POSIX sidecar lock encloses connection PRAGMAs, schema-version reads and atomic migrations. Multiprocess tests cover simultaneous creation, upgrades and preservation of committed rows. |
| F07 — editorial changes create false vintages | Fixed | `data-v1` canonical identity hashes parsed observations and measurement semantics. Titles, CSV formatting, unused charts and signed-zero spelling do not change identity. Legacy bundles are compared by statistical identity and reused/reactivated without rewriting stored history. |
| F08 — inaccessible truncated calendar details | Fixed | Base UI Dialog exposes the complete title, date and status through keyboard and touch interaction; Escape closes it and focus returns to the trigger. Browser tests run at desktop, tablet and mobile widths. |
| F09 — vulnerable unused dependency tree | Fixed | Removed the unused shadcn CLI dependency and its transitive tree, without other package-version changes. The five CSS variants used by the app are retained locally with their MIT notice. `npm audit --audit-level=low` changes from seven high findings to zero vulnerabilities. |
| F10 — destructive parser-reprocessing instructions | Fixed | Troubleshooting now requires a consistent online backup followed by ordinary ingest. Ingest always parses and validates before identity comparison, so changed parser output creates a vintage and identical output preserves history. Row-deletion instructions are removed. Online-backup CLI consistency was checked locally; CI also checks it in the running container. |

## 2. Implemented fixes

**Batch 1 — data integrity (F01, F02, F07).** Updated validation, the migration adapter/parser,
ingestion, repository comparison, migration insights and API models. Citizenship checks apply to every
applicable stored period rather than only the latest headline. Invalid data never becomes the live
vintage. Canonical identity includes values, statuses, standard errors, period bounds and measurement
semantics; it avoids a one-time false correction for every legacy digest. Added focused validation,
parser, ingestion, correction and identity regressions. Production source fixtures were not edited to
make checks pass.

**Batch 2 — reliability (F05, F06).** Updated configuration, fetcher and SQLite initialization. The
existing ten-second minimum remains enforced, including redirects and multiple processes. Reservation
records precede requests; successful or failed completion records follow them. Reads are bounded to
the latest 64 KiB. A schema sidecar protects initialization before SQLite's own transaction protection
takes over. Added storage-failure and multiprocess regressions.

**Batch 3 — UI (F03, F04, F08, plus F02 presentation).** Updated Overview, Release analysis and Calendar,
regenerated API types and frontend fixtures, and added browser regressions. Selected-bundle capture
time replaces response time in the freshness label; uncertainty is labelled as SE; full calendar
details work with keyboard and touch; corrections have their own panel and missing-value wording.

**Batch 4 — security and operations (F09, F10, CI).** Removed the unused CLI dependency and retained its
five used CSS variants locally with their MIT notice. Reprocessing remains a normal ingest with full
validation and a preceding online backup. Updated the data dictionary, known limitations and
troubleshooting guidance. CI now checks frontend lint and dependency audit, all three browser widths,
and an offline Docker persistence/scheduler/backup smoke in `scripts/smoke_docker.sh`.

## 3. Regression test evidence

New behavior was reproduced with failing tests before implementation. The four logical batches were
verified independently, then together. These session logs are local evidence, not committed artifacts:

| Area | RED evidence | GREEN evidence |
|---|---|---|
| F01 | `nzstats-remediation-f01-{red,pipeline-red,bounds-red,review-red}.log` | Focused validation/parser/ingest suite: 135 passed; included in full suite. |
| F02/F07 | `nzstats-remediation-f02-f07-{corrections-red,identity-red,signed-zero-red,publication-wording-red}.log` | Focused correction/identity suite: 195 passed; included in full suite. |
| F05 | `nzstats-remediation-f05-{config-red,fetcher-red,durability-edge-red,newer-corruption-red}.log` | Focused fetcher/config suite: 88 passed, including review regression for a newer damaged journal record. |
| F06 | `nzstats-remediation-f06-red.log`: two concurrent-start failures | Focused database/API suite: 111 passed. |
| F03/F04/F08 and correction UI | `nzstats-remediation-f03-backend-red.log`; `nzstats-remediation-ui-red.log`: four failed, 34 passed | Focused UI: 38 passed; freshness/backend models: nine passed; all included in final suites. |
| F09 | `nzstats-remediation-ops-audit-baseline.log`: seven high vulnerabilities | `npm audit --audit-level=low`: zero vulnerabilities. |

The new committed tests describe the cases directly: `backend/tests/validate/test_rules_citizenship.py`,
`backend/tests/pipeline/test_ingest_citizenship.py`,
`backend/tests/pipeline/test_statistical_identity.py`, `backend/tests/insights/test_corrections.py`,
`backend/tests/insights/test_freshness.py`, `backend/tests/sources/test_fetcher_safety.py`,
`backend/tests/store/test_concurrent_migrations.py`, page tests and `frontend/e2e/remediation.spec.ts`.
Failure injection covers the absence of outbound HTTP when durable pacing storage fails.

## 4. Statistical reconciliation results

The new code was run against the full official June, July and August 2026 release pages and CSVs
cached during the preceding deliberate audit. This replay used `httpx.MockTransport`: **zero external
requests** during remediation. It did not substitute excerpt fixtures for full source files.

| Reference month | Official publication date | Monthly net migration | Year-ended net migration |
|---|---|---:|---:|
| June 2026 | 14 August 2026 | 1,607 | 17,624 |
| July 2026 | 14 September 2026 | 5,170 | 20,350 |
| August 2026 | 14 October 2026 | 2,193 | 20,503 |

All **24 headline values** (eight per release, including arrivals, departures and citizenship net
migration) remained equal to the cached official data. June monthly net was revised to 2,331 in the
July publication and to 1,997 in August; the earlier-publication revision comparison retains that
history, separately from within-publication corrections. Official independently rounded components
can differ by one person from their net; existing evidence-based tolerances remain in force.

Re-ingesting August, including legacy digest compatibility, returned `unchanged`: **164 releases,
771 vintages and 29,395 observations** before and after. SQLite integrity and foreign-key checks passed.
A malformed HTTP-200 release response failed with `layout_changed`, retained the same counts and kept
the last good published bundle. Scheduler construction retained calendar refresh, minute release
watch and daily catch-up jobs. Evidence: local `nzstats-remediation-reconciliation.log`.

## 5. Complete test and CI outcomes

Run from the indicated directory, with the backend environment activated so `python` and `nzstats`
resolve to this checkout. The final verification results are recorded below; warnings are identified
rather than counted as failed tests.

| Directory | Command/check | Local outcome |
|---|---|---|
| `backend` | `PYTHONPATH=src python -m pytest -o addopts='' --cov=nzstats --cov-report=term-missing --cov-report=json:/tmp/nzstats-remediation-coverage.json` (Python 3.12.13) | **651 passed**, one known Starlette/httpx deprecation warning; **96.5%** statement coverage (terminal rounds to 97%; 2,694 statements, 94 misses). |
| `backend` | `.venv/bin/pytest` (local Python 3.14) | **651 passed**, one known warning. |
| `backend` | `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .` | Passed; 107 Python files formatted. |
| `frontend` | `npm test` | **120 passed**, 13 files (fresh final run). |
| `frontend` | `npm run typecheck`, `npm run lint`, `npm run build` | Passed; three known UI Fast Refresh warnings and the existing chart-bundle size warning. |
| `frontend` | `npm audit --audit-level=low` | **Zero vulnerabilities** following dependency removal. |
| `frontend` | `npm run gen:api` | Generated schema reviewed and included; succeeded. |
| `backend` | `python ../scripts/dump_frontend_fixtures.py` | Generated fixture changes reviewed and included; succeeded. |
| `frontend` | `PATH="$PWD/../backend/.venv/bin:$PATH" E2E_DATA_DIR=/tmp/nzstats-remediation-e2e-final npx playwright test` | **39 passed** across 1440, 768 and 390 px (fresh final run). |
| Repository | `bash -n scripts/smoke_docker.sh`, `git diff --check`, `docker-compose config --quiet` | Passed. |
| Repository | `PYTHONPATH=backend/src python "$AUDIT_DIR/reconcile.py"` (preceding audit's local cached-source replay) | Passed; results in §4. The cached audit workspace is local and is not required by CI. |
| Repository | `nzstats serve --no-scheduler` and `nzstats backup <temporary-destination>` against an isolated temporary database | Live API online-backup consistency and sentinel preservation passed; no source requests. |
| Repository / CI | `docker build -t nzstats:ci .` then `bash scripts/smoke_docker.sh nzstats:ci` | **Passed in Linux CI**: image build, health, named-volume restart/recreation, scheduler startup and online backup. Local daemon unavailable. |

The [implementation CI run](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/38833986960)
passed all three jobs (**backend, frontend, docker**) for implementation commit
`4f68ec217b6d2227e0f0d5ee528c70d73263fa47`. It independently ran the full backend/frontend/browser
checks and the offline Docker smoke, including the online backup integrity and persistence sentinel.
This report update records that completed run; check [PR #2's checks](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/2/checks)
for subsequent commits. CI also emits existing action-runtime deprecation and upcoming runner-image
migration notices; these did not fail any job.

Browser regressions include freshness wording, explicit standard errors, full calendar details and
focus restoration, and distinct same-publication corrections with missing values rendered as missing.
The 39 scenarios comprise 27 existing scenarios at three widths and 12 added remediation scenarios.
Desktop, tablet and mobile screenshots were inspected, including mobile dark mode: the 390 px viewport
kept content within the available 358 px body width and produced no browser errors. Screenshots remain
local diagnostic artifacts.

GitHub Actions now runs backend lint/format/tests, frontend type freshness/typecheck/lint/tests/build/
dependency audit/browser tests, followed by the Docker job. The Docker smoke uses `--network none`, a
named data volume, restart and recreation, a scheduler-enabled start and an online backup integrity
check. A passing workflow proves those exercised cases; it cannot prove an unattended live publication.

## 6. Remaining deployment verification gaps

- Local container execution could not run because the Docker daemon is absent. Compose configuration
  and script syntax passed, and Linux CI passed the offline Docker smoke. The actual production host
  remains a separate verification environment.
- Production host bind-mount ownership, service deployment and restart with the actual host's data
  remain unverified. CI exercises a named volume under the image's normal user.
- An entire unattended scheduled publication has not been observed. No source requests were issued
  to simulate that milestone. Confirm the source calendar before observing a future release.
- Existing manual rechecks remain necessary for later corrections to an already published release;
  this remediation does not add a scheduled historical-correction sweep.

## 7. Outstanding risks

- The pacing journal is append-only. Reads are bounded to its latest 64 KiB, but disk usage grows over
  time. Do not delete, truncate or replace its inode while any service or CLI process uses it.
- If receipt of a long `Retry-After` cannot be durably recorded, recovery sees the unfinished
  reservation and applies the conservative fixed 30-minute fallback. It cannot reconstruct an
  unpersisted server deadline longer than that fallback. This is documented in troubleshooting.
- Measurement metadata is shared per series rather than versioned per vintage. The identity checks
  include its semantics, but this work does not redesign historical metadata storage.
- The existing large chart bundle, three Fast Refresh warnings and one Starlette/httpx test warning
  remain. None failed the required checks.
- Full official source replay is evidence for the cached publications, not proof against every future
  upstream layout. Layout and validation errors continue to preserve last-known-good data.

## 8. Final recommendation for independent verification

[PR #2](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/2) is open and its implementation
CI passed. Review its diff and require passing checks for its latest head before merge consideration.
Do not merge or deploy as part of this task. Request a **fresh independent Codex audit** of the
remediation and its statistical/deployment evidence, with particular attention to
invalid-source rollback, legacy-vintage compatibility and durable pacing failure modes. Stop before
Phase 2; its design and implementation remain outside this remediation.
