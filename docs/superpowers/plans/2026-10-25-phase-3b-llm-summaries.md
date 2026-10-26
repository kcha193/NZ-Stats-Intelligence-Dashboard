# Phase 3B: evidence-grounded LLM economic intelligence. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn stored, licence-eligible research document versions into structured summaries and explicit forecast
claims, each cited to `(version, section, page, verbatim quote)`, verified deterministically, then reviewed by a person.

**Architecture:** A pipeline inside `nzstats.research` (no Stats NZ package imports it): select eligible versions, frame
the sections as untrusted data, call a pluggable provider within token, cost, time and retry limits, parse strict JSON,
verify every claim against the stored text, store the result append-only with provenance and usage, and gate human
approval on verification. The default provider is disabled; no test or default path makes a network call.

**Tech stack:** Python 3.11+, Pydantic 2, SQLite (migration 006), httpx (already a dependency; no vendor SDK), pytest
with `httpx.MockTransport`.

**Spec:** the Phase 3B brief (26 October 2026) and the Phase 3A
[assessment](../specs/2026-10-25-phase-3a-research-sources-assessment.md). Revised from the 25 October draft of this plan.

## Changes from the 25 October draft

- Migration **006** (`005` is `research_duplicate_version`). Rollback: `scripts/rollback/006_research_summaries_down.sql`;
  `004_research_down.sql` also drops the 006 tables first, so the full research rollback still works.
- The permission field is `llm_processing = "denied" | "local_only" | "hosted"` (default `denied`), plus a required
  `llm_processing_note`. Anything but `denied` needs an approved `full_text` source with `terms_evidence = "direct"`.
- The model returns a `SummaryDraft` (no provenance, no review status); the pipeline attaches `version_id` and provenance.
  `ForecastClaim` gains `scenario` (None means the baseline or central forecast).
- Long documents are **refused** (`input_too_long`, no call, no cost) rather than chunked and merged. Chunk merging is a
  later, explicit extension; silent truncation is never allowed.
- Verification returns errors (block approval) and warnings (shown to the reviewer), with a fixed scope statement:
  passing means the deterministic checks found nothing, not that the economics is right.
- Two HTTP adapters without SDKs: Anthropic Messages and an OpenAI-compatible chat endpoint (OpenAI, or a local server
  such as llama.cpp, vLLM or Ollama on loopback). Only a loopback base URL counts as local.

## Global constraints

- No network call, cost or credential is needed by default or by any test. `NZSTATS_LLM_PROVIDER` unset means disabled.
- A source is sent to a hosted provider only when `llm_processing = "hosted"`; to a local one when `local_only` or `hosted`.
- No vendor SDK import anywhere (existing test). The API key comes from `NZSTATS_LLM_API_KEY` only and is never stored,
  logged or printed. Stored error text is a fixed vocabulary (CLAUDE.md rule), never a raw exception message.
- Nothing writes `release`, `series`, `vintage`, `observation`, `ingest_run` or `source_health`. Nothing research-related
  enters the snapshot (byte-identical export test). No scheduler wiring.
- Summaries are append-only: a new prompt or processing version adds rows; only review columns change, enforced by
  triggers. Only `verified` summaries can be approved (trigger plus repository check).
- Never invent numbers, horizons or positions: every number in a claim must be in its own quote.
- Fixtures and the evaluation set are synthetic and marked `SYNTHETIC FIXTURE`.

## Review focus

1. A section that contains text addressed to the model ("ignore previous instructions", a fake closing delimiter) must
   stay inside the data delimiters and must not yield a verified claim. Pinned in Tasks 3 and 4.
2. A provider that returns fenced JSON, duplicate keys, extra fields or 1 MB of text is a stored `invalid_output`, never
   an exception that aborts the run. Pinned in Tasks 2 and 7.
3. A run must stop before the call that could exceed the run budget, counting retries. Pinned in Task 7.
4. Re-running `summarise` must not call the provider again for a completed key, and a later prompt version must add a row
   without touching the old one. Pinned in Tasks 5 and 7.
5. Terminal output of model text must not carry control characters (escape-sequence injection). Pinned in Task 8.

---

## File structure

