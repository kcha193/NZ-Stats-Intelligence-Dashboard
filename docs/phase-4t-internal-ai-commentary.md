# Phase 4T: internal AI commentary without mandatory human review

7 November 2026, Pacific/Auckland. Baseline: main `6b37ebb` (PR #47 merged).

> **Outcome (added in Phase 4U; the sections below are the pre-run record and are unchanged):** the one authorised real inference described in section H ran on
> 7 November 2026. It was a successful execution and a failed economic verification: see [Outcome of the authorised run](#outcome-of-the-authorised-run-added-in-phase-4u).

**No OpenRouter request, crawl, scheduler, deployment, approval or merge happened.** This record holds metadata only. No report text, model output,
gold or key was read into the hosted session. The real-database check below printed ids, categories and counts.

## The policy change

The owner uses the Economic Outlook page alone, on their own machine. They do not need to approve every AI summary or annotate a gold set before
reading one. This phase replaces those two gates with automated checks, visible check results and source links, **for internal drafts only**.

Unchanged: public publication (`public.py`), the private preview (`private.py`), every source's access, LLM and display settings, the snapshot,
the Netlify site, the verifier and its thresholds, the attempt ledger and the spending caps.

## A. Mandatory human review removed from internal draft use

| Before | Now |
|---|---|
| Each draft named by id and output hash in `data/internal-drafts.json` | Optional. `auto_display` in the same file shows every eligible summary |
| Hosted run needs a human gold file (`Approval.gold_*`) | Optional for an internal-draft run (`InternalDraftApproval.evaluation`) |

Kept for anyone who wants it: the explicit list (unchanged meaning when `auto_display` is absent), the gold-bound `Approval` format, `score-gold` and `check-gold`.
A run without gold writes `evaluation.json` as `{"human_evaluation": "not_evaluated"}`. With gold it says `gold_bound_not_yet_scored`. Neither says passed.

## B. Requirements that remain mandatory

An `InternalDraftApproval` (`backend/src/nzstats/research/pilot.py`) must bind all of these, and `execute` checks each against the freeze before any network call:

- the experiment and its spend limit (`phase-4s-treasury-v3`, exactly US$0.50)
- approver, approval time and expiry (in force now, 24 hours or less)
- the `freeze.json` hash, and for each document its version, `request_sha256`, `body_sha256` and per-section rights
- model `anthropic/claude-opus-5.5` and route `google-vertex/europe` (both fixed literals)
- privacy terms: `zdr` true, `data_collection` deny, `allow_fallbacks` false, `require_parameters` true. These must also equal the frozen body's `provider` block
- provider review, dated account-controls evidence and `dedicated_key_confirmed: true`

Still enforced, unchanged: version-scoped source eligibility (a revoked import approval refuses), the raw original's hash, the plan's ledger precondition,
one attempt per experiment, two per version, four lifetime (three used), US$5 lifetime (US$0.508 spent), the read-only key and catalogue preflight, and the verified backup.
Only the `phase-4s-treasury-v3` plan accepts this format. The Phase 4N plan does not (`PilotPlan.approvals`), and a gold-bound document cannot be read as one.

## C. The automatic internal draft workflow

Enable it in ignored `data/internal-drafts.json`:

```json
{"auto_display": {"enabled": true, "enabled_by": "<name>", "enabled_on": "2026-11-07", "note": "<why>"},
 "withdrawn": [{"summary_id": 3, "withdrawn_by": "<name>", "withdrawn_on": "2026-11-07", "note": "<why>"}]}
```

Then `nzstats serve --host 127.0.0.1 --internal-drafts` (since Phase 4AA, a loopback start without the flag also shows them). Only `"enabled": true` turns it on. A typo or unknown key shows nothing. `withdrawn` applies in both modes.

`drafts.py` stays the one gate. In auto mode a summary is shown only when all of these hold, rechecked on every request:

| Rule | Check |
|---|---|
| Complete, schema-valid output | status `verified` or `failed_verification`, and `output_json` still parses |
| Output unchanged | `sha256(raw_output)` equals the stored `output_sha256` |
| Normal finish | the stored `finish_reason` is `stop`, whatever the status mapping says |
| Provider identity and request integrity | OpenRouter: hosted, a reviewed route, the four privacy terms in the stored parameters, the serving provider and a `gen-` response id recorded, and a billed call recorded as `ok`. A local model (`openai_compatible`, not hosted) is also accepted. Anything else is refused, including the test `fake` provider and direct hosted providers |
| Not rejected or withdrawn | `review_status != rejected`, and not in `withdrawn` |
| Current source | current version, not purged, not a duplicate |
| Source permissions | registry entry, `full_text`, the approval that let it in still holds, an https address on an allowed host |
| Safety | no section reads like instructions to a model |
| One per document | the newest summary of a version holds the slot even when it is refused (withdrawn, rejected, failed integrity), so an older output never resurfaces in its place |

`invalid_output` and `provider_error` (malformed, truncated, refused, route-unverified, usage-unverified) never appear as commentary. Each report only counts them.
`research summary ID` prints `internal draft: yes`, or the reason not.

## D. Automated economic verification

No change to `verify-4`, its thresholds or the prompt. It still checks numbers, quotes and citations, periods and horizons, issuers (Treasury versus third parties),
OCR decision claims, missing evidence and the publication date. A newer report from the same institution is still flagged on the older draft.
The draft API now adds a summary-level category:

| Category | Meaning |
|---|---|
| `no_automated_issue` | the checks raised nothing. Not "verified" |
| `automated_warning` | warnings only |
| `failed_automated_checks` | at least one error. Every failed claim is marked with its reasons |
| `unusable_response` | no usable output. Counted on the report, never shown |

There are no confidence percentages. Claim-level findings and provenance are unchanged and still served.

## E. Dashboard

On `/economic-outlook` (internal drafts on), the page now shows:

- the fixed notice "AI-generated research draft. Automated checks may miss errors. Not independently reviewed." above the section and on every draft page
- "Latest institutional commentary": one card each for Treasury and the Reserve Bank, with the newest report held, its publication date, the document's own date when stated, the validation badge, the AI outlook labelled "AI interpretation", and a link to the full draft. It says when there is no commentary, or when the response was unusable
- drafts split into current and earlier reports
- each held report with its category

On the draft page:

- a "claims failed the automated checks" panel, with reasons in view and links to each claim
- a filter for only the claims with warnings or failures
- "AI interpretation" above model text. Quoted evidence is called "Statement in the official report" only when the checks raised nothing about the claim, and otherwise "Quote cited by the AI, not confirmed by the automated checks", because the quote comes from the model
- third-party forecasts labelled "Third party, not the report's author"
- the document date
- reasons open by default on failed claims

The labels "Human reviewed", "Approved", "Verified", "Evidence checked", "Published here" and "Official statistic" never appear. Statistical pages are untouched.

## F. Tests

Fail-first: each new test was run against main's code and failed (37 backend pilot tests, 8 frontend), then passed. Three pilot guards were checked by mutation.
Removing each guard made its test fail: the plan's accepted formats, the request hash and the optional-gold hash. The plan-format test first passed for the wrong reasons
(a missing raw file, then a consumed 4N slot). It was fixed so only the guard can refuse.

| Suite | Result |
|---|---|
| `test_drafts_auto.py` (new) | auto mode, integrity refusals (13 cases), withdrawal, rejection, unusable responses, categories, public and private gate isolation, API leak and label checks, local-only request checks, read-only routes |
| `test_pilot_internal_draft.py` (new) | no gold runs, consent still required, terms and hashes bound, old approvals not reusable, ledger and caps intact, malformed output never shown, a complete mocked run appears as a draft |
| `test_research_isolation.py` | adds: an auto-display config changes no snapshot byte |
| Backend, frontend | see Verification |

Synthetic documents and mocked OpenRouter responses only.

## G. Treasury version 3 experiment readiness

Unchanged: version 3, sections 0 to 2, `outlook-v5`, `verify-4`, Claude Opus 5.5, `google-vertex/europe`, low effort, 12,000 output tokens, US$0.50, one attempt, no retry, no fallback.
The Phase 4S freeze (`data/phase-4s/freeze/`, format 3) is still the one to use. Human gold is **no longer required**.
**Readiness: GO WITH CONDITIONS to run once, after the owner steps below. NO-GO without them.**

## H. Exact next action for one authorised real inference

All owner steps. None needs Claude Code, and the key must never enter its session.

1. Review and merge this PR.
2. Run `scripts/openrouter_key_reading.py` (read-only), and confirm the account's logging, training and ZDR settings, with a dated note.
3. Confirm the freeze still matches: `research summary`/`status` show no new version 3 import, and `freeze.json` hashes to `ab615391…8fd7`. Otherwise freeze again with `--experiment phase-4s-treasury-v3`.
4. Write `data/phase-4t/approval.json` (`chmod 600`) from the template below. Copy `request_sha256` and `body_sha256` from `freeze.json`. Expiry must be 24 hours or less.
5. From the repo root, with the dedicated key in the environment only:
   `NZSTATS_LLM_API_KEY=… python scripts/run_hosted_pilot.py execute --frozen data/phase-4s/freeze --approval data/phase-4t/approval.json --output data/phase-4t/run`
6. Turn on `auto_display` (section C), then `nzstats serve --host 127.0.0.1 --internal-drafts`. The draft appears if the response is complete. If it is unusable, the report says so, and there is no retry.

```json
{"state": "authorised", "purpose": "internal_draft", "experiment": "phase-4s-treasury-v3",
 "experiment_spend_limit_usd": 0.5, "approved_by": "<name>",
 "approved_at": "<ISO time with offset>", "expires_at": "<at most 24 h later>",
 "frozen_sha256": "<sha256 of freeze.json>", "model": "anthropic/claude-opus-5.5", "provider_id": "google-vertex/europe",
 "privacy": {"zdr": true, "data_collection": "deny", "allow_fallbacks": false, "require_parameters": true},
 "provider_review": "<what you checked>", "account_controls_evidence": "<dated evidence>", "dedicated_key_confirmed": true,
 "documents": [{"version_id": 3, "request_sha256": "<from freeze.json>", "body_sha256": "<from freeze.json>",
   "sections": [{"ordinal": 0, "rights_basis": "…", "third_party_rights": "…", "attribution": "…"},
                {"ordinal": 1, "rights_basis": "…", "third_party_rights": "…", "attribution": "…"},
                {"ordinal": 2, "rights_basis": "…", "third_party_rights": "…", "attribution": "…"}]}]}
```

That uses the fourth and last lifetime attempt. Any later run needs a separately reviewed code change, below.

## Future commentary updates (design, not built)

The repeatable path for a new Treasury report:

manual import (permitted source) → `import` validates the source, version and hashes → a reviewed experiment plan names the version → `freeze` →
an `InternalDraftApproval` → one request → `verify-4` → stored draft → auto display with its findings and evidence.

None of this needs a 130-sentence gold exercise. Inference stays off because there are no attempts left, by design. A future policy, reviewed in its own PR, would replace per-run approvals with:

- a standing operator-signed policy file: institution, document series, maximum calls per document version (one), a fixed total cap, an expiry date, and the same route and privacy terms
- an explicit operator command per new document, never a schedule or the on-open refresh
- a raised lifetime ledger limit, raised only in that reviewed change, with the history kept

This PR implements none of it, adds no unattended paid inference and does not raise any limit.

## Known limits

- The hash binds `raw_output`. The page shows `output_json`, which the pipeline derived from it in the same transaction. Both columns are immutable under migration 006's triggers, so the gate does not re-derive one from the other.
- The local-model path accepts `openai_compatible` with `hosted = 0`. The adapter counts a base URL as hosted only when its host is not loopback, so a loopback proxy to a remote model would count as local. Only the operator configures that. It still needs a normal finish and every other rule.
- "No automated issue detected" is narrow. The checks test where a quote, number, unit and horizon sit in the document, not whether the economics is right.

## Protections (unchanged and retested)

Off by default. Loopback binds only, with no override. Requests need a loopback `Host`, a same-origin `Origin` and `Sec-Fetch-Site`, and the dashboard header.
GET only, over a read-only connection, `no-store` and `noindex`. The response model is an allowlist: raw output, hashes, parameters, response ids, usage, cost and the owner's notes have no field.
The exporter's app has no draft routes. The static reader has no draft data. Restricted documents are never ingested automatically. Nothing new is fetched.

## Real-database check (read-only, metadata only)

With auto display on in memory and `mode=ro`: one draft, summary 3 (Treasury, version 1). It failed automated checks: 18 claims, 7 failed, 1 warning, 10 clean, unreviewed.
Summaries 1 and 2 are refused as `provider_error`. Treasury's newest report (the 29 October FEU, version 3) has no commentary.
The RBNZ report has 1 unusable attempt, counted and not shown. Database changes: 0.

## Verification

| Check | Result |
|---|---|
| Backend suite | **5,080 passed**, 0 failed (after the review fixes; 5,072 on the reviewed commit) |
| Ruff lint, format | clean |
| Frontend `npm test` | 49 files, **555 passed** |
| Browser suites (Playwright, `e2e_static.sh`) | **Not run.** No public, static or snapshot code changed. The `netlify.test.ts` unit check passes. The draft UI was checked in jsdom only, not in a browser |
| Typecheck, build | clean |
| oxlint | no new warnings |
| Independent review | **Codex could not run.** It refused every model available on this machine (`gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-5.4`) with "not supported when using Codex with a ChatGPT account", and no review took place. A fresh Claude security reviewer (same vendor) reviewed the diff and found no blocker. It found five medium defects. Fixed: an older summary could resurface when the newest was refused, model quotes on failed claims were labelled as the report's statement, no finish-reason recheck, and weak local-path evidence. The fifth is recorded under Known limits. The fixes are pinned by tests and mutation checks |
| CI | the GitHub Actions billing block (Phase 4R and 4S) is outside this change |

## Outcome of the authorised run (added in Phase 4U)

The Treasury version 3 experiment (`phase-4s-treasury-v3`, run 3) ran once. This is recorded from the local database, read-only. Full record, ledger and error analysis:
[phase-4u-treasury-v3-outcome.md](phase-4u-treasury-v3-outcome.md).

- **Execution: succeeded.** Summary 4, version 3, `anthropic/claude-opus-5.5` via `google-vertex/europe`, low effort. Usage outcome `ok`, `finish_reason` `stop`, complete schema-valid JSON,
  10,041 input and 3,421 output tokens, no retry, no fallback.
- **Economic verification: failed.** Status `failed_verification` under `verify-4`: 13 errors, 25 warnings, on 7 of 24 claims. The 13 errors split into: 3 `period_not_supported`, 3 `forecast_as_fact`,
  1 `missing_unit` and 6 on the one decision (5 from a single cause, 1 vote-notation false rejection).
- **Cost:** US$0.1182479760 for this call. Lifetime spend US$0.6267107880 of US$5.00; **remaining US$4.3732892120** (the earlier US$4.49 was the pre-run figure). Attempts 4 of 4: none left.
  Limits and caps are unchanged.
- **Display:** with `auto_display` on, the internal draft list shows summary 4 as "failed automated checks", unreviewed. It is not human-reviewed, and nothing in it is independently validated.
  The automated checks do not test the economics.
- Section H's last line ("That uses the fourth and last lifetime attempt") has now happened. Any further request needs the separately reviewed code change described under
  "Future commentary updates"; nothing in this outcome authorises one.

## Rollback

Remove `auto_display` from `data/internal-drafts.json`, or stop passing `--internal-drafts` (since Phase 4AA: pass `--no-internal-drafts`). There is no migration and no database write.
The gold-bound `Approval` format still works for the experiment.
