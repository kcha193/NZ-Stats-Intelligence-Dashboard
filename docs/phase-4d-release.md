# Phase 4D integration and release evidence

Assessed 29 October 2026 (Pacific/Auckland). **Production release: NO-GO.**
The code release candidate can be reviewed separately from data activation. No merge to main, deployment,
live statistical collection, source-permission change or production migration was performed.

## Phase 4C ancestry reconciliation

Remote main was confirmed as `8f9f2a0d0932173020815bedab389048664a4f5e`.

| PR | Feature head | Actual merged target | Merge commit | Feature on original main? |
|---|---|---|---|---|
| [19](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/19) | `48c34a0` GDP | main | `8f9f2a0` | Yes |
| [20](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/20) | `a9c76f2` labour plus GDP conflict fix | feat/phase-4c-gdp | `c38099c` | No |
| [21](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/21) | `35a7633` synthetic-only OCR | feat/phase-4c-labour | `c82572f` | No |
| [22](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/22) | `33091a9` pages, Outlook and snapshots | feat/phase-4c-ocr | `d2e2a37` | No |

`feat/phase-4d-release` starts from main and merges both completed remote tips: GDP `c38099c` through
`072a762`, then OCR/integration `d2e2a37` through **`dd0d5c8`**. Neither tip alone contains the entire final
stack. The only merge conflict was in `docs/progress.md`; both historical review/implementation records were
retained. All four feature heads, all four merge commits and GDP chronology fix `48c34a0` are ancestors of
the integrated tree. No Phase 4C database migration was missing; the current schema remains 10.