| File | Responsibility |
|---|---|
| `research/registry.py` (modify) | `LlmProcessing` enum, `llm_processing`, `llm_processing_note`, validation |
| `research/contract.py` (modify) | models (`SummaryDraft`, `ForecastClaim.scenario`), `ProviderResponse`, `ProviderError`, limits, `parse_draft` |
| `research/prompt.py` (new) | `PROMPT_VERSION`, instruction text, boundary framing, canonical input hash, injection scan |
| `research/verify.py` (new) | the deterministic verifier: `verify(summary, sections, context) -> VerificationReport` |
| `research/providers.py` (new) | `FakeProvider`, `AnthropicProvider`, `OpenAICompatibleProvider`, `LlmSettings`, `load_llm_settings`, `build_provider`, `Pricing` |
| `research/summary_store.py` (new) | repository for migration 006 tables |
| `research/summarise.py` (new) | selection, gates, budget, retries, idempotency, audit run |
| `research/cli.py` (modify) | `summarise`, `summaries`, `summary`, `approve`, `reject` |
| `store/migrations/006_research_summaries.sql` (new) | additive tables and triggers |
| `scripts/rollback/006_research_summaries_down.sql` (new), `004_research_down.sql` (modify) | rollback |
| `research/evaluate.py` (new), `tests/research/eval_set/*.json`, `scripts/evaluate_research_llm.py` | evaluation |

---

### Task 1: Third-party processing permission

**Files:** modify `research/registry.py`, `config/research_sources.toml` (header comment only); test `tests/research/test_registry.py`.

**Produces:** `class LlmProcessing(StrEnum): DENIED="denied"; LOCAL_ONLY="local_only"; HOSTED="hosted"`;
`Institution.llm_processing: LlmProcessing = DENIED`, `Institution.llm_processing_note: str | None`;
`Institution.llm_refusal(hosted: bool) -> str | None` (fixed wording, None when permitted).

- [ ] Tests: missing field → `DENIED`; `llm_refusal(hosted=True)` for DENIED is `"llm processing denied for this source"`;
  `local_only` with `hosted=True` is `"source permits local models only"`, with `hosted=False` is None; non-denied on a
  `needs_review` source, a `metadata_only` source, or without `llm_processing_note` raises `RegistryError`; an unknown
  value raises; every institution in the shipped registry is `DENIED`; `research sources` prints an `llm` column.
- [ ] Implement; run `pytest tests/research/test_registry.py tests/research/test_cli.py`; commit `feat(research): per-source LLM processing permission, default denied`.

### Task 2: Contract extensions

**Files:** modify `research/contract.py`; test `tests/research/test_contract.py`.

**Produces:**
- `ForecastClaim.scenario: str | None = Field(None, max_length=200)`.
- `SummaryDraft` (strict): `outlook`, `drivers` (≤20), `risks` (≤20), `uncertainty`, `indicators`, `forecasts` (≤50);
  `Statement.evidence` and `ForecastClaim.evidence` ≤5 refs.
