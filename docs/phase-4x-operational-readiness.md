# Phase 4X: operational activation and first new-report readiness

7 November 2026, Pacific/Auckland. Baseline main `b5bf3c1` (PR #51 merged; `origin/main` identical after a safe fetch).
Codes, counts, hashes and structure only: no Treasury text, model output, key or private absolute path.
**No OpenRouter request (not even a key or model probe), no report acquisition, no paid inference, no source-permission
change, no historical record change, no commit, push, merge or deployment.** Private evidence (logs, backup, restore, policy,
UI copy, screenshots) is under ignored `data/phase-4x/` (directory mode 0700, files 0600).

**Follow-up, 8 November 2026:** the owner approved the section 4 registry lines ("yes" to the parent's exact question, 2026-11-08
Pacific/Auckland), and the two lines were applied. The user then separately authorised commit, push and a pull request on
2026-11-08: the registry change and the generic `research summarise` guard are **submitted together for review in one PR**. Sections 1 to 3, the 7 November parts of sections 6
and 7, and sections 9 and 10 (except their 8 November rows) are the **historical pre-approval record**: Treasury was `denied`
then. Still no paid inference, provider probe, `--confirm`, reservation, import, display or publication change.

## Verdict: GO WITH CONDITIONS

GO for the operator workflow on the next **real** Treasury FEU. **NO-GO for any paid request now**: no new report is held, the
current Treasury report (version 3) is permanently ineligible (version 1, also held, is spent too), and no paid processing is
authorised in Phase 4X. Not GO for unattended or automatic use (out of scope by design).

Rights: **approved by the owner 2026-11-08 and applied locally** (section 4). Conditions, in order: (1) the registry change and
this phase's generic `research summarise` guard are reviewed and integrated **together** (the guard must not land after the
registry change; both are in the same PR); (2) the next FEU is saved by the owner in a browser and passes the per-report rights
checks (section 4); (3) the runbook below runs in a real terminal, with its typed confirmation.

## 1. Before-state and the migration-014 finding

| | Live database before this phase |
|---|---|
| File SHA-256 | `1fd02a03…94b71cd` (unchanged by every read in this phase) |
| Schema | versions 1 to 14, 33 tables, 80,501 rows; `integrity_check` ok, 0 foreign-key violations |
| Raw tree | 48 files, every one referenced by `raw_artifact` and named by its own hash |
| Research | 3 document versions, 4 summaries, 4 reservations (all `settled`), 3 runs, 4 usage rows, 0 policy events |

**Migration 014 was already present at baseline**, before this phase's backup and rehearsal. Its origin is inferred, not
recorded: `nzstats serve`, `health`, `backup` and `alert-check` apply pending migrations at startup, and the `ops_process` record
shows an on-open `serve` that started 22:32:59 NZDT (after main reached `b5bf3c1`, merged 21:21 NZDT) and stopped cleanly 56 s
later, matching the database file time. That earlier `serve` is the **likely** origin. `schema_version` keeps no timestamp, so
this is not proven. No contemporaneous post-v3, pre-014 backup was found under `data/` (the Phase 4T pre-execution bundle is
schema 13 but predates the v3 request). The checks below prove that 014's structure is additive and that rolling it back on a
copy loses nothing. Without pre-014 copies of the post-v3 rows they cannot independently prove what happened during the earlier
real migration; the baseline-to-final checks cover only this phase. Design note, not changed here: migrations that matter should
not depend on whichever command opens the database first.

## 2. Backup, restore rehearsal, migration

All shipped tooling, run from the repository root:

