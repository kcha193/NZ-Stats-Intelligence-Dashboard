# Phase 4S: validation readiness and Treasury version 3 pilot preparation

7 November 2026, Pacific/Auckland. Baseline: main `61214c7` (PR #46 merged 6 Nov 21:15 UTC).

**No OpenRouter request, crawl, scheduler, deployment, approval or merge happened. Nothing was published.** This record holds metadata only: counts, codes, hashes.
Report text, the frozen request body, model output and gold stay in ignored `data/`. No report text, annotation or key was read into the hosted session
(the freeze body was inspected by parameter names and message sizes only).

## Verdicts

| Subsystem | Verdict | Why |
|---|---|---|
| Human gold for version 3 | **NOT AVAILABLE, stopped at the owner gate** | No gold file exists. See below |
| Validated scoring | **Not possible yet, and not possible before the run** | `score-gold` scores stored summaries; version 3 has none |
| Treasury version 3 pilot | **GO WITH CONDITIONS to review the code change and freeze. NO-GO to run** | Conditions below |
| Stats NZ on-open refresh | **GO WITH CONDITIONS** (unchanged) | Labour evidence intact. The next live proof is card spending on 12 Nov |
| Economic intelligence, private and public display | **NO-GO** (unchanged) | No complete, verified, human-reviewed summary |
| Public site, Netlify | **NO-GO** (unchanged) | Not touched |

## Repository health

| Check | Result |
|---|---|
| PR #46 | Merged, merge commit `61214c7` |
| CI on main for that merge | All three jobs fail in about 5 seconds with no failed step. Same cause as recorded in Phase 4R: the account's payment or spending limit stops the jobs from starting. **Billing, not code.** The last green runs (PR #43 and earlier) ran the same suite. Rerun needs the owner to clear the billing block; the agent has no access to it |
| Backend suite on main (local) | **4,980 passed**, 0 failed |
| Backend suite, ruff, format on this branch | See Verification |
| npm audit | 0 vulnerabilities |
| Python audit (`pip-audit` run in isolation on the venv's packages) | 9 findings in 2 packages, all in the **local venv**: `pypdf` 6.21.2 (fixed in 6.21.3 and 6.21.4) and `certifi` 2026.7.22 (fixed in 2026.10.18). The repo already requires `pypdf>=6.21.4`, so CI is not affected. The owner decides the venv update (`pip install -U pypdf certifi`); it was not done here |

## Owner review package and human gold

`research owner-review-package --out data/phase-4s/owner-review-check` (a separate directory, so the owner's page was not overwritten) ran offline and reads no model output.
Result: 130 gold sentences, gold status **"not saved yet: expected at data/annotations/gold-extension-v3.json"**, review sections **withheld**. The package is still blind, as designed.

The owner's decisions file of 7 November (`gold-done: Yes`, `third-party-in-scope: Yes, they count`) exists in `data/phase-4r/` and `~/Downloads/`. **It is a record of answers, not gold.**
No `gold-extension-v3.json` exists in `data/annotations/`, `data/`, Downloads or Desktop. Nothing here treats the gold as done. The second answer is recorded
for the scoring rules: third-party forecasts count in scope.

**Exact owner steps** (nothing here needs Claude Code, and none of it should be done with a model output open):

1. Open `data/phase-4r/owner-review/gold-worksheet-v3.html` in a browser. Do not open `data/phase-4q/feu-comparison.md`, `data/annotations/phase-4q-feu-2026-10-29.json` (the AI pack), any draft or summary page.
2. Mark the sentences. Use "Add another claim from this sentence" for each extra claim. Type your own name and the date, tick the attestation, then press "Check and download gold extension". The browser saves `gold-extension-v3.json`.
3. `mv ~/Downloads/gold-extension-v3.json data/annotations/ && chmod 600 data/annotations/gold-extension-v3.json`
4. Check it is valid: `nzstats research score-gold --extension data/annotations/gold-extension-v3.json`. A valid file prints "version 3: no stored summary to score". An invalid one prints "refused: the gold extension is not valid: ...".
5. `nzstats research owner-review-package` (default output). The page now unlocks the remaining decisions. Answer them and save the decisions file.
6. Tell Claude Code the file is in place. It will record the file's SHA-256 for the approval, and nothing else about its contents is needed.

## Scoring

Not run. `score-gold` joins the gold extension to **stored `verified` or `failed_verification` summaries of the same version** (`cli._score_gold`). Version 3 has no summary,
so every denominator is zero ("unmeasured", never a pass) even once gold exists. Precision, recall, numerical fidelity, period exactness and issuer accuracy become
measurable only from the output of the one experiment below, which is the reason to run it. Before the run, gold also lets the owner confirm the gold's own validity (step 4) and fix the targets.

## Verifier limitations

No verifier, threshold or prompt change was made. The material limits for this experiment stay as Phase 4Q and 4R recorded them, and all fail closed:
a true figure beside a comparison in one clause is rejected (prompt `outlook-v5` asks for a null period in that shape, and a Phase 4Q test confirms that passes);
4,830 true labels refused and 4,072 wrong third-party labels accepted by the older wording (all identical at the Phase 4Q baseline); a decision reported second-hand cannot pass.
**One failed claim rejects the whole summary**, so a rejection is the likely outcome for a thin or ambiguous document even when most claims are right. That is why the
experiment is judged on raw measures against human gold, not on the verifier's verdict. No new synthetic search for further wordings was run: the Phase 4R convergence
review found that more patching moves error between classes, and its proposal is a separate, reviewed `verify-5` after the owner's decisions.

## The experiment: Treasury version 3, one request

Prepared by a reviewed code change in this PR. **It authorises nothing.**

| Item | Value |
|---|---|
| Experiment | `phase-4s-treasury-v3`, `max_attempts=1`, spend cap **US$0.50** |
| Document | Treasury version 3, 29 October 2026 (published 2 Nov), content `f39f10d7…f4e6`, text `d2092d5b…57a5`, sections hash `253087af…0c9e` |
| Sections | Ordinals 0 to 2 (pages 1 to 3, the prose), 13,141 characters. Pages 4 and 5 (tables and credited third-party charts) excluded |
| Prompt, verifier, contract | `outlook-v5` (rules `f976a085…1ae0`, never used by any request), `verify-4`, processing `3b-1`, contract 2 |
| Model and route | `anthropic/claude-opus-5.5`, alias target `…-20260921`, `google-vertex/europe` only, ZDR, `data_collection=deny`, no fallback, `require_parameters` |
| Reasoning, output cap, timeout | Low, **12,000** tokens, 300 s |
| Attempts | One request, no retry. It uses the **last** of the 4 lifetime attempts, which is also RBNZ's only remaining slot |
| Freeze | Format 3, `data/phase-4s/freeze/`. `freeze.json` SHA-256 `ab615391…8fd7`, request `2f15b2e1…d928`, body `7f297b40…519a`. Messages: system 12,896 characters, user 13,644 |
| Re-freeze | Draws a new random boundary and changes every hash. If anything below changes, freeze again and re-approve |

**Conservative cost.** Worst case **US$0.3901**: every input byte counted as a token, plus 2,048, plus the full 12,000 output tokens at US$4.40 and US$22.00 per million.
That is inside the US$0.50 cap and inside the US$4.49 remainder. Spent so far is US$0.508463 of US$5, so the worst case takes the lifetime total to US$0.899, and the experiment cap is a hard ceiling of US$1.009.
Phase 4O's real run cost US$0.126 for 16,693 input and 2,455 output tokens; a likely actual here is US$0.10 to 0.20, an estimate and not a measurement.

**Why a separate experiment.** The Phase 4N plan hard-coded versions 1 and 2, a fixed experiment name, a fixed approval literal and "exactly one prior attempt".
Those are right for 4N and wrong for a version with no attempt. `pilot.PilotPlan` now carries each experiment's versions, freeze format and expected prior attempts.
Each plan refuses the other's versions; format 3 freezes and `phase-4s-treasury-v3` approvals cannot run under 4N, and the reverse. The ledger, the lifetime limit of 4, the US$5 cap and the per-version limit of 2 are unchanged,
and no attempt, response or cost record was touched or reset.

### Rechecks before the freeze (7 Nov, unauthenticated catalogue reads, no key, no inference)

| Item | Result |
|---|---|
| Model alias and slug | Listed once, `canonical_slug` `anthropic/claude-opus-5.5-20260921`, as approved |
| Route | `google-vertex/europe` found exactly once in the ordinary and the ZDR lists. Provider `Google`, status 0 |
| Retention and caching | ZDR list: `safety_retention=false`. Ordinary list omits the field (accepted by the code as in Phase 4L). Implicit caching false |
| Capabilities | Context 1,000,000, max completion 128,000, all four required parameters supported, `low` effort supported |
| Price | Endpoint US$0.0000044 and US$0.000022 per token = US$4.40 and US$22.00 per million, as bound. The model-level listing shows the generic US$4 and US$20; the route's own price is the one billed and bound |
| Source rights | The pipeline's version-scoped hosted check passed for version 3 at freeze. Crown copyright, CC BY 4.0 with third-party material and logos excluded. **The publication page was not seen by the agent** (HTTP 403 to automation) |
| Dedicated key, account controls | **Not rechecked.** The key stays out of this session. The owner runs `scripts/openrouter_key_reading.py` (read-only, no inference) and re-confirms logging, training and ZDR settings in the account, with dated evidence |

## Stats NZ live refresh

Read-only, offline. `nzstats status`: **OK**. Refresh run 16 (4 Nov, `open`, completed, 1 discovered, 1 ingested, 0 failures, 6 requests) and ingest run 23
(labour market statistics, September 2026 quarter, `ingested`) are intact, the database passes `integrity_check`, the pre-refresh backup is verified, and all five
series are current. No scheduler was introduced and no code on the refresh path changed. Still true: this proves one release family. The next supported release is
electronic card transactions (October 2026) on 12 November 10:45 NZDT; opening the dashboard then is the next live proof.

## Remaining owner decisions and conditions

Before any run, in order:

1. Human gold for version 3 saved and valid (steps above), then the other package decisions (IMF labels, five fact years, `ocr-decision` date, `economists-author`).
2. Check the Treasury 29 October publication page in a browser and decide whether third-party content or pages 4 and 5 stay excluded (the freeze excludes them).
3. Key reading and a dated account-controls check; clear the GitHub billing block if CI evidence is wanted.
4. Review and merge this code change (independent review requested, not merged here).
5. Fix the scoring targets before the run (`phase-4q-evidence-grounding.md`: complete schema-valid JSON, zero added-year rejections, issuer accuracy 100%, numbers 100%, pages cited 3 of 3, recall with its denominator).
6. A **fresh, expiring (24 hours or less), version-specific approval** (`pilot.Approval` with `experiment: phase-4s-treasury-v3` and `experiment_spend_limit_usd: 0.5`) bound to a freeze made after the above. A merge or "go ahead" supplies none of it.

If the verifier rejects the summary, the raw measures still answer the question. The summary stays rejected and is not retried. No result is displayed or approved automatically.

## Verification

Run on this branch with `PYTHONPATH` at the worktree (the venv's editable install points at main).

| Check | Result |
|---|---|
| Backend suite | **4,994 passed, 5 skipped**, 0 failed, 5 min 58 s. The 5 skips are the jsdom gold-form tests (the worktree has no `node_modules`); they passed on main and this change does not touch the gold form |
| Ruff lint, format | Clean |
| New tests | `backend/tests/research/test_pilot_treasury_v3.py`, 19. Four guards were checked by mutation (removing the prior-attempts check, the plan's version check, or raising `LIFETIME_ATTEMPTS` makes the test that names it fail). Two tests first passed for the wrong reason (the mock key endpoint refused, not the guard); an independent reviewer and a mutation caught that and both were fixed |
| Phase 4N tests | `test_pilot.py` unchanged and passing |
| Frontend, browser, static suites | **Not re-run**: no frontend, API or snapshot code changed since Phase 4R |
| Independent review | One fresh Claude reviewer, working from the diff and synthetic tests only (no `data/`, no network). No blocker or unintended-spend path. Three test weaknesses and a mutable-dict nit, all fixed. Same model family as the author, so the Codex connector review of the PR is the different-vendor check |
| CI | Not available: billing block (see above) |
