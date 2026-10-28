# Phase 3F: Economic intelligence pilot and release acceptance

Date: 2026-10-28. Branch `feat/phase-3f-pilot-acceptance` from `main` at `2fab229` (Phases 3A to 3E and 4B merged).
Status: hardening, tooling and offline verification complete. **The real-data pilot did not start**: no institution has a
recorded permission, and none was invented. Nothing was activated, deployed, spent or published; no request was made to
any institution, to stats.govt.nz, or to a model provider; no permission setting was changed.

## 1. Recommendation

| Decision | Recommendation | Why |
|---|---|---|
| Merge this branch | **GO WITH CONDITIONS** | Every local CI-equivalent check passes (section 6) and the 3E residual risks it targeted are closed with failing-first tests. Conditions: hosted CI has never run on it (B1), so say so in the PR; take a backup of the live database before the first start of the new code (it applies migrations 8, 9 and 10: the live database is at schema 7). |
| Real-data research pilot (Treasury or any source) | **NO-GO until B2 to B5 are done** | Gate 1 to 4 are 0 of 4 for all ten sources. The Treasury's licence page has still never been read by a person on record; automated readers get 403. Nothing may be stored, summarised or shown, and the evaluation needs an independent annotation first. |
| Private research preview on the owner's machine | **GO WITH CONDITIONS** once a source is permitted and reviewed | The server now refuses to publish research on anything but loopback unless the operator overrides it explicitly (B7 mitigated in code). |
| Stats NZ-only draft Netlify deployment | **GO WITH CONDITIONS** | Local static-site checks pass (270 specs) and the real-data snapshot is byte-identical to `main`'s and valid for publication. Conditions: the owner supplies the site and token, sets `PUBLISH_ENABLED=1` and deploys a draft first (B10). |
| CPI release-vintage backfill, December 2025 to June 2026 | **GO WITH CONDITIONS (owner approval)** | Tooling to verify it exists and was run on the current data. Conditions: back up, approve about 26 sequential requests (at least 4.5 minutes at the 10 second floor), run `research cpi-reconcile` before and after. |
| Public research (static or live) | **NO-GO** | No display permission, no reviewed summary; the static site excludes research by design. |

## 2. Baseline (re-checked 2026-10-28)

Read: `CLAUDE.md`, the Phase 3E report and blocker register, the research and CPI runbooks, `main` (`2fab229`), open PRs
(**none**), the Actions history, the registry. Worktrees `phase-1`, `phase-3d-b`, `phase-4b-dashboard-ux` and
`phase-4b-dashboard-ux-integrated` are older, merged or unrelated and were not touched.

| ID | Blocker | State on 2026-10-28 | Evidence | Next owner action |
|---|---|---|---|---|
| B1 | GitHub Actions blocked by billing | **Open, unchanged** | Latest run 40634680122 (`main`, 04:51 UTC) failed in 4 s with zero steps: "The job was not started because recent account payments have failed or your spending limit needs to be increased." | Fix billing; re-run CI on this PR; watch the first Ubuntu run (`playwright install --with-deps`). |
| B2 | Treasury terms never read directly | **Open, unchanged** | `research readiness`: `terms_evidence: search`, 0 of 4 gates. Not retried: automated readers are refused (403) and bypassing that is out of bounds. | Read `https://www.treasury.govt.nz/copyright-and-licensing` in a browser and record it. |
| B3 | Treasury automated access refused | **Open, unchanged** | As above. Manual import is built and tested but `manual_import = "denied"`. | Choose crawler probe or manual import (needs B2). |
| B4 | No LLM provider, budget or paid-call approval | **Open, unchanged** | `NZSTATS_LLM_PROVIDER` unset; every source `llm_processing = denied`. | Prefer a local model; or a hosted one with caps set. |
| B5 | No independent annotation | **Open, unchanged** | No `data/annotations/` file. | Annotate two or three pilot documents before reading model output. |
| B6 | No public display decision | **Open, unchanged** | Every source `public_display = none`. | After review. |
| B7 | API unauthenticated, Compose binds all interfaces | **Mitigated in code** | `nzstats serve` exits 2 for `NZSTATS_PUBLIC_RESEARCH=1` on any non-loopback address (`research/api.py: bind_refusal`; `tests/research/test_bind_guard.py`). The Compose file is unchanged: with research off, behaviour is as before. | Keep research off on shared hosts; for a preview use `--host 127.0.0.1`. |
| B8 | CPI first releases before September 2026 not stored | **Open; tooling ready** | `research cpi-vintages`: one vintage (2026-09). `research cpi-reconcile` on a copy of the live data: 2 vintages reproduced exactly by kept official files, 1,607 outcomes checked, no discrepancy. | Approve the throttled backfill (section 5). |
| B9 | Docker image not built or smoke-tested | **Open, unchanged** | Docker CLI 29.6.2 only; `docker info`: cannot connect to `/var/run/docker.sock`; no Colima, OrbStack or Podman. | A Docker host, or B1 fixed (CI builds both images). |
| B10 | Netlify first deployment pending | **Open; checks done** | Section 6. | Site, token, `PUBLISH_ENABLED=1`, draft deploy. |
| new | Live database is at schema 7, not 8 | **Noted** | `schema_version` max 7 on the live file; a copy migrated 7 to 10 cleanly and passed `verify-backup`. | Back up first; the first start of new code applies 8, 9, 10. |