| Step | Command | Result |
|---|---|---|
| Bundle | `nzstats backup --bundle data/phase-4x/backup-20261107T094142Z` | database plus 48 raw artifacts, verified, schema 14 |
| Verify | `nzstats verify-backup data/phase-4x/backup-…` | ok, schema 14, 48 raw artifacts |
| Restore | `nzstats restore-backup data/phase-4x/backup-… data/phase-4x/restore-…` (new, empty directory) | restored and verified; live database never touched |
| Restored vs live | `verify-backup …/nzstats.db --raw-dir …/raw --live data/nzstats.db` | ok, schema 14 (expected 14), 80,501 rows in 33 tables |
| Content | per-table SHA-256 over every row, schema SQL, ledger, raw tree | **33 of 33 tables identical**, schema identical, ledger identical, 48 of 48 raw files identical; bundle and restored database byte-identical (`b3c57a92…`) |
| 014 additivity | `scripts/rollback/014_research_policy_audit_down.sql` on a **separate copy** of the restore | schema 13; the 32 remaining tables identical to live; schema SQL identical to the Phase 4T schema-13 bundle; integrity ok. Shows the structure is additive and the rehearsal lost nothing; not independent proof of the earlier real migration |
| Migrate | `nzstats migrate` on live, after the rehearsal | `schema version 14`, no-op; full state snapshot identical to the baseline |

The older-schema allowance was not needed (bundle and code are both at 14).

## 3. Ledger (`nzstats research policy-audit`, read-only)

```
Lifetime ledger: 4 of 8 attempts used (policy scopes may use the last 4); US$0.6267107880 of US$5.00 spent.
Policy audit: 0 events (append-only).
```

| Reservation | Version | Experiment | Prompt | Actual (US$) | Outcome |
|---|---|---|---|---|---|
| 1 | 2 (RBNZ) | Phase 4M (untagged) | `outlook-v3` | 0.1798984440 | provider error, output truncated |
| 2 | 1 (Treasury 15 Oct) | Phase 4M (untagged) | `outlook-v3` | 0.2023797600 | provider error, invalid response |
| 3 | 1 (Treasury 15 Oct) | `phase-4n-second-pilot` | `outlook-v4` | 0.1261846080 | ok, summary 3, failed verification |
| 4 | 3 (Treasury 29 Oct) | `phase-4s-treasury-v3` | `outlook-v5` | 0.1182479760 | ok, summary 4, failed verification |
| | | | | **0.6267107880** | US$4.3732892120 left; 4 policy-scoped attempts left; no policy request ever made |

## 4. Treasury processing-rights configuration (APPROVED 2026-11-08, applied locally)

Proposed 7 November; approved by the owner on 8 November 2026 ("yes" to the parent's exact question covering these two lines and
the per-report rights checks). Applied to `config/research_sources.toml` inside `[institutions.treasury]`, after
`manual_import_note`, and submitted for review in the same PR as the guard. The only other registry edit is the header comment for `llm_processing`, which said "none
is set". Nothing else changed: not `review_status`, `content_policy`, the crawler or discovery settings, `manual_import`,
`licence`, `licence_url`, `public_display`, `private_display`, nor any other institution, including RBNZ. The pre-approval
registry (identical to main `b5bf3c1`) is kept privately under `data/phase-4x/approval-2026-11-08/`.

<!-- approved-registry:start -->
```toml
llm_processing = "hosted"
llm_processing_note = "Hosted processing confirmed by Kevin Chang on 2026-11-08 for operator-run `research run-policy` requests only (docs/phase-4x-operational-readiness.md). Basis: the Treasury copyright and licensing page, read by the owner in a browser on 2026-10-31, licenses Crown copyright material under CC BY 4.0 unless indicated otherwise for specific items or collections, with credit to the Treasury; material marked 'Copyright Held by Non-Crown Party' and government logos and emblems are excluded. The owner reads CC BY 4.0 as permitting the text of a manually imported Fortnightly Economic Update to be sent to OpenRouter for anthropic/claude-opus-5.5 on google-vertex/europe only, with zero data retention and data collection denied, to produce unreviewed internal commentary. Per document: sections with an item-specific or third-party notice are excluded, and the operator confirms that document's own notices at the terminal. Not covered: automated acquisition, public or private display, publication, RBNZ."
```
<!-- approved-registry:end -->

`backend/tests/research/test_phase_4x_readiness.py` reads this block and checks that it appears exactly once in the shipped
registry. Removing it must give back the pinned pre-approval registry (SHA-256 of the parsed file, comments ignored, equal to main
`b5bf3c1`). Against that baseline: only these two keys changed; every other Treasury field is equal; the crawler refusal, public
display `none` and private display `none` are unchanged; every other institution is unchanged, including RBNZ `denied`; and the
policy licence pin is unchanged. A mutation of any other Treasury field fails the test.