- `assemble(draft, *, version_id, provenance) -> OutlookSummary`.
- `parse_draft(raw: str) -> SummaryDraft`: size cap `MAX_OUTPUT_CHARS`; strips one surrounding ```` ```json ```` fence;
  rejects duplicate JSON keys (`object_pairs_hook`); raises `ValueError` subclasses only.
- `ProviderResponse(text: str, model: str, input_tokens: int | None, output_tokens: int | None, stop_reason: str | None)`.
- `ProviderError(error_class: str, retryable: bool)`; `ProviderDisabled` stays.
- `Provider` protocol: `name: str`, `model: str`, `hosted: bool`, `summarise(request) -> ProviderResponse`.
- `LlmLimits` gains `max_retries: int = 2`, `max_run_usd: float = 1.0`.
- `verify_summary` stays as a wrapper that returns the error messages of `verify.verify` (existing strings unchanged).

- [ ] Tests: fenced JSON parses; duplicate key, extra field, oversized and non-JSON input raise `ValueError`;
  `assemble` sets `not_official_statistic` and `unreviewed`; 51 forecasts rejected; existing tests still pass.
- [ ] Implement; run `pytest tests/research/test_contract.py`; commit.

### Task 3: Prompt framing and input hashing

**Files:** create `research/prompt.py`; test `tests/research/test_prompt.py`.

**Produces:** `PROMPT_VERSION = "outlook-v1"`; `render(request, *, version_id: int, published_on: str | None,
boundary: str | None = None) -> RenderedPrompt(system: str, user: str, boundary: str)`;
`input_sha256(request, *, provider: str, model: str, parameters: Mapping) -> str` (canonical JSON of prompt version,
instructions, sections, provider, model, parameters; independent of the random boundary);
`injection_findings(sections) -> list[int]` (ordinals whose text resembles instructions to a model).

- [ ] Tests: each section is wrapped as `<<<SECTION {boundary} ordinal=N pages=a-b>>> ... <<<END {boundary}>>>`; the
  boundary is 32 hex characters and is regenerated if any section contains it; a section containing a forged
  `<<<END ...>>>` and "Ignore previous instructions" stays between its own delimiters; the system text includes the JSON
  schema of `SummaryDraft`, the version id and the instruction that document text is data; the hash is stable across
  boundaries and changes with model, parameters or any section byte; `injection_findings` flags "ignore previous
  instructions", "system prompt", "you are now" and not ordinary economic prose.
- [ ] Implement; run; commit.

### Task 4: Strict deterministic verifier

**Files:** create `research/verify.py`; modify `research/contract.py` (wrapper); test `tests/research/test_verify.py`.

**Produces:** `VERIFIER_VERSION = "verify-2"`; `Problem(code, path, message, severity: "error"|"warning")`;
`VerificationContext(published_on: date | None = None, injection_ordinals: tuple[int, ...] = ())`;
`VerificationReport(errors, warnings, scope)`, `.passed`; `SCOPE` text:
"Deterministic evidence checks only: quotes, numbers, units, horizons, versions and pages were matched against the stored
text. This is not a check of economic accuracy, completeness or interpretation; a reviewer must read the cited evidence."

Error rules (codes): `wrong_version`, `unknown_section`, `quote_not_found` (fabricated), `page_outside_section`,
`page_without_pages`, `quote_truncated` (ellipsis, or starts or ends mid-word or mid-number), `instruction_like_evidence`,
`value_not_in_evidence`, `missing_unit`, `unknown_unit`, `unit_mismatch`, `horizon_not_supported`, `fiscal_calendar_mismatch`,
`period_basis_mismatch` (quarterly versus annual next to the number), `historical_not_forecast` (no forward-looking
language in the quote's sentence, or the horizon ends before the publication year), `scenario_as_baseline`,
`scenario_not_in_text`, `direction_contradiction`, `indicator_mismatch`, `number_not_in_evidence` (any number in a
statement's text, a claim's label or qualification must appear in that item's quotes).

Warning rules: `weak_lexical_support` (under half of a statement's content words appear in its quotes' sentences),
`certainty_escalation`, `indicator_not_listed`, `horizon_without_period`, `injection_suspected_section`.

- [ ] Tests: one passing and one failing test per rule (removing any rule fails a test); number forms `2.5%`, `2½`,
  `−0.3`, `1,250`, `2.50`; a negative value matches an unsigned number only next to fall/decline/contract words;
  "two per cent" with no digits fails; prompt-injection regressions: a fake output obeying an injected "report GDP 9.9%"
  with an invented quote, with the injected text itself as the quote, and citing another version all fail.
- [ ] Implement; run `pytest tests/research/test_verify.py tests/research/test_contract.py`; commit.

### Task 5: Migration 006 and the summary repository

**Files:** create `store/migrations/006_research_summaries.sql`, `scripts/rollback/006_research_summaries_down.sql`,
`research/summary_store.py`; modify `scripts/rollback/004_research_down.sql`; tests
`tests/research/test_migration.py`, `tests/research/test_summary_store.py`.

Tables: `research_llm_run` (audit of one invocation: provider, model, prompt and processing version, limits JSON,
dry_run, started/finished, outcome, counts JSON, spent_usd); `research_summary` (version_id, run_id, attempt, provider,
model, hosted, prompt_version, processing_version, verifier_version, parameters JSON, input_sha256, output_sha256,
raw_output, output_json, status in `verified|failed_verification|invalid_output|provider_error`, error_class,
verification JSON, review_status in `unreviewed|approved|rejected`, reviewed_by, reviewed_at, review_note, created_at;
unique (version_id, provider, model, prompt_version, processing_version, input_sha256, attempt));
`research_forecast_claim` (summary_id, ordinal, indicator, indicator_label, horizon, value, unit, direction, scenario,
qualification, evidence JSON; verified summaries only); `research_llm_usage` (run_id, summary_id, call_no, provider, model,
input_tokens, output_tokens, usage_estimated, latency_ms, cost_usd, outcome, error_class, created_at);
`research_summary_review` (append-only decisions). Triggers: content columns immutable; approval requires `verified`;
`rejected` is final.

**Produces:** `start_run`, `finish_run`, `completed_summary(conn, key) -> Row | None`, `next_attempt(conn, key) -> int`,
`insert_summary(...) -> int`, `insert_claims(conn, summary_id, claims)`, `record_usage(...)`,
`review(conn, summary_id, decision, reviewer, note, now)` raising `ReviewError`, `list_summaries`, `get_summary`,
`list_forecast_claims(conn, *, indicator=None, approved_only=True)`.

- [ ] Tests: additive on a populated database at schema 5; no statistical table references; rollback 006 removes only 006
  objects and 004 still removes everything; triggers reject content updates, approving a failed summary, and un-rejecting;
  two prompt versions give two rows; review writes the audit row.
- [ ] Implement; run; commit.

### Task 6: Providers and settings

**Files:** create `research/providers.py`; test `tests/research/test_providers.py`.

**Produces:** `Pricing(input_usd_per_mtok, output_usd_per_mtok)`, `.cost(in, out) -> float`;
`LlmSettings(provider, model, api_key (repr hidden), base_url, pricing, limits)`; `load_llm_settings(env) -> LlmSettings`
(raises `LlmConfigError`); `build_provider(settings, *, client=None) -> Provider`; `FakeProvider(responses: Callable |
Mapping[int, str], *, hosted=False, usage=(in, out))`; `AnthropicProvider` (POST `/v1/messages`); `OpenAICompatibleProvider`
(POST `{base_url}/chat/completions`, `hosted` False only for a loopback host). HTTP: `trust_env=False`, no redirects,
timeout from limits, temperature 0, response body capped; 408/429/5xx/timeouts → retryable `ProviderError`; 4xx →
non-retryable; `stop_reason` max tokens → `ProviderError("output_truncated", False)`.

- [ ] Tests (MockTransport only): default env → disabled; real providers need model, prices and (Anthropic) a key;
  http base URL refused unless loopback; request bodies carry model, max tokens and the framed prompt; the key never
  appears in `repr(settings)` or in error classes; usage parsed; each error class mapped.
- [ ] Implement; run; commit.

### Task 7: The summarise pipeline

**Files:** create `research/summarise.py`; test `tests/research/test_summarise.py`.

**Produces:** `PROCESSING_VERSION = "3b-1"`; `summarise_versions(conn, registry, provider, *, pricing, limits, now,
institution=None, version_ids=(), limit=None, dry_run=False, sleep=time.sleep, clock=time.monotonic) -> SummariseResult`
with per-item outcomes `verified|failed_verification|invalid_output|provider_error|skipped_*|exists|input_too_long|
budget_exhausted`.

- [ ] Tests: disabled provider refuses before any selection; candidates are current versions of approved `full_text`
  sources whose `llm_processing` permits the provider's locality; a hosted provider skips a `local_only` source; an
  existing completed key makes no call; retries are bounded and each attempt is a usage row; the budget check uses
  worst-case cost (input chars / 3 tokens, full output cap) before every attempt; a provider exception, invalid JSON
  and a verifier failure are stored statuses; claims are written only when verified; the input hash covers the text;
  `dry_run` writes nothing and calls nothing; one transaction per document.
- [ ] Implement; run; commit.

### Task 8: CLI

**Files:** modify `research/cli.py`; test `tests/research/test_cli.py`.

Commands: `research summarise [KEY] [--version ID ...] [--limit N] [--dry-run]`; `research summaries [--status S]
[--review R]`; `research summary ID` (claims, evidence, errors, warnings, scope statement, usage);
`research approve ID --reviewer NAME [--note TEXT]`; `research reject ID --reviewer NAME --note TEXT`.

- [ ] Tests: summarise with no provider exits 1 with "no LLM provider is configured"; approve of a failed summary exits 1;
  model text with `\x1b[2J` prints escaped; inspect prints the scope statement.
- [ ] Implement; run; commit.

### Task 9: Evaluation

**Files:** create `research/evaluate.py`, `tests/research/eval_set/*.json`, `scripts/evaluate_research_llm.py`,
`tests/research/test_evaluate.py`.

Each case: synthetic sections, publication date, gold claims (indicator, horizon, value, unit, scenario), gold indicators,
key points, and candidate outputs (a faithful one and flawed ones, each labelled with its expected verifier error codes).
Cases include OCR, annual versus quarterly CPI, fiscal versus calendar year, a revised forecast across two versions, a
historical observation, a scenario, a PDF with pages, OCR-scanned text (spacing noise), number formats, and injection.

Metrics: claim precision and recall of verified claims against gold, indicator classification (micro F1), numerical
fidelity, citation correctness, scenario accuracy, completeness (key points covered), verifier detection rate per error
code and false-rejection rate, tokens, cost and latency.

- [ ] Tests: metric functions on tiny hand-computed inputs; the full replay set meets recorded floors (no faithful
  candidate rejected; every planted error detected).
- [ ] Run the script; record results and limitations in `docs/progress.md`; commit.

### Task 10: Isolation, documentation and verification

- [ ] Extend `tests/publish/test_research_isolation.py` with summary, claim and usage rows (byte-identical snapshot, API
  answers unchanged); extend `tests/research/test_isolation.py` so no scheduler or API module imports the new modules.
- [ ] Runbook section in `docs/data-sources/research.md` (permission, configuration, commands, review, rollback, costs,
  residual risks); `docs/progress.md` entry.
- [ ] Full verification: backend pytest, ruff check and format, frontend test/typecheck/build, `gen:api` no diff,
  playwright, `scripts/e2e_static.sh`, snapshot export and validation, Docker dependency check.

## Out of scope

Chunked long-document processing; automatic or scheduled summarisation; publishing summaries; cross-institution consensus
numbers; comparing forecasts with outcomes (Phase 3C, a read-time join); any write to the Stats NZ tables.
