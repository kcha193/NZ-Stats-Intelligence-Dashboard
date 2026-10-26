# Phase 3B: evidence-grounded LLM summaries and forecast extraction. Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:writing-plans to expand each task into TDD steps before
> implementing, then superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** For stored research document versions, produce a structured, evidence-grounded summary (main outlook, drivers,
risks, uncertainty, indicator classification, explicit forecast claims). Every claim is verified deterministically
against the stored sections, then reviewed by a person. The output is never official statistical evidence.

**Builds on:** Phase 3A ([plan](2026-10-25-phase-3a-research-sources.md),
[assessment](../specs/2026-10-25-phase-3a-research-sources-assessment.md)). The contract already exists in
`backend/src/nzstats/research/contract.py`: `OutlookSummary`, `ForecastClaim`, `EvidenceRef`, `ModelProvenance`,
`LlmLimits`, `Provider`, `DisabledProvider`, `build_request`, `parse_summary` and `verify_summary`, all tested. No model is
called in 3A.

## Must be true before Phase 3B starts

1. **At least one source is approved for `full_text`** and has real versions stored. The Treasury is the likeliest
   (CC BY 4.0 per search results): read its licence page directly, run `research discover treasury`, then approve it.
   Until then there is nothing to summarise but synthetic fixtures.
2. **The terms allow third-party processing.** Sending text to an external LLM provider is processing by a third party.
   Record per source whether that is allowed (a new registry field, `llm_processing = "allowed" | "local_only" | "no"`),
   default `no`. A source with `no` is never sent to a hosted model.
3. **Choose a provider and a budget.** This is Kevin's decision: a hosted provider, or a local model, or both. Credentials
   come from the environment only, are never stored in the database or logs, and the dashboard and all tests must keep
   working with no credentials (the default stays `DisabledProvider`).
4. **Decide whether the Docker image ships the `research` extra** (`pypdf`), since most institutional reports are PDFs.
5. **Re-probe** the priority sources with the project User-Agent (one throttled request each). The 25 October probes used a
   generic client.

## Design

```
research_document_version (+ sections)
  -> select: approved full_text source, llm_processing allowed, no summary for (version, prompt_version, model)
  -> build_request: sections in ordinal order, framed as untrusted quoted data, capped by LlmLimits
  -> Provider.summarise (pluggable; disabled by default; timeout and token caps)
  -> parse_summary (strict schema, size cap, extra fields rejected)
  -> verify_summary (quotes verbatim in the cited section and page, forecast numbers in their own quote, versions match)
  -> store summary + provenance + verifier result, review_status = 'unreviewed'
  -> human review: approve / reject (CLI), with reviewer and time
```

Separation stays strict. Parsing (3A extractors) produces text. Deterministic validation (3A `validate`, 3B
`verify_summary`) decides what is supported. The LLM only interprets, and its output goes to its own tables.

**No retrieval system.** A report is one document, typically 5–60 pages, so it fits the input cap section by section. The
evidence model cites `(version_id, section_ordinal, page)` directly. A general RAG index would add a ranking step that can
drop the evidence a claim needs, and nothing here needs cross-document search. Revisit only if a concrete requirement
appears (for example "compare every bank's OCR call this quarter"). Even then, select whole versions by institution and
date with SQL, not by embedding similarity.

**Long documents.** Over `max_input_chars`, summarise per contiguous section group and merge deterministically: union of
forecast claims, outlook from the first group, each with its own evidence. Never truncate silently;
`SummaryRequest.truncated` is recorded.

**Prompt injection.** Sections are wrapped in delimiters with a per-request random boundary, and the instructions say
the text is data. The provider gets no tools and no network. The verifier rejects any claim whose quote is not in the
document, so an injected instruction cannot add numbers that are not there. It cannot stop misreading of real text,
which is why human review remains.

## Data model (migration `005_research_summaries.sql`, additive)

