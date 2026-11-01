# Phase 4J: first local economic intelligence pilot

1 November 2026, Pacific/Auckland. Started from latest main `c09a759`, the merge of PR #33.

**Current verdict: NO-GO for an accepted economic intelligence workflow.** No pilot model has run and there are no
summaries to approve. Stages 1–2 have a reproducible preflight and a concrete approval proposal. Stages 3–4
remain gated by the owner's explicit instructions. This is not evidence of model quality.

CI remediation is separate: [PR #34](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/34).
This branch changes no verifier, source registry or display permission. It tightens the research contract to
reject non-finite numeric values before verification or storage.

## 1. Annotation review and current deterministic results

Inputs: [Phase 4H execution](phase-4h-execution.md), [Phase 4I quality](phase-4i-research-quality.md),
[PR #33 audit](pr-33-verification-audit.md), and the [research runbook](data-sources/research.md).
The report bodies and annotations remain under ignored `data/`. They were checked by local Python code without
printing source text into this agent's model context. This technical review does not substitute for human
reading of the economics or approval of the Claude-written annotations.

Reproduce from the repository root using the installed backend Python environment:

```sh
python scripts/check_research_baseline.py data/phase-4h/annotations/baseline-2026-10-31.json \
  --gold data/annotations/phase-4i-evaluate.json --db data/nzstats.db
```

The checker opens SQLite read-only and does not call a model. Its exit code is **not an acceptance gate**:
it returns zero even when individual reference claims fail. Read its findings and counts.

| Check on current main | Finding |
|---|---|
| Two imported documents | Version 1 Treasury PDF; version 2 RBNZ HTML. Raw bytes, stored content hash, text hash and fresh extraction agree. All fields of 7 PDF and 15 HTML sections, including offsets, agree |
| Evidence integrity | 46/46 anchored quotes match their recorded section offsets and locate without truncation; 46/46 page references are inside their sections |
| Issuer attribution | Correct issuer gives no issuer finding for all 9 annotated forecast items. Swapping issuers gives 7 errors and 2 warnings; Treasury items 26 and 28 are warning-only (`issuer_unclear`) |
| Treasury table forecasts | All four author GDP/CPI gold cells remain refused with `table_column_unverified`. No rule or threshold was relaxed |
| Other gold forecasts | Treasury migration draws `horizon_not_supported`; the RBNZ December-quarter CPI forecast passes. These are current findings, superseding the earlier check's clean migration result |
| Fact/interpretation classification | The checker's value-free reference records pass for 12/15 Treasury facts and 6/7 RBNZ facts; 3 and 1 respectively receive `forecast_as_fact`. All 12 interpretation records pass that limited check |
| Split minus sign | Keeping the sign passes the value check; dropping it is caught |
| RBNZ decision | Combining both annotated decision passages fails `decision_action_not_supported` and `decision_rate_contradiction`. Using policy item 0 alone (section 2) verifies the hold, rate, date and 4–3 vote without errors or warnings. Policy item 1 (section 13) exposes both hold/increase language and two rates to the adopted-clause check |
| Decision mutation probes | Missing/wrong votes remain caught. Filing the decision as a forecast remains refused |
| Historical comparisons | 7 matches, 9 `no_official_value`, 2 `not_comparable`. The 9 unavailable cases are Treasury CPI, GDP and labour figures. Their relevant vintages were captured on 29 October, after the report; they are withheld rather than backfilled into a historical answer |
| Monthly migration | Both figures remain uncomparable: adjustment basis is not stated. An invented seasonal adjustment is rejected |
| Gold-constructed aggregate | Raw forecast precision/recall and numerical/issuer/decision metrics are 1.0, but accepted recall and verified rate are 0.0. These synthetic reference outputs are **not** model results or accepted summaries |

### Ambiguities requiring review

- **Treasury dates:** the report is dated 15 October; the annotation records issue date 19 October and the stored
  publication date is 19 October. Preserve both labels. The current comparison uses the stored publication date;
  choosing 15 October instead requires an explicit decision, not a silent database correction. The 29 October
  captures are ineligible at either cutoff.
- **PDF table layout:** repeated year groups and detached real-GDP/inflation and actual/forecast labels do not
  preserve column ownership in extracted reading order. The four table gold values describe the annotation,
  not verifiable accepted forecasts. Human review of the original page is still needed. Keep these cells refused
  until a separately tested column-aware extractor exists; do not infer columns or change the verifier here.
- **Source versus forecaster:** the Treasury reports IMF material. Items 26 and 28 show that the lexical issuer
  gate alone cannot guarantee 100% attribution. A reviewer must explicitly audit every retained third-party
  forecast, including warning-only cases. An issuer warning is not a clean acceptance.
- **Reference scopes:** the unsupported migration horizon, mixed fact/forecast passages and broad RBNZ vote
  citation need human assessment in context. Exact quotation proves location, not classification or horizon.
  The narrower decision citation is a candidate correction, not an owner-approved annotation change.
- **RBNZ horizon:** retain “December quarter” as in the 4I gold. Do not add an unstated year or reinterpret an
  annual CPI rate at a quarter as a quarterly change.
- **RBNZ page chrome:** section 0 is a browser-warning banner and supplies no economic evidence.
- **Other extraction hazards:** chart axes remain in PDF sections 0–3; four private-use bullet glyphs remain
  quality warnings. Neither authorises taking a number without a clear row, column and sign.
- **Original import notes:** append-only import audit notes retain a literal `<date>` placeholder. No download
  date was invented and no historical audit row was edited.
- **Annotation units:** Phase 4H's `people` unit is invalid for the contract. Keep that file as history; use 4I's
  `persons`. Both sets remain marked owner review pending.

Pinned original annotation SHA-256 values (unchanged):

| File under ignored `data/` | SHA-256 |
|---|---|
| `phase-4h/annotations/baseline-2026-10-31.json` | `693fce86718e4baf0121197c203abaa15a9202fc1bd14fb29d33e09c8f57836b` |
| `annotations/phase-4h-evaluate.json` | `74d4d9fd4251b584fac6c4d7823e723fb163c4fd21a8c6eceb8718eb0c066bcc` |
| `annotations/phase-4i-evaluate.json` | `f04d64f0960497053b7c3a990ca8efa0244f80e11394e9133f0482655ba68711` |

Local evidence: `data/phase-4j-baseline-check.log`, `phase-4j-extraction-audit.json`. Initial number-only annotation
checks also flag numbers requiring surrounding context; they are triage, not claims of numerical errors.
The current checker does not validate the numerical meaning of every value-free fact. Human review remains required.

## 2. Proposed local runtime and model

The [proposal manifest](../config/phase-4j-pilot.json) is inert: no application reads it and it grants nothing.
Every approval has its own pending record. Only publisher metadata and documentation were fetched; no weights,
runtime package or institutional page was fetched, and no inference endpoint was contacted.

| Selection | Pinned proposal |
|---|---|
| Machine | Apple M4, 24 GiB unified RAM (`hw.memsize = 25769803776`); memory-pressure snapshot reports 63% free. This is not a loaded-model fit test |
| Weights | Official [Qwen/Qwen3-14B-GGUF](https://huggingface.co/Qwen/Qwen3-14B-GGUF), `Qwen3-14B-Q5_K_M.gguf`, revision `530227a7d994db8eca5ab5ced2fb692b614357fd` |
| Licence/size | Apache-2.0; publisher metadata reports 10,514,569,568 bytes (9.79 GiB) |
| Expected SHA-256 | `e7c9aba1129ca2936be9eca01419d9f86af40e08caa01230d5574b34d08e3e31` from publisher LFS metadata. Nothing was downloaded in this task; the downloaded hash remains unset |
| Runtime | [llama.cpp v0.8.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.8.0), commit `8642541b255bfb5dc39cd351a178be09013a55d6`; build `llama-server` with Metal after approval. Record version, executable SHA-256, build flags and compiler version |
| Server | `127.0.0.1:8081`, alias `phase4j-qwen3-14b-q5km`, one slot, 32,768-token context, Q8_0 K/V cache, seed 42, no thinking, no context shift |
| Request | Existing `openai_compatible` adapter, loopback `/v1`, temperature 0, 6,000 maximum output tokens, 900-second timeout, zero retries, one document per source |

The base model configuration has 40 layers, 8 KV heads and head dimension 128. A full 32k Q8_0 K/V cache is
approximately 2.66 GiB before runtime overhead; 9.79 GiB weights plus that cache is a plausible fit with room for
the OS and compute buffers. This is an estimate. Check actual resident/Metal memory and pressure after loading;
stop on load failure, memory pressure or insufficient context. Do not silently substitute a smaller model.

Rendered request estimates are 40,192 characters / 13,398 conservative tokens for Treasury and 31,082 / 10,361 for
RBNZ (author framing adds a few characters). These are the adapter's characters/3 budget estimates, **not tokenizer
measurements**. After approval, measure actual templated tokens and require input + 6,000 output + 2,048 headroom
≤ 32,768. No truncation, context shifting or silent reduction of evidence.

The [model card](https://huggingface.co/Qwen/Qwen3-14B) documents the hard `enable_thinking=false` switch.
The adapter's temperature 0 differs from Qwen's recommended sampling defaults; retain it for this bounded
baseline, record repetition/JSON failures and do not tune automatically. Greedy decoding is not a guarantee of
identical bytes across GPU builds. The prompt also contains a random framing boundary; its canonical input hash
excludes that boundary. Record template/runtime hashes and all settings, without claiming bitwise reproducibility.

### Prepared launch settings — use only after approvals

The flags are checked against the pinned runtime's documentation, not a locally installed executable. After
approved installation, inspect `--help` and `--version` first; stop if the pinned build differs.

```sh
# WEIGHTS and LLAMA_SERVER are absolute paths selected after approval, outside tracked source.
# Run the server and the CLI under the profile. Do not use -hf or a model router.
sandbox-exec -f config/phase-4j-loopback.sb "$LLAMA_SERVER" \
  --model "$WEIGHTS" --alias phase4j-qwen3-14b-q5km \
  --host 127.0.0.1 --port 8081 --ctx-size 32768 --parallel 1 \
  --n-gpu-layers 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 \
  --batch-size 512 --ubatch-size 128 --seed 42 --n-predict 6000 \
  --jinja --chat-template-kwargs '{"enable_thinking":false}' \
  --no-context-shift --offline --no-webui
```

Use a clean CLI environment, without sourcing `.env` or inheriting keys/proxies. Set the following variables
explicitly, plus `NZSTATS_DATA_DIR` and the reviewed `NZSTATS_RESEARCH_SOURCES_FILE`; invoke the installed Python
CLI directly from the repository root. `env -i` with a selected `PATH` is suitable. Nothing should start a dashboard,
refresh or scheduler for the pilot.

```text
NZSTATS_LLM_PROVIDER=openai_compatible
NZSTATS_LLM_BASE_URL=http://127.0.0.1:8081/v1
NZSTATS_LLM_MODEL=phase4j-qwen3-14b-q5km
NZSTATS_LLM_INPUT_USD_PER_MTOK=0
NZSTATS_LLM_OUTPUT_USD_PER_MTOK=0
NZSTATS_LLM_MAX_INPUT_CHARS=45000
NZSTATS_LLM_MAX_OUTPUT_TOKENS=6000
NZSTATS_LLM_TIMEOUT_SECONDS=900
NZSTATS_LLM_MAX_RETRIES=0
NZSTATS_LLM_MAX_DOCUMENTS=1
NZSTATS_LLM_MAX_RUN_USD=1
NZSTATS_LLM_MAX_PERIOD_USD=10
```

Local zero prices do not bound computation: the document count, token cap, timeout and two-attempt ledger do.
The adapter's timeout is a transport timeout, not an absolute whole-run wall deadline; use a 960-second external
deadline per attempt and stop the server if it expires. A killed attempt counts against the two-document limit.

### Network and JSON checks

The adapter ignores proxies, refuses redirects and classifies a numeric loopback URL as local. A URL alone does
not prove offline execution. Apply [the network profile](../config/phase-4j-loopback.sb) to **both** server and CLI.
It denies networking except requests to the loopback model port and that listener's inbound/bind operations.

A standard-library socket probe under this exact profile passed: loopback request/reply; policy-denied outbound
TCP and UDP to a documentation-only address; denied another loopback port; denied outbound UDP even with the
socket bound to 8081. These tests never contacted an LLM. Evidence: `data/phase-4j-network-probe.json`.
The sandbox's `localhost` bind filter did **not** reject a wildcard bind in a separate probe. Therefore the runtime's
explicit `--host 127.0.0.1` and an actual `lsof -nP -a -p PID -i` listener inspection remain mandatory. Refuse an
unexpected listener; capture process/child sockets before, during and after inference. Socket snapshots alone
cannot prove absence of short-lived traffic. If sandbox enforcement is unavailable, stop instead of running
unrestricted. This profile is not a file-access sandbox.

Before either document, test only synthetic JSON through the approved local server: model alias/version identity,
non-thinking response, token usage, context settings and strict parsing. The existing adapter sends the schema in
the prompt; it does **not** request grammar-constrained decoding. `parse_draft` rejects duplicate keys, trailing
non-JSON text, extra fields, non-finite numbers and oversized/invalid output (one JSON code fence is tolerated by
the existing parser). A truncated finish reason fails. Contract validation and verify-3 remain separate required
checks. Do not repair JSON, relax validation or retry failures automatically.

The synthetic preparation probe found that Python's JSON parser and the previous Pydantic configuration accepted
`NaN`, `Infinity`, `-Infinity` and exponent overflow. Eleven failing-first cases cover facts, forecasts and stored
summary parsing. The shared research contract now sets `allow_inf_nan=False`; malformed non-finite numbers fail
validation. Existing finite-value and parsing regressions remain in place. No evidence rule changes.

## 3. Independent approvals and controlled execution

All rows below are **pending**, with null approver/date/evidence in the manifest:

| Approval ID | Exact proposed authority |
|---|---|
| `treasury_local_only` | Set Treasury `llm_processing = "local_only"`, with its own owner/terms/date note |
| `rbnz_local_only` | Set RBNZ `llm_processing = "local_only"`, with its own owner/terms/date note |
| `selected_model_and_runtime` | Select the pinned Qwen weights and llama.cpp release/settings above |
| `weights_download_and_local_execution` | Download the pinned weights and runtime/build inputs, hash them, then execute locally under the controls above |
| `gold_owner_review` | Human review of the annotation files and ambiguities above before scores count as acceptance |

The first four approvals are required before any model download or document inference. Record the owner's
explicit response separately for every ID; never infer one permission from another. Registry notes are separate
reviewable edits per source after approval; this manifest is not consulted by the application and cannot enforce
the gate. Preserve manual-import acquisition, denied crawlers and `public_display = private_display = "none"`.
Terms were directly reviewed for manual storage in Phase 4H; this proposal does not pretend they already approve
LLM processing or private display.

After the required owner approvals:

1. Verify a fresh database/raw bundle backup before any write. Freeze the two version IDs, raw/text hashes,
   current registry, reviewed gold hash, prompt/verifier versions and run manifest. Confirm no prior pilot attempt.
2. Acquire only the approved pinned weights/runtime. Compare the downloaded bytes with publisher hash/size;
   capture executable/template/build provenance. A hash mismatch stops the pilot. Do not use mutable `main` URLs.
3. Run the network probes, actual bind/memory/token checks and synthetic JSON smoke. Never send a source
   document to Codex or another hosted model for diagnosis, review or JSON repair.
4. Dry-run each source with exact version pinning under the clean environment/profile:
   `python -m nzstats.cli research summarise treasury --version 1 --limit 1 --dry-run` and the equivalent
   `rbnz --version 2`. Confirm one intended candidate, local provider, no truncation and no model calls. The CLI
   opens a writable connection and applies pending migrations even in a dry-run, so verify schema currency
   before invoking it; the summariser itself writes no dry-run audit or summary rows.
5. Remove only `--dry-run`. Run once per source, serially, recording the attempt before starting. This is a
   **pilot-wide** cap, not merely a per-invocation CLI limit. Re-running after a failure can otherwise create a
   new attempt; do not do so. Record provider/parse/verifier failures and stop on unexpected errors.
6. Keep raw responses, evidence and logs under ignored local data. Record run/summary/version IDs, timestamps,
   wall and provider latency, input/output tokens (reported versus estimated/missing), finish reason,
   validation codes, warnings and the weights/executable hashes for each attempt, including failed attempts.
7. Evaluate with the reviewed gold using `research evaluate --annotations FILE --model phase4j-qwen3-14b-q5km`.
   Record raw and accepted metrics and denominators separately. Review every quote, value, unit, horizon,
   scenario, issuer and decision, including all numbers in prose. No source quote goes into a public PR.
8. Require Kevin's review before issuing any `research approve`. The agent must not approve on Kevin's behalf.
   A failed/ambiguous summary is withheld. Another attempt or modified model/prompt is a separate proposal.

Acceptance is the user's Phase 4J standard: citation correctness ≥95%; 100% numerical fidelity for accepted
aligned forecasts; 100% issuer accuracy; no IMF attribution to Treasury; no policy decision as a forecast;
Treasury table ambiguity refused; no unsupported Stats NZ comparison. Also report decision completeness and
fidelity, all warnings and exclusions. Passing a metric cannot override a known false attribution or quotation.
The earlier 4I raw-recall target of 5/6 is historical; it cannot justify accepting ambiguous table cells or bypassing
the current verification failures. Missing fields/claims remain visible in the failure report.

## 4. Deferred private browser UI

Build a separate UI PR **only after** reviewed summaries exist, per-source `private_display = "summary"`
approvals are recorded, and the owner approves `private_browser_ui`. These remain separate pending manifest rows.
The existing Phase 4I private router is the data source: `/api/private/research/items` and `…/items/{id}`, with
`X-NZStats-Client: dashboard`, loopback/same-origin checks, no caching and operator opt-in. Do not reuse the
public research endpoints for private data.

Use the established Economic Outlook design. Show institution, report date and publication date distinctly,
executive outlook, drivers/risks, author forecasts, separately labelled third-party forecasts, OCR decisions and
votes, and evidence with page/section. Keep institutional commentary visibly separate from official statistics.
The private API currently carries reported figures but no Stats NZ comparison values. A later comparison needs
a read-only private API addition using `official_compare`, with eligible historical capture, definition and
precision checks; do not substitute current dashboard values in the browser. Withhold the 9 unavailable and 2
uncomparable cases recorded above.

The preview stays off by default and loopback-only. No public research display, static research snapshot,
publication, scheduler, Docker or hosting work is authorised. No UI scaffold is built by this preflight.

## 5. Verification and decision record

Current evidence and final independent review are recorded with this PR and in [progress.md](progress.md).
Independent Codex High review found no actionable issues in the final contract change or approval packet;
its own 46 contract tests passed on Python 3.14. It did not inspect private documents or validate a model.

| Verification | Result |
|---|---|
| Full backend, Python 3.12, after contract change | 3,593 passed; includes statistical, integration, security and research regressions |
| Failure-first non-finite probes | All 11 failed before the guard; all 46 contract cases pass after it |
| Backend lint/format and synthetic replay | Pass; all recorded metric floors retained, 38/38 labelled probes |
| Frontend and existing browser regressions, CI-remediation toolchain | 524 unit tests; types/lint/build; live 174; research 18 (3 skips); local static/parity 315 (24 skips) |
| Research browser after contract hardening | 18 passed, 3 expected screenshot skips |
| Public OpenAPI, source registry and verifier | OpenAPI byte-identical; no registry or verifier changes |
| Security and documentation | Staged Gitleaks and diff checks pass; pending-approval manifest JSON and local documentation links validated; original annotation hashes unchanged |

Existing Starlette/httpx deprecation, three Fast Refresh warnings and the frontend chunk-size warning remain.
The separate PR #34 hosted frontend job passes; other hosted conclusions were still pending at this record.
Docker/hosting execution, real inference and the future private UI are outside this completed preflight.
The deterministic check is a real-document reference check; synthetic replay and fixture browser tests are
regressions only. No actual model latency, usage, JSON quality or economic-summary metrics exist yet.

**NO-GO for acceptance/display; approval-ready proposal for a controlled local experiment.** Evidence that would
change the verdict: recorded independent permissions, owner-reviewed gold, successful offline/provenance checks,
two bounded model outcomes meeting the acceptance criteria, and human-approved summaries. A private UI then
requires its own approvals. Nothing in this record authorises a merge or public deployment.
