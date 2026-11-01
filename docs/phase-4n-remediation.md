# Phase 4N: OpenRouter reasoning-token and truncation remediation

2 November 2026, Pacific/Auckland. Baseline: `3c0efbf`, main after merged
[PR #39](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/39).

**Code remediation complete; no real inference was run.** Real inference spend in this phase: US$0. This phase read only
metadata from the Phase 4M envelopes. No report text, reasoning text, gold annotations or credentials were read or sent.
The [second-pilot proposal](phase-4n-second-pilot-proposal.md) awaits separate owner approval.

## Root-cause analysis

### Confirmed by response metadata or code

| Finding | Evidence |
|---|---|
| **Treasury exhausted its budget on reasoning** | `completion_tokens` 6,000, `reasoning_tokens` 6,000, `content` null, `finish_reason=length`, `native_finish_reason=max_tokens` |
| **RBNZ ran out during final JSON** | 1,457 reasoning tokens left 4,543 for JSON: 12,407 characters. Keys were written in the order outlook, decisions, forecasts, facts, guidance, assumptions, drivers. The text stopped in or after `drivers`, with `risks` and `uncertainty` never reached |
| The output was verbose | 22% of the JSON was whitespace (2,707 characters, 207 line breaks). 29 evidence entries for about 20 claims, median quote 116 characters, quotes 26% of the JSON. About 227 output tokens per claim |
| Effort and cap were hardcoded | `openrouter.py` sent `high` in two places and capped at 6,000; `pilot.py` hardcoded 6,000 in the settings, cost bound and preflight |
| Reasoning counts inside the cap and is billed as output | Billed output cost was 6,000 × US$22/M on both requests, regardless of the reasoning share. OpenRouter and Anthropic documentation agree |
| Failure classes hid the cause | Treasury stored `invalid_response` and RBNZ `output_truncated`. Reasoning tokens were not stored. A synthetic reproduction on the unchanged code returned those same two classes |
| A larger cap alone would risk a new failure | The timeout was 120 s. 12,000 tokens at the observed 107–136 tokens/s takes 88–112 s, leaving almost no margin, and a timeout still costs the attempt |
| The instructions named the wrong schema | They said `OutlookSummary`, but the prompt shows `SummaryDraft`, and they repeated rules 1–4 |

### Not failed

HTTP (200), the route and returned identity, privacy parameters, billing reconciliation and the frozen-request controls all
worked. **The economic verifier never ran**, because neither response reached it. Model quality remains unmeasured.

### Checked against provider evidence

| Option | Result |
|---|---|
| Lower effort on this route | **Supported.** The catalogue lists `max, xhigh, high, medium, low` |
| Disable reasoning | **Not available.** The catalogue marks reasoning mandatory; Anthropic documents a 400 error for disabling it on Opus 5.5 |
| Separate reasoning-token budget | **Not available as a hard bound.** Anthropic rejects `budget_tokens` on Opus 5.5. OpenRouter says effort-only models use `reasoning.max_tokens` to choose an effort level. OpenRouter's nominal 80% share for `high` did not hold: Treasury reached 100% |
| Output cap of 12,000 | **Supported.** Endpoint maximum 128,000 |
| Provider-enforced `json_schema` | Not adopted. The endpoint advertises `structured_outputs`, but compatibility with this schema is unverified without inference, and it would not prevent truncation |

### Hypotheses the next trial must test

These have no real-model evidence yet:

- Low effort reduces Treasury reasoning enough. Treasury's true need at `high` is unknown; 6,000 is only a lower bound.
- The revised rules reduce final tokens. Whitespace and quote length are measured in characters, not tokens.
- The model respects the 20,000-character target and the instruction not to draft in its reasoning.
- Low effort keeps recall and attribution quality. Anthropic describes low effort as best for short, scoped tasks.

## Code changes

| Area | Change |
|---|---|
| Reasoning | `NZSTATS_OPENROUTER_REASONING_EFFORT` is required, with no default. Reviewed values are `low` and `medium`; `high` and above are refused. `reasoning.max_tokens` is never sent |
| Output and timeout | Maximum 12,000 tokens. The timeout must allow at least 60 tokens/s, so 12,000 tokens needs at least 200 s; the experiment uses 300 s |
| Prompt `outlook-v4` | Shorter instructions without the duplicated rules. New rules 14–18: cover every decision and stated forecast, omit rather than guess, one sentence per text field, each figure once, shortest quote that contains the number, unit and horizon, compact single-line JSON, omit null fields, stay under 20,000 characters. Rules 1–13 are unchanged |
| Contract and verifier | Contract 2, `verify-3`, `3b-1` and all thresholds unchanged |
| Experiment scope | `phase-4n-second-pilot` is a reviewed code constant pinning prompt, effort, cap, timeout, two attempts and US$1. Only the bounded pilot runner sets it; no environment variable can |
| Freeze and approval | Freeze format 2 and the request hash bind the experiment, effort, cap and timeout; the freeze also binds spend. `Approval` requires the experiment and spend limit. `HostedConsent` binds the experiment. All Phase 4M freezes and approvals are refused |
| Preflight | Refuses if the catalogue no longer lists the effort, the output limit is below the cap, price or parameters change, or key usage does not match the ledger |
| Diagnostics | Reasoning tokens and finish reasons are stored in summary metadata. The raw response stays in the private capture, with a new content-free `diagnostics.json` beside it |

### Failure classes

A specific cause is named only when the metadata supports it. All are non-retryable, keep reported billing, store no
model text and cannot reach review or display.

| Class | Meaning |
|---|---|
| `reasoning_budget_exhausted` | Length stop, no final text, reasoning equals output, and output reached the cap |
| `final_json_truncated` | Length stop where the JSON parser ran out of text mid-document |
| `output_truncated` | Length stop where a specific cause is not established, including text that parses or is invalid before its end. Always rejected |
| `missing_final_content` | Normal stop with null, empty or blank content |
| `invalid_json` | Normal stop with content that is not one JSON object |
| `schema_mismatch` | Valid JSON that fails `SummaryDraft` (stored status `invalid_output`) |
| `failed_verification` | Parsed output the evidence verifier rejects (a stored status) |
| `route_unverified` | Returned model or provider differs from the approved route |
| `usage_unverified`, `usage_exceeded` | Usage is missing or inconsistent, or above the cap or price |
| `upstream_error`, `refused` | A non-null error field in the body or any choice under HTTP 200; a content-filter stop or refusal metadata |
| `invalid_response` | A malformed envelope, or more than one choice |

## Historical pilot evidence

No Phase 4M row changes, and there is **no schema migration**. A run now names its experiment in the existing
`research_llm_run.limits` JSON. Runs without one, including Phase 4M's, belong to `phase-4m`, whose attempts stay consumed.

| Control | Result on the live ledger (read-only) |
|---|---|
| Phase 4M scope, either version | `attempt_consumed` |
| Second experiment, Treasury then RBNZ | Allowed, subject to approval |
| Second experiment, a third attempt | `lifetime_attempts_exhausted` |
| Lifetime spend | US$0.382278204, counted across all experiments toward US$5 |
| Rows before and after freezing | 1 run, 2 summaries, 2 usage, 2 reservations, unchanged |

Document IDs stay fixed by `PILOT_VERSIONS`. The limits of four attempts overall and two per version count immutable
reservation rows, so editing a run's tag can neither add attempts nor restore a consumed slot. A further experiment needs
another reviewed code change and fresh consent.

## Synthetic before and after

Mocked HTTP with envelope shapes matching Phase 4M. These results test classification and controls, not model quality.

| Synthetic envelope | Before (`3c0efbf`, 6,000) | After (12,000, low) |
|---|---|---|
| All output is reasoning, content null | `invalid_response`, reasoning unrecorded | `reasoning_budget_exhausted`, 12,000 reasoning |
| Partial JSON after some reasoning | `output_truncated`, reasoning unrecorded | `final_json_truncated`, reasoning recorded |
| Complete JSON, normal stop | Accepted by the adapter | Accepted by the adapter; reasoning recorded; still parsed, verified and left unreviewed |

Before the code changed, 122 tests in the focused files failed. Many failed at the shared revised-settings fixture rather
than at a distinct assertion, so the table above is the more specific evidence for each defect.

## Verification

- Full backend on Python 3.12 at `17a328f`: **3,877 passed**, with the one existing Starlette/httpx warning.
- PR CI at `17a328f`: backend, frontend, static site and Docker all pass.
- Ruff lint and format: pass, 326 files. Staged Gitleaks: no leaks.
- Offline freezes and a read-only ledger simulation ran locally and printed metadata only. Live ledger counts and spend
  were unchanged afterwards.
- Independent Codex review used `gpt-6-sol` at high effort on an export with no `data/` directory, because this account
  no longer accepts the configured `gpt-6.1-sol`. Cycle 1 found 4 issues and cycle 2 found 5. All 9 are closed: 8 by code or
  test changes, with failing tests first, and 1 by correcting the proposal. Cycle 1's migration suggestion was met without a
  migration, by counting immutable reservation rows.
- **Cycle 3 has not completed.** It stopped at the Codex usage limit before reporting, so the cycle 2 fixes have not yet
  had independent review.
- Synthetic tests cannot establish model quality.

## Remaining risks and owner decisions

- **Reasoning may still exhaust the budget.** Effort is not a ceiling and Treasury's need is unknown. The stop conditions
  cover this; running Treasury first limits exposure.
- **Low effort may lower recall or attribution quality.** Only the gold evaluation can show this. Thresholds stay fixed.
- **The size target may omit interpretive statements.** Rule 18 protects decisions and forecasts first. Omissions are reported.
- **The experiment tag is not tamper-proof.** Anyone with local database write access could edit `limits` and hide
  spend from the experiment's US$1 limit. Attempt limits, the US$5 lifetime count and the key's own limit do not depend on
  the tag. Making the tag immutable would need a migration, which the runner deliberately avoids.
- **Unchanged limits from earlier phases.** Treasury table cells stay rejected, a provider label does not prove region,
  and rights and account evidence remain owner attestations. The version-specific private-display gap from Phase 4L is
  still open and is outside this phase.
- **Local summaries also move to `outlook-v4`.** Stored `outlook-v3` rows are kept. A future local run creates a new key.

Owner decisions are listed in the [proposal](phase-4n-second-pilot-proposal.md#fresh-approvals-required).

## Verdict

**GO WITH CONDITIONS** for a second controlled inference trial, after separate owner approval and fresh preflight.
**NO-GO** for inference today, and for economic intelligence or display.
