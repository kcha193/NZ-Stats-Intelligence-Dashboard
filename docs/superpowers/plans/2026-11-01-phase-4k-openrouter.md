# Phase 4K OpenRouter Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task.

**Goal:** Prepare PR A with secure hosted HTTP integration and synthetic evidence, stopping before real transmission.

**Architecture:** Extend the existing OpenAI-compatible HTTP adapter. Add a version-scoped consent check to the existing pipeline and retain its atomic spend reservations. Leave the CLI unable to supply hosted consents until separately reviewed PR B.

**Tech Stack:** Existing Python, httpx, SQLite, pytest; no new runtime dependency.

**Spec:** Owner's Phase 4K request; acceptance and approval proposal in `docs/phase-4k-openrouter.md`.

## Global Constraints

- Preserve PR #36 and `config/phase-4j-pilot.json` unchanged.
- No real document transmission, model server, institutional crawl, scheduler or display activation.
- HTTPS, no redirects/proxies/retries/fallbacks; explicit provider only, ZDR and no training.
- Two documents, one durable attempt each, lifetime US$5 ceiling; retain deterministic verification.
- Synthetic fixtures only; no report bodies or keys in Git or review context.

## Review Focus

- OpenRouter reached through generic compatible configuration must not bypass privacy controls.
- Changed source text, version, model or provider must invalidate consent.
- Failed, concurrent and interrupted requests must consume their single attempt.
- Billed errors and excessive usage/cost must remain accounted for and refuse acceptance.
- Unknown response model/provider, missing usage and non-JSON output must fail closed.

### Task 1: Routing and response controls

**Files:** `research/providers.py`, `research/openrouter.py`, `research/contract.py`, `tests/research/test_openrouter.py`.

**Interfaces:** `LlmSettings.openrouter_provider`; provider response optional serving provider, response ID and cost; `OpenRouterProvider` reuses compatible framing and HTTP transport.

- [x] Write synthetic request/config/error/usage tests, run and observe missing functionality.
- [x] Implement fixed HTTPS endpoint, two reviewed route profiles, mandatory privacy block, JSON mode and response checks.
- [x] Run provider tests and Ruff. Expected: all pass, keys absent from error/log output.

### Task 2: Consent and durable limits

**Files:** `research/hosted.py`, `research/summarise.py`, `research/summary_store.py`, `tests/research/test_hosted.py`.

**Interfaces:** `HostedConsent` binds version, content/text hashes, canonical request hash, model/provider and independent review evidence; `summarise_versions(hosted_consents=...)` defaults empty. `reserve` atomically enforces OpenRouter's attempt and lifetime spend ceilings.

- [x] Write fail-first consent, budget, concurrency, billed-error and repeated-failure tests.
- [x] Add additive consent gate; no CLI approval loader or institutional permission changes.
- [x] Preserve reported costs and response metadata; reject anomalies without retry.
- [x] Run research tests and full backend. Expected: pass without external calls.

### Task 3: Reviewable proposal and delivery

**Files:** `config/phase-4k-pilot.json`, `docs/phase-4k-openrouter.md`, runbook and progress.

- [x] Record live public catalogue/ZDR evidence, pricing, privacy caveats, pending source-specific rights/owner review, human gold/display gates and conservative cost bounds.
- [x] Run frontend checks, browsers, replay, audits, secret scanning; inspect final diff.
- [ ] Commit/push PR A as authorised; request independent Codex High review (maximum three cycles). Do not merge. PR B/C stay blocked by explicit approvals.

## Execution record

- Owner supplied the full specification and instructed continuous safe preparation. No additional design approval is inferred for real transmission.
- Main `13cd20e` contains PRs #34–#36. Clean worktree; provider/budget baseline: 60 passed.
- Inline execution; independent whole-branch review after implementation. No per-task commits required.
- Three independent Codex Sol 6.1 High review cycles; eight findings reproduced failing-first and fixed.
  The final context-admission fix has local regression evidence; no fourth review or clean-final-head claim.
- Python 3.12 full 3,672 before final narrow fixes; latest research/publication 2,021 and focused 146 pass.
  Frontend 524; live/research/static browser 174/18/315 (3/24 expected skips); replay 38/38.
  Ruff, API schema, npm audit, fresh-environment pip-audit, Gitleaks and documentation checks pass.
- Ruling: audit of the shared environment found vulnerable certifi/pip/pypdf. Do not mutate that shared
  environment; validate in an updated isolated Python 3.12 environment and require pypdf >=6.21.4.
