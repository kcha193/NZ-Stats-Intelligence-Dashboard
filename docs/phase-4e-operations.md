# Phase 4E monitoring, acceptance and rollback runbook

Use [the release matrix](phase-4e-release.md) and [machine evidence](phase-4e-evidence/README.md) together. These procedures do not grant deployment or source permissions. The seven-release batch is approved in this session; any expansion, retry after a stop, Netlify upload, production publication, research access or paid model call needs its applicable approval.

## Before any further collection

1. Check the activation ledger and preserve its recorded stop, request count, captures and shared `data/.request-pace` journal. Never rerun the general `backfill`, `discover`, an ICS crawl or an uncapped all-category command to complete this batch. The approved baseline is seven calendar GETs plus 23 page/file GETs; retries and redirects are network attempts, not free budget. This execution stops before an unexpected URL, retry, redirect or budget expansion.
2. Check that production ingestion and publisher processes are stopped. Do not start `serve` with its scheduler to inspect data: startup jobs contact the source. Use loopback `serve --no-scheduler` over an isolated copy for checks.
3. Require a fresh SQLite online backup, complete raw tree and source configuration. Restore it into a separate directory; `verify-backup` must pass with no row-count differences, every referenced raw SHA-256/size must agree, and table/index/trigger definitions must match schema 10. Verify all raw-tree files, not just referenced files. A prior rehearsal is not this backup.
4. Record the approved commit, scope, window and owner decision. Stop on a changed release date, identity, download listing, unexpected file/structure/statistic, source block or unexplained discrepancy. Review warnings before the next release. Retain last-known-good observations and the verified DB/raw backup.
5. Process only the seven explicit release keys in [the Phase 4D plan](phase-4d-backfill-plan.md). Record requests/attempts, URL, UTC capture time, content type/size/SHA-256, publication time, bundle identity, vintage IDs and per-release independent reconciliation. Never backdate capture time. Conservative earliest-stored labels survive activation.

The session's guarded operator scripts and full raw captures remain private ignored audit artifacts under `data/phase-4e/`. Do not rerun them blindly: they mutate production and are tied to the current ledger. Portable offline arithmetic and input checks are in `docs/phase-4e-evidence/reproduce_offline.py`; they never contact the source.

## Hosted and container gates

Owner: restore GitHub Actions payment/spending-limit/runner eligibility, then obtain a successful run on the exact release commit. Record run/job URLs and actual executed steps. A zero-step failure or skipped Docker job does not pass.

Supply an available Docker daemon. The separate `docker-compose` executable can validate syntax here; its success does not build an image. On a runtime:

```sh
docker build -t nzstats:phase-4e .
bash scripts/smoke_docker.sh nzstats:phase-4e
docker build -f Dockerfile.publisher -t nzstats-publisher:phase-4e .
```

The application smoke uses network isolation and checks health, SQLite persistence across restart/recreation, online backup, provider refusal and scheduler startup jobs. Independently restore-verify its backup and matching raw artifacts as well. The application image uses Python 3.12 / Node 20; the publisher uses Python 3.12 / Node 22 and its pinned Netlify CLI. Host frontend checks do not prove the publisher image works.

For the publisher, use an isolated **copy** of production data and an empty private work directory. Run `once` with `--network none`, `PUBLISH_ENABLED=0` and `PUBLISH_SITE_URL` set to the owner-confirmed canonical origin. Give the container no Netlify credentials. Verify dry-run export/validation/build exit 0, production-origin manifest, no deployment/state promotion and unchanged source rows. This remaining container smoke must be recorded separately from the image build. Do not start a publisher loop with upload enabled for a smoke check.

## Netlify draft and production acceptance

1. Owner selects/confirms the exact Netlify site ID/name and canonical HTTPS origin. The current `.example` origin is a reserved rehearsal placeholder; it is never a deploy target. No Git-linked automatic deployment. Keep credentials in private environment/configuration, never reports, shell arguments, screenshots or snapshots.
2. Export from the reconciled production database into a new candidate directory; require `origin=production`, full publication validation and a release-specific check that **both** `gdp.json` and `labour-market.json` exist. The general exporter intentionally treats them as optional, so its success alone does not satisfy Phase 4E.
3. Build with the confirmed origin. Recheck exact latest GDP/HLFS/LCI values, all macro points versus SQL and official captures, CPI history/revisions, September CPI preservation, ECT/migration unchanged payloads, source attribution, freshness, sitemap/canonicals, security headers, no private research/model/credential/path leakage, direct routes and real 404s, desktop/mobile, CSV and PNG exports. Archive manifest, SHA-256 inventory, code SHA, UTC/Auckland timestamps and screenshot/browser results.
4. Present that exact candidate and its manifest for **separate draft-upload approval**. Upload only after approval. Capture site ID, deploy ID, draft URL, upload start/end and CLI result. Verify actual Netlify edge headers, JSON/content types, compressed responses, canonical target, all important routes/404s and downloads against the same immutable manifest. Local emulator checks do not prove Netlify edge behaviour.
5. Owner accepts the verified draft separately. Record that acceptance and then request explicit production publication approval, with rollback reference. A draft upload is not production approval. Keep scheduled publication disabled.
6. Deploy the accepted bytes, or rebuild and prove the complete file inventory unchanged. Verify the production domain and immutable deploy URL: manifest snapshot ID, every manifest file hash, expected statistical values and source URLs, code SHA and final edge/browser/export checks. Record deploy ID/URL, actual UTC/Auckland deployment and validation timestamps, owner approval, result and rollback reference. If the canonical origin changes after draft acceptance, rebuild and review again.
7. No production release is complete until live verification passes. `deployed_unverified` is a failure requiring investigation; it is not release acceptance. Do not manually edit a manifest or the publisher state to manufacture success.

