# Phase 4E: first release validation

Assessment: 29 October 2026, Pacific/Auckland. **Production deployment: NO-GO.**
The owner approved only the enumerated seven-release official backfill and conservative provenance limits during this session. Netlify site/origin are undecided; no draft upload or production deployment is authorised. No merge, paid LLM call, research permission change or RBNZ access occurred.

## Baseline and acceptance matrix

Latest fetched main is `3ac92addea52908d926a93e4015c217cf6cde125`, the owner's merge of [PR #23](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/23). Its tree equals the reviewed `2ee17db6e908d39e94d6aed4070cd4c531514234` tree. Both Phase 4C completed tips (`c38099c`, `d2e2a37`), GDP chronology fix `48c34a0`, Outlook qualifier fix `33091a9` and final GDP identity remediation are ancestors. The older [Phase 4D report](phase-4d-release.md) describes its pre-merge assessment; this report supersedes its current-state claims.

| Gate | Result | Evidence / action remaining |
|---|---|---|
| Phase 4C integration | PASS | Main ancestry and identical reviewed tree |
| Production schema | PASS | Schema 10; all 74 table/index/trigger SQL definitions match a freshly migrated reference |
| Offline seven-release plan | PASS | Seven captured release identities/dates and selected URLs; 30 logical GETs; 246 vintages / 23,730 observations before two previously uncaptured workbooks |
| Owner backfill approval | APPROVED | Exact seven releases, fresh backup, sequential pacing, earliest-stored provenance; no scope expansion |
| Fresh backup and independent restore | PASS | Online backup and complete raw tree, restored separately; 20 referenced artifacts, hashes/sizes and all 26 table counts agree |
| Actual backfill and production reconciliation | PASS | Seven releases, 30 logical GETs / 30 attempts, 268 new vintages / 24,093 observations; no unexplained discrepancies |
| Local CI checks | PASS | Backend 2,809; frontend 478; lint/format/types/build/schema/audit; live browser 150; static 312 and three expected skips |
| Hosted GitHub Actions | BLOCKED | Merge-commit run failed before execution because of billing; Docker skipped |
| Docker runtime | BLOCKED | CLI available; no daemon. Compose syntax checks pass using separate `docker-compose`. Images/smoke not run |
| Official-only publication rehearsal | PASS LOCALLY; DEPLOYMENT BLOCKED | Populated production-origin snapshot; latest macro SQL equality, unchanged ECT/migration/September CPI, six desktop/mobile views and twelve exports; provisional origin only |
| Netlify target and canonical origin | BLOCKED | Owner has not selected/confirmed them |
| Draft upload and draft acceptance | NOT AUTHORISED / NOT RUN | Separate upload approval, then separate acceptance |
| Production deployment and live verification | NOT AUTHORISED / NOT RUN | All gates, accepted draft and separate production approval required |
| OCR and institutional research | RESTRICTED | OCR synthetic only; no RBNZ acquisition; research, LLM processing and public display remain disabled |
| Scheduler and monitoring | LOCAL EVIDENCE ONLY | Five jobs registered without starting them; container runtime, deployed cadence and external alert delivery unverified |

## Actual backfill and statistics acceptance

Owner approval preceded all 30 Stats NZ requests. The fresh pre-activation backup was created at **29 October 2026 20:45:30 NZDT** and independently restored with exact database/raw checks before collection. The source window ran **20:46:12–20:57:42 NZDT**. Seven live calendar entries matched the planned dates/identities before a single registration transaction; six new registrations were added. Each release then passed before the next began. Every response was HTTP 200; there were no retries, redirects, blocks, budget overruns or scope extensions. The smallest timestamped request-start gap was 10 seconds; the shared pacer also waits at least 10 seconds after the preceding response.

| Release | Page/file GETs | New series-vintages | New observations |
|---|---:|---:|---:|
| CPI December 2025 | 5 | 74 | 5,673 |
| CPI March 2026 | 5 | 74 | 5,718 |
| Labour March 2026 | 2 | 11 | 1,613 |
| GDP March 2026 | 2 | 12 | 1,845 |
| CPI June 2026 | 5 | 74 | 5,763 |
| Labour June 2026 | 2 | 11 | 1,624 |
| GDP June 2026 | 2 | 12 | 1,857 |
| Total, excluding seven calendar GETs | 23 | 268 | 24,093 |

Production now holds **187 release registrations, 450 series, 791 series-vintages, 76,402 observations and 43 raw-artifact records**, at schema 10. All 52,309 pre-existing observations, 523 vintages and 523 historical definitions compare exactly with the fresh pre-activation backup, including September CPI. All 43 raw artifacts pass hash/size checks. All research tables remain empty.

The extra **22 vintages / 363 observations** over the offline 246 / 23,730 baseline come entirely from the previously uncaptured December/March CPI workbooks. This was an enumerated optional part of the approved 30-request plan. Independent standard-library XLSX XML parsing matches their 176 / 187 observations across eleven series each, plus June's 198 observations. Some workbook decimal strings differ from decimal representations of SQLite REAL by at most **4×10⁻¹⁶**; exact conversion to the same binary float and the published one-decimal figures agree. This is an explained storage representation difference, with no statistical tolerance change.

