# Phase 4K: hosted economic intelligence preparation

1 November 2026, Pacific/Auckland. Base: `13cd20e`, latest main including PRs #34, #35 and #36.

**GO WITH CONDITIONS for PR A integration review. NO-GO for real transmission, accepted intelligence or display.**
No inference endpoint was contacted, including with synthetic content. HTTP tests use MockTransport. No report
text was sent to this agent, another agent, OpenRouter or a model provider. No local model was run. The two
reports' version metadata was frozen by a local read-only SQL query. The existing offline evidence checker
also ran locally, exposing only anchor/comparison counts to this agent; its report text stayed local.

The [hosted proposal](../config/phase-4k-pilot.json) records separate pending decisions. It is inert, grants
nothing and is not loaded by the application. PR #36's [local consent](../config/phase-4j-pilot.json) is unchanged.
Manual import, local processing, hosted processing, gold review, output approval and display remain distinct.

## Model and provider selection

Public GETs to OpenRouter's current `/models`, model `/endpoints`, `/providers` and `/endpoints/zdr` were inspected.
The two candidate routes are preserved in [catalogue evidence](../config/phase-4k-catalogue.json). Availability
and prices are a dated snapshot; check them again immediately before approving any transmission.

| Role | Exact API model | Exact `provider.only` slug | Returned provider label | Input/output US$/M | Context / output limit |
|---|---|---|---|---|---|
| Proposed primary | `anthropic/claude-opus-5.5` | `google-vertex/europe` | `Google` | 4.40 / 22.00 | 1,000,000 / 128,000 |
| Optional comparison, separately gated | `openai/gpt-5.6-sol` | `azure/eu` | `Azure` | 4.40 / 22.00 | 1,050,000 / 128,000 (922,000 prompt limit) |

Both routes were present in the ZDR endpoint list with `safety_retention=false`, operational status 0,
`response_format` support and no implicit caching advertised. Google advertises `max_tokens`; Azure advertises
`max_completion_tokens`. The adapter uses the corresponding field and sends high reasoning effort. There is
one model string, never a fallback list, router alias, tool, plugin, search request, file or document upload.
The API identifiers above were confirmed from the live catalogue, rather than inferred from Codex product names.