**Existing rights evidence, structure only:**

| Evidence | Where | What it supports | What it does not |
|---|---|---|---|
| Owner's browser reading of the Treasury licensing page, 2026-10-31 | registry `manual_import_note`, `licence`, `licence_url`, `terms_evidence = "direct"` | storing browser-saved copies with attribution; CC BY 4.0 default with stated exclusions | hosted processing (never recorded); automated access (the pages returned 403; crawler stays `needs_review`) |
| Phase 4K preliminary assessment | `docs/phase-4k-openrouter.md` | Crown material generally CC BY 4.0; third-party copyright excluded | "Source-specific hosted processing is not explicitly authorised"; verdict at the time: pending, refuse |
| Phase 4M owner attestation | `docs/phase-4m-owner-approval.md` | owner affirmed full retained-text rights, including third-party portions, **for Treasury version 1 only** | any other version; recorded as an attestation, not an independent licence grant |
| Phase 4Q import record of the 29 October FEU | `docs/phase-4q-treasury-feu-refresh.md` | no item-specific notice found by extraction or rendering | it records third-party content: charts and tables credit other organisations, including a commercial data vendor; Crown crest on page 1 |

**What the 8 November approval covers, and what it does not:**

- **Covers:** the two registry lines above as the Treasury hosted-processing record, used only through the bounded operator
  workflow (`research run-policy`: Treasury FEU, one call per new document, the code ceilings and the reviewed route).
- **Per-report scope (kept from the proposal):** sections with an explicit item-specific or third-party notice are excluded by
  the tripwire and cannot be named back in. Sections that only credit a source ("Source: …") are **not** excluded by code. For each
  real new report, the operator checks that document's own notices and credits, and confirms at the terminal before any request.
  A report whose rights are unclear is not run.
- **Does not cover:** a blanket attestation of rights in unidentified third-party material, or any actual new document (none is
  held). No owner rights grant beyond these lines and the per-report checks is recorded. Not covered either: automated
  acquisition, public or private display, publication, RBNZ, and any change to `licence`/`licence_url`, all of which stay as they
  were. No paid processing is authorised by the approval itself.

The licence pin covers only `licence` and `licence_url`. A rights decision that changes either one means regenerating the policy
(section 6). The approved note alone does not.

## 5. Code limits verified, and one genuine gap fixed

Each required limit is enforced in code and pinned by a named test (Phase 4W suites, all passing):

| Limit | Where enforced | Test |
|---|---|---|
| Treasury FEU only; RBNZ excluded | `InferencePolicy.institution/series` literals; `institution_mismatch`, `series_mismatch` | `test_policy.py` schema and source tests |
| 4 additional policy-scoped attempts; legacy scopes stay at 4 | `LIFETIME_ATTEMPTS = 8` for `policy-*` only, `LEGACY_LIFETIME_ATTEMPTS = 4` | `test_policy_scopes_see_a_ceiling_of_eight…`, `test_raising_the_ceiling_reopens_no_existing_experiment…` |
| US$0.50 per request, US$2 per policy, US$5 lifetime | `POLICY_MAX_PER_CALL_USD`, `POLICY_MAX_USD`, `LIFETIME_USD`; checked at dry run, freeze and execution | `test_over_the_per_call_cap…`, `test_capacity_checks_name_the_exhausted_limit`, `test_global_budget_exhaustion…` |
| One request per new content or version | `version_attempted`, `content_already_attempted`, `content_already_executed`; unique executed-content index | `test_a_version_with_any_recorded_attempt…`, `test_the_same_content_under_a_new_version_row…` |
| Window of at most 30 days, checked at call time | `_bounded` validator; window rechecked after the prompt | `test_the_validity_window_is_checked_at_call_time`, `test_a_policy_that_expires_while_the_prompt_is_open…` |
| No retries | one reservation; a provider failure consumes the attempt | `test_a_provider_failure_is_not_retried_and_consumes_the_attempt` |
| `outlook-v6` and `verify-5`, pinned by hash | `POLICY_PROMPTS`, `POLICY_VERIFIERS`, `verifier_sha256` | `test_pins_that_do_not_match_the_code_are_refused…` |

