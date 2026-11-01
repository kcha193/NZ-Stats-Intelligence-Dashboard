# Phase 4M: owner decisions and executable OpenRouter pilot

2 November 2026, Pacific/Auckland. Baseline: `9e85e5b10b916085348a924fbe73d74ef3091316`,
freshly fetched main after merged [PR #38](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/38).
**The first real pilot ran: two requests, two rejected responses. NO-GO for economic intelligence or display.**
Kevin explicitly approved the final manifest/scopes and confirmed full retained-text rights, including any
third-party portions, by replying “yes approve” to the concrete final question. This is recorded as an owner
attestation, not an independently established third-party licence grant. Processing approvals are complete;
both one-attempt slots are now consumed. Neither output was approved.

## Actual inference outcomes

The approved freeze SHA-256 was
`8a73c08c6a52357b89eeedd6de290b2c396a52bcd3556f3bc6747fdd5234c19a`.
Consent was recorded at **2026-11-01 20:25:27 UTC** (2 November, 09:25:27 NZDT), expiring one hour later.
The timestamp is the receipt/recording time of the owner's message. Both requests ran within that window,
with exact captured request-body hashes matching the freeze, no retries/fallback and no optional model.

| Actual result | Treasury v1, sections 0–6 | RBNZ v2, sections 1–14 |
|---|---|---|
| Returned model / provider | `anthropic/claude-opus-5.5` / `Google` | Same |
| Requested route / catalogue identity | `google-vertex/europe` / `anthropic/claude-opus-5.5-20260921` | Same |
| Input / output tokens | **16,460 / 6,000** | **11,299 / 6,000** |
| Reasoning tokens included in output | **6,000** | **1,457** |
| Reported cost, US$ | **0.202379760** | **0.179898444** |
| Recorded latency | **56.090 s** | **43.995 s** |
| HTTP / finish reason | **200 / `length`** | **200 / `length`** |
| Stored outcome / error | `provider_error` / `invalid_response` | `provider_error` / `output_truncated` |
| Received final content | Null; no final JSON | Incomplete JSON; 12,407 characters |
| Complete JSON / schema | Fail / fail | Fail / fail |
| Economic/statistical verification | Not admitted: no complete schema-valid output | Same |
| Human / display approval | None | None |

Actual reported inference total: **US$0.382278204**, exactly matching the dedicated key's post-run usage;
remaining key limit **US$4.617721796**, no reset, BYOK usage zero. Total input/output: **27,759 / 12,000**;
combined recorded request latency **100.085 s**. Both reservations settled on reported billing. These are actual
results, not dry-run estimates. The returned Google label still does not independently prove upstream region/account settings.

No prompt, reasoning setting, output cap or verifier threshold was changed after observing these failures.
No JSON was repaired, reassembled or resubmitted to obtain a passing result. The incomplete RBNZ response has
**20 intact claim-like fragments**, all rejected for admission; the local forensic worksheet shows each with its
received evidence, the entire surviving content/tail and every approved source section. Treasury has no final-content
claim to enumerate. Raw envelopes, including reasoning, remain local; reasoning is not accepted economic intelligence.

| Economic acceptance measure | Actual numerator / denominator | Outcome |
|---|---|---|
| Complete JSON outputs | **0 / 2** | Fail |
| Schema-valid outputs / scoreable document coverage | **0 / 2** | Fail |
| Accepted summaries | **0 / 2** | Fail |
| Accepted aligned numerical fidelity | **0 / 0** | Unmeasured; cannot pass 100% |
| Accepted issuer accuracy | **0 / 0** | Unmeasured; cannot pass 100% |
| Accepted citation correctness | **0 / 0** | Unmeasured; cannot pass ≥95% |
| Raw/accepted precision, recall and claim coverage | No complete schema-valid prediction set | Unscored; no passing claim |

The unchanged gold evaluator records **two provider errors**, no scoreable output and both versions without a
completed summary. The 20 forensic fragments are review aids only, never a substitute prediction set. Literal
substring checks on their quotes do not establish semantic citation correctness or numerical/issuer fidelity.
**Accepted economic claims: 0. Entire rejected responses: 2; all 20 intact RBNZ review fragments remain rejected.**

Local human review: `data/phase-4m/actual-run-20261102/human-review.html`.
Exact outcomes: `outcome-metadata.json`; evidence: `human-review-evidence.json`; unchanged-reference evaluation:
`gold-evaluation.md` / `.json`, all in that same ignored directory with restrictive modes.
Only the four intended LLM audit tables changed against the fresh execution backup. Statistical data,
source/document/section permissions and original annotations stayed unchanged.

**No processing owner approval is missing now.** Human output approval and separate private-display/UI approval
have not been granted, and these failed outputs cannot be promoted by automatic approval. The Economic Outlook UI PR
is withheld. Both version attempts are consumed; there is no permitted automatic or ordinary rerun. Any future trial
requires a separate reviewed proposal; never reset the ledger or change document identity to bypass the restriction.

## Local review packet

Open `data/phase-4m/approval-checklist.html` locally. It links to the existing
`data/phase-4l/owner-review.html`, the original Treasury PDF and metadata-only decision worksheet
`data/phase-4m/owner-decisions.json`. The RBNZ original is presented escaped in the existing packet;
do not execute the saved HTML. Review the PDF visually as well as the extracted text.
The original packet, documents and annotation files are preserved. Their hashes are checked locally.
Report text, quotes, annotations, request/response bodies and account evidence stay under ignored `data/`.
Do not paste them into Codex, GitHub, logs or review comments. Share only decisions, hashes and non-secret metadata.
The historical concrete decision is in `data/phase-4m/final-request-review.html`; its inert pending template is
preserved. Actual approval is `data/phase-4m/execution-approval.approved.json`, supported by the verbatim owner reply.

## Approval checklist for Kevin

For each decision, record **approve, deny or defer**, approver, UTC decision/expiry times and local evidence.
Fields started pending. A blank field, checked box, PR merge or broad “go ahead” supplies no missing evidence.
The worksheet is a review document, has no runtime loader and cannot enable processing.

| Decision | Review requirement | Recorded outcome / limitations |
|---|---|---|
| Treasury v1 rights/scope | Inspect PDF pages 1–7 and every notice, chart, source label and IMF contribution. Bind exact whole-section ordinals/hashes and full retained-text rights | Owner explicitly approved **0–6** and affirmed rights including third-party portions in the final question. Recorded as owner attestation under applicable Crown licence/held permissions; no independent legal audit or fabricated grant |
| RBNZ v2 rights/scope | Inspect saved HTML/notices; bind exact ordinals/hashes and full retained-text rights; exclude chrome **0** | Owner explicitly approved **1–14** and the same full-rights assertion. Automated website access remains separately restricted |
| Exact route/privacy | Approve `anthropic/claude-opus-5.5` through the **OpenRouter intermediary**, only `google-vertex/europe`, expected response label `Google`, subject to fresh eligibility | Owner explicitly approved the route and documented upstream/retention/legal/residency limitations. Fresh checks passed. No substitution was authorised or used |
| Account controls | Dated non-secret evidence: logging and improvement/training opt-ins off; applicable strict ZDR; safety retention disallowed; no auxiliary logging | Owner reports checks complete and approved the final packet. Evidence is the recorded owner attestation; account/upstream settings were not independently audited |
| Dedicated key/budget | Pilot-only key, **US$5 lifetime limit with no reset**, prior usage accounted for and no other consumer; secure secret supply | Preflight verified US$5 remaining/zero usage. Post-run usage is US$0.382278204, remaining US$4.617721796. Dedication/no other consumers is owner-attested. No secret or key-bearing screenshot exposed |
| Human gold review | Read originals, baseline and gold locally; bind the reviewed file/hash and retain explicit rejection cases | Owner explicitly confirmed the unchanged gold, SHA-256 `f04d64f0960497053b7c3a990ca8efa0244f80e11394e9133f0482655ba68711`, with documented rejection cases retained. Local reviewed copy: `data/phase-4m/reviewed-gold-20261102.json`. This is an owner attestation, not an independent agent audit of economic meaning |

**Before execution, Treasury-only operation was an available option.** The owner approved both; both attempts
are now consumed. Neither document may be run again under this approval.
An excluded section cannot be silently rewritten or partially trimmed to fit approval; a changed extraction/scope
requires new hashes and a separately reviewed request. Owner consent does not create missing third-party rights.

Treasury's general Crown licence permits attributed reuse but excludes specified items and non-Crown rights;
the exact PDF's notices control the decision. [Treasury licensing](https://www.treasury.govt.nz/copyright-and-licensing).
RBNZ permits accurate, acknowledged use of Bank material but excludes identified third-party content and
separately restricts automated access. [RBNZ terms](https://www.rbnz.govt.nz/about-our-site/terms-of-use).

ZDR is a routing/retention policy, not proof of end-to-end EU residency or independent audit of the upstream
account. `zdr=true` can allow safety-retaining endpoints under some settings; require strict eligibility and
fresh `safety_retention=false`. [OpenRouter ZDR](https://openrouter.ai/docs/guides/features/zdr).
Metadata/billing retention, anonymous categorisation, in-flight CSAM screening and legally required retention
remain possible; both logging/improvement opt-ins must be off. [Data collection](https://openrouter.ai/docs/guides/privacy/data-collection),
[privacy policy](https://openrouter.ai/privacy), [terms](https://openrouter.ai/terms).
Review Google's upstream arrangements; the response label alone proves no region/account settings.
[Google-managed Claude](https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/google-managed).

## Gold decisions before scoring

- Keep the **four Treasury table-column cases rejected**; visual review cannot restore missing extraction structure.
- Resolve Treasury migration's unsupported horizon only from original evidence; otherwise retain an expected rejection.
- Audit every Treasury/IMF issuer, including warning-only attribution cases; narrow/reclassify mixed fact/forecast passages from evidence.
- For RBNZ, personally confirm the proposed section-2 decision evidence: hold, 2.75%, 28 October 2026, 4–3. Broad discussion is not interchangeable decision evidence.
- Preserve CPI horizon/annual-rate basis, comparison cutoffs, unknown migration basis and the Treasury 15/19 October date ambiguity. Do not invent missing details.

The existing 46 anchors and comparison results are reference checks, not generated-model performance.
The full worksheet and original annotation hashes are in [Phase 4L](phase-4l-controlled-pilot.md#gold-review-worksheet-and-economic-acceptance).

## Execution and later approvals

The bounded runner is implemented with synthetic HTTP tests. `HostedConsent` now requires an ordered exact
ordinal list and a hash of the entire stored section inventory. Missing, extra or changed sections/headings/pages,
including excluded sections, invalidate consent; the selected subset alone reaches request construction and verification.
The explicit launcher `scripts/run_hosted_pilot.py` keeps backup wiring outside the isolated research domain.
It constructs no application runtime/scheduler and performs no migrations. Offline freeze has rendered the
candidate subsets locally without transmission. The final packet presents exact ordered sections/hashes, framed request hash,
dates, `outlook-v3`, contract 2, `verify-3`, processing `3b-1`, 45,000-character/6,000-output-token caps and
conservative cost bound for **separate final expiring request consent per version**. That consent is pending
until the owner approves the actual freeze and retained-text rights. That approval was subsequently received and
used for the two attempts above. No global source permission was changed.

The current freeze manifest SHA-256 is
`8a73c08c6a52357b89eeedd6de290b2c396a52bcd3556f3bc6747fdd5234c19a`.
Its original proposal status is immutable; the separate signed owner record grants the actual execution authority.

| Exact version / proposed ordinals | Canonical input SHA-256 | Frozen body SHA-256 | Conservative token-cost ceiling |
|---|---|---|---|
| Treasury v1 / 0–6 | `5cd9f11a951d4480323734dad2312f4ff9bc405fc9a3ce1cdbb7010fd733d0fa` | `719414e9ef71c4b25a59e32f88c74b7de040df82997e833ca9cbee44b48b3695` | US$0.31835760 |
| RBNZ v2 / 1–14, excluding 0 | `34de8497f0d4702c39caf74c54b7f54b6b6789afb080be6ad177d9e766bc71bf` | `1f62dc6ad1c7bb52728f97e602e8d36af468ef5118c57af5f309bfc49a675597` | US$0.27663240 |

Combined conservative bound: **US$0.59499000**, distinct from the actual US$0.382278204 bill. A changed subset requires a new freeze.
Execution validates a separate strict `Approval` over the freeze and gold, per-section rights records,
owner/time/expiry (maximum 24 hours), route/privacy and account/key attestations. It rechecks raw bytes,
stored identity, exact framing/body, atomic attempt/spend limits and fresh OpenRouter key/model/endpoint/ZDR
metadata. The model alias must still resolve to `anthropic/claude-opus-5.5-20260921`.
An omitted retention field in the ordinary endpoint catalogue is not a licence/privacy attestation;
explicit `safety_retention=false` in the ZDR list is mandatory, and an explicit ordinary-catalogue conflict refuses.
This matches the saved 4L API response shapes; no privacy threshold was loosened.

```sh
# Both actions require the separately installed/checked runtime. Never source or print credentials here.
python scripts/run_hosted_pilot.py freeze --data-dir data --scope data/phase-4m/proposed-scopes.json --output data/phase-4m/NEW_FREEZE
# Only with a complete, owner-approved record; pending worksheet/template is refused:
python scripts/run_hosted_pilot.py execute --data-dir data --frozen data/phase-4m/frozen-proposal --approval data/phase-4m/APPROVED_RECORD.json --output data/phase-4m/NEW_RUN
```

The execution launcher creates/verifies/restores a fresh backup before calling the existing pipeline.
Request bytes and bounded response bytes are captured exclusively with restrictive modes, before parsing.
Interrupted/oversized streams preserve the received prefix and status/truncation/error metadata. A recognised
credential echo is redacted before persistence; successful responses containing it are refused. HTTP-error
classification and valid billing metadata remain intact. No auth headers, raw exception messages or secrets are captured.

Only then execute serially, at most once per approved version across all runs, with the exact approved route,
strict ZDR/no collection, no retries or fallback and US$5 total lifetime inference spend. Failed/interrupted
attempts consume their slots. Preserve real responses and claim-by-claim evidence locally with restrictive modes.
Report requested/actual model and provider, tokens, cost, latency, finish reason, schema/verifier failures and
accepted/rejected claims. Record unknown outcomes honestly; never tune prompts/thresholds to obtain a pass.

Human review must explicitly report accepted numerical fidelity **100%**, issuer accuracy **100%** and citation
correctness **at least 95%**, each with numerator/denominator and scope. Report raw/accepted precision, recall,
coverage, omissions and rejections separately. Empty denominators are unmeasured, never passing.
No generated summary is automatically approved. Human output approval and separate private-display/UI approval
must precede the Economic Outlook UI PR. Preserve loopback/version/public-display restrictions; no crawling,
scheduled ingestion, public deployment or automatic merge.

## Verification and preserved boundaries

General owner assent, completed-review and checked-controls attestations are recorded verbatim locally.
During initial preflight, the credential in ignored local configuration was used for authenticated read-only
`GET /api/v1/key`; the secret, key label, identifiers and raw key response were neither printed nor retained.
That initial check returned HTTP 200: US$5 limit, `limit_reset=null`, US$5 remaining, key/BYOK usage zero and
`is_management_key=false`. Sanitised receipt: `data/phase-4m/key-budget-check.json`.
[Current-key API](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key).
The subsequently approved two inference calls used the same dedicated credential. Post-run key usage/balance
reconcile to US$0.382278204 / US$4.617721796 as recorded above; the initial zero-usage snapshot is historical.
The unchanged gold and exact frozen scopes are bound by the owner's explicit final confirmation. The key metadata
does not establish logging/training settings or upstream arrangements; those remain owner-attested under the accepted limitations.
On 2 November, fresh schema-13 backup/restore checks verified **45 raw artifacts**; the actual run created
one run row, two rejected-summary rows, two usage rows and two settled reservation rows.
The isolated Python 3.12 runtime dependency audit passes after upgrading its bundled pip; the shared runtime is unchanged.
Independent Codex `gpt-6.1-sol` / high implementation review found two material capture issues, reproduced
failing-first and fixed: credential echoes and missing partial-stream evidence. Full isolated backend: **3,738 passed**
before the final alias guard; final-source research: **1,981 passed**; latest runner/isolation: **28 passed**.
Ruff lint/format (326 files), runtime dependency audit and local artifact/link/diff checks pass. Verification receipts are local.
Before PR delivery, the full isolated Python 3.12 suite was rerun against final code: **3,739 passed** in
319.26 seconds, with the same existing warning. Staged Gitleaks and staged credential/source-text exclusion checks pass;
only the 11 intended code/test/documentation files are included.
Two real inference requests are recorded above. Output/UI approvals are absent. Actual model quality is unmeasured,
not passing; no complete economic summary exists. The pilot itself involved no crawl, scheduled ingestion,
publication, deployment, commit, push or merge. The owner subsequently requested PR delivery of the runner,
tests and this metadata-only report. Original/response bodies, gold, owner consent and credentials remain local.
No further inference, summary/display approval, merge or deployment is authorised by that delivery.
**NO-GO for economic intelligence and display.**
