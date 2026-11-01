# Phase 4L: controlled hosted pilot — approval hold

1 November 2026, Pacific/Auckland. Baseline: `7922fd78e7ea17077faebded0157af35f2164449`, latest main
after [PR #37](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/37), merged at 20:34 NZDT.
Implementation/verification configuration: Codex `gpt-6.1-sol`, reasoning `high`.

**NO-GO for inference or displaying insights. GO WITH CONDITIONS for preflight review.** Stage 2 has
outstanding owner decisions for both documents. No pilot inference request was made, including synthetic probes;
pilot inference spend remains **US$0**. Actual-model economic metrics are **unavailable**, not zero or passing.
No optional GPT run, source-permission change, summary approval, private/public display activation, institutional
crawl, scheduler, publication or deployment occurred.

This is an approval-hold deliverable, not completion of the real pilot. The adapter, verifier and original
[4K proposal](../config/phase-4k-pilot.json) are unchanged. PR #36's
[local-only consent](phase-4k-local-processing-approval.md) grants no hosted-processing authority.

## Preflight evidence

| Requirement | Evidence / outcome |
|---|---|
| Latest merged baseline | PR #37 merged; local HEAD and freshly fetched `origin/main` both `7922fd7` before branching |
| Reviewed integration CI | [PR #37 run 41283475739](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/41283475739): backend, frontend, static-site and Docker all passed on `6f04a21` |
| Merge CI | [Run 41285323041](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/41285323041), tracked separately from the PR-head run; see verification below |
| Fresh backup | `data/backups/pre-4l-20261101T074522Z`: schema 13, manifest/database and **45/45** raw artifact hashes verified by `verify_bundle` |
| Restore | `data/phase-4l/restore-20261101T074522Z`: verified restore into a new directory; order-independent row digests and counts of **all 32 tables** match the live read-only snapshot |
| Data integrity | Raw hash, stored raw/text hashes and fresh extraction agree for both versions; every field of **7 Treasury / 15 RBNZ sections** agrees. Live table digests unchanged after backup/extraction |
| Permissions | Both: manual import approved, full-text storage, `needs_review`, LLM denied, private/public display none. Crawlers remain refused |
| Independent hosted gate | Read-only `summarise_versions(..., dry_run=True, hosted_consents=())` with a network-blocking MockTransport refuses both exact versions for missing/mismatched consent: **0 network calls, 0 DB changes, no run/reservation** |
| Pilot ledger | Live `research_summary`, `research_llm_usage` and `research_llm_reservation`: **0 rows** each |

The refusal probe is not a dry run of approved input and does not approve a request hash. The backup was created
from a SQLite `mode=ro`, `query_only` connection through the existing bundle function; no runtime construction,
migration or CLI serve/refresh occurred. Recheck backup freshness and live state before eventual execution.
Local-only detailed evidence: `data/phase-4l/preflight.json`, `refusal-probe.json` and the verified backup manifest.
The final comparison found all 31 non-`ops_process` tables unchanged. In `ops_process`, only an existing
process's `last_heartbeat_at` advanced; all other fields and the six-row count agree. The all-32-table equality
above describes the backup/restore snapshot, not a claim that an active dashboard's heartbeat never changes.

| Exact version | Original raw SHA-256 | Original text SHA-256 |
|---|---|---|
| Treasury v1, FEU dated 15 October; stored publication 19 October 2026 | `63aaa9df152fb8793e3ec1f7489e79893cc38c5985ad8fbf2afba78565483073` | `d5f72d5eb82977459f6ff6e9158fb88cede1aebeb059a1adf742ff44d868dc4b` |
| RBNZ v2, OCR decision, 28 October 2026 | `ee38b509c027e828f66c35ea20ed8d6658ab1db0e6a5a97e19a8f7e921fb32ed` | `ca5486fb5ea1b85666a117650e4d3271376cc7184d62d2004c88def843191290` |

## Model, provider and privacy

Four unauthenticated public GETs refreshed the model list, Opus endpoint list, provider list and ZDR endpoint
list. [Catalogue evidence](../config/phase-4l-catalogue.json) records retrieval times, response hashes and the
selected entry. Full public JSON responses remain under ignored `data/phase-4l/`.

| Field | Fresh result |
|---|---|
| Endpoint | `https://openrouter.ai/api/v1/chat/completions` |
| Model / canonical catalogue slug | `anthropic/claude-opus-5.5` / `anthropic/claude-opus-5.5-20260921` |
| Exact upstream route / response label | `google-vertex/europe` / `Google` |
| Prices, US$/million tokens | **4.40 input / 22.00 output**, unchanged; no cache discount assumed |
| Availability | Exact route present in both endpoint lists, status `0`, `safety_retention=false`, implicit caching false |
| Compatibility | Advertises `max_tokens`, `response_format`, `reasoning`, `reasoning_effort`; context 1,000,000, maximum completion 128,000. Pilot output stays 6,000 including reasoning |

Required request policy stays:

```json
{"provider":{"only":["google-vertex/europe"],"zdr":true,"data_collection":"deny","allow_fallbacks":false,"require_parameters":true}}
```

The route is proposed, not owner-approved. Recheck availability, identity, price, parameter compatibility and
`safety_retention=false` immediately before any transmission. Stop on changes; never substitute another route.
The returned `Google` label does not independently prove region or actual upstream account configuration.
The public provider record identifies Google, with [cloud terms](https://cloud.google.com/terms/) and
[privacy notice](https://cloud.google.com/terms/cloud-privacy-notice); this is not access to OpenRouter's contract.

[OpenRouter ZDR guidance](https://openrouter.ai/docs/guides/features/zdr) distinguishes model groups and allows
some safety-retaining endpoints depending on account/guardrail settings. Require explicit strict zero-retention
settings for the applicable model group/route; do not rely on account defaults or `zdr=true` alone. This route's
fresh `safety_retention=false` is an attestation, not an independent audit. Request policy is unchanged.

[Data collection guidance](https://openrouter.ai/docs/guides/privacy/data-collection) describes separate logging
and product-improvement opt-ins, metadata retention, anonymous ZDR-model categorisation and CSAM/legal exceptions.
Both opt-ins must be off. ZDR does not mean no processing by OpenRouter, no legal preservation or guaranteed
end-to-end EU residency. Owner acceptance of these limitations remains pending. Review the
[privacy policy](https://openrouter.ai/privacy) and [terms](https://openrouter.ai/terms), including input rights.

[Anthropic's Google-managed guidance](https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/google-managed)
places data handling with Google Cloud. Neither public documentation nor the catalogue establishes the upstream
account's logging/monitoring arrangements. Resolve any conflict before approval. Direct Anthropic, other Google
regions and the optional GPT route are not authorised substitutes.

No account, Keychain entry or real API credential was read. A **dedicated US$5 non-resetting key limit**, zero
prior pilot usage and disabled logging/training preferences remain **unverified**. The updated isolated Python
3.12 verification environment passes its audit; that does not certify the old shared runtime for execution.

## Source-specific rights and exact input decisions

Public indexed licensing/terms pages were reviewed; no project client fetched institutional pages or reports.
The exact imported bytes were inspected only by local extraction/hash/marker code, with source text kept out
of this hosted agent and reviewer. This cannot establish legal ownership or replace a person's rights review.

| Source | Basis and exact-document observations | Outcome |
|---|---|---|
| Treasury v1 | [Treasury licence](https://www.treasury.govt.nz/copyright-and-licensing): Crown material normally CC BY 4.0, with item-specific and third-party exceptions, logos excluded. Local scan flags third-party names in sections 0–2 and source labels in 0–3. Original PDF charts and IMF material require inspection; the absence of extracted copyright keywords proves no permission | **Hosted processing withheld** pending exact third-party rights and section review, attribution/changes plan and explicit owner consent |
| RBNZ v2 | [RBNZ terms](https://www.rbnz.govt.nz/about-our-site/terms-of-use): Bank material may be reproduced accurately with acknowledgement; identified third-party material excluded. No selected third-party-name markers occur in extracted sections; this is not proof of absence. Section 0 is browser chrome and must be excluded. Automated access still needs separate written permission | **Hosted processing withheld** pending exact saved-HTML rights review, permitted external processing under selected terms and explicit owner consent |

There are **no approved input sections for either source**. The local packet
`data/phase-4l/owner-review.html` (mode `0600`, inside a `0700` directory) presents the 22 section texts, page
references, raw-document identity and both annotation files for owner inspection. RBNZ saved HTML is escaped,
not executed; Treasury's original local PDF must also be read for visual table/chart ownership. The local
preflight JSON inventories each section's text and heading hashes. The packet is ignored, contains third-party
material and must not be committed or uploaded. It is a review aid, not an economic output or approval record.

Record these separate decisions, with Kevin's name, explicit approve/deny, UTC approval/expiry times and evidence:

| Decision ID | Concrete decision still required |
|---|---|
| `treasury_v1_hosted_rights_scope` | Review the exact PDF and all notices/charts/IMF material. For every retained section in ordinals **0–6**, record the rights basis covering hosted processing, third-party exclusions and attribution/changes. Approve only the chosen ordinal list and its hashes for **Opus 5.5 → google-vertex/europe through OpenRouter**, or deny/defer Treasury |
| `rbnz_v2_hosted_rights_scope` | Review the exact saved HTML and third-party exceptions. Select from ordinals **1–14**; **exclude 0**. Record rights basis, attribution and explicit permission for the same hosted route, or deny/defer RBNZ |
| `primary_route_privacy` | Accept the exact model/route, OpenRouter intermediary, upstream terms and retention/legal/residency limitations above, conditional on a fresh matching check |
| `dedicated_key_budget` | Confirm the dedicated key has a **US$5 lifetime limit with no reset**, pilot-only use, prior usage accounted for, and no other consumer. Supply it only through secure environment/Keychain; never chat/Git |
| `account_controls` | Record dated, non-secret evidence that private input/output logging and product-improvement/training are off, strict zero-retention controls apply, and no safety-retention exception or auxiliary logging integration applies to this route |
| `gold_human_review` | A person reads both originals and baseline/gold, resolves the worksheet below and signs a separate reviewed gold copy with its SHA-256 and scope coverage |
| `exact_request_freeze` | After section selection, review canonical rendered input hash, ordered sections/headings, source dates, prompt `outlook-v3`, contract 2, `verify-3`, processing `3b-1`, caps and conservative cost bound. Record one expiring `HostedConsent` per approved version |

These decisions are independent. One source may proceed while the other remains withheld. Rights review cannot
grant rights a third party has not licensed. A broad “go ahead” or merge of this PR does not fill missing evidence.
No approver, timestamps, rights findings, request hash or reviewed-gold hash has been invented.

The normal pipeline currently loads **all stored sections**. A later reviewed bounded runner must actually
enforce the approved subset, fail closed on any extra/missing/changed section and hash the exact request; merely
writing an ordinal list in a manifest does not exclude browser chrome or third-party material. No approval loader
or executable pilot runner is added while the owner decisions are unresolved.

## Gold review worksheet and economic acceptance

Original gold remains `data/annotations/phase-4i-evaluate.json`, SHA-256
`f04d64f0960497053b7c3a990ca8efa0244f80e11394e9133f0482655ba68711`; original baseline remains
`693fce86718e4baf0121197c203abaa15a9202fc1bd14fb29d33e09c8f57836b`. Neither was changed or marked reviewed.
**Human review is outstanding.** The offline checker was rerun against current main:

| Reference problem | Required disposition before scoring real output |
|---|---|
| 46 anchored items | All 46 quotes/offsets and page references match. Location alone does not establish claim meaning or classification |
| Four Treasury GDP/CPI table cells | Still `table_column_unverified`; retain as expected rejections/coverage limitations. Visual review cannot repair lost column structure in the extractor. Never count these as accepted forecasts or silently remove their rejection checks |
| Treasury migration gold | Still `horizon_not_supported`; correct the gold's horizon only if explicit original evidence supports it; otherwise exclude from accepted-gold expectations and retain a documented rejection case |
| Treasury versus IMF | All 9 annotated forecast issuers pass when kept. Swapping issuers produces 7 errors, **2 warning-only** cases (Treasury items 26/28). Human audit of every retained third-party forecast is mandatory; warnings do not prove 100% attribution |
| RBNZ decision | Broad combined evidence still yields `decision_action_not_supported` and `decision_rate_contradiction`. Candidate correction from 4J: policy item 0, **section 2 only**, rather than the mixed discussion in section 13. A person must confirm hold **2.75%**, **28 October 2026**, **4–3**, then freeze the narrowed evidence |
| Fact/forecast and horizon scope | Mixed passages still flag `forecast_as_fact` (Treasury 3, RBNZ 1). Keep RBNZ CPI “December quarter” and annual-rate basis; invent neither year nor quarterly change. Reclassify or narrow only from source evidence |
| Historical comparisons | **7 match, 9 unavailable at cutoff, 2 uncomparable**. No later-vintage replacement; no invented migration adjustment basis. Preserve Treasury report date 15 October separately from stored publication 19 October |

These are deterministic reference findings, **not model performance**. The checker returns zero despite refused
reference claims; its exit status is not the acceptance gate. Existing statistical rules and thresholds are intact.

| Real-model metric | Required gate | Actual result / denominator |
|---|---|---|
| Citation correctness | ≥95%, with claim/section/page/quote audit | Not measured / 0 generated claims |
| Accepted aligned numerical fidelity | 100% with horizon, unit, basis, sign and column ownership | Not measured / 0 accepted aligned forecasts |
| Forecast issuer accuracy | 100%, including every Treasury/IMF attribution | Not measured / 0 generated forecasts |
| RBNZ policy decision | Correct action, rate, date and votes; no decision-as-forecast | Not measured / 0 generated decisions |
| Unsupported tables/comparisons | Rejected; report omissions and reasons | Reference refusals reproduced; no generated claims to assess |

After approvals and the independently reviewed runner, execute serially: at most v1 Treasury and v2 RBNZ, one
attempt each across all runs, **US$5 lifetime**, retries zero, fallback zero, no optional GPT invocation. An error
or interrupted attempt consumes its slot. Preserve exact framed request/response locally with restrictive modes,
requested/returned identities, response ID, summary/run IDs, usage, cost, latency, errors and verifier findings.
Do not repair/retry malformed output or adjust the prompt/verifier after seeing results without separate review.
Account for missing/failed results and raw versus accepted precision/recall/coverage separately; empty denominators
cannot pass a percentage gate. Prepare claim-by-claim evidence for a person's inspection; never auto-approve.

## Private API readiness

**NO-GO for exposing hosted-generated summaries today.** The existing loopback-only private API retains useful
controls: separate private-display permission, verified plus reviewer-approved output, current-version/duplicate/
purge checks, same-origin/Host/header checks, `no-store`, evidence and attribution, and re-verification on read.
The 241 focused checks include private API/gate regressions; no route was enabled.

However, `research/private.py::_assess` calls the institution-wide `private_display_level` and `llm_refusal`.
It does not consult version-specific `HostedConsent`, and that processing record is not persisted as a display
authorisation. A properly version-approved hosted result would still be withheld with the registry denied.
Setting an institution globally hosted to make it appear would broaden permissions and is not an acceptable fix.

A later separately reviewed change needs durable, revocable exact-version processing provenance and independent
display approval checked on every read, while preserving all existing controls. Expiry/revocation semantics must
be explicit: processing consent is not display consent. Actual verified output, human summary approval and separate
private-display/UI approval are prerequisites. Public display remains a separate decision and is outside this pilot.

## Verification and delivery

- Focused hosted/provider/budget/private/evaluation suite: **241 passed**; only the existing Starlette/httpx warning.
- Backend Ruff lint and format: pass, 323 files unchanged.
- `npm audit --audit-level=low`: **0 vulnerabilities**.
- Updated isolated Python 3.12 runtime: `pip-audit --path ... --skip-editable`: **no known vulnerabilities**;
  the unpublished editable `nzstats` distribution is the sole skip. No shared-runtime upgrade is claimed.
- Full Python 3.12 backend: **3,703 passed**, one existing Starlette/httpx deprecation warning, 320.81 seconds.
  Receipt: ignored `data/phase-4l/backend-tests.log`. Frontend/browser suites were not rerun locally for these
  documentation-only changes; PR CI runs the repository's normal checks.
- Markdown local links, balanced fences, catalogue JSON and staged diff checks pass. Staged Gitleaks: no leaks.
- Independent Codex `gpt-6.1-sol` / high review of the three-file preflight deliverable: **no actionable material
  findings**. Rights, human gold, account controls, local backup/database and local test/audit assertions were
  outside that review's evidence boundary. Receipt: ignored `data/phase-4l/independent-review.txt`.
- Merge/PR CI status is tracked separately in [progress](progress.md) and the PR. At the pre-push check the
  merge's backend/frontend/static jobs passed; Docker was still running. Synthetic test passes do not establish
  model quality.

Delivery is a focused preflight/decision PR only, with independent Codex Sol 6.1 High review requested; **no
automatic merge**. Stage 3 inference, Stage 4 actual-model evaluation and Stage 5 output/display approval remain
blocked by the specific decisions above. No accepted economic insights exist to display.
