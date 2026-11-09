# Repository health, data-integrity and maintenance review

9 November 2026, Pacific/Auckland. Baseline: `origin/main` `80991aa` (PR #56 merged), clean worktree, no open PRs.
Branch `fix/repo-health-review-2026-11-09`. Broader proposals, none adopted, are in
[repository-health-recommendations.md](repository-health-recommendations.md).

**Scope held.** No paid inference, no Stats NZ or institutional request, no production database write, no permission,
policy or visibility change, no credential rotation, no deployment, no issue closed or edited. The real database was read
only with SQLite `mode=ro` and `query_only=ON`. Reproductions used throwaway databases under a scratch directory.

**Phase 4AD is not unblocked.** No Fortnightly Economic Update newer than 29 October (issued 2 November) was found. Treasury's
listing returned HTTP 403 to automated fetches (`curl` and the web-fetch tool, one request each, not retried or bypassed), so
that statement rests on two search-index results plus the fortnightly Monday cadence (next issue about 16 November). The owner
should confirm it in a browser. Nothing in this review depends on it.

## Result in one paragraph

No credential, database, raw document, report text or model response is in the repository or its history. One real defect was
found and fixed: `nzstats backup` migrated an existing database before copying it, so the documented "pre-upgrade" backup was
a post-upgrade one (reproduced 13 → 14; matches the undocumented-origin migration 014 recorded in project memory). The repository
is **public** although the Netlify runbook and issue #9 assume private; secret scanning and push protection are off. The
dashboard cannot notice a corrected or re-posted official release: every automatic path skips a release that already has data.
That is documented in the README but invisible to the operator. Documentation was corrected where it was demonstrably stale.

## Findings

Severity: High = data-integrity or exposure risk that has been or could easily be hit; Medium = real gap, mitigated or
unlikely; Low = accuracy or hygiene; Info = verified-good record. "Confirmed" means reproduced or read in code. "Potential"
means a mechanism exists but no occurrence was found.

| ID | Sev. | Where | Evidence and impact | Type | Minimal remediation | Verification |
|---|---|---|---|---|---|---|
| RH-01 | High | `docs/netlify-deployment.md:72,224` (old text); issue #9 body | `gh repo view`: `visibility PUBLIC`, created 2026-10-11. The runbook said "it is private" and "must stay private"; #9 says "Repository is **private**". Anyone reading the docs would assume a private source tree. | Confirmed (doc defect) | **Done:** docs now state public, treat all commits as published, and say nothing is deployed. Visibility itself is the owner's decision. | `gh repo view --json visibility` |
| RH-02 | Medium | GitHub repo settings | `security_and_analysis`: secret scanning, push protection, Dependabot security updates all `disabled`; `main` has no branch protection or ruleset; no `SECURITY.md`, no `LICENSE`. Default workflow token is `read`, fork PR approval off. | Confirmed (configuration gap) | Owner action in Settings (free on public repos). Not changed here. See recommendations R4. | `gh api repos/.../ ` after the owner acts |
| RH-03 | Low | `docs/superpowers/plans/2026-10-11-nz-stats-dashboard-phase-1.md:85,10100,10101` | Owner's personal email and an absolute local path in a public plan document (sample `NZSTATS_CONTACT`). Not a credential. Commit author metadata is public anyway. | Confirmed | Left as is: editing HEAD does not remove history, and the file is a dated record. Owner decides if a rewrite matters. | `git grep -nI 'gmail.com'` |
| RH-04 | Info | whole history | `gitleaks git` over 422 commits (17 MB): 2 hits, both false positives (a table-row id "B10 … Netlify" in two specs). No file named `.env`, `*.db`, `*.sqlite*`, `*.pem`, `*.key`, `*.log`, `raw/`, `data/` or `*.pdf` was ever added. Tracked env files are examples with empty or placeholder values. 13 of 13 `eval_set` files and `outlook.html` are marked SYNTHETIC; frontend research fixtures are `research_synthetic_*`. Tracked Stats NZ fixtures are official excerpts (CC BY 4.0). 148 further hits in the working tree are all in git-ignored `data/` and `.worktrees/`. | Confirmed clean | None. | Re-run: `gitleaks git --redact=100 .` |
| RH-05 | High | `pipeline/refresh.py:97-137`; `scheduler/planner.py:65,148`; `cli.py` `ingest --due` | A release is selected only if `NOT EXISTS (… vintage …)`. A correction or re-post under the same release page (`release_key = <series>:<period label>`) is never re-downloaded by the on-open check, the scheduler watch, the catch-up job or `ingest --due`. Only `nzstats ingest --release-key` re-checks, and `_ingest` handles it correctly (new bundle digest → new vintages, status `corrected`, earlier vintages untouched). The dashboard keeps showing the original figures with no warning. Documented in README and the Phase 4G doc, but nothing surfaces it. | Confirmed (design limitation) | Safe, manual: the runbook below. Detection: owner-gated proposals R2. No automatic ingestion expanded. | Runbook; the read-only SQL below |
| RH-06 | Medium | `store/repo.py:74-137` (`published_at = pub`, lines 103 and 113) | `upsert_release` overwrites an ingested release's `published_at` with whatever any later calendar read lists as published, later or earlier (reproduced: 19 Oct → 27 Oct → 5 Oct). It then no longer matches the vintage captured on the original day; first-published research scoring and `previous_points` use that date. **Not occurring in production today**: 0 releases have a first capture earlier than `published_at`, 0 have more than one bundle. | Potential (mechanism reproduced) | Freeze `published_at` once a vintage exists and record the observed change. Needs a decision and a migration, so proposal R3, not a hot fix. | Repro in this record; read-only SQL below |
| RH-07 | Low | `docs/phase-4g-on-open-refresh.md:91`; `pipeline/refresh.py:13` | Both said a correction is re-ingested "with a reason". `nzstats ingest` has no reason option and records none. | Confirmed (doc defect) | **Done:** wording corrected; the operator keeps their own note. | `grep 'with a reason'` |
| RH-08 | Low | `store/repo.py:83-137` | Title and headline edits seen on rediscovery overwrite the stored values, discarding a free correction signal (the month listing is fetched on every check). | Potential | Record changes as events, proposal R2. | Read-only comparison against a stored copy |
| RH-09 | High | `cli.py` (`backup`, lines 394-420 after the fix); `scripts/backup.sh`; README; Phase 4W step 2 | `backup` and `backup --bundle` ran `migrate(conn)` before copying. Repro on a schema-13 database: command reported `verified (schema 14)`; the live file went 13 → 14; the bundle labelled `pre-upgrade` was schema 14. The README, `scripts/backup.sh` and "run `nzstats migrate` (take a backup first)" all led here. Project memory records migration 014 already applied at the Phase 4X baseline with no pre-014 backup. | Confirmed defect | **Fixed:** an existing database is copied as it is; verification allows an older schema; the output says to run `nzstats migrate` after restoring. A brand-new database is still created at the current schema. | `test_cli_backup_copies_an_older_schema_database_without_migrating_it` (failed first, 2 cases); 111 related tests |
| RH-10 | Medium | `api/app.py:78`; `runtime.py:50`; `cli.py` `health`, `alert-check`; most `research` commands | Starting the new version migrates at once, with no backup opportunity: `git pull && docker compose up -d --build` and `scripts/run.sh` both do. Backups taken after the restart hold the new schema. RH-09 hid this because the backup command migrated too. | Confirmed behaviour; risk is operator ordering | **Done:** README orders "back up before `git pull`". A code safeguard (automatic pre-migration bundle) is proposal R1. | Doc check; none for code |
| RH-11 | Low | `scripts/rollback/` | Down scripts exist for migrations 004, 006-010, 014 only. None for 011 (ops), 012 (refresh), 013 (catch-up); 001-003 and 005 have none (005 is a column added to a table that 004's script drops). Nothing claims otherwise, but for 011-013 the only rollback is restoring the pre-migration bundle, which RH-09 undermined. | Potential | Document "restore-only" for 011-013, or write additive-drop scripts and rehearse them. R5. | Rehearsal on a restored copy, as Phase 4X did for 014 |
| RH-12 | Low | `catalog.py:45-53` | `INACTIVE_CATEGORIES` reasons still say CPI is "planned for Phase 2" and labour and GDP are "not ingested". Dormant: only categories with no stored release use them, and the UI shows names only, but the API payload carries the text. | Confirmed (stale text) | Update the strings and the fixtures they feed. R6 (touches the API fixtures). | `pytest` overview tests; `gen:api` unchanged |
| RH-13 | Low | README, architecture, data-sources | Stale statements (below). | Confirmed | **Done.** | Doc tests |
| RH-14 | Info | `.github/workflows/ci.yml` | Latest main run `42469806645`: backend, frontend, static-site, docker all success; the PR run for `8e2ff60` also green. No secrets, no deploy step, no `pull_request_target`; the Docker job builds the images and runs an offline smoke test; nothing is pushed or deployed. The billing block of 5-6 November cleared by 7 November (first success 2026-11-07 21:52 UTC). | Verified | Memory note updated. | `gh run list` |
| RH-15 | Info | backup code | Positive evidence: bundles verify raw-file hashes against content-addressed names, never overwrite, restore only into a new empty directory and re-verify, tolerate older schemas, and migrations run one transaction per file under a file lock. | Verified | None. | Existing round-trip tests |

## 1. Security and publication

* **Visibility.** Public (RH-01). `has_pages` is false; there is no Pages site and no Pages workflow. No Netlify site exists
  in this record and the publisher is disabled by default.
* **Detection used, values never printed:** `gitleaks git --redact=100` over all history and `gitleaks dir` over the working
  tree; file-name pattern scan over every file ever added (`git log --all --diff-filter=A`); counts and file names of
  credential-shaped strings (`sk-or-v1-`, `ghp_`, `github_pat_`, `nfp_`, private-key headers) in tracked files, all zero;
  env example files viewed with values masked.
* **Licensed content.** Tracked research material is synthetic by construction (marker strings; 13 of 13 evaluation files).
  The earliest `outlook-*` screenshots (`docs/screenshots/phase-3c`) predate the first real document import (31 October).
  That is inferred from dates; the images were not re-inspected. No PDF is tracked and none was ever added. Docs mention the
  ledger, hashes and counts of the real Treasury and RBNZ imports, but no report text.
* **What the working tree holds that is not published:** the working-tree scan (3.5 GB including dependencies) reports 146
  hits, all under git-ignored `data/` (128) and `.worktrees/` (18), as expected for local raw and model material; the other 2
  are the tracked false positives. Their contents were not inspected. Confirm `data/` is never force-added.
* **Not done, owner's call:** change visibility, enable GitHub secret scanning, push protection and Dependabot, protect `main`,
  add `SECURITY.md` and a licence, and decide on the personal email in the 11 October plan (RH-03).

## 2. Corrections, republications and superseded releases

### What is detected

| Situation | Detected? | Why |
|---|---|---|
| New release, new period | Yes | No vintage yet; on-open check, scheduler or catch-up selects it. |
| Stats NZ revises earlier periods inside a **later** release | Yes | Arrives in that release's files as a new vintage; earlier vintages stay. |
| Same release page re-posted with changed statistics | **No** | Release has a vintage; excluded everywhere (RH-05). |
| Files replaced at the same URL, page unchanged | **No** | Same. |
| Correction published as a separate, differently titled release | Yes, as a **new** release | New `release_key`; it is not linked to the original as a correction. |
| Release still unavailable or failing validation | Partly | Retried once a day; the dashboard says it could not verify; the previous data stays shown. |
| Publication date moved after ingest | Silently accepted | `published_at` is overwritten (RH-06). |
| Page headline or title edited | Silently accepted | Overwritten on rediscovery (RH-08). |

### How the dashboard can show outdated statistics after a correction

1. **S1.** Corrected CSV/workbook posted under the existing release: stored vintage stays current; header says "up to date".
2. **S2.** Corrected release re-listed with a later date: date overwritten, data not refreshed (RH-05 + RH-06).
3. **S3.** Server not opened or scheduler off (`--offline`, or no browser opening): no check at all. A 30-minute freshness
   window then bounds re-checks even when open.
4. **S4.** Away more than six months, or more than six missing releases: the rest are listed pending; history is `backfill`'s job.
5. **S5.** A corrected file fails validation: not stored; last good data shown, labelled unverified.
6. **S6.** Public Netlify site: serves the last deployed snapshot. Nothing is deployed, and a snapshot is only as current as the
   last publisher run.
7. **S7.** 46 releases in the real database have status `published` but no vintage (history before the catch-up boundary).
   They are by design `backfill`'s job; they are not stale data, but they are not shown.

### Read-only checks the owner can run today (no network)

```sh
sqlite3 'file:data/nzstats.db?mode=ro' <<'SQL'
.headers on
-- releases that already hold more than one bundle (a stored correction or reversion)
SELECT r.release_key, r.status, COUNT(DISTINCT v.bundle_sha256) AS bundles
FROM release r JOIN vintage v ON v.release_id = r.id GROUP BY r.id HAVING bundles > 1;
-- releases whose publication date now postdates their first capture (RH-06 drift)
SELECT r.release_key, r.published_at, MIN(v.captured_at) AS first_captured
FROM release r JOIN vintage v ON v.release_id = r.id
GROUP BY r.id HAVING MIN(v.captured_at) < r.published_at;
SQL
```

On 2026-11-09 both returned no rows (12 releases with vintages across CPI, ECT, GDP, labour and migration; schema 14).

### Manual remediation when a correction is suspected (owner-run, one release)

1. Confirm the correction on the official release page in a browser; note the page URL and the date.
2. `scripts/run.sh backup --bundle data/backups/pre-correction-<release>-<UTC stamp>` then `scripts/run.sh verify-backup` on it
   (the backup now preserves the current schema).
3. `scripts/run.sh ingest --release-key "<key>"`. This is one release's page and files at 10-second spacing, not a bulk
   operation. `unchanged` means the parsed statistics are identical; `ingested` means a new bundle was stored and the
   release is `corrected`; `failed` stored nothing.
4. Reconcile the new figures with the official page, and check that the earlier bundle's vintage rows are unchanged
   (re-run the first query above: `bundles` should now read 2).
5. Write down why, since the command records no reason.

Nothing in this review expands automatic acquisition. Detection options that would are in the recommendations and need an
explicit decision.

## 3. Operational integrity

| Area | State |
|---|---|
| Backup | `create_bundle` uses SQLite's online backup, copies every referenced raw file, checks each against its content hash, writes a manifest, re-verifies, then renames into place; never overwrites. The on-open refresh takes one verified `pre-refresh-*` bundle before ingesting. **Fixed:** the CLI no longer migrates first (RH-09). |
| Restore | `restore-backup` writes only to a new empty directory and re-verifies; the README steps for replacing `data/nzstats.db` by hand are consistent with the tests. |
| Migrations | One file per transaction with its `schema_version` marker, under a file lock, covered by concurrency tests. Applied on open by `serve`, `health`, `alert-check`, new-database `backup` and most `research` commands (RH-10). |
| Rollback | 7 of 14 migrations have a down script (RH-11). The 014 rollback was rehearsed on a restored copy in Phase 4X. |
| Recovery gap | The origin of migration 014 in production could not be reconstructed (`schema_version` has no timestamp). RH-09 is the demonstrated mechanism by which that can happen. |

Targeted safeguard implemented: RH-09 only. The migrate-on-open ordering (RH-10) is a startup semantics change and is left to a
decision (R1).

## 4. Issue hygiene (proposed updates; nothing posted or closed)

### #31 Phase 4H execution — proposed: close as completed with conditions

| Condition | State on `main` |
|---|---|
| A: verified unmigrated backup, bounded on-open check, status and counts recorded | **Fulfilled** (4H comment 31 Oct; `refresh_run 4`). |
| A: independent reconciliation of every new release | **Fulfilled for labour** (run 16, 4 November). CPI, GDP, ECT and migration new-release paths have **no live proof**; chart refetch in a browser was not recorded. |
| A: explicit GO / NO-GO for on-open operation | **Recorded**: GO WITH CONDITIONS (4H and 4R). The issue body's tick boxes were never updated. |
| B: hashes, readiness, health, quality, glyph investigation, annotations | **Fulfilled** (4H; PR #32). |
| B: local-only model processing review | **Superseded.** Later documented owner decisions (Phases 4K to 4X) approved hosted Treasury processing under caps. The "no hosted/paid LLM" constraint was intentionally replaced; the other constraints (crawlers disabled, no Netlify or public display) still hold. |
| B: private preview proposal | **Superseded** by the internal, loopback-only draft view (4P) and "AI Economic Intelligence" (4AA). |
| Open items named in 4R (human gold, Phase 4O reviews, key reading) | **Not exit criteria**; some made optional by 4T. Track elsewhere. |

Proposed closing comment: "Stage A and B exit criteria are met as recorded in `docs/phase-4r-acceptance.md`, GO WITH
CONDITIONS. The local-model/private-preview steps were superseded by Phases 4K to 4AA. Carry-forward (new issue): live
new-release proof for ECT (October, due 12 November), CPI, GDP and migration, and a recorded browser chart refresh."

### #9 GitHub Pages publication — proposed: owner decides; likely close as superseded

| Criterion | State |
|---|---|
| Docker app unchanged, migrations and scheduler intact | Fulfilled in CI (`docker` job). |
| Public pages validated in static mode; no localhost or `/api` requests; deep links | Fulfilled offline (`static-site` job, `scripts/e2e_static.sh`). |
| Refresh of a shared story URL at the **Pages project path** | **Superseded**: the design targets Netlify at a root path. |
| Freshness and provenance visible; no stale figures as current | Implemented (snapshot manifest, generated-at); live staleness alerting relies on an external uptime check not yet set up. |
| Security review: only permitted public data shipped | Offline leak scan, fixture refusal and research isolation tests pass; **no live artefact reviewed**. |
| Runbook with rollback, manual refresh, failed refresh, first publication | Present (`netlify-deployment.md`, `phase-4e-operations.md`); the first-launch rollback reference is recorded as unknown. |
| "Do not activate deployment or change visibility without approval" | Deployment not activated. **Visibility is now public**, contradicting the issue's premise ("private"). |
| Pages workflow in Phase 2 | **Not built**; Pages is disabled (API 404). |

The Netlify design (`docs/superpowers/specs/2026-10-24-netlify-static-publication.md`) does not record why it replaced Pages, so
the supersession is an inference the owner should confirm. Proposed comment: "The repository is public (2026-11-09), so
Pages no longer needs a paid plan, but the implemented route is Netlify static publication; nothing is deployed. Close as
superseded if Netlify is the chosen route, otherwise retitle and list what remains (a Pages workflow, Pages-path base)."

## 5. Documentation corrected

| File | Was | Now |
|---|---|---|
| `README.md` | "No paid AI, no notifications"; only migration and ECT implemented; CPI, labour, GDP "Phase 2"; container-only scheduler paragraph; update step before backup; ECT "existing scheduler" | Implemented categories and pages; local-only alerts; gated, off-by-default AI described; container scheduler versus local on-open; back up before `git pull`; no automatic re-check of a release with data |
| `docs/architecture.md` | "migration adapter" as the only adapter; "re-ingesting identical bytes"; only the scheduler; short API and page lists | Per-category adapters; statistics-digest identity and `corrected`; collection modes; migrate-on-open and backup behaviour; current API routes and pages |
| `docs/data-sources.md` | Research sources "none approved"; migration release "scheduled for 14 Oct" as fact | Current permissions as of 2026-11-09; observation dated as historical; corrections note |
| `docs/netlify-deployment.md` | Repository "private", "must stay private" | Public, treat commits as published, nothing deployed |
| `docs/phase-4g-on-open-refresh.md` | Re-ingest "with a reason" | No reason option; no detection |
| `docs/progress.md` | (new entry) | Dated entry above the Phase 4AC record; older entries untouched as history |

Historical records (Phase 4W "take a backup first", Phase 4X, 4H) were not rewritten.

## 6. Verification

| Check | Result |
|---|---|
| New regression test, written first | 2 cases failed ("verified (schema 14)"), then passed |
| Backup, CLI, runbook, run-script and Phase 4F doc tests | 111 passed |
| Ruff lint and format | clean (379 files) |
| Full backend suite (run after the last code and doc edit) | 5,936 passed, 0 failed, 1 existing Starlette deprecation warning (5,934 before plus the 2 new cases) |
| Frontend | not run: no frontend or API-contract file changed |
| Hosted CI on main | green (`42469806645`); PR CI to be recorded on the PR |

Not verifiable here: the hosted behaviour of any deployment (none exists), Treasury's current listing (403), and anything that
needs a Stats NZ request.