**Gap found and fixed (smallest change, failing test first).** Treasury's permission is institution-wide. Once it is `hosted`, the
older generic `nzstats research summarise` path would also accept Treasury text for a hosted provider: `anthropic`, or an
`openai_compatible` endpoint off this machine. OpenRouter alone requires a per-version consent there. That path has its own
defaults: 2 retries, US$1 per run, US$10 per 30 days, any Treasury document and no ZDR route. It is outside the policy, the US$5
lifetime ledger and the one-request rule, so it could have re-sent version 3. Granting the proposed permission would have widened
processing well beyond what is being approved.

- Fix: `research summarise` now refuses any hosted provider before a client is built (exit 2, fixed wording, nothing requested
  or recorded). Local loopback models are unchanged. Hosted processing runs only through `research run-policy` (and the existing
  consent-bound pilot runners). `backend/src/nzstats/research/cli.py`, one guard.
- Regression: `test_cli.py::test_summarise_never_sends_text_to_a_hosted_provider_even_when_the_source_permits_it` (anthropic and
  remote openai-compatible, real and dry run). It failed before the fix, because the generic path ran.
- `docs/data-sources/research.md` step 5 no longer tells an owner to run hosted `research summarise`.

## 6. Policy prepared (authorises nothing)

`nzstats research policy-init data/phase-4x/policy-treasury-feu-phase-4x.json --issued-by "Kevin Chang" --policy-id treasury-feu-phase-4x`

| | |
|---|---|
| File | `data/phase-4x/policy-treasury-feu-phase-4x.json`, mode 0600, file SHA-256 `22bbfbc9…3a52fcf2` |
| Policy hash | `6bc867b34aba4c6faac2f09f24a5e58b4dfe319f8c991f45819c1d995925563b`; ledger scope `policy-6bc867b34aba4c6f` |
| Window | 2026-11-07 22:44:25 to 2026-12-07 22:44:25 NZDT (09:44:25Z each day) |
| Limits | 4 calls, US$0.50 per call, US$2.00 aggregate |
| Pins | `outlook-v6` `addaa683…`, `verify-5` `c9660544…`, licence `b3453e1e…`; route `anthropic/claude-opus-5.5` via `google-vertex/europe`, ZDR, data collection denied, no fallbacks, low effort, 12,000 output tokens |

It is not an effective permission. On 7 November (historical, pre-approval) every dry run refused `llm_processing_denied`. On
8 November, after the approved change, the file is unchanged (mode 0600, same file hash, same policy hash), its licence,
verifier and prompt pins still match the approved registry and code, and it is valid until 2026-12-07 22:44 NZDT (log
`data/phase-4x/approval-2026-11-08/53-policy-check.log`).
Regenerate it (new file name, new id) if the owner's decision changes `licence` or `licence_url`, if `verify.py` or the
`outlook-v6` rules change, or after 7 December. Revoke it with `research policy-revoke` if it should not be used at all.

## 7. Real version 3 is refused; synthetic paths

**7 November, historical (pre-approval, Treasury `denied`).** Real database (opened `mode=ro`), real policy, no key in the
environment:

```
research run-policy data/phase-4x/policy-treasury-feu-phase-4x.json --version 3 --dry-run
Sections:  ordinals [0, 1, 2, 3, 4] (pages 1-5); excluded by rights tripwire: []
Worst case: US$0.4247 (cap US$0.50)    Lifetime: 4 of 8, US$0.6267107880 of US$5.00
Status: REFUSED  - llm_processing_denied  - version_attempted                      (exit 2)
```

With the **proposed** registry, as a temporary copy (`NZSTATS_RESEARCH_SOURCES_FILE`), against the same read-only database:
`REFUSED - version_attempted` alone. The hosted permission does not reopen version 3. `database_not_migrated` (Phase 4W) is gone.
The live database hash was identical before and after.

