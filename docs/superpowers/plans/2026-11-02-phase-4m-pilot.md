# Phase 4M bounded pilot implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. The user has authorised continuation. Do not commit, push or merge without further instruction.

**Goal:** Make the existing version-scoped hosted path executable with an explicit section scope and separately approved frozen request, retaining real responses locally.

**Architecture:** Extend `HostedConsent` with section ordinals and an inventory hash; use the existing pipeline/reservations/verifier. A local-only pilot module freezes requests without network access and executes only complete, unexpired approval records after backup, catalogue and key checks. No global source/display permission changes.

**Tech Stack:** Existing Python/Pydantic/httpx/SQLite, pytest with synthetic fixtures.

**Spec:** User's Phase 4M request; `docs/phase-4m-owner-approval.md`, `docs/phase-4k-openrouter.md`, `docs/phase-4l-controlled-pilot.md`.

## Global constraints

- Exact Opus 5.5 / google-vertex/europe route; strict ZDR, data collection denied, no fallback/retry.
- At most two exact versions, one attempt/version across runs, US$5 lifetime, 45,000 input characters, 6,000 output tokens.
- No report text in agent/review/Git/log output. Local bodies under ignored data with restrictive modes.
- Gold unchanged; documented rejection cases retained. Final request consent remains distinct from general/version assent.
- No display, summary approval, crawling, ingestion, deployment or merge.

## Review focus

- Changed/extraneous/missing sections or headings must invalidate consent, including changes outside the selected subset.
- A pending worksheet or generic approval must never become executable consent.
- Frozen framing/body and approved canonical hash must agree at transmission.
- Capture failure or interrupted/failed inference must never permit a second attempt.
- Preflight failure must cause no inference; unknown account/rights evidence must remain unresolved.

### Task 1: bind and enforce section scope

Files: `backend/src/nzstats/research/hosted.py`, `summarise.py`; `backend/tests/research/test_hosted.py`.

- [x] Add failing synthetic tests for selected-subset delivery, missing/extra/changed section identity, invalid/duplicate ordinals, and consent mutation.
- [x] Add `section_inventory_sha256(sections)` and explicit `approved_section_ordinals` / `sections_sha256` fields to `HostedConsent`; use the validated subset in request building and verification.
- [x] Run the scoped tests and existing hosted/provider/budget regressions; inspect the diff.

### Task 2: local frozen request runner and body retention

Files: `backend/src/nzstats/research/pilot.py`, `providers.py`, `openrouter.py`; `backend/tests/research/test_pilot.py`.

- [x] Write failing tests for offline freeze, incomplete/expired approval refusal, exact framed request capture, raw response retention (including invalid JSON), Treasury-only operation, and repeat-attempt refusal.
- [x] Implement strict local approval models, deterministic frozen framing, restrictive exclusive artifacts, fresh key/catalogue/backup checks and serial calls through `summarise_versions`.
- [x] Preserve actual response bytes before parsing; never persist auth headers or arbitrary exception text. Leave outputs unapproved.
- [x] Run focused regressions, full backend suite and Ruff. No changes to prompt or verifier thresholds.

### Task 3: freeze proposal and independent review

- [x] Record owner statements without inventing source rights, section selections, timestamps or economic decisions.
- [x] Prepare local proposed-scope freezes for concrete owner review, with canonical/body hashes and conservative cost bounds. Keep rights and final consent pending where unspecified.
- [x] Request independent Codex High review of implementation; resolve material findings with failing-first regressions.
- [x] Execute only if the owner explicitly supplies the missing rights/scope and approves the final freeze; otherwise report precise remaining gates and zero real inference.
- [x] Update progress/project status and inspect final diff. No automatic commit/PR/merge.

## Execution ledger

- Task 1 complete: selected scope / inventory drift tests observed RED on missing consent fields, then GREEN; hosted/provider/budget 135 passed.
- Task 2 complete: pilot module missing RED, synthetic runner cases GREEN. Independent review credential echo and partial stream reproductions RED→GREEN. Final focused provider/pipeline 248 passed, then runner/isolation 28 passed after canonical alias guard.
- Ruling: backup wiring moved to `scripts/run_hosted_pilot.py` after existing isolation test failed; no isolation rule was loosened. The launcher supplies the required verified-backup callback. Cost if wrong: execution cannot satisfy its backup prerequisite; synthetic integration and isolation tests cover it.
- Full isolated backend 3,738 passed before final alias guard; final-source research 1,981 passed. Ruff 326 files, dependency audit, local links/JSON/permissions/freeze checks pass.
- Task 3 execution complete: owner replied “yes approve” to the exact final manifest, both section lists, full retained-text/third-party-rights confirmation and 60-minute window. Explicit owner attestation recorded; underlying licence grants not independently certified.
- Two real requests, one/version, zero retries/fallback: Treasury 16,460/6,000 tokens, US$0.202379760, 56.090s, no final content; RBNZ 11,299/6,000, US$0.179898444, 43.995s, partial JSON. Both finish `length`; both rejected. Total US$0.382278204 reconciles exactly to the key. No prompt/cap/verifier adjustment after outcomes.
- Human review packet retains raw envelopes and every intact final-content fragment (20 RBNZ, all rejected), received evidence and incomplete tail. No repaired prediction set or output approval. Quality gates have empty accepted denominators and do not pass. Economic Outlook UI PR withheld.
- Independent outcome metadata review confirms arithmetic, owner scope, NO-GO and metric integrity. Its P2 historical preflight wording finding was corrected in documentation. Originals/economic meaning/account settings stayed outside reviewer evidence.
- No processing owner approval is missing. Human output and separate private-display/UI approval absent; failed outputs cannot be promoted, both attempts consumed. Further inference is not authorised under this pilot. Final project status/diff checks recorded; no commit, push or merge.
- Delivery subsequently authorised: user invoked finishing-a-development-branch and requested a new PR. Preserve the workspace; commit/push only the runner, tests and safe metadata documentation, with `main` as base. Keep originals, response/request bodies, gold, credentials and owner records ignored locally. No automatic merge or new inference.
- Delivery verification: fresh full isolated Python 3.12 backend **3,739 passed**, one existing warning, 319.26 seconds. Ruff lint/format and staged Gitleaks/privacy/link/diff checks pass. Branch `feat/phase-4m-controlled-pilot`, base `main` at `9e85e5b` confirmed by fresh fetch; workspace preserved.
