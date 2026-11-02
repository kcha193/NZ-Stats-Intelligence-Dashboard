# Phase 4N: second controlled pilot proposal

**Update, 2 November 2026:** Treasury ran once under its own approval and failed verification. RBNZ has not run and is not
authorised. See [phase-4o-treasury-pilot.md](phase-4o-treasury-pilot.md). The rest of this document is the original proposal.

**Proposal only. No approval exists, and no inference has run.** Nothing in this document, its
[metadata record](../config/phase-4n-pilot.json) or a merge of this work grants processing authority. Remediation
evidence is in [phase-4n-remediation.md](phase-4n-remediation.md).

## What is being asked

Two more real requests, one per document, to test the revised configuration. This is a new experiment. It does not
reuse, reset or replace the two consumed Phase 4M attempts.

| Item | Proposed value |
|---|---|
| Experiment | `phase-4n-second-pilot`, one attempt per version, two in total |
| Model / alias target | `anthropic/claude-opus-5.5` / `anthropic/claude-opus-5.5-20260921` |
| Exact provider | `google-vertex/europe` only, expected response label `Google` |
| Routing | `only` that endpoint, `zdr=true`, `data_collection=deny`, `allow_fallbacks=false`, `require_parameters=true`; ZDR list must show `safety_retention=false` |
| Reasoning | `reasoning: {"effort": "low"}`. No separate budget exists on this route |
| Output cap | **12,000** tokens, reasoning and final JSON combined. Endpoint maximum: 128,000 |
| Expected final JSON | About 4,000–7,500 tokens, target under 20,000 characters. An estimate, not a measurement |
| Timeout | 300 s (12,000 tokens would take about 88–112 s at the rates Phase 4M observed) |
| Prompt | `outlook-v4`, system text SHA-256 `e2298a91098f6bfc1240bdb685cf25e9c9264ef99eafb9dc658cf37b1346f097` |
| Rules | SHA-256 `b77701837d1ad6a9d8bf0e06ce7789dc16710bc467d88e6d47c0c88ecfa1c821` |
| Contract / schema | Contract 2 unchanged; draft schema SHA-256 `95f1ff48a55cca4cda6662d86f2461c5c7380bd49d3531c10da2854d2451c3e4` |
| Verifier / processing | `verify-3` and `3b-1`, unchanged |
| Retries / fallback | Zero / none. Any error consumes the attempt |

## Frozen candidates and cost

Offline freezes exist locally under ignored `data/phase-4n/`. Each is one document, so the second can wait for the
result of the first. Both use the section scopes approved in Phase 4M. A fresh freeze is needed if anything changes.

| Order | Version / sections | Freeze SHA-256 | Canonical request SHA-256 | Conservative bound |
|---|---|---|---|---|
| 1 | Treasury v1 / 0–6 | `57554ecff8751aac2261def808955ecc284dd366034186267502c615a4449c95` | `64de36f21bbcba9d2fbefaa4a2ef9793426000f337afbb9ba3adb387ebaf8aa5` | US$0.4532308 |
| 2 | RBNZ v2 / 1–14 | `417152dfff4afc3ded44eaffd9119d039b94deed04fe0d83bc9a1664f5a472ab` | `17cd795eabc595036ec1d5fc0ae13cc5988c7e26164bf1c624809e8dca32e8ec` | US$0.4115056 |

| Cost view | Treasury | RBNZ | Total |
|---|---|---|---|
| Conservative bound: every input byte is a token, plus the full output cap | US$0.4532 | US$0.4115 | **US$0.8647** |
| Maximum at Phase 4M's actual input tokens, with the full output cap | US$0.3364 | US$0.3137 | US$0.6501 |
| Estimate: Phase 4M input, 9,000 / 6,000 output tokens | US$0.2704 | US$0.1817 | US$0.4521 |

Prices are US$4.40 input and US$22.00 output per million tokens. Reasoning is billed as output.

**Spending authorisation requested: US$1.00 for this experiment, inside the unchanged US$5 lifetime cap.** Lifetime
spend is US$0.382278204, so the conservative bound would take it to at most US$1.2470146. The same dedicated
non-resetting key stays in use, with US$4.617721796 remaining. Preflight refuses if key usage differs from the
ledger's recorded spend by more than US$0.000001.

## Recommended sequence

1. Run **Treasury first, alone**. It is the harder document: Phase 4M exhausted its budget on reasoning.
2. Review its diagnostics and output.
3. Run RBNZ only after a separate go-ahead, under its own freeze and approval.