| Table | Columns (main) |
|---|---|
| `research_summary` | id, version_id → `research_document_version`, provider, model, prompt_version, processing_version, parameters (JSON), input_text_sha256, created_at, output (JSON, the validated `OutlookSummary`), verifier_problems (JSON list), status (`verified`, `failed_verification`, `provider_error`), review_status (`unreviewed`, `approved`, `rejected`), reviewed_by, reviewed_at, review_note. Unique (version_id, provider, model, prompt_version, processing_version) |
| `research_forecast_claim` | id, summary_id, indicator, indicator_label, horizon, value, unit, direction, qualification, evidence (JSON). Written only for `verified` summaries; queryable for "what did each institution forecast" |
| `research_llm_usage` | id, summary_id, input/output tokens, latency, cost estimate. Budgets and audit |

Nothing references the statistical tables. Comparing a forecast with the later official outcome is a read-time join on
indicator and horizon in a separate, labelled view, never a write to `observation`.

## Tasks

1. **Registry field `llm_processing`** (default `no`; validated; shown in `research sources`). Tests: missing → `no`;
   `allowed` requires `terms_evidence = "direct"`.
2. **Migration 005, rollback script and repository.** Same tests as 004: additive on a populated database, rollback drops
   only 005 objects, unique key, no foreign key into the statistical tables.
3. **Request framing.** Random boundary delimiters; section headers carry ordinal and pages; tests for injection text
   staying inside the delimiters, the truncation flag and the cap.
4. **Provider plug-ins.** `FakeProvider` (canned JSON, for tests) and one real provider behind an optional extra and an
   environment variable. Timeouts, retries and caps from `LlmLimits`. Tests use only the fake; no network.
5. **Summarise command.** `nzstats research summarise KEY [--limit N] [--dry-run]`. Refuses when the provider is
   disabled, the source is not approved or `llm_processing` is not allowed. Idempotent per unique key. Records usage.
   A provider error or schema failure is stored as a status, never raised past the run.
6. **Verifier extensions.** Number formats (`2.5%`, `2½`, `−0.3`, "two per cent"; reject the words form unless the
   quote contains digits), and the horizon must appear in or next to the quote. A forecast with `value` and no unit is
   flagged. Mutation tests: every verifier rule has a test that fails when the rule is removed.
7. **Review workflow.** `research review list|show|approve|reject` with reviewer name and note; only `verified`
   summaries can be approved.
8. **Evaluation set.** 10–20 hand-annotated documents (synthetic, plus real ones only where the licence allows keeping
   them locally; never committed). Measure verifier pass rate, claim precision and recall against the annotations, and
   indicator classification accuracy. Record the results in `docs/progress.md` with the model and prompt version.
9. **Isolation and publication tests.** Summaries never reach the snapshot (byte-identical export). If research
   publication is later wanted, follow the extension in `docs/netlify-deployment.md` (approved and verified only).

## Risks

| Risk | Mitigation |
|---|---|
| Licence: sending text to a hosted model | `llm_processing` per source, default `no`; local-model option |
| Hallucinated numbers or quotes | `verify_summary` (verbatim quotes, numbers in quotes), stored problems, human review |
| Misread but verbatim evidence (wrong horizon, scenario taken as forecast) | `qualification` and horizon are required fields, a horizon check, human review; summaries are labelled interpretation |
| PDF tables lose structure, so numbers attach to the wrong row | the per-page section keeps the page for a reviewer to check; a table-aware extractor version later (`pdf-2`) |
| Cost runaway | `LlmLimits`, usage table, `--limit`, no scheduler wiring until a budget exists |
| Prompt injection | delimiters, no tools, verifier, review; the text is never rendered as HTML |
| Model drift | provenance on every row; re-summarise by new `processing_version`, keep old rows |

## Out of scope

Automatic publication of summaries; scheduling; cross-institution consensus numbers (a later, explicit derived view);
any write to the Stats NZ statistical tables.