## Monitoring operating policy

The existing scheduler registers `refresh_calendar` at 06:00 Auckland, `release_watch` every minute, `catch_up` at 07:30, and two startup jobs. Calls share the persistent 10-second pacer, source blocks produce a 30-minute cooldown, updates validate transactionally, and failed updates retain prior observations. Registration was checked locally without starting jobs. Actual running jobs/restart recovery and the next live release remain unverified.

The publisher validates a production-only snapshot before building/uploading, uses a process lock, advances confirmed state only after the live manifest matches, and throttles calendar-only/unverified redeploys. Its tests use fakes. It does not independently reconstruct every statistical identity at every scheduled publication, and the generic contract permits absent GDP/labour. Keep publication disabled until the release-specific checks and the authorised operating workflow have been accepted. Routine future collection is outside this seven-release approval.

A monitoring operator must check all of the following, not just HTTP 200:

| Check | Trigger / response |
|---|---|
| API health and SQLite | HTTP failure or `database_ok != true`: stop publisher, investigate host/DB; do not treat `database_ok` as a full integrity check |
| Source and ingestion health | Any blocked/layout/validation/network failure or failed/missing expected release: retain last-good data, investigate; no alternate fetch route or weakened threshold |
| Scheduled release completion | Reconcile registry publication time/reference quarter with an actual successful vintage. At publication +3 hours without verified data, escalate to owner; do not silently advance freshness |
| Category completeness | GDP and HLFS/LCI files/series must exist and reflect the expected approved reference periods. Fresh calendar metadata alone cannot make an incomplete dataset acceptable |
| Public manifest | Compare live ID with accepted publisher history and expected data timestamp; a new `generated_at` alone is insufficient |
| Publisher operation | Failed build/export/upload or `deployed_unverified`: alert owner, preserve state/history and known-good site; no repeated forced deployments |
| Raw/archive recovery | Check latest DB/raw backup age and hashes after each approved collection; rehearse restore before releases and after storage changes |
| Corrections | Review official correction notices through an approved source plan. Existing stored releases are not automatically re-fetched merely because they already have data |
| Restrictions | Keep public research off on reachable hosts, source acquisition/LLM/public-display permissions denied, and OCR unavailable |

Before enabling an unattended workflow, owner must choose the monitor/alert destination and operator, authorise routine collection/publication, configure it on the actual host, and demonstrate an alert and recovery end to end. No external alert service or recipient was configured/contacted in this phase. Watch the captured next labour release, **4 November 2026 10:45 NZDT**: its unseen layout must fail closed. Next captured GDP release is **17 December 2026 10:45 NZDT**; confirm future schedules through the approved calendar workflow.

## Rollback

Database rollback and site rollback are different operations. Record the fresh pre-activation backup and DB/raw manifest hash; retain it after backfill. Recovery requires stopped writers, restoring the matching database **and raw tree** into a separate verified directory, then a reviewed cutover. Preserve the pacing journal/cooldown, current failed artifacts and audit ledger. Re-run integrity/foreign-key/schema/raw checks, protected observation comparisons, independent statistics and snapshot validation before restarting anything. Do not overwrite the live database while a process holds it open.

For a deployed website: stop the publisher first, retain current state/history/manifest, then restore the exact approved last-good Netlify deploy ID. Verify its live manifest and file hashes. Keep automatic publication off until the cause is understood. Never force-publish the same failed dataset as a recovery action.

This is the first production release: no previous accepted Netlify production deploy or site is known. Before production approval, the owner must establish the actual rollback deploy/reference or an explicit first-launch unpublish procedure. The private pre-backfill dataset and an undeployed `.example` rehearsal are not an existing public rollback deployment. Rollback is prepared as a procedure; Netlify rollback remains untested and blocks acceptance.