Production-readiness matrix (changes from 3E marked):

| Area | State | Rating |
|---|---|---|
| Source permissions | 0 of 4 gates for all ten sources | Blocked (owner) |
| Institutional research availability | Zero publications, versions or summaries stored (live and copy) | Blocked |
| Research extraction quality / summary accuracy on real documents | Never measured: no authorised document | Untested |
| LLM spend control | **Concurrency-safe reservations, interrupted-call accounting, health reporting (new)** | Ready, offline-verified |
| Source retention and withdrawal | **Targeted purge, tombstones, resumable file step, orphan detection (new)** | Ready, offline-verified; older backups are outside its reach |
| Official data and vintages | One CPI vintage; **independent reconciliation tool (new)** run on it, clean | Partial (backfill needs approval) |
| Public API access control | **Loopback-only guard (new)**; still no authentication | Safe by default; override is explicit |
| Netlify | Static checks pass; first deploy not done | Ready for a draft (owner) |
| CI | Hosted: blocked. Local equivalents: all pass | Blocked (billing) |
| Docker | Not built | Not verified |

## 3. Production hardening (all tests failed first)

**3.1 Concurrency-safe model spend (migration 009, `research_llm_reservation`).** Before each provider call the worst-case
cost is reserved under `BEGIN IMMEDIATE`, in the same transaction that checks the rolling 30-day total (settled actuals plus
every held or abandoned reservation) against the cap. Two processes started together with room for one call: the second is
refused (`budget_exhausted`) and never contacts the provider. The reservation is settled to the actual cost the moment the
call returns, before the result is stored, so a failure while storing keeps the true cost. Tests: two threads racing for the
last of the budget; a real child process killed with `os._exit` mid-call (a `held` reservation that keeps counting, then
`abandoned` by the next run once no live call could hold it); an interrupt (`KeyboardInterrupt`) abandoned at once and
recorded on the run; a storage failure after the response; failures billed at zero, at the reported usage or at the worst
case; append-only, forward-only triggers; legacy runs without reservations counted as before. `research health` reports
`unsettled_model_calls` for any call of unknown outcome. Spend is therefore never undercounted by a crash; the cost of that
is that an interrupted call blocks its worst case for up to 30 days unless the cap is raised after checking the provider's
billing.

**3.2 Targeted purge and orphan prevention (migration 010, `research/purge.py`).** `research purge KEY --acquisition
manual|crawler|all` or `--version N`: a dry-run plan by default, `--apply` with a reason, a name and a note. Removes the
text, the derived model output, the claims and the raw files (including unlinked byte variants of the same document
address), withdraws published summaries; keeps version tombstones with hashes, summary rows with placeholders, and every
append-only log. Two steps because files cannot join a transaction; the file step is resumable and idempotent. Deleted
content is overwritten and the WAL truncated (a test searches the database files for a sentinel and finds none). Purged
text cannot be stored again, through import or crawl, under any address. Failure injection: database-step failure changes
nothing; file-removal failure leaves a pending record that health reports and `--finish` completes; file already missing;
file shared by another record is kept; a tampered stored path is never followed; Stats NZ files are never touched. Orphan
prevention: a duplicate or rolled-back store removes the file it just wrote; a manual re-import with different bytes keeps no
unlinked copy; `research orphans` lists stray files (older than an hour, to avoid a file mid-write) and missing ones.

