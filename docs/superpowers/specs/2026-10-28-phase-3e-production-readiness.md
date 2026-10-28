# Phase 3E: Economic Outlook production readiness

Date: 2026-10-28. Branch `feat/phase-3e-production-readiness` from `main` at `8e4aa8b` (PRs #14 and #15 merged).
Status: offline implementation and verification complete; nothing activated, deployed, spent or published.

## 1. Go / no-go

| Decision | Recommendation | Why |
|---|---|---|
| Private preview of the Economic Outlook **with real research** | **No-go** | No institution has any recorded permission. The Treasury's licence page has never been read directly (HTTP 403 to automated readers), so nothing can be stored, summarised or shown. |
| Stats NZ dashboard and its static Netlify site | **Go for a draft deploy** once the Netlify checklist is done | The real-database snapshot is byte-identical between `main` and this branch and validates for publication; research is never in a snapshot. |
| Merge this branch | **Go after review**, with the caveat that CI cannot run | All local CI-equivalent checks pass (section 7). GitHub Actions has been blocked by account billing since 2026-10-24, so no hosted check has run. |
| First real research pilot (Treasury) | **Ready to start once the owner unblocks B2 and B3** | The tooling now supports both a crawler pilot and a permission-compliant manual import, each behind its own recorded approval. |

## 2. What was reviewed

`CLAUDE.md`; the Phase 3A to 3D specs, plans and runbooks (`docs/data-sources/research.md`, `docs/cpi-release-runbook.md`,
`docs/netlify-deployment.md`); `config/research_sources.toml`; the research package, store, migrations, CLI and API; CI
(`.github/workflows/ci.yml`), `Dockerfile`, `docker-compose.yml`, `netlify.toml`; the Actions run history (`gh run list`,
check-run annotations); and a read-only copy of the real database (`data/nzstats.db`, copied with SQLite's online
backup; the live file's SHA-256 was checked unchanged afterwards).

Open PRs: none. Worktrees: `phase-4b-dashboard-ux` holds uncommitted, unrelated dashboard UX work and was not touched.

## 3. Production-readiness matrix

| Area | State | Evidence | Rating |
|---|---|---|---|
| Source permissions | Every source `needs_review` or `restricted`; `llm_processing = denied`, `public_display = none`, `manual_import = denied` everywhere | `research readiness` on the real registry: 0 of 4 gates for all ten | Blocked (owner) |
| Source accessibility | Treasury `/publications`, `/sitemap.xml` and the licence page refused automated readers (403); RBNZ restricted; ANZ terms forbid display; ASB robots disallows its PDF folder; Westpac 403 | 3A/3D records in `research.md` | Blocked for crawling; manual import now possible per source |
| Institutional research availability | Zero publications, versions or summaries stored | `research health` on the DB copy | Blocked |
| LLM provider | None configured; no paid-call approval; no budget given | `NZSTATS_LLM_PROVIDER` unset | Blocked (owner) |
| Research extraction quality | Heuristic grading exists (`research quality`) but has only seen synthetic text | 3D-A tests | Untested on real documents |
| Summary accuracy and human review | Deterministic verifier (26 rules), append-only review and publication; replay metrics are synthetic only | `RECORDED_BASELINE` | Ready mechanically; no real evaluation |
| Official data and vintages | 43 published releases; CPI holds **one** release vintage (September 2026 quarter). Earlier quarters' "first-published" values are the earliest stored, correctly labelled | `research cpi-vintages` on the DB copy | Partial (backfill needs approval) |
| Public API and licensing controls | Research routes off unless `NZSTATS_PUBLIC_RESEARCH=1`; one re-verifying gate; **no authentication**; Compose publishes port 8000 on every host interface | `api.py`, `docker-compose.yml` | Safe only while off; preview must be loopback or behind an authenticating proxy |
| Netlify deployment | Publisher, validator and parity specs exist; first deploy never done | `docs/netlify-deployment.md` | Ready for a draft deploy (owner) |
| CI | Every run since 2026-10-24 00:33 UTC fails in 3 to 5 s with zero steps: "The job was not started because recent account payments have failed or your spending limit needs to be increased." Latest: run 40605431393 (`main`, 2026-10-27 23:55 UTC) | `gh run view`, check-run annotations | Blocked (billing) |
| Docker | No container runtime on this machine (Docker CLI only, no daemon, no Colima/OrbStack/Podman); image and smoke test not run | `docker info` | Not verified |
| Operational monitoring | Stats NZ health existed; research had only per-run health. Now `research health` (exit 1 on attention), rolling model budget, backup verification | this branch | Ready |

## 4. Blocker register

| ID | Blocker | Owner | Required action | Unblocks |
|---|---|---|---|---|
| B1 | GitHub Actions blocked by account billing | Kevin | Settings, Billing and plans: fix the failed payment or raise the spending limit. Then re-run CI on this PR and watch the first run on the Ubuntu 26 image (`playwright install --with-deps` is the likeliest casualty). | Hosted CI, Docker job |
| B2 | Treasury terms never read directly | Kevin | Read `https://www.treasury.govt.nz/copyright-and-licensing` in a browser. Record what it says about automated access, storage, third-party (model) processing and republication, and any exclusions (third-party data, logos), in `licence` and `access_notes`; set `terms_evidence = "direct"`. | Every Treasury gate |
| B3 | Treasury automated access refused (403) | Kevin | Choose one route. **Crawler:** authorise one discovery probe with the project User-Agent (`scripts/run.sh research discover treasury`); stop if refused. **Manual import:** if the terms permit storing a copy, set `manual_import = "approved"` with its three approval fields and `content_policy = "full_text"`. | Storage (gate 2) |
| B4 | No LLM provider, budget or paid-call approval | Kevin | Prefer a local model first (`llm_processing = "local_only"`, loopback `openai_compatible`, prices 0). For a hosted model: `llm_processing = "hosted"` with the terms' basis in `llm_processing_note`, explicit approval of paid calls, and `NZSTATS_LLM_MAX_RUN_USD` and `NZSTATS_LLM_MAX_PERIOD_USD` set. | Summaries, real evaluation |
| B5 | No independent annotation of real documents | Kevin (or a named annotator) | Annotate the two or three pilot documents in `data/annotations/treasury.json` **before** reading the model's output. | Precision, recall, citation scores |
| B6 | No public display decision | Kevin | After review: `public_display = "link_only"` with its approval fields, then per-summary `research publish`. | Preview or public display |
| B7 | API has no authentication; Compose binds `8000:8000` on all interfaces | Kevin | Keep `NZSTATS_PUBLIC_RESEARCH` unset on any reachable host. For a preview, run on loopback (`nzstats serve --host 127.0.0.1`) or change the published port to `127.0.0.1:8000:8000`, or put an authenticating reverse proxy in front. Not changed here: it is a deployment setting. | Safe private preview |
| B8 | CPI first releases before September 2026 not stored | Kevin | Approve one throttled backfill (section 6). | Genuine first-published baselines for 2025-12 to 2026-06 |
| B9 | Docker image not built or smoke-tested since 3B | Kevin | On a Docker host: `docker build -t nzstats:ci . && bash scripts/smoke_docker.sh nzstats:ci && docker build -f Dockerfile.publisher -t nzstats-publisher:ci .`, or restore CI (B1). | Container release |
| B10 | Netlify first deployment pending | Kevin | Follow `docs/netlify-deployment.md` (site, token, `PUBLISH_ENABLED=1`, draft deploy first). | Public static site |

## 5. What this phase adds (offline, tested)

1. **Manual document import** (`nzstats research import KEY FILE --url --importer --note [--published-on] [--title]
   [--series]`). A new, separately recorded permission, `manual_import = "approved"`, with `manual_import_approved_by`,
   `_on` and `_note`. The loader refuses it without `content_policy = "full_text"`, `terms_evidence = "direct"` and
   allowed hosts, and for a `restricted` source. It never grants automated access: the crawler stays refused. No request
   is made; the document address must pass the institution's URL policy (https, allowed host and path, not blocked), so
   only approved source URLs are recorded. The file goes through the crawler's extraction, wall and challenge
   detection, minimum length and shrink guard, and its store (content-addressed raw bytes, versions, sections, pages).
   Migration 008 adds `research_document_version.acquisition` (`crawler` or `manual`) and an append-only
   `research_manual_import` audit log (who, when, hashes, format, outcome, the permissions in force, a private note),
   written in the same transaction as the version. Possession of a file is never treated as permission.
2. **Separate approvals, end to end.** `Institution.source_permitted` (crawler approval or manual import) now gates LLM
   processing and display, so an imported document still needs `llm_processing`, `public_display`, human review and a
   publish decision, each recorded separately. Revoking any of them withholds the item on the next request.
3. **Research health** (`nzstats research health [--json]`): routes, crawler state and repeated failures, staleness
   against an optional `expected_publication_days`, unsummarised versions, summaries awaiting review or a publication
   decision, poor extractions, published summaries that the public gate now withholds (revocation or drift), 30-day
   model spend against its cap, and the API switch. No names, notes or document text. Exit 1 when attention is needed.
4. **Bounded processing budget.** On top of the per-run worst-case budget, a rolling 30-day cap
   (`NZSTATS_LLM_MAX_PERIOD_USD`, default $10) counts every recorded call, failed ones included; each run may spend only
   what the window has left, and the run record stores the cap and the remainder.
5. **CPI vintage audit** (`nzstats research cpi-vintages`) and an independent oracle test (below).
6. **Backup and restore validation** (`nzstats verify-backup PATH [--live DB] [--raw-dir DIR]`); `nzstats backup` now
   verifies its own copy and exits 1 if it fails.
7. **Runbooks**: manual import, reviewer workflow, source onboarding, health monitoring, withdrawal, backup and restore
   (`docs/data-sources/research.md`, `README.md`), CPI backfill (`docs/cpi-release-runbook.md`).

Tests added: 38 manual import (registry rules, provenance, versions, URL policy, walls, formats, size, PDF pages,
append-only audit, LLM eligibility, revocation through the gate and the API, approvals scoped to acquisition), 9 health, 3 readiness, 4 CLI (import,
health), 3 summarise and provider (rolling cap), 15 CPI oracle and coverage, 8 backup verification, 1 migration 008
rollback.

An automated security review of the first commits found that `source_permitted` let a manual-import approval keep
crawled versions usable after the crawler approval was revoked. Fixed in `bf1996d`: each approval now covers only the
versions it let in (`Institution.holds(acquisition)`), with failing-first tests in both directions.

An independent code review of the whole diff (security, licensing, statistics, operations) then found no critical or
high issue after that fix, and confirmed: no gate widened beyond intent, no new field reaches the API or snapshot, the
audit row is atomic with the version, revocation is immediate, the oracle is independent, and the backup check never
writes the copy. Its medium and low findings, fixed with failing-first tests: spend recorded only on an aborted run now
counts toward the 30-day cap; `verify-backup` fails when a non-empty `-wal` sits beside the copy and reports an
unreadable `--live` database instead of crashing; a parser crash on a hostile import file is a refusal; re-importing
text the crawler stored first warns `stored_by_crawler` (it stays under the crawler approval); and a failing audit
insert is shown to roll the version back. Accepted as follow-ups (section 11): concurrent summarise runs, a targeted
purge of imported copies, and the reviewer's labelling notes.

## 6. Historical data readiness

**Finding.** The production database holds exactly one CPI release vintage: the September 2026 quarter (published
2026-10-22 10:45 NZDT, captured 21:04 NZDT, one bundle). Every earlier quarter's "first-published" value is therefore
the value printed in the September 2026 release, the earliest stored, not the original release. The code already labels
it so (`first_release = false`, "earliest stored"), and nothing manufactures an earlier vintage.

**How much it matters.** Annual and annual average change use the unadjusted index, which Stats NZ does not revise:
across the four real release files held as fixtures (December 2025 to September 2026) every unadjusted index value is
identical in each later file. So for those measures the earliest stored value equals the first-published one. The
seasonally adjusted index is re-estimated every quarter (the files differ), so a seasonally adjusted quarterly change
from the earliest stored release is not the first-published figure. That is now asserted by a test on the real files.

**Independent verification.** `tests/research/test_outcomes_oracle.py` parses the official CSVs with the csv module and
Decimal, without the adapter, database or `outcomes.compute`, and checks all four measures for all four quarters:
first-published from each quarter's own release, latest from the newest, and the earliest-stored labelling when only the
newest release is stored. A further test ingests the releases out of order (September first, then the older ones, as a
backfill would) and gets the in-order result: release order, not ingestion order, decides.

**Backfill plan (needs approval: it contacts stats.govt.nz).** The real release files for December 2025, March 2026 and
June 2026 parse with the current adapter (they are the fixtures). One run:

```sh
scripts/backup.sh   # or: scripts/run.sh backup data/backups/before-cpi-backfill.db
scripts/run.sh backfill --series-slug consumers-price-index --since 2025-12 --until 2026-06
scripts/run.sh research cpi-vintages
```

Roughly 11 calendar-month pages plus about 5 files per release, about 26 requests, at least four and a half minutes at
the 10 second floor, sequential. Older quarters (before December 2025) need a vintage-depth probe first, like
`scripts/probe_vintages.py` for migration, because the file layout may differ; until then they stay "earliest stored".
GDP, labour-market and OCR data are separate official-source integrations and are not in this release.

## 7. Verification evidence (this machine, 2026-10-28)

| Check | Result |
|---|---|
| Backend `pytest` (Python 3.14 venv; CI uses 3.12) | 2414 passed |
| `ruff check .`, `ruff format --check .` | clean |
| Frontend `npm test`, `typecheck`, `lint`, `build` | 458 passed; clean; existing fast-refresh warnings only; built |
| `npm run gen:api` | no change to `src/api/schema.d.ts` (no API model changed) |
| Playwright live; research (synthetic); static site incl. visual parity | 108 passed; 18 passed, 3 screenshot captures skipped; 252 passed |
| Real-DB copy: `migrate` | schema 7 to 8 applied cleanly |
| Real-DB copy: `verify-backup --raw-dir data/raw` | ok: schema 8, 54,012 rows in 23 tables, no missing raw artifact |
| Real-DB snapshot, `main` versus branch (`--now` fixed) | byte-identical, id `7be455c2b866`, 216 files, 43 releases; `validate-snapshot --for-publish` valid |
| Live `data/nzstats.db` | SHA-256 unchanged after the audit |
| Docker build and smoke | not run (no runtime) |
| GitHub Actions | not run (billing) |

## 8. First-source activation status

Not activated. The Treasury remains the only candidate that could plausibly satisfy all four decisions (Crown copyright,
CC BY 4.0 per a search summary, published forecast tables), but the evidence is still indirect. No request was made to
any institution in this phase, and no permission setting was changed. RBNZ stays `restricted`.

## 9. Real-model evaluation

Not run. There is no authorised document, provider or budget. The protocol is ready: annotate first (B5), then
`research summarise treasury --dry-run`, a bounded run, `research evaluate --annotations data/annotations/treasury.json`,
with metrics, model, prompt version, tokens, cost and latency recorded in `docs/progress.md` under a "real documents,
real model" heading, never alongside the synthetic replay baseline.

## 10. Controlled publication

**Access controls today.** Research routes serve only publication-approved, re-verified summaries, but the API has no
authentication. The real risk is configuration: Compose publishes `8000:8000` on every interface, so setting
`NZSTATS_PUBLIC_RESEARCH=1` in `.env` on a NAS would expose research to the LAN, or further if the port is forwarded.

**Private preview procedure (when B2 to B6 are done).** On the owner's machine only: back up, `nzstats serve --host
127.0.0.1 --no-scheduler` with `NZSTATS_PUBLIC_RESEARCH=1` and `NZSTATS_STATIC_DIR=../frontend/dist`, open
`/economic-outlook`, then stop. A remote preview needs an authenticating reverse proxy or a private network (for
example Tailscale) in front, never a bare published port.

**Optional static research publication: design only, not built, not enabled.**

- Opt-in per export: `nzstats export-snapshot --include-research` plus `NZSTATS_PUBLISH_RESEARCH=1`; without both, the
  snapshot stays as now. A per-source allowlist (`static_display = true`, its own approval fields) on top of
  `public_display`, so showing research on a CDN is a separate decision from serving it from the app.
- Built only from `public.public_summaries` at export time, then re-verified by `validate-snapshot` against the registry
  and database (the same gate run twice), with new, closed snapshot kinds (`research_feed`, `research_item`), the
  existing allowlist output models, and a schema check that rejects any field not in them: no raw report text, document
  sections, reviewer or approver names, notes, internal paths, provider parameters, usage or cost.
- Document links only on the institution's allowed hosts; quotes only at `excerpt`.
- Atomic, validated snapshots as today (staged directory, content id, rename); withdrawal = `research withdraw` then an
  immediate forced republish (`publish-site --force`); a withdrawn or revoked item must be absent from the next snapshot,
  tested by a parity spec, and the previous deploy can be rolled forward, never back, past a withdrawal.

## 11. Residual risks

- A manually imported file is trusted to be the document at the stated URL; the tool cannot check that without a
  request. The importer's name and note are the accountability, and the audit log is append-only.
- `data/raw` now holds files that cannot be re-fetched (manual imports). Backups must include it (`README.md`).
- Revoking a permission stops processing and display but does not delete stored text; the rollback and deletion steps
  are in `research.md`.
- Heuristic wall detection and extraction grading are untested on real Treasury documents.
- Budget: two summarise processes started together each read the remaining 30-day budget once, so together they can
  spend up to twice it; a process killed outright records no spend for its last document. Run summarise from one
  place at a time (a lock or reservation row is the follow-up).
- No targeted purge: deleting imported copies after a licence is withdrawn needs the full research rollback today (a
  purge of `acquisition = 'manual'` versions and their raw files is the follow-up). A `duplicate` import leaves its raw
  file unreferenced.
- The import URL is the importer's statement; its query string is kept in the document address.
- "First release" means the earliest stored bundle of that quarter's own release, which could be a correction if the
  original was never stored; `cpi-vintages` checks the unadjusted series only.