The implementation commit is **`9cc55e2fd99dde5cf1f29be356eea6f20f43dd2a`**, in
[draft PR #23](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/23), targeting main.
GitHub confirms the PR has no merge conflict; it remains draft and unmerged. A documentation-only follow-up
records the PR/check evidence; current PR head is authoritative for that follow-up. Main remains unchanged.

## Statistical reconciliation and fixes

[Independent statistical report](phase-4d-statistical-reconciliation.md) and
[backfill dry run](phase-4d-backfill-plan.md) contain exact source URLs, release dates, formulas and counts.
Independent CSV/ZIP/Decimal calculations confirm 1,226 GDP growth/level checks, 323 labour-force identities,
969 labour rate/level checks and 528 LCI growth/index checks within existing tolerances. The captured GDP
page's “Annual growth” is annual average growth, not annual change of a quarter. No tolerance was loosened.

Two production correctness changes were necessary:

- Late historical captures, corrected/revised artifacts, snapshots and later changed bundles cannot acquire
  first-publication status solely from their release title. The earliest inserted bundle is retained. Eligibility
  additionally requires an original-source capture on the official Auckland release day, after publication.
  Earliest-stored outcomes remain visible; first errors, revision-against-first, accuracy samples and rankings
  exclude unverified baselines. Latest-outcome comparisons remain descriptive and labelled.
- Removed the unsubstantiated GDP “2009/10 prices” assertion. Chain-volume/current-price distinctions remain.
  A presentation correction also covers pre-Phase-4D persisted metadata, without rewriting observations or the
  immutable historical definition records. No alternative reference year was invented.

Publication-day capture is an operational eligibility rule, not proof that an upstream publisher never silently
changed a file earlier that day. There is no historical attestation mechanism. Historical originals unavailable
from approved evidence remain unavailable, including the revised March labour archive as a complete original bundle.

The final independent code review raised two P2 findings: a second same-day bundle could be labelled original,
and old persisted GDP metadata could retain the unsupported year. Both were reproduced by failing tests and
fixed in one pass. Regression tests cover original-versus-correction eligibility and API/dashboard/CSV
presentation while proving stored observations and historical metadata are retained. No findings were deferred.

## Verification evidence

Verified locally on the final implementation tree:

| Check | Result |
|---|---|
| Backend, clean Python 3.12 and existing Python 3.14 | 2,785 passed on each; Ruff lint and format clean |
| Frontend | 478 passed; typecheck, lint, live/static builds and generated API schema parity passed |
| Dependency audit | Zero vulnerabilities at `npm audit --audit-level=low` |
| Live browser | 150 passed |
| Synthetic-research browser, including screenshots | 21 passed |
| Static browser/security/parity | 312 passed, three expected skips |
| Backup/database/migration focused checks | 33 passed; restore verification passed again after final implementation |
| Production CPI reconciliation | Two vintages and 1,607 outcomes; no discrepancies |

Existing warnings: Starlette/httpx deprecation, three frontend Fast Refresh exports and the large ECharts bundle.
These are not hidden as failures or described as clean warning-free output. Head-specific hosted CI remains a
separate check. The clean Python 3.12 environment installs `backend[dev]` from the declared dependencies;
frontend verification used Node 20.20.2 and npm 10.8.2, matching the configured Node major.

The reproducible commands are:

```sh
cd backend
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
cd ../frontend
npm test
npm run typecheck
npm run lint
npm run build
npm run gen:api  # backend venv on PATH; generated schema must match
npx playwright test --workers=4
npx playwright test -c playwright.research.config.ts --workers=3
cd ..
scripts/e2e_static.sh --workers=4
```

All browser runs use isolated fixture databases and no scheduler. The research run uses fictional institutions
and its own synthetic registry on loopback only. Browser checks include home/overview, GDP, labour, CPI,
migration, card spending, Outlook, forecast outcomes, historical vintages, CSVs, PNGs, all three viewport sizes,
light/dark mode, static routing/headers/network isolation and live/static parity.

A separate SQL-to-HTTP check compared **every GDP and labour point** with the latest database vintage:
12 GDP series / 1,857 points and 11 labour series / 1,624 points matched exactly. The independent arithmetic
report verifies the underlying official observations. Production has no macro vintages, so this populated
agreement is fixture-database evidence; it cannot substitute for post-backfill production reconciliation.

[Screenshot gallery and provenance](screenshots/phase-4d/README.md) includes populated GDP/labour at all three
viewport sizes and both themes, OCR unavailable, and explicitly synthetic forecast views. Screenshot review
does not claim physical-device or assistive-technology certification.

## Production database, recovery and operations

[Operational evidence](phase-4d-operations.md): production is already schema 10 with 181 releases,
523 series-vintages and 52,309 observations. GDP/HLFS/LCI have no vintages; CPI holds September 2026 only.
Read-only SQLite online backup plus the raw tree was restored and checked: 54,014 rows in 26 tables,
20 referenced artifacts with matching hashes/sizes, integrity/foreign keys/migration objects all valid.
The live main-file hash remained unchanged. The pre-approved-backfill fresh backup is still pending.

Hosted Actions are billing-blocked before steps execute; existing runs are not green. Docker CLI/Compose
configuration checks are available, but no daemon exists: image builds and container smoke are NOT RUN.
Neither absence is waived by local tests. Institutional research has no production rows and remains disabled;
OCR remains synthetic-only with no RBNZ acquisition path.

The implementation-head PR run [40832127618](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/40832127618)
was triggered by opening #23. Backend, frontend and static-site each failed **before starting**, with zero steps,
empty runner names and runner ID 0; Docker was skipped. Each check's failure annotation cites failed account
payments or the spending limit. This is fresh head-specific evidence of the billing block, not executed CI.

## Netlify draft preparation

A local production-origin, Stats NZ-only candidate was exported from the restored production copy:

- Snapshot `5bb766a751b3fb4d199a6810439ae82dd73f3793ebb506e0f2e5f2cce6f695eb`.
- 216 files, 3,145,656 payload bytes, 181 release registrations / 45 published; four release analyses.
- Generated 29 October 2026 19:30 NZDT; underlying data last updated 22 October 2026 21:04 NZDT.
- `validate-snapshot --for-publish` and `check-site --for-publish` passed; 19 pages prerendered.
- Local response checks: dashboard routes 200 with their own canonical; manifest JSON 200; missing data,
  absent GDP JSON and research API are JSON 404. CSP, nosniff and caching/security rules are applied by the emulator.
- No database, raw artifact, ingestion log, fixture marker or research payload is present in the public snapshot.
  GDP/labour files are correctly absent. A fresh export timestamp does not imply complete or fresh macro coverage.

The retained candidate is ignored local output under `data/phase-4d-netlify-candidate/`, served for inspection
with the existing local Netlify rules emulator. **Nothing was uploaded to Netlify.** Canonicals use the reserved,
provisional origin `https://nzstats-release.example`; no real canonical site URL is configured. The owner must
confirm the actual origin and site, then the candidate must be rebuilt and checked before an authorised draft
upload. Actual Netlify edge responses and draft URL validation remain pending that deployment approval.

## Owner decisions and release verdict

| Gate | Required owner action |
|---|---|
| Integration | Review and explicitly approve merging the final Phase 4D PR into main. No auto-merge. |
| Official backfill | Authorise the seven-release batch and request budget in the dry run, with fresh restorable backup, sequential processing and per-release reconciliation. Historical captures remain earliest stored unless independently attested. |
| Hosted validation | Restore Actions billing/runner eligibility and obtain final-head CI; supply a Docker runtime for both images and smoke checks. |
| Netlify | Confirm canonical origin/site and separately authorise a draft deployment after data and validation gates. Production publication needs its own approval. |
| OCR/research | Separate documented official-source/permission decisions are required to activate either; they stay disabled. |

**GO WITH CONDITIONS for integration review; NO-GO for populated macro production release or deployment.**
The unresolved gates are explicit authorisations, original-vintage evidence, production population and hosted/runtime
verification. Completing local code checks does not grant any of those approvals.