**3.3 Loopback-only research.** See B7. Tested for IPv4, IPv6, mapped, wildcard, empty and named hosts, for the exact override value, and for `nzstats serve` exiting 2 before uvicorn starts.

**3.4 Lifecycle acceptance test** (`test_acceptance.py`): through the real API, a published summary follows each decision on
the very next request: revocation hides it, restoring brings it back (nothing was deleted), withdrawal hides it, republication
shows it, purge removes it for good; no response ever contains document text, model output, names or notes. It also records
the one thing a purge cannot do: a backup taken earlier still holds the text.

## 4. Real-data pilot

**Stopped at the permission gate, as required.** `research readiness` on the real registry: all ten sources 0 of 4. The first
blocker for the Treasury is "needs review: no recorded approval; the terms have not been read directly". No request was made
to the Treasury or any institution; the refused 403 was not retried or worked around. Nothing was stored, summarised or
evaluated, so there is **no real-data quality report** and no accuracy figure; the synthetic replay baseline remains the only
number and must not be read as real accuracy.

What is ready for the day the owner unblocks B2 to B5: the manual import and crawler routes, the readiness tool, the
annotation format, `research evaluate`, `research quality`, the bounded budget and the purge to undo it. The protocol is
unchanged (3E section 9): annotate first, `summarise --dry-run`, a bounded run, `research evaluate`, record the result under
"real documents, real model" in `docs/progress.md`. A suggested acceptance bar, for the owner to confirm before the run, not a
claim: zero verifier errors on approved summaries, every forecast value matches the annotation exactly, every cited quote is
found in the stated section, and any miss is written up before a second batch.

## 5. Official statistics

Not backfilled (it contacts stats.govt.nz). Prepared and checked offline:

- `scripts/backup.sh`, then `scripts/run.sh backfill --series-slug consumers-price-index --since 2025-12 --until 2026-06`,
  then `research cpi-vintages` and `research cpi-reconcile`. About 26 sequential requests, at least 4.5 minutes.
- `research cpi-reconcile` (new) checks, with no request and independently of the adapter and the outcome code, that every
  stored all-groups index vintage is reproduced exactly by an official file kept under `data/raw` and that the reported
  first-published and latest outcomes equal values computed from those files (rounded half away from zero to one decimal).
  **Baseline on the current data: 2 vintages reproduced, 1,607 outcomes checked, no discrepancies; the only genuine first
  release is 2026-09.** Seven tests on the real December 2025 to September 2026 files: in-order and out-of-order backfills
  reconcile alike; a changed stored value, a missing file and a non-series file are each caught.
- Expectation for the real backfill (from the four real files): the unadjusted index is identical across releases, so annual
  and annual-average changes will equal the earliest stored values; the seasonally adjusted index is re-estimated each
  quarter, so December 2025, March 2026 and June 2026 will gain genuine first-published values that differ from today's
  earliest-stored ones for the seasonally adjusted quarterly change. Any other difference is a defect to investigate.

## 6. Verification evidence (this machine, 2026-10-28)

| Check | Result |
|---|---|
| Hosted CI | **Not run**: billing (B1). Local results below are not hosted CI. |
| Backend `pytest` (Python 3.14 venv; CI uses 3.12) | 2512 passed (was 2414 in 3E; 98 new) |
| `ruff check .`, `ruff format --check .` | clean |
| Frontend `npm audit --audit-level=low` | no findings |
| `npm run gen:api` | no change to `src/api/schema.d.ts` |
| Frontend typecheck, lint, tests, build | clean; lint shows existing fast-refresh warnings only; tests and build pass |
| Playwright live; research (synthetic data); static site incl. visual parity | 126 passed; 18 passed, 3 screenshot captures skipped; 270 passed |
| Docker build and smoke (application and publisher images) | **Not run**: no container runtime (B9) |
| Live database copy (online backup of `data/nzstats.db`, schema 7) | `migrate`: 7 to 10 clean; `verify-backup --raw-dir`: ok, 54,014 rows in 26 tables |
| `research readiness`, `health`, `cpi-vintages`, `cpi-reconcile`, `orphans` on the copy | 0 of 4 gates everywhere; all gated; one vintage; reconciled with no discrepancies; 0 orphans |
| Snapshot of the copy, `main` code versus this branch, same `--now` | byte-identical (`diff -r`), id `7be455c2b866`, 216 files, 43 releases; `validate-snapshot --for-publish` valid; no research content in it |
| Live `data/nzstats.db` SHA-256 before and after | unchanged (`6a85d50a…`) |
| Draft Netlify deploy | **Not done**: needs the owner's authorisation and token (B10) |