Running both in one approval would save a step but could spend a slot on a configuration the first result had already
shown to be wrong. Worst-case exposure with Treasury alone is US$0.4532.

## Fresh approvals required

Each decision is separate. A merge, a general “go ahead” or the Phase 4M records supply none of them.

| Decision | Required before any request |
|---|---|
| Experiment and spend | Approve `phase-4n-second-pilot`, two attempts and the US$1 limit, or set different terms in a reviewed change |
| Configuration | Approve low effort and 12,000 tokens, knowing low effort may reduce recall (see risks) |
| Treasury v1 consent | Fresh expiring consent for exact sections 0–6 and their request hash: rights basis, third-party and IMF material, attribution. Owner attestation is not an independent licence audit |
| RBNZ v2 consent | The same for sections 1–14, excluding chrome section 0. RBNZ's automated-access restriction still applies |
| Route and privacy | Accept OpenRouter as intermediary and the upstream route, with the documented retention, legal and residency limits |
| Account controls | Dated recheck: logging and improvement opt-ins off, strict ZDR, no safety retention, no auxiliary logging |
| Dedicated key | Confirm pilot-only use, US$5 lifetime limit, no reset and no other consumer. Supply it securely, never in chat or Git |
| Gold | Bind the reviewed gold and its SHA-256, retaining the documented rejection cases |
| Final request | Approve the exact fresh freeze with an expiry of 24 hours or less |

The approval record must name `experiment: "phase-4n-second-pilot"` and `experiment_spend_limit_usd: 1.0`. Phase 4M
approval records are refused by shape, its freezes by format and prompt version.

## Acceptance criteria

Report every measure with numerator and denominator. An empty denominator is unmeasured, never a pass.

| Measure | Gate |
|---|---|
| HTTP 200, `finish_reason=stop`, complete JSON | Every attempt |
| Schema-valid (`SummaryDraft`, contract 2) | Every attempt |
| Requested and returned model and provider | Exact match |
| Reasoning and final-output tokens | Recorded separately when reported. An absent count is recorded as unknown, makes this budget analysis unmeasured and does not by itself reject the output |
| Accepted aligned numerical fidelity | 100% |
| Accepted forecast issuer accuracy | 100%, including every Treasury/IMF attribution |
| Citation correctness | At least 95% |
| RBNZ decision | Hold, 2.75%, 28 October 2026, 4–3 against the reviewed gold; never as a forecast |
| Unsupported tables and comparisons | Still rejected, with omissions and reasons reported |
| Precision, recall, coverage | Reported raw and accepted, separately. Low recall is a recorded limitation for review |
| Human review | Claim by claim. No automatic approval, and no display without separate private-display approval |

## Stop conditions

Stop and make no further request, with no prompt or setting change, if any of these occur:

- Any `reasoning_budget_exhausted`, `final_json_truncated`, `output_truncated`, `missing_final_content`,
  `invalid_json`, `schema_mismatch`, `upstream_error` or `route_unverified` result.
- Verifier failure on a document. Treat it as a result to review, and do not adjust thresholds.
- A changed price, effort list, output limit, alias, parameter or retention attestation at preflight.
- Key usage that does not reconcile with the ledger, or a cost above the bound.
- A failed backup or restore check, a changed document, section or gold hash, or an expired approval.
- Any credential or report text found in a log, Git or a review.

Rollback needs no destructive step. Rows stay append-only; a failed attempt stays recorded and rejected. Withdraw by not
issuing further approvals, and revoke the key at OpenRouter if needed. Nothing reaches display.

## If the trial truncates again

Do not raise the cap in place. Use the diagnostics to choose the next proposal:

- `reasoning_budget_exhausted` at low effort: effort is not enough on this document. Propose a larger cap with a costed
  reason, or a different reviewed model.
- `final_json_truncated` with modest reasoning: the document needs more output than the rules allow. Propose bounded
  multi-stage extraction.

Multi-stage extraction is designed but not built. It would make one call per approved section group, each validated
against that group's exact sections, with a final synthesis limited to the validated claims and never adding cross-section
inference. Every call would have its own freeze entry, reservation, usage row and request hash. It changes the request
count and input scope, so it needs its own reviewed experiment and consent.

## Verdict

**GO WITH CONDITIONS** for a second controlled inference trial, after the owner decisions above and a fresh preflight.
**NO-GO** for any request today, and for economic intelligence or display until a human reviews real output.