Selection rationale: Opus 5.5 is the proposed quality-first primary for dense institutional interpretation and
careful source/numerical extraction. Its [publisher description](https://www.anthropic.com/claude-opus-5-5)
and [OpenRouter model page](https://openrouter.ai/anthropic/claude-opus-5.5) support considering it for financial
analysis; they do not establish accuracy on these two reports. GPT-5.6 Sol provides a separate model family for
comparison if later requested. Sonnet was also available, but price is not the deciding criterion for this bounded
pilot. No empirical model ranking, citation score or economic-accuracy claim is made before the actual evaluation.

Both candidates support long contexts well beyond these documents. JSON-object response mode is paired with
the existing schema-bearing prompt, strict Pydantic contract and deterministic verifier. This is JSON mode,
not a claim of provider-enforced JSON Schema conformance. Schema failures are retained as failures and never
repaired or retried automatically. Six thousand total output tokens include reasoning; insufficient output is a
recorded truncation failure, requiring a new proposal rather than automatic tuning.

## Privacy and security assessment

Every request contains exactly:

```json
{"provider":{"only":["google-vertex/europe"],"zdr":true,"data_collection":"deny","allow_fallbacks":false,"require_parameters":true}}
```

The optional comparison uses only `azure/eu` instead. Full endpoint slugs matter: a base provider slug can match
multiple variants/regions. Direct `anthropic` and `openai` routes are excluded under the current ZDR policy;
they are not substitutes. The server must refuse an unavailable/ineligible route, unsupported parameter or
privacy conflict; the client never relaxes these controls. See [routing schema](https://openrouter.ai/docs/guides/routing/provider-selection)
and [ZDR policy](https://openrouter.ai/docs/guides/features/zdr).

OpenRouter is itself a processor/intermediary, not just an invisible link to Google or Microsoft. Its
[data-collection rules](https://openrouter.ai/docs/guides/privacy/data-collection), [privacy policy](https://openrouter.ai/privacy)
and [terms](https://openrouter.ai/terms) require review alongside the upstream terms. Prompt/output logging and
OpenRouter's product-improvement opt-in must both be off in the actual account. API metadata, billing and account
records can persist. ZDR does **not** rule out CSAM screening, reporting/legal preservation, other legal duties or
all operational retention. The owner must explicitly accept these limitations. An EU upstream slug does not
prove end-to-end EU residency: the fixed OpenRouter endpoint is `https://openrouter.ai/api/v1`.

Upstream review: [Google's Claude documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/partner-models/use-claude)
and [abuse-monitoring policy](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/abuse-monitoring?hl=en)
distinguish model-specific safeguards; do not apply the terms for covered Fable/Mythos models automatically to
Opus. [Anthropic's Google-managed route guidance](https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/google-managed)
also distinguishes cloud processing from the direct API. [Microsoft's data/privacy guidance](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy)
excludes model training without permission, but default abuse monitoring may retain flagged samples; modified
monitoring changes this. OpenRouter marks the selected endpoints ZDR, but the actual upstream account agreements
and modified-monitoring configuration are not visible to this client. Eligibility is based on OpenRouter's
current attestation and enforced request policy, not an independently audited retention guarantee. Any policy
conflict discovered before execution is a stop condition requiring clarification, not weaker routing.

Transport: fixed HTTPS endpoint, TLS verification, no redirects even for an injected redirect-enabled client,
and an owned httpx client with `trust_env=False` (no proxy variables). No automated retries. Unknown/missing
response model/provider, missing/invalid usage or cost, non-JSON output, tools, truncation and excessive usage/cost
are refused. Reported serving label, response ID, tokens, cost and latency are kept in local summary/usage audit
records, including bounded recognised metadata and valid billing on rejected/HTTP-error responses. Unknown
arbitrary labels are dropped to avoid persisting echoed credentials/text. Region identity cannot be independently verified from the provider display
label alone. The requested exact route is recorded separately. Invalid contracts remain unapproved.

Use a **dedicated non-resetting API key capped at US$5**, supplied as `NZSTATS_LLM_API_KEY` by a secure environment
or macOS Keychain-backed launcher. Do not paste it into chat or source files. No credential was read during
preparation. Dedicated-key creation, spending limits and the real account settings remain unverified/pending.

## Independent source permission assessment

No institutional website was crawled or fetched. Earlier owner-browser/manual-import evidence is documented in
[Phase 4H](phase-4h-execution.md) and [Phase 4J](phase-4j-local-pilot.md); indexed copyright/terms descriptions
were checked without retrieving report bodies. This is a preliminary rights assessment, not a new licence grant.

| Exact imported version | Preliminary basis | Outstanding decision | Current hosted verdict |
|---|---|---|---|
| Treasury FEU dated 15 October 2026, version 1; stored publication date 19 October | Crown material is generally CC BY 4.0 unless otherwise marked; third-party copyright is excluded from blanket permission | Human review of this exact PDF's notices, charts, IMF material and other third-party content; permitted hosted input scope; attribution/changes and OpenRouter/upstream terms; explicit Kevin confirmation for Google route | Pending; refuse |
| RBNZ OCR decision dated 28 October 2026, version 2 | Bank material may be reproduced with acknowledgement, accuracy and non-misleading presentation; third-party exceptions apply | Human review of this exact HTML's rights and externally hosted AI processing under the selected terms; exclude browser chrome from approved economic scope; explicit Kevin confirmation for Google route | Pending; refuse |

Rights references: [Treasury copyright/licensing](https://www.treasury.govt.nz/copyright-and-licensing) and
[RBNZ terms](https://www.rbnz.govt.nz/about-our-site/terms-of-use). Source-specific hosted processing is not
explicitly authorised by the earlier storage/local-consent evidence. The third-party material review is not
complete; neither report currently passes the hosted gate. RBNZ's automated-access restriction remains in force.

`HostedConsent` is an independent, expiring record binding institution, exact version, raw/text hashes, canonical
request hash, exact model/provider, owner, time, rights review, provider/privacy review and US$5 budget. Changed
sections, headings, prompt, route or output cap invalidate the request hash. Storage/acquisition and stored
full-text policy are also checked. Source-wide `llm_processing=hosted` cannot bypass the version gate. A valid
version-specific consent can authorise that version without enabling the institution globally.

**PR A deliberately has no approval-file loader or CLI approval writer.** The normal CLI supplies no consents
and therefore refuses all OpenRouter documents, even if an institution is marked hosted. PR B must independently
review the concrete owner decisions, frozen input scope and a bounded runner before making the pilot executable.
The proposal JSON is never a way to enable processing. Treasury can proceed alone if it passes and RBNZ does not.

## Cost bounds and controlled execution proposal

Proposed limits: two versions, one inference attempt per version across all runs/models/prompts, zero retries,
zero fallback, US$5 total inference spend, no background worker or scheduler. Atomic SQLite reservations retain
the rolling spend gate and add lifetime OpenRouter spend plus attempt counts. Failed, zero-charge and interrupted
attempts all count; elapsed billing windows never reset the pilot. Concurrent reservations cannot both use the
same version. Spending above the expected price/usage is audited and refused, not hidden.

The OpenRouter reservation uses full rendered UTF-8 bytes plus 2,048 template tokens as an input ceiling,
rather than the existing chars/3 estimate. At 45,000 source characters, the maximum source bytes are 180,000.
Require rendered input plus output below 272,000 tokens, avoiding the comparison model's long-context surcharge.
Even the admission ceiling at US$4.40/M input plus 6,000 output at US$22/M is below US$1.33 per request and
US$2.66 for two; the actual per-document dry-run bound must fit the remaining US$5 before approval/execution.
No cache discounts are assumed. Upstream billing cannot be reversed by a client-side rejection; the dedicated
key limit is an independent control. Credit-purchase/platform fees are separate from inference token spend.

After all applicable approvals, PR B should:

1. Verify a fresh database/raw backup, hashes and restoration manifest. Freeze registry, version IDs, document
   dates, selected provider/model/prices, prompt/verifier/schema, approved sections and reviewed gold hash.
2. Recheck current model/provider eligibility and supported parameters without sending institutional text.
   Stop on unavailable routes, changed prices or incompatible privacy/retention policies.
3. Record Kevin's source-specific hosted confirmations and selected-provider/privacy/budget approval. Review
   all third-party rights. Never turn on institution-wide hosted permission to make the run work.
4. Prepare a reviewed runner supplying only these expiring consents. Verify one exact dry-run candidate per
   permitted version, rendered input hash, token/cost bound and zero network calls. No schema migration/dry-run
   write before the backup check. Preserve exact framed request/response locally under ignored data, with
   restrictive file permissions, rather than in logs or Git. This provenance capture remains PR B work.
5. Execute serially, at most once per authorised version. Record provider, actual model, tokens/cost, latency,
   stop/error class, summary/run IDs and verifier findings. An error consumes the attempt. No prompt/model or
   verifier changes, repair, retry or comparison run without a separately reviewed proposal.

## Economic evaluation and dashboard readiness

**Real inference requests: 0. Real pilot spend: US$0. Actual-model quality metrics: unavailable.**
No generated economic commentary exists. Earlier deterministic/synthetic scores are not model acceptance.
Human review of both the 4H baseline and corrected 4I gold remains required, including the ambiguities in Phase 4J.

For PR B, report raw and accepted precision, recall, coverage, citation correctness and denominators separately;
also rejected findings and source limitations. Require citations ≥95%, accepted aligned numerical fidelity 100%,
issuer accuracy 100%, and no unsupported policy/economic claims. Audit every IMF-versus-Treasury attribution,
OCR hold/rate/date/4–3 vote, horizon/unit/definition/basis and section/page citation. Keep Treasury repeated-column
table cells refused. Do not invent migration adjustment bases or compare monthly with year-ended series. Keep
historical comparisons bounded by the relevant report cutoff; post-cutoff captures are unavailable. Preserve
the Treasury 15/19 October date ambiguity explicitly. Do not weaken verify-3 to improve acceptance/coverage.

PR C remains blocked. The existing private API is a foundation, but there is no approved summary or display
permission. An actual person must approve the output and separate private-display rights before the polished
Economic Outlook frontend is built. Current institution LLM gates also keep the preview empty; version-specific
processing/display compatibility will need review in PR C. Public/static research, Netlify exposure and public
permissions remain disabled. No scheduler or UI change is part of PR A.

## Verification and delivery

Verification results and review receipt are recorded in [progress](progress.md). Synthetic provider/hosted tests
cover credentials, exact routing, unsupported/unsafe configuration, HTTP errors/timeouts/redirects, malformed
JSON, usage/cost anomalies, consent mutations/expiry, concurrency, repeated failures, dry-run costs and audit.
The full backend, frontend/browser and privacy/isolation suites are regression evidence, not model evaluation.

Delivery is PR A only, with independent Codex High review limited to three cycles and no automatic merge.
PR B (approvals/real pilot) and PR C (private frontend) must wait for their explicit gates. Remaining blockers:
source rights and exact scope, Kevin's hosted/provider/budget approvals, actual account/key controls, fresh backup,
human gold review, real evaluation, human output approval and separate private-display/UI approval.