## 7. Security and statistical review

An independent reviewer (separate agent, read-only, security and data-integrity brief) read the three feature commits. No
critical issue. Every finding below was reproduced or reasoned, then fixed with a failing-first test unless marked.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | High | A `summarise` call in flight when a purge commits could still store a summary, raw output and claims for the purged text (migration 010 blocked only sections and publication). | Triggers refuse new summaries and claims for a purged version; the summariser records outcome `purged` (the call was billed and settled, its output refused). |
| 2 | Medium | `wal_checkpoint(TRUNCATE)` reports a busy log instead of failing, so a held reader left old pages in the database files while the purge claimed success. | The result is checked (busy timeout lifted, retried); `PurgeResult.wal_truncated`, a CLI warning and exit 1; `purge --finish` retries. |
| 3 | Medium | The purged-text gate ran before the write lock (a purge committing between check and store); matched only the text hash (a changed extractor got the same bytes through); and refused a surviving publication holding the same text. | Re-checked inside the transaction; matches the file hash too; a publication that still holds the text in an unpurged version is not refused. |
| 4 | Medium | A run with a shorter timeout abandoned another process's still-live reservation, whose later `settle` then raised and discarded a billed result. | Each reservation carries its own deadline (`expires_at`); `settle` of an already abandoned reservation is a no-op that leaves it at its worst case. |
| 5 | Medium-low | `cpi-reconcile` reported success with no vintages or outcomes. | Nothing to check is a discrepancy. Also noted and accepted: first/latest selection mirrors the outcome code, so the independent parts are the file fidelity and the arithmetic. |
| 6 | Low | The orphan sweep could unlink non-artifact names; the "newly created" test for discarding a file is racy. | The sweep only considers artifact names and temp files older than an hour. The discard race (two processes saving identical bytes) is accepted: the result is at worst a missing file, which `research orphans` reports as a problem. |
| 7 | Low | `unsafe_path` purge artifacts looked finished. | The integrity check and health report them. |
| 8 | Low | An acquisition-scoped purge could include versions added after the plan. | Refused if the selection changed since the plan. Accepted: byte variants fetched under a different address are not found by the address sweep. |
| 9 | Low | The crawler logged a traceback and counted a failure each run for a purged document. | Recorded as `skipped_purged`, no traceback. Accepted: it still requests the page, because only a fetch can show whether the text was revised. |
| 10 | Low | Human-written review and publication notes are kept and could quote the text. | Accepted and documented: audit notes are not redacted; reviewers should not paste source text into them. |

Sound, per the reviewer: the budget arithmetic (no double counting, legacy runs, window edges, outer transactions), the
placeholder-only redaction triggers, path safety, SQL construction, the public and API gates, and the loopback guard (no
bypass found; it errs only towards refusing unusual spellings such as `127.1`).

**Statistical review.** The CPI arithmetic in `cpi_reconcile` uses Decimal and half-away-from-zero rounding to one decimal and
the same quarter-back and annual-average definitions as the outcome code, so agreement is a real test of the stored values and
the adapter, not a tautology. On the current data it reproduces both stored vintages exactly and all 1,607 outcomes. What it
cannot do is test the first/latest selection logic independently, and the unadjusted index being unrevised is shown only on
four real files. No forecast-accuracy statistic exists for real documents; none should be quoted.


## 8. Residual risks

- A backup taken before a purge still holds the purged content; expire backups when a permission is withdrawn (stated in the
  runbook and the CLI output, and recorded by a test).
- The reservation is the worst case under an estimate of the input size; a provider reporting more tokens than estimated
  settles above the reservation, so the cap can be exceeded by at most that underestimate per call.
- Purge file removal is not atomic with the database step; `research purge --finish` and health cover the gap. Crawling a purged page still makes a request each run.
- An interrupted call holds its worst case for up to 30 days. Intended: unknown is not free.
- A purge blocks the exact purged text for that institution for good; re-storing it would need a deliberate database
  change by the owner. There is no `unpurge` on purpose.
- Publication metadata (title, address) remains after a purge, as does the version title; only text, derived output and
  files are removed.
- The loopback guard is a start-up check: it cannot see a proxy or port mapping in front of a loopback listener, which is
  why the override exists and is documented, not automatic.
- Everything in section 4 and the Docker and hosted-CI rows of section 6 is unverified.