**8 November, live approved registry.** `research sources` shows Treasury `hosted` and every other source `denied`. The same dry
run: `REFUSED - version_attempted` only (exit 2; same request hash, US$0.4247 worst case). Version 1: `version_attempted` only.
`policy-audit`: 4 of 8 attempts, US$0.6267107880, 0 events. Generic `research summarise treasury --dry-run` with a hosted
(placeholder, non-routable) endpoint: refused before any client was built, exit 2. Log
`data/phase-4x/approval-2026-11-08/51-preflight-audit.log` and `52-generic-summarise-guard.log`. No reservation, request or
`--confirm`.

Synthetic acceptance, `backend/tests/research/test_phase_4x_readiness.py`: 5 tests (adapted on 8 November to the approved
registry). Each runs in its own `tmp_path` database, raw tree and policy. Sockets are blocked for the module, and the provider is an `httpx.MockTransport`.

| Case | Result |
|---|---|
| Shipped registry | Treasury `hosted`; every other source `denied` |
| Approved lines vs pinned pre-approval baseline | only the two keys; licence pin kept; display, crawler, other Treasury fields and RBNZ unchanged |
| New synthetic FEU under the approved entry | eligible with no refusal code; the dry run makes 0 requests; a confirmed run makes exactly 1 mocked request; summary `outlook-v6`, `verify-5`, `unreviewed` |
| Same report re-saved (new bytes, same text, same address) | import returns the attempted version `unchanged`: `version_attempted` |
| Same bytes under a new address and version row | `content_already_attempted`; still 1 request in total |
| Real ledger shape (the 4 historical amounts and tags, US$0.6267107880) | v3-shaped version `version_attempted`; 4 new reports run (4 requests); the 5th `policy_calls_exhausted`; a legacy scope (`phase-4n-second-pilot`) cannot reserve |

Mutation check: a proposal that also changed `licence`, a disabled content-equivalence check (7 November) and a change to another
Treasury field (`verified_on`, 8 November) each failed these tests.

## 8. Next real Treasury FEU: exact commands (do not run until the verdict's conditions hold)

Placeholders are in angle brackets: **replace every placeholder before running anything**. Nothing here is invented: there is
no new report yet, and version 3 must not be relabelled or re-imported to look new. Run from the repository root with the venv
active, in one shell session (the variables below carry between steps). Nothing in this section was executed in Phase 4X.

