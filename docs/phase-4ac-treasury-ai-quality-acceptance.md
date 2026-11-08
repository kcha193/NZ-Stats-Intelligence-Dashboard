# Phase 4AC: first new Treasury AI quality acceptance

8 November 2026, Pacific/Auckland. **PENDING — WAITING FOR NEW TREASURY REPORT.**
Offline preparation is ready for the next genuinely new Fortnightly Economic
Update (FEU). Live quality acceptance has not occurred. No paid request is
authorised by this document or by passing the offline tests.

## Baseline and scope

Initial HEAD and freshly fetched `origin/main` both match the expected
`8394e556d45d1d1e7ac8f08eb264ee81265e8712`. The initial worktree was clean;
GitHub reported no open PRs. Phase 4AB is integrated. This phase reuses the
policy runner, `outlook-v6`, `verify-5`, diagnostics and `presentation-1`.
It changes documentation only; no prompt, contract, verifier, policy pin,
permission, ledger or historical summary is modified.

The [official FEU collection](https://www.treasury.govt.nz/publications/research-and-commentary/fortnightly-economic-updates)
was checked on 8 November. Its newest entry remains the
[29 October 2026 FEU](https://www.treasury.govt.nz/publications/feu/fortnightly-economic-update-29-october-2026),
with issue date 2 November. No newer FEU was established from the official
publication record. These were publication-metadata checks, not PDF acquisition.
An absent newer listing is a dated observation, not a prediction of the next date.
Version 3 already represents that report and is permanently spent. Do not reuse,
rename, re-import or alter an old report to make it appear new.

No report was acquired or imported, no OpenRouter endpoint was contacted
(including account/model probes), and no inference, polling process, production
server, migration or deployment was started. Tests use synthetic/fixture data and
mocked providers. Production evidence was read with SQLite `mode=ro` and
`query_only=ON`; the private probe also blocks socket connections.

## Historical benchmark

Fresh read-only replays reproduce the original verification and response hashes
for summaries 3 and 4. The benchmark uses `verify-5` for comparison with the next
result, while preserving the original results. Claims without errors include
warning-only claims; clean, warning-only and failed are disjoint. Percentages
below use all claims as denominator. Errors and warnings count findings, which
can overlap on the same claim.

Summaries 1 and 2 remain unusable `provider_error` records without recoverable
parsed output or raw response. Their quality is not assessable; their original
attempts and costs remain in the ledger.

| Measure | Summary 3: 15 October, issued 19 October | Summary 4: 29 October, issued 2 November | New `outlook-v6` result |
|---|---|---|---|
| Total claims | 18 | 24 | Pending |
| Claims without errors / eligible for presentation | 11/18 (61.1%) | 17/24 (70.8%) | Pending |
| Clean claims | 10/18 (55.6%) | 6/24 (25.0%) | Pending |
| Warning-only claims | 1/18 (5.6%) | 11/24 (45.8%) | Pending |
| Failed / excluded claims | 7/18 (38.9%) | 7/24 (29.2%) | Pending |
| Original errors / warnings | 8 / 6 (`verify-3` label, compatibility `verify-4`) | 13 / 25 (`verify-4`) | Pending |
| `verify-5` errors / warnings | 8 / 6 | 11 / 25 | Pending |
| Claims carrying any warning, including failed | 4/18 (22.2%) | 17/24 (70.8%) | Pending |
| Independent rule findings, strict | 8 | 8 (original: 10) | Pending |
| Grouped underlying problems | 7 | 7 (original: 9) | Pending |
| Unsupported/unresolved monetary decisions | 0; no decision claims (rate not applicable) | 1/1 decisions (100%); 1/24 total claims (4.2%); five findings | Pending |
| Period / horizon / fiscal-calendar findings | 5 / 1 / 1 | 2 / 0 / 0 (original periods: 3) | Pending |
| Unit / currency findings | 0 / 0 | 1 / 0: missing foreign-money unit, contract limitation | Pending |
| Forecast attribution findings | 1 (`issuer_not_in_evidence`) | 0 | Pending |
| Forecast presented as fact findings | 0 | 3 | Pending |
| Unsupported-number findings | 0 | 0 | Pending |
| Evidence citation findings | 0 | 0 | Pending |
| Newly accepted / rejected historical claims | 0 / 0 | 0 / 0 | Not applicable |

Strict independent findings subtract only the three guaranteed decision
instrument/rate/action cascades when `decision_not_in_evidence` is present on
that claim. Grouped problems additionally join its possible date cascade;
summary 3 groups the horizon/fiscal pair into one year-basis problem. Retain both
counts and the original finding codes. These are investigation counts, not
independent observations or proven economic mistakes. See the existing
[Phase 4AB root-cause inventory](phase-4ab-historical-ai-remediation.md#root-cause-findings)
and [Phase 4V limitations](phase-4v-economic-accuracy.md#9-open-items); do not repeat
their remediation or edit historical outputs.

Unsupported numbers means `number_not_in_evidence` / `value_not_in_evidence`;
it does not absorb unit, period or interpretation errors. Citation findings use
the diagnostics citation-code set. Zero citation errors establishes matching
locations, not faithful economics. Zero currency findings does not establish
currency correctness: the historical foreign-dollar claim lacks an expressible
unit and remains excluded. Table-cell currency association remains a verifier
limitation. The unresolved decision and forecast/fact cases remain conservative
failures, not confirmed fabrications or accepted facts.

The two historical reports differ in length, selected sections, subject matter
and prompt. They are descriptive baselines, not a controlled experiment. A new
report must show its selected pages/sections, input length, claim-kind counts and
all numerator/denominator pairs beside these results. Report numerical-field
and forecast/decision rates with their own denominators too. Never label one
different report proof of statistical superiority or a general v6 accuracy gain.

## Quality scorecard

Use one private assessment record with source/version/raw/text/section hashes,
publication and document dates, summary/output/request hashes, prompt/verifier
pins, policy hash, run/reservation/event IDs, evaluator and assessment time.
For every claim record its path, kind, evidence section/page/offset, automated
findings, substantive assessment, severity and whether it enters highlights.
Keep source text, model output and detailed cost evidence in ignored
`data/phase-4ac/` (directory 0700, private files 0600).

Each dimension is **PASS**, **CONDITIONAL**, **FAIL**, or **NOT ASSESSED**.
Record reasons and supporting artifact references, rather than averaging scores.
A material defect changes the economic conclusion, direction, magnitude,
decision, institution, time basis or an executive user's likely interpretation.
Unresolved material ambiguity is not a pass. Mark genuinely absent topics
not applicable with a reason; never turn missing assessment into zero defects.
For each inventory record total eligible, assessed and unassessed items. Report
completeness as assessed/eligible and unassessed/eligible; quality outcome rates
use assessed items only. When assessed is zero, quality rates are not assessable.

| Dimension | Assessment and measures | Passing evidence |
|---|---|---|
| A. Factual grounding | Inventory every numerical assertion, including prose, structured facts, forecasts, decisions and derived/comparative numbers. Check value/sign/scale, unit, currency, observation period, source, adjustment and whether the cited evidence supports that exact assertion. Record total eligible, assessed and unassessed numerical assertions; report supported/unsupported/ambiguous outcomes over assessed assertions and findings by type. | Every promoted numerical assertion has defensible support for every applicable field. Missing metadata is explicit; unsupported conversions, inferred periods and unexpressible units are excluded. A lexical pass alone is insufficient. |
| B. Forecast representation | For every forecast and time-sensitive fact/decision, check realised versus expected, institution/issuer role, explicit horizon and fiscal/calendar basis, scenario/conditions and original versus superseded vintage. Count faithful/ambiguous/incorrect representations over assessed applicable claims; report unassessed/eligible separately. A survey's measured expectation can be an observed fact; an expected OCR move is not an adopted decision. | Forecasts are faithfully represented, attributed and qualified. Check actual OCR decision maker, event date, action, resulting rate and vote separately. This assesses representation, not whether a future forecast comes true. |
| C. Economic reasoning | Read each interpretive claim in permitted source context. Record whether the inference follows, facts and inference are separated, causality is supported, material uncertainty is retained, and conclusions are mutually consistent and within what the report establishes. Record eligible, assessed and unassessed interpretations; report defensible/limited/unsupported outcomes over assessed interpretations. | An explicit substantive economic assessment, with reasons, finds no serious defect undermining the executive interpretation. Automated textual verification cannot establish this. |
| D. Coverage | Before judging output, inventory material items in the permitted sections by macro developments, monetary policy, inflation, labour, consumption, business activity and global risks where present. Match each to a defensible output claim; count covered/material eligible items, omissions and excluded-rights topics separately. | No material omission distorts the overall reading. Disclose omissions or coverage restrictions; do not add unsupported claims to raise a percentage. Excluded sections never enter the coverage denominator. |
| E. Readability and usefulness | Assess executive clarity, conciseness, prioritisation, plain explanation, separation of history/forecast/inference and traceable links/dates. Record each criterion as met/limited/unmet with an example reference and check the rendered highlights. | A general reader can identify the key supported developments and their limits without confusing a forecast, observation or AI interpretation. Warnings and missing metadata stay visible. |
| F. Operational reliability | Check the actual new document identity, rights, selected sections, complete response, JSON contract, exact model/provider/privacy, stored hashes and versions, one reservation/transmission, actual cost/usage/audit agreement, historical preservation and internal-only presentation. | All operational gates hold and originals remain intact; unusable output is withheld and its cost/attempt retained. An eligible dry run is preparation, not evidence that a live request succeeded. |

All six dimensions for the **new response are NOT ASSESSED** today. Offline
operational tests do not replace F's real-run checks or the substantive work in
A–E. An evaluator's acceptance assessment is not a new human-approval requirement
for internal viewing; the existing automatic internal gate remains unchanged.

## Policy readiness: local read-only evidence

| Check | Observed on 8 November |
|---|---|
| Source registry | Treasury `llm_processing=hosted`, manual import approved; every other institution, including RBNZ, `denied`. Public and private display remain `none`. Automated Treasury acquisition remains refused. |
| Policy | Existing `data/phase-4x/policy-treasury-feu-phase-4x.json`, regular private file, mode 0600; hash `6bc867b34aba4c6faac2f09f24a5e58b4dfe319f8c991f45819c1d995925563b` |
| Validity / revocation | Valid, not revoked. Expires **7 December 2026 22:44:25 NZDT** (`2026-12-07T09:44:25Z`); no renewal performed. |
| Prompt pin | `outlook-v6`, `addaa683cfa0501f624a3bf99dfcc077efd18fd2bd9eedf6b03ff55ec66ca7b5`, matches code |
| Verifier pin | `verify-5`, file hash `c9660544e23f505e02ab10ace602ff5e6af9e369252953f4295a8fa3505c28a7`, matches code |
| Licence pin | `b3453e1efb4d9ef1efea9758010ab99e376531eea731f7fb1537f86da002a1e2`, matches registry |
| Route | `anthropic/claude-opus-5.5`, `google-vertex/europe`, ZDR, data collection denied, no fallback, required parameters, low model effort, 12,000 output-token ceiling |
| Limits | One attempt per eligible new document; at most 4 calls and US$2 per policy, US$0.50 per call, US$5 lifetime; legacy experiment ceilings preserved |
| Ledger / audit | 4/8 lifetime attempts; US$0.6267107880 spent, US$4.3732892120 remaining; 0 policy calls / US$0 policy spend, 0 policy events |
| Historical version 1 dry run | Refused: `version_attempted`; worst-case estimate US$0.4654452; zero requests/reservations |
| Historical version 3 dry run | Refused: `version_attempted`; worst-case estimate US$0.4247056; zero requests/reservations |

These historical cost estimates are not estimates for an unknown next report.
No excluded ordinals were found by the tripwire for the held versions; that
does not establish third-party rights. No account balance, live model price or
live provider availability was probed. Those are rechecked by the existing
operator-run execution after separate authorisation. This phase consumed **zero
new attempts and US$0 inference spend**.

## Source, rights and import gates

Use [Phase 4X's rights scope and runbook](phase-4x-operational-readiness.md#4-treasury-processing-rights-configuration-approved-2026-11-08-applied-locally).
The registry approval is bounded, not permission for arbitrary third-party
material. The owner must independently establish the new FEU from its official
publication record, save its actual PDF in a browser, record both the publication
page and PDF URL, document date and issue date, then inspect notices and credits
on the actual PDF. Stop if any intended section's rights are ambiguous.
Do not automate acquisition, bypass restrictions or infer rights from the general
Treasury licence alone.

Create a private section inventory: ordinal/page range, extraction quality,
rights evidence, include/exclude reason and selected-section hashes. Explicit
third-party notices are excluded by code and cannot be named back in. A source
credit alone is not caught by that tripwire: the owner must resolve it and omit
the affected section with an explicit section list. If Crown and unpermitted
material cannot be separated within an existing section, omit that whole section
or stop. Do not edit the PDF to bypass identity or rights checks.

Before import, take a current verified bundle, restore to a new separate directory
and verify the restored database/raw tree against that bundle. Preserve the
original production database and raw artifacts. After import, check publication
identity, current document version, original PDF/raw hash, extracted-text hash,
page/section inventory, extraction quality, manual provenance and licence pins.
Only a genuinely new publication is eligible here. An `updated` version of an
old report, or `unchanged`, `duplicate` or `reactivated`, is not the next new FEU.

## Owner-run execution: prepared, not executed

Run from the repository root with the backend venv active. Replace all placeholders.
This uses the existing Phase 4X command structure. Keep document and issue dates
separate: **`--published-on` takes the official issue/publication date**, as the
CLI specifies, not the document's signed date. The private import note records
both dates. This clarifies the `FEU_DATE` example in Phase 4X; no stored dates
are changed.

```sh
umask 077
nzstats research sources
nzstats research policy-audit
DOCUMENT_DATE="<official document date YYYY-MM-DD>"
PUBLICATION_DATE="<official issue date YYYY-MM-DD>"
STAMP="<unique UTC stamp>"
PDF="data/imports/feu-${DOCUMENT_DATE}.pdf"  # saved manually by the owner
BUNDLE="data/backups/pre-feu-${DOCUMENT_DATE}-${STAMP}"
RESTORE="data/phase-4ac/restore-${STAMP}"   # new directory
nzstats backup --bundle "$BUNDLE"
nzstats verify-backup "$BUNDLE"
nzstats restore-backup "$BUNDLE" "$RESTORE"
nzstats verify-backup "$RESTORE/nzstats.db" --raw-dir "$RESTORE/raw"

nzstats research import treasury "$PDF" \
  --url "<official PDF URL>" --importer "Kevin Chang" --series FEU \
  --published-on "$PUBLICATION_DATE" \
  --note "<browser acquisition date; official publication page URL; document and issue dates; rights inspection record>"
# Stop unless this is independently established new content and import says 'new'.
VERSION="<version ID printed by import, never historical 1 or 3>"
POLICY_FILE="data/phase-4x/policy-treasury-feu-phase-4x.json"
SECTIONS="<explicit comma-separated permitted section ordinals>"
nzstats research run-policy "$POLICY_FILE" --version "$VERSION" \
  --sections "$SECTIONS" --dry-run
```

Retain content-free preflight identity, hashes, section selection/exclusions,
worst-case cost, available capacity and refusal codes privately. The dry run must
say **ELIGIBLE**. On refusal, record the exact reason and stop. Never increase a
budget, modify a route/pin, reset a reservation or retry to work around it.
If the policy expires before the new report, stop for the documented
[owner-controlled renewal](phase-4x-operational-readiness.md#6-policy-prepared-authorises-nothing)
using a new file/id and a fresh dry run. Do not silently renew it.

**Mandatory separate boundary:** the owner must authorise this particular paid
request and execute it in a real terminal. Treasury hosted consent and automatic
internal viewing do not supply that authorisation. The owner privately loads the
dedicated key as documented in Phase 4X, checks the dry-run scope/cost, copies its
eight-character code into the command below and retypes it at the runner's prompt.
The agent must not supply the code, simulate a terminal/approval, read or print
the key, or execute this command autonomously.

```sh
# OWNER ONLY, AFTER SEPARATE AUTHORISATION; same policy/version/sections as dry run.
CODE="<eight-character code from that eligible dry run>"
nzstats research run-policy "$POLICY_FILE" --version "$VERSION" \
  --sections "$SECTIONS" --confirm "$CODE"
# Owner clears the key from the shell afterwards, as in Phase 4X.
```

No unattended job is installed. The existing runner rechecks authority, source,
key controls, live price, route and privacy, makes a verified backup, reserves
once and never retries. A failure or interrupted reservation still counts;
inspect the authoritative ledger/audit instead of resetting it.

## Post-run acceptance: only after an actual authorised response

1. Record the actual run, summary, version, reservation and event IDs. Reconcile
   one transmission/reservation, tokens, actual billed cost and remaining caps
   against both audit and ledger; preserve unresolved worst-case holds. Run
   `nzstats research policy-audit`. If no other authorised work intervened, the
   expected lifetime count after one reserved call is 5/8, not a reset baseline.
2. Check `finish_reason=stop`, usable schema-valid JSON, raw response/output hash,
   source/version/section binding, stored request/body hashes, `outlook-v6` rule
   hash, `verify-5` file hash and the policy pins. Check both requested route and
   actual serving-provider metadata, response identity, ZDR, denied collection
   and disabled fallbacks. A configured provider alone is insufficient.
3. Run `nzstats research diagnose <SUMMARY_ID> --proposed verify-5 --json` and
   retain its redacted counts privately. Use `--out data/phase-4ac/new-summary.html`
   for a private review artifact; `--include-text` only when needed locally.
   Confirm stored verification reproduces and hashes are intact. If output is
   truncated, malformed or missing, record the failure and cost, withhold it and
   do not retry or manufacture a replacement.
4. Complete A–E against the permitted source sections; group root causes using
   the benchmark conventions. An unresolved verifier finding remains excluded;
   do not change rules simply to make this result pass. Record severe economic
   reasoning defects even when textual checks pass.
5. Inspect the derived `presentation-1` result through the existing internal API
   and Economic Outlook on an isolated offline copy. Confirm model/prompt/verifier
   provenance, source links, separate document/issue dates, visible warnings,
   original detail access and **zero failed claims in all executive highlights**.
   Where document-date metadata is absent, retain that limitation and check the
   official record; never substitute the issue date or fabricate a display field.
   Confirm public/private routes and static/snapshot exports contain no draft.
   Internal viewing requires no new human approval. Do not start a production
   server merely for verification; it can write heartbeat rows.
6. Compare final production table/raw fingerprints to the pre-import baseline:
   explicitly account for the new import/run rows while requiring original
   summaries, original verification, historical ledger rows and official economic
   observations to remain identical. Append the new column of raw counts and
   proportions to the benchmark, with report-length/section/claim-kind caveats.
   Save the six dimension results and a reasoned verdict. One report cannot
   establish general or statistical superiority of `outlook-v6`.

## Offline coverage and verification

The coverage audit found existing tests for all fifteen requested safeguards.
No new test duplicates or product changes were justified. Paths below are under
`backend/tests/research/` unless otherwise stated. Provider calls in tests are mocks.

| Requested check | Existing evidence reused |
|---|---|
| 1. Source identity | `test_policy.py` source/provenance/raw-integrity cases; `test_verify.py` wrong-version/section citations |
| 2. Explicitly new version | `test_phase_4x_readiness.py` new synthetic FEU/import; `test_policy.py` superseded version; `test_policy_review_regressions.py` current-version race checks |
| 3. Duplicate / attempted content | Readiness re-save/re-import cases, policy content hash tests, atomic concurrent reservation regressions |
| 4. Expiry / revocation | `test_policy.py`, `test_policy_run.py`, review regressions at confirmation, backup, reservation and transmission boundaries |
| 5. Section scope | `test_policy.py` explicit selection/missing ordinal; `test_policy_run.py` confirmation binds scope; empty CLI selection refused |
| 6. Third-party protection | `test_policy.py` excluded-section/no-eligible-section cases; source-credit rights still require the per-report operator check |
| 7. Missing / unsupported money unit | `test_verify_records.py`, `test_verify5_currency.py`, truth corpus and `test_assessment.py` inexpressible-unit partition |
| 8. Forecast / fact | `test_verify_records.py`, `test_prompt_v6.py`, truth-labelled scorecard and differential tests |
| 9. Monetary decision attribution | `test_verify_records.py`, `test_verify_attribution.py`, vote notation and truth corpus |
| 10. Malformed / truncated response | `test_openrouter.py`, `test_policy_run.py` unusable response/cost/no-display tests |
| 11. Wrong route / privacy | `test_openrouter.py`, policy live-route/ZDR refusal tests, `test_drafts_auto.py` verified response metadata |
| 12. Ledger / caps | All policy suites, `test_policy_plumbing.py`, review regressions, reservation/hosted/pilot tests |
| 13. Failed claims excluded | `test_assessment.py`, `test_drafts_api.py`; frontend Outlook/detail unit tests and `e2e/internal-drafts.spec.ts` |
| 14. Local-only / static isolation | Draft bind/Host/Origin/header tests, policy isolation, `backend/tests/publish/test_research_isolation.py`, static network/security browser suites |
| 15. Original history preserved | Assessment write-denial and API before/after regressions, policy legacy-ledger equality, fresh all-table/raw fingerprints |

| Verification | Fresh result |
|---|---|
| Full backend suite | 5,934 passed, 1 existing Starlette deprecation warning; 448.18 seconds (`backend-full.txt`) |
| Research and snapshot isolation | 4,161 passed, same existing warning (`research-isolation.txt`); includes verifier, prompt, diagnostics, internal-draft API and history preservation |
| Focused policy, ledger, pinning, readiness, assessment and diagnostics | 287 passed (`pytest -o addopts=''` over the nine named test files; `backend-focused.txt`) |
| Truth-labelled corpus | 46 examples unchanged; `verify-5` false rejections 3/22 supported, false acceptances 0/19 unsupported, ambiguous accepted 0/3, inexpressible accepted 0/2. Constructed cases only (`truth-corpus.txt`). |
| Ruff lint / formatting | All checks passed; 379 files already formatted |
| Frontend unit tests | 573 passed in 49 files |
| Frontend typecheck / lint / production build | Passed; existing fast-refresh lint and bundle-size warnings remain |
| Local Outlook / internal-draft browser checks | 21 passed across desktop/tablet/mobile (`playwright-live.txt`) |
| Synthetic public research browser checks | 18 passed, 3 intentional screenshot-review skips (`playwright-research.txt`) |
| Focused static Outlook, network and security checks | 33 passed, 9 intentional internal-route/static skips (`playwright-static.txt`) |
| Production preservation | 32/33 table fingerprints identical, including every research/verification/ledger/statistical table; the only change in `ops_process` is the existing server's heartbeat. All 48 raw files and the database file hash are identical; integrity and foreign keys pass. |
| Documentation / secret checks | Markdown fences and local targets valid; staged whitespace check and Gitleaks passed. Independent local review found one denominator ambiguity, corrected and rechecked with no remaining finding. GitHub Codex review requested on the PR; current outcome is recorded in its conversation. |

The production dashboard was already running before the evidence probe (loopback,
on-open mode, scheduler disabled). Its heartbeat changed during testing. Replacing
only that field with its baseline value in an **in-memory comparison** reproduces
the original table hash exactly; no production value was changed or restored.
The existing process was left alone. This is not an all-33-tables-identical claim.

Full logs, redacted benchmark JSON, policy facts and integrity evidence remain in
ignored `data/phase-4ac/`; source/model text and private cost evidence are not
committed. Browser servers and static exports used isolated synthetic data;
no production dashboard was opened by this task. No API contract or application
code changed, so schema regeneration, new real-data UI screenshots and Docker
acceptance were unnecessary. No deployment or public export was performed.

## Acceptance decision

| Verdict | Required evidence |
|---|---|
| GO | Approved policy followed; genuinely new document processed once; complete valid response; no unresolved material numerical, decision or attribution defect promoted; defensible economic interpretation and correct internal provenance; audit/security/spending intact; A–F assessed. |
| GO WITH CONDITIONS | Usable, useful result with failed/ambiguous claims excluded and material limitations disclosed. Conditions are specific; no general accuracy-improvement claim. Operational authority and integrity must still pass. |
| NO-GO | Rights/permission failure, unusable response, integrity/provenance/spending failure, unsupported material executive claims or serious economic interpretation defects. Preserve cost and attempts; no retry. |
| PENDING | No genuinely new FEU or no separate paid-run authorisation; substantive new-response evidence is absent. PENDING is not NO-GO. |

**Current verdict: PENDING — WAITING FOR NEW TREASURY REPORT.** Offline readiness
does not make Phase 4AC live acceptance GO. Resume with independent official
publication identification, manual rights-reviewed acquisition and the owner-run
gates above. Keep the focused PR open for review; do not automatically merge.