Full live GDP/labour file hashes equal the independently audited retained originals. Every selected production macro row matches the corresponding official rows: March/June GDP **1,845 / 1,857**, labour **1,613 / 1,624**. Independent CSV/ZIP/Decimal arithmetic covers **1,226 GDP growth checks**, **323 labour-force identities**, **969 HLFS rate checks**, and **528 LCI growth checks**, within the existing 0.06 pp / 1.5 thousand / 0.08 pp / 0.06 pp limits. GDP quarterly, annual change and annual-average definitions remain distinct; labour reference periods, SA HLFS and unadjusted LCI are explicit. CPI reconciliation checks **eight all-groups index vintages and 1,607 outcomes against twelve official files**, with zero discrepancies.

Warnings were reviewed against the exact official rows. December fruit/vegetable and gas quarterly movements are −8.1967% / +5.1365%; June petrol, private transport and transport are +20.0831% / +12.9655% / +5.9724%. These are official movements, not parser discrepancies. Seven optional CPI SA series end in March 2023; they remain explicitly discontinued/stale, without extrapolation. GDP's leading unpublished growth quarters are blank upstream and remain absent. Later GDP and labour historical revisions match the audited files and remain separate vintage observations. No thresholds were loosened.

All seven historical captures are **ineligible for first-published scoring**. Production GDP March's earliest-stored 0.8% versus latest 0.9%, and unemployment's 5.3% versus 5.4%, are retained. In-memory synthetic claims against the actual production outcomes verify missing first-error/revision scores and release-day look-ahead exclusion; no forecast was stored. Existing September CPI retains its separate release-day eligibility under the operational rule, which does not prove the publisher never changed a file earlier that day. There are no actual production research claims to score.

## Verification boundaries

Commands and machine evidence are linked in [the evidence index](phase-4e-evidence/README.md). Local checks used the repository CI commands and Python 3.12, with Node 20 for frontend checks. Existing warnings remain: Starlette/httpx deprecation, three Fast Refresh export warnings and the large ECharts chunk. The research browser suite uses fictional institutions on loopback only: 18 passed, three screenshot-only cases skipped. Its first attempt could not bind an occupied port; the successful isolated retry is the accepted result.

The first frontend run collected 44 files / 465 cases. A fresh inventory proved all 47 tracked test files / 478 cases were present, and the final full run passed all 478. No test files or exclusions were changed. The final count, rather than the incomplete initial discovery, is the acceptance evidence.

[Hosted run 40835493335](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/40835493335) is specific to merged main. Backend, frontend and static-site have no executed steps; the backend annotation says account payments failed or the spending limit must be increased. These are not executed test failures or green CI. No rerun or billing change was triggered. The Ubuntu image migration notice is separate from the billing failure.

The source/backup checks used read-only production access until the approved activation window. The independently restored fresh backup is retained privately under `data/backups/`; backup paths and raw bodies are excluded from publication. No production migration was necessary.

## Undeployed publication candidate

The rebuilt candidate has production origin and snapshot ID **`75b42648f75c34e0635ff8a6fa8d6a61e0b12a84abe67c2920cef07823578d66`**: 224 snapshot files / 3,579,047 payload bytes, 187 registrations / 51 published, eleven release analyses. The data timestamp is **29 October 2026 20:57:42 NZDT**. The exact generated timestamp and all file hashes are in [the snapshot manifest](phase-4e-evidence/snapshot-manifest.json); [the complete site inventory](phase-4e-evidence/candidate-files.json) also covers built assets and HTML.

`validate-snapshot --for-publish` and `check-site --for-publish` passed. Both GDP and labour files are present; all **1,857 GDP and 1,624 labour points** equal the latest SQL vintages. Thirty ECT/migration payloads are unchanged; latest September CPI points are identical, while its authorised history/revision context now includes the backfill. Fourteen local route/header/canonical assertions passed, including JSON APIs, missing data and real 404s. CSP, nosniff and HSTS header rules are present in the emulator. Private research/model output, credentials, database/raw files and internal paths are excluded by publication validation.

Six populated production-data browser views passed at 1440×900 and 390×844, with no horizontal overflow, page errors or external requests. All six CSV and six PNG exports downloaded successfully; hashes and dimensions/provenance are recorded in [publication evidence](phase-4e-evidence/publication.json). [Screenshots](screenshots/phase-4e/README.md) show the actual production dataset. The initial incomplete-data rehearsal could not produce a GDP heading; it was not accepted as populated-site evidence. The final populated candidate passed.

**Nothing was uploaded.** Canonicals/sitemap/export footers still use the reserved rehearsal origin `https://nzstats-release.example`. This candidate must be rebuilt and verified against an explicitly confirmed real site/origin before requesting draft-upload approval. Actual Netlify TLS/compression/edge headers, draft acceptance, production validation, deployed snapshot/commit/URL/timestamps and a real site rollback reference remain pending. Their machine fields are null, not placeholders presented as deployments.

## Restrictions and verdict

A historical release title and earliest insertion do not establish first publication. Revised March labour and corrected December CPI remain official historical captures with uncertain original-vintage provenance. First errors, revisions against first and ranked accuracy samples must exclude these uncertain baselines. There are no real research forecasts to evaluate; fixture coverage does not create production research evidence.

All statistical discrepancies must be explained or block acceptance. Underutilisation cannot be reconstructed from the stored headline components; check the official value/definition without inventing missing components. The GDP chain-volume reference year remains unverified and is not displayed. The independent audit covers the selected dashboard series, not every series in the full source archives.

**Current verdict: NO-GO for production release or deployment.** Backfill approval does not waive hosted/runtime gates or authorise Netlify. Operational steps, required owner/account actions and rollback rules are in [the Phase 4E runbook](phase-4e-operations.md).