```sh
# 0. Rights: approved 2026-11-08 and applied locally (section 4); integrate it with the summarise guard first. Then check:
nzstats research sources                      # treasury shows llm "hosted"; every other source "denied"

# 1. The owner saves the new FEU PDF in a browser (no crawler, no scripted browser) and reads its own notices:
#    item-specific copyright, "Copyright Held by Non-Crown Party", third-party credits on charts and tables.
#    Sections with explicit notices are excluded by code; for "Source: ..." credits the operator decides per report.
#    Stop if the rights of anything to be sent are unclear (section 4, per-report scope).
FEU_DATE="<YYYY-MM-DD>"                       # the report's own date
STAMP="<UTC-STAMP>"                           # e.g. the output of: date -u +%Y%m%dT%H%M%SZ
PDF="data/imports/feu-${FEU_DATE}.pdf"

# 2. Fresh verified backup, rehearsed into a NEW directory:
nzstats backup --bundle "data/backups/pre-feu-${FEU_DATE}-${STAMP}"
nzstats verify-backup "data/backups/pre-feu-${FEU_DATE}-${STAMP}"
nzstats restore-backup "data/backups/pre-feu-${FEU_DATE}-${STAMP}" "data/restore-check-${STAMP}"

# 3. Manual import. The output names the version id: "treasury: new publication <P> version <V> sha256 <...>".
nzstats research import treasury "$PDF" \
  --url "<the exact www.treasury.govt.nz address of the PDF>" --importer "Kevin Chang" \
  --note "<saved in a browser on <date>; notices read; how obtained>" --series FEU --published-on "$FEU_DATE"
#    Continue ONLY if the outcome is "new". "unchanged", "duplicate" or "reactivated" mean the content is not new: stop.
VERSION="<V from the import output>"

# 4a. Policy, reuse (default): the Phase 4X policy, while it is valid (to 2026-12-07 22:44 NZDT) and its pins still match.
POLICY_FILE="data/phase-4x/policy-treasury-feu-phase-4x.json"

# 4b. Policy, renewal (OPTIONAL; only after expiry, a licence or licence_url change, or a verifier or prompt change).
#     Skip this block when reusing. It points POLICY_FILE at a NEW file before creating it (policy-init never overwrites).
# POLICY_FILE="data/policy-treasury-feu-<new-id>.json"
# nzstats research policy-init "$POLICY_FILE" --issued-by "Kevin Chang" --policy-id "treasury-feu-<new-id>"

# 5. Offline preflight. Read every line: sections and exclusions, worst case at or under US$0.50, capacity. Must say ELIGIBLE.
nzstats research run-policy "$POLICY_FILE" --version "$VERSION" --dry-run
CODE="<8-character confirmation code printed by step 5>"

# 6. Paid, ONE request. Not executed in Phase 4X. A real terminal only (not a pipe, script or agent); the dedicated OpenRouter
#    key is read without echo. The same POLICY_FILE and VERSION as step 5; retype the code at the prompt.
read -rs NZSTATS_LLM_API_KEY && export NZSTATS_LLM_API_KEY
nzstats research run-policy "$POLICY_FILE" --version "$VERSION" --confirm "$CODE"
unset NZSTATS_LLM_API_KEY
#    The run makes its own verified backup under data/policy-runs/, rechecks the key limit and usage, the model price and the
#    ZDR route, reserves once and never retries.

# 7. Afterwards:
nzstats research policy-audit                 # one executed event; lifetime 5 of 8
nzstats serve --offline --internal-drafts     # loopback only
#    A usable response appears as an unreviewed internal draft with its per-claim checks. An unusable response (provider error,
#    truncated or invalid JSON) is never displayed; the attempt and its cost still count in the ledger and the audit.
```

If `--sections` is given in step 5, give the same value in step 6: the confirmation code binds the section set.

## 9. Verification

| Check | Result |
|---|---|
| Backend full suite (Python 3.14 venv) | 5,840 passed, 0 failed, exit 0 (includes the 7 new cases) |
| New and changed tests | `test_phase_4x_readiness.py` 5 passed; `test_cli.py` 70 passed (2 new cases) |
| Final focused run (after the documentation corrections) | readiness, `test_cli.py` and all six policy suites: 259 passed, explicit summary (`-o addopts=''`), log `data/phase-4x/41-focused-tests-final.log` |
| Ruff (final) | `ruff check` all checks passed; `ruff format --check` 375 files already formatted; log `data/phase-4x/40-ruff-final.log` (supersedes `21-ruff.log`, which recorded a fixed B905 finding) |
| `git diff --check` | clean, including both new files; log `data/phase-4x/42-diff-check-final.log` |
| Frontend | vitest 557 passed (49 files); `tsc -b` 0; oxlint 0 errors (existing warnings only); `vite build` ok |
| Browser, synthetic research config | 18 passed, 3 skipped by design |
| Main dashboard Playwright | `e2e/outlook.spec.ts`, 15 passed on desktop, tablet and mobile (fixture database). The full main suite was not repeated: no frontend change in this phase |
| **8 Nov** targeted suites, approved registry | `tests/research`, `tests/store`, `tests/api`, `tests/publish` (registry, policy, CLI, hosted consent, pilot, drafts, private, public, migrations): 4,451 passed, exit 0, log `data/phase-4x/approval-2026-11-08/50-targeted-tests.log` |
| **8 Nov** supplementary | top-level CLI, config, runbook docs, ops: 220 passed, exit 0, `57-supplementary-tests.log`; final readiness, registry and research CLI after the documentation edits: 145 passed, exit 0, `58-final-focused-tests.log` |
| **8 Nov** Ruff and whitespace | `ruff check` all passed, `ruff format --check` 375 formatted (`54-ruff.log`); `git diff --check` clean and no trailing whitespace in the new files (`55-diff-check.log`) |
| **8 Nov** live state | all 33 tables, ledger (4 settled, US$0.6267107880), 48 raw files, integrity and the database file hash identical before and after the follow-up (`56-state-compare.log`) |
| **8 Nov, PR preparation** (tree as submitted) | backend `pytest -o addopts=''` 5,840 passed, exit 0; vitest 557 passed; typecheck, lint and build exit 0; `gen:api` leaves `schema.d.ts` unchanged; Playwright research config 18 passed, 3 skipped; `e2e/outlook.spec.ts` 15 passed. Private logs in `data/phase-4x/pr-prep-2026-11-08/` |
| Hosted CI (read-only) | main `b5bf3c1` run 42355129775: backend, frontend and static-site **not started**, "recent account payments have failed or your spending limit needs to be increased", about 3 s, 0 steps; docker skipped. The GitHub billing block again, not a code result. No rerun, comment or message. |

