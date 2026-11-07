# Phase 4U: Treasury version 3 pilot outcome and diagnosis of the 13 errors

7 November 2026, Pacific/Auckland. Baseline main `8fbcb36` (PR #48 merged). Documentation only: no code, verifier, prompt, ledger, limit or permission changed.
**No OpenRouter request, crawl, scheduler, deployment or merge.** Local evidence is in the ignored `data/phase-4u/`; this file holds codes, counts and
structural metadata only. It contains no Treasury text, model output or quoted claim.

## Verdict

- **Inference execution: succeeded.** One request, complete schema-valid JSON, normal finish.
- **Economic verification: failed.** `verify-4` rejected summary 4 with 13 errors on 7 of its claims.
- **Nothing here is independently validated.** The automated checks test where a quote, number, unit and horizon sit in the stored text. They do not test the
  economics. No person has read summary 4. It is an unreviewed internal draft that displays as "failed automated checks".
- The error classes below are **rule-computed proposals**, made without reading the report. Only one error is demonstrated as a verifier gap. Every other row needs the
  owner's read of the private review page before it is treated as settled.

## A. Recorded outcome (verified from the local database, read-only)

| Field | Stored value |
|---|---|
| Summary | id 4, document version 3 (Treasury, 5-page PDF, sections 0 to 2 = pages 1 to 3 sent), run 3, attempt 1 |
| Status | `failed_verification`, review status `unreviewed`, no error class |
| Pipeline | prompt `outlook-v5`, processing `3b-1`, verifier `verify-4`, experiment `phase-4s-treasury-v3` |
| Route | `anthropic/claude-opus-5.5`, `google-vertex/europe`, serving provider Google, low effort, 12,000-token cap, ZDR on, data collection deny, no fallbacks |
| Response | usage outcome `ok`, `finish_reason` = `stop`, 10,041 input and 3,421 output tokens, 0 reasoning tokens, 24,861 ms, not estimated |
| Integrity | SHA-256 of `raw_output` equals the stored `output_sha256` (8,115 characters). Stored verification re-runs to the same 13 errors and 25 warnings |
| Verification | `verify-4`, `passed` false, **13 errors, 25 warnings** (12 `definition_not_stated`, 8 `source_not_named`, 4 `horizon_without_period`, 1 `weak_lexical_support`) |
| Draft display | `auto_display` on: summary 4 is listed as an internal draft with 24 claims: 7 failed, 11 warning, 6 clean |
| Human evaluation | `not_evaluated`, no gold |

HTTP 200 is not a stored field. The recorded facts that imply a successful response are the settled reservation, the usage outcome `ok` and `finish_reason` = `stop`.

### Ledger reconciliation (exact, from `research_llm_reservation` and `research_llm_usage`)

| Reservation | Version | Run | Outcome | Settled USD |
|---|---|---|---|---|
| 1 | 2 | 1 | `output_truncated` | 0.1798984440 |
| 2 | 1 | 1 | `invalid_response` | 0.2023797600 |
| 3 | 1 | 2 | `failed_verification` | 0.1261846080 |
| 4 | 3 | 3 | `failed_verification` | **0.1182479760** |
| **Lifetime spend** | | | | **0.6267107880** |
| **Remaining of the US$5.00 lifetime cap** | | | | **4.3732892120** |

- `lifetime_spent()` returns the same 0.6267107880, and the sum of the four usage rows matches it. The reserved worst case for run 3 was 0.3900688; it settled on the reported cost.
- **Do not reuse US$4.49.** That figure (4.491537188) is `period_remaining_usd` in `data/phase-4t/run/result.json`, which was computed before the run settled (5 minus 0.508462812).
- **Attempts: 4 of 4 used** (`LIFETIME_ATTEMPTS` = 4), none left in this build. Version 3 has used 1 of its 2 per-version attempts. No retry ran. Limits and caps are unchanged by this phase.

## B. Forensic comparison of summary 4 against version 3

Method: `data/phase-4u/forensics.py` (ignored, not committed). It opens the database `mode=ro`, re-runs the unmodified `verify-4` on the stored summary and the stored sections,
and uses the verifier's own helpers for diagnostics. It writes one private page, `data/phase-4u/summary-4-review.html` (mode 0600), and prints only codes, counts and booleans. Nothing stored changed.
The page shows each claim in full, its citation, the source context with the quote marked, the stored verifier message, the diagnostic reasons and a proposed class,
and lets the owner record a different class (kept in the browser until exported).

The 13 errors fall on seven claims: six facts (0, 4, 6, 8, 9, 11) and the one decision. Five of the six decision errors share one cause.

| # | Error code | Claim | Proposed class (rule-computed) | What the diagnostics show (no text) |
|---|---|---|---|---|
| 1 | `period_not_supported` | fact 0 | Ambiguous, conservative failure | The figure's own clause states two months; the claim names one. The verifier calls that "ambiguous or contradictory period". Prompt rule 6 says leave `period` null in this case |
| 2 | `period_not_supported` | fact 6 | Ambiguous, conservative failure | Same pattern |
| 3 | `period_not_supported` | fact 8 | Ambiguous, conservative failure | Same pattern |
| 4 | `forecast_as_fact` | fact 0 | Ambiguous, conservative failure | Forward stems `expect` and `to be`, no outturn wording, and the clause refers to a past period. Rules cannot settle it |
| 5 | `forecast_as_fact` | fact 4 | Ambiguous, conservative failure (false-positive candidate) | Only the generic stem `to be`, no outturn wording, past period reference |
| 6 | `forecast_as_fact` | fact 11 | **Possible verifier false positive** | The only forward match is the noun form of `expect`; a future-period reference. If it is a survey measure of expectations it is an outturn the report states |
| 7 | `missing_unit` | fact 9 | **Genuine model omission** | The cited text shows a currency or scale marker beside the value, so the unit was recoverable; the model left it null |
| 8 | `decision_not_in_evidence` | decision 0 | Ambiguous, conservative failure | Root error. A cited sentence has a decision verb, the OCR and one resulting rate, but a forward-list word sits ahead of the verb in the same clause. In memory, neutralising it makes the wording rule pass, but the adopted clause also matches both a hold word and an increase word |
| 9 | `decision_instrument_not_supported` | decision 0 | Cascade of #8 | No sentence was accepted as the decision, so there was nothing to check |
| 10 | `decision_rate_not_supported` | decision 0 | Cascade of #8 | Same |
| 11 | `decision_action_not_supported` | decision 0 | Cascade of #8 | Same, and the double action wording would fail it anyway |
| 12 | `decision_date_not_supported` | decision 0 | Cascade of #8 | Same |
| 13 | `vote_not_in_evidence` | decision 0 | **Verifier false positive, confirmed** | See the next section |

Counts: ambiguous 10 (3 period, 2 forecast, 5 decision), possible false positive 1, confirmed false positive 1, genuine model omission 1.
No row was demonstrated as a genuinely unsupported claim, and none as a claim the report supports beyond doubt except row 13's notation. That is a limit of rules, not a finding of accuracy.
Rows 1 to 3 are also a contract limitation: there is no structured place for the base period of a comparison, so the safe move is null.
Rows 8 to 12 also show an evidence-selection issue: the one sentence in the given sections that passes the decision-wording rule is not the one cited, and it states no rate, so swapping to it leaves four errors.

### OCR vote notation: `4:3` against `4–3`

- The report states the vote with a colon, once, and the model copied the claimed pair correctly. The raw PDF (pages 1 to 3, read fresh with pypdf) also has a colon, so this is the document's notation and not an extraction artefact.
- `_VOTE_PAIR` reads a dash (`–`, `—`, `-`) or the word "to" between the counts. It has no colon form. Synthetic probe with the unmodified verifier: `4–3`, `4-3`, `4 to 3` and `four to three` are read as (4, 3); `4:3`, `4 : 3` and `4/3` are not read at all.
- Counterfactual, in memory only: rewriting the colon vote notation as an en dash in the vote sentence and re-running the unmodified verifier removes `vote_not_in_evidence` and no other error.
- So the 13th error is a false rejection caused by notation. Fixing it would not change the draft's status: the other 12 errors remain.

## C. Recommended remediation, in priority order

No threshold is relaxed, no verifier or prompt is changed in this PR, and nothing here needs inference.

1. **Verifier defect with a failing-first test (confirmed): vote colon notation.** Add `:` as a separator in the vote-pair pattern, with synthetic tests (colon accepted; a wrong pair still rejected; a time such as `9:30` in a non-vote sentence ignored). Risk: low; the pair must still equal the claimed pair and sit in a sentence with vote wording.
2. **Owner read of the private page** (rows 4 to 6 and 8 to 12). Two candidate verifier gaps are waiting on it, and each needs its own failing-first test on a synthetic sentence if confirmed: (a) the noun `expectations` matching the forward-word stem; (b) a forward-list word ahead of the decision verb in the same clause. Do not patch either before the read: both guards protect against forecasts presented as fact or as decisions.
3. **Prompt `outlook-v6` (offline, tested without inference).** (a) Reconcile rule 3 ("never fill a missing unit") with rule 8: a unit shown beside the figure must be recorded, null only when the document gives no number. (b) Decision entries: cite the single sentence that states the action and resulting rate, and cite the vote in its own quote; do not quote a clause that also carries a forward-looking word. (c) State plainly that a clause naming two periods gets a null `period` (three violations here). Risk: prompt edits change the cache key and need a new freeze; the effect can be measured only by a new request.
4. **Evidence selection.** Offer the model numbered sentences and let it cite by number, with the pipeline filling the verbatim quote. This removes quote and truncation errors and pins the sentence context. Larger change; design it offline first.
5. **Contract v3 (optional).** A `comparison_period` field so a figure's base period can be stated without breaking rule 6. Risk: schema, verifier and UI changes.
6. **Omit when unsupported.** Rule 14 already says to leave out a claim the evidence cannot support. Candidates the verifier shows: facts whose clause is forward-worded with no outturn, decisions whose cited clause carries two action words, facts with a unit but no unit field. Whether the dashboard should collapse failed claims is a policy choice for the owner.
7. **Future operator-controlled inference.** Attempts are 4 of 4, so any further request needs a separately reviewed code change: a standing operator-signed policy (institution, series, one call per document version, a fixed cap, an expiry), an explicit command per document, and a raised lifetime attempt limit made only in that change, with history kept. The remaining US$4.3732892120 does not by itself permit anything. Do not run another request until items 1 to 3 are done and a replay of the stored output against the new verifier shows the effect.

## D. Dashboard status and next phase

- **Internal dashboard:** `nzstats serve --no-scheduler --internal-drafts` with `auto_display` lists summary 4 (latest Treasury report) and summary 3 (older version). Read-only check through `draft_summaries`: summary 4 has 24 claims (7 failed, 11 warning, 6 clean), status `failed_verification`, `unreviewed`. It carries the fixed notice and shows each claim's check result. It is not checked, reviewed or published, and it never reaches the public, private or snapshot gates. The server and UI were not started for this record.
- **Recommended next phase: 4V, offline.** (1) The owner reads the private page and records classes. (2) Failing-first tests and the colon fix for the vote pair. (3) Tests for any candidate the owner confirms. (4) Draft `outlook-v6` and a replay harness over the stored output. (5) Score summary 4 against gold if the owner chooses to provide it; version 3 now has a stored summary, so `score-gold` can measure it. No inference.

## Verification

| Check | Result |
|---|---|
| Ledger | Four settled reservations and four usage rows agree; `lifetime_spent()` = 0.6267107880 |
| Stored output | Hash intact; verification reproduces exactly (13 errors, 25 warnings) |
| Database writes | None. Opened `mode=ro`; no migration |
| Private page | Generated locally, mode 0600, in ignored `data/`; 13 sections; no network resources |
| Code, tests | No code changed, so the suites were not re-run for this PR |
| Independent review | Not run. Codex refuses every model on this machine (recorded in Phase 4T); no hosted reviewer saw any Treasury text |