## 10. Local Economic Outlook (real data, isolated copy)

`nzstats serve --offline --internal-drafts --host 127.0.0.1 --port 8799`, with `NZSTATS_DATA_DIR` pointing at a **copy** of the
verified restore plus the owner's drafts file, so the live database got no heartbeat row. No scheduler, no on-open check, no
public or private research flag. No owner server was running (no listener on the dashboard ports), so none was disturbed. A
structural Playwright check blocked every non-loopback request and printed no draft text.

| Check | Result |
|---|---|
| Capabilities | `research_public: false`, `internal_drafts: true` |
| Isolation | `/api/research/feed` 404, `/api/private/research/items` 404, `/api/internal/drafts` without the dashboard header 403 |
| Draft mode | `automatic` (owner's `auto_display` enabled 2026-11-07); 2 drafts: summary 4 (Treasury 29 Oct) and summary 3 (15 Oct, labelled Historical, newer report named) |
| Labels | fixed notice "AI-generated research draft. Automated checks may miss errors. Not independently reviewed."; badges Failed automated checks, Historical, Newest, Unusable AI response, not shown (RBNZ); 0 "reviewed/endorsed/approved/verified" labels |
| Flags per draft | `approved_for_publication`, `checks_passed`, `human_reviewed`, `official_statistic` all false; summary 4: 13 errors, 25 warnings; provenance `outlook-v5`/`verify-4` |
| Source links | only `www.treasury.govt.nz` and `www.rbnz.govt.nz` |
| Errors and requests | no page errors in light or dark; 0 external requests attempted |

Observation, not a defect: summary 3 was stored under `verify-3`, but the drafts show `verify-4`. That is the documented Phase 4V
rule (`resolve_verifier`: older labels are re-checked and shown under the `verify-4` rules). Screenshots, light and dark, are in
`data/phase-4x/` for the owner; the agent did not read them, because they contain model output.

## 11. Blockers and residual risks

- **Integration.** The approved registry change (2026-11-08) and the `research summarise` guard are in one PR and one commit.
  They must be reviewed and merged together; the registry change must never reach main without the guard. Not merged.
- **Per-report rights checks.** Source credits are not excluded by code; each real report needs the operator's check and
  terminal confirmation.
- **No new report yet.** The workflow waits for an actual new FEU. Version 3 is permanently spent.
- Migration 014 was present at baseline, most likely applied by an earlier `serve` start; no contemporaneous post-v3, pre-014
  backup was found. Its structure is proven additive, but the earlier real migration cannot be independently reconstructed. The
  design note in section 1 stands.
- Thin per-call headroom (US$0.4247 of US$0.50 on the 29 October FEU). A longer report may refuse `per_call_cap_exceeded`.
- `outlook-v6` and `verify-5` have still never met a real model. Expect failed checks to remain possible.
- The terminal check stops automation and honest mistakes; it is not a sandbox. The tripwire is a regex, not a legal review.
- Hosted CI is billing-blocked; local results stand alone.
