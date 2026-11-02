# Phase 4Q: economic accuracy and evidence grounding

2 November 2026, Pacific/Auckland. Baseline: main `9332bd9`, including PR #41 and PR #42.

**Verdict: GO WITH CONDITIONS to prepare one bounded experiment. No run is authorised, and no new inference ran.** Economic intelligence,
private display and public display stay **NO-GO**. The Phase 4O rejection stands: no complete, verified summary exists.

This record holds metadata only: codes, counts and hashes. Worksheets, gold and diagnostics stay under ignored `data/phase-4q/`.

## Handling of reports and model outputs

The brief requires reports and model outputs to stay out of Claude Code's hosted context.

- **Model outputs:** never displayed to the agent. Local scripts printed codes, booleans, counts and masked token shapes only.
- **Reports:** this session had already read the full text of both FEUs and part of the RBNZ release, for the earlier Treasury assessment
  (`phase-4q-treasury-feu-refresh.md`), before this instruction arrived. That cannot be undone. Nothing further was read, and the scratch copies
  were deleted. The shared session context means this diagnosis is not fully blind to the reports, which is one more reason for the human review.
- **Worksheets:** written straight to ignored files, without being displayed.

## Root causes of the Phase 4O failures

Stage 1 tested each of the five rejected facts by code. "Year removed" reruns the verifier on a copy with only the year taken out.

| Fact | Year stated within 2 sentences | Baseline period | Extraction | Passes `verify-4` with year removed | Finding |
|---|---|---|---|---|---|
| 0 | No | No year | Quote found by a second extractor | Yes | **Model-added year.** `verify-3` also misread a comparison's period as this figure's |
| 1 | No | Same figure and month, **different year**, by number match only | Found | Yes | **Model-added year.** The year is not stated near the figure, and may also be wrong. Needs a person |
| 2 | No | No year; month agrees | Found | No | **Model-added year, and no period in the cited sentence.** The sentence's only month is a comparison base. Needs a person |
| 3 | Only in the comparison's own period | Same year and month | Found | Yes | **Year borrowed from the comparison base.** Plausibly true, not stated for this figure. Needs a person |
| 4 | No | No year | Quote found. Sentence boundary differs between extractors | Yes | **Model-added year** |

| Category in the brief | Result |
|---|---|
| Model-invented years | **4 of 5** (facts 0, 1, 2, 4). The year is absent near the figure and equals the publication year. Whether the year is true is a separate question; it is not stated |
| Incorrectly inferred reference period | **1 of 5**, fact 2: month and year taken from outside the cited sentence |
| Genuine periods the verifier missed | **2 of 5 had a real verifier weakness**, facts 0 and 3: a comparison's period read as ambiguous. Neither fact passes as written, because each also has the year problem |
| Ambiguous source dates | **2 for a person:** fact 2 (period only in the previous sentence) and fact 3 (year only in the comparison) |
| Wrong period from extraction | **None found.** All 5 quotes are found by a second extractor. Fact 4's sentence boundary is flagged for the reviewer, and its period result does not depend on it |

**Main cause:** the prompt forbade filling a forecast's horizon but said nothing about a fact's period, and it supplied the publication date. Where the
sentence gave no year, the model supplied one.

**Separate rejections, unchanged:** one forecast's horizon and fiscal basis, and one forecast's issuer. They still fail under `verify-4`.

## Confirmed model errors versus possible verifier errors

| | Items | Confidence |
|---|---|---|
| Model added a year not stated for the figure | Facts 0, 1, 2, 4 | High, by location. A person should confirm against the PDF |
| Model cited a sentence without the period | Fact 2 | High for the location, not for the reading |
| Verifier misread comparisons | Facts 0, 3 | Confirmed by synthetic reproduction, fixed. Fact results are unchanged |
| Verifier accepted a comparison month as the figure's period | No Phase 4O fact relied on this | Confirmed by failing test, fixed: a real false acceptance |
| Verifier accepted a third party's forecast labelled as the author's | Found on the 29 October pack | Confirmed by failing test, fixed |
| Five "IMF" labels on Phase 4O forecasts | Unresolved | Needs the human review. The verifier cannot settle them |

## Changes

### Prompt `outlook-v5`

Rules SHA-256 `0afe7ab091760eab…`, full value in `config/phase-4q-prompt.json`. **No request has used this prompt.**

- Dates and periods copied exactly as stated beside the figure. A missing year stays missing. Nothing is added from the publication date, page
  header, another sentence or reasoning. No period in the sentence means a null period.
- The base of a comparison is that other figure's period.
- Facts and forecasts are never restated as each other.
- A reported forecast belongs to whoever made it, including "the MPC expects" and "markets expect". If the document does not say whose it is, it is left out.
- Coverage: each headline point and main heading gets its main figure or a statement. An unsupported claim is worse than a gap.

`outlook-v4` stays reproducible byte for byte, with a test against both recorded hashes. The Phase 4N experiment stays bound to it.

### Verifier `verify-4`

| Change | Effect | Test |
|---|---|---|
| A figure's period stops at a comparison ("up from", "from N in", "compared with", "compared to", "versus", "relative to"), but only when the figure really is part of that comparison | Accepts a figure's true period beside a comparison. Rejects a comparison's period used as the figure's | `test_period_grounding.py` |
| A comparison holding its own period stops a heading or neighbouring sentence from supplying one | Stricter | `test_period_grounding.py` |
| "said it expected", "expected" directly after a name, and "markets expect" or "markets expected" credit the forecaster. Comparatives ("higher than the RBNZ expected") credit nobody, and the wording is not inherited from an earlier sentence | Stricter: relabelling as the author is rejected | `test_verify_attribution.py` |
| Several third parties credited in one clause can no longer cancel out | Stricter: none of them is the author | `test_verify_attribution.py` |

No threshold changed. One failed claim still rejects a summary.

**The first `verify-4` was wrong, and review caught it.** It introduced two false acceptances that `verify-3` rejected: a comparison before a figure could become the figure's period, and
a second mention could hide a third party's forecast. Both now have failing-first tests and are fixed. This change accepts some claims `verify-3` rejected, so it is **not** purely a tightening. An old-versus-new
differential on 2,420 invented cases found 152 newly accepted, all giving the figure its true period, and 112 newly rejected, all a comparison month or a heading wrongly supporting a figure. That is a test of the shapes tried, not a proof.

### Measured effect, offline, no model

| Measure | Before | After |
|---|---|---|
| Phase 4O summary, recomputed | 8 errors; 10 clean, 1 warning, 7 failed | **Identical** |
| Facts passing with only the year removed | 2 of 5 | 4 of 5 |
| 29 October pack: corruptions caught, of those measurable | 57/59 | **69/69** |
| 29 October pack: wrong issuer caught | 2/4 | **4/4** |
| 29 October pack: true claims rejected | 9/26 | 7/26 |

The 69/69 covers only the probe's fixed corruptions. It could not detect the two false acceptances above, so it is not evidence that nothing was weakened. The pack is an AI reading of one document, not human gold. The remaining rejected claims: 3 `forecast_as_fact` where an outturn shares a clause with a
forecast word, 2 `period_not_supported`, 1 second-hand decision and 1 unit the contract lacks. None were changed, because they fail closed and need a
person's view.

The stored Phase 4O row is untouched and still records `verify-3`. Internal drafts rerun the checks, so the draft page now names `verify-4`, with the same counts.

## Gold evaluation proposal

The Phase 4O gold could not show a good result: all five forecasts were expected rejections, and third-party forecasts were excluded.

`research/gold_extension.py` adds an extension with four separately scored groups: accepted-eligible, expected rejection, ambiguous and third-party forecast.
It is refused unless a named reviewer is recorded, the name is not an AI tool's, the date is not in the future, and it attests it was written without seeing model output. Those are attestations, which code cannot prove.

`research gold-worksheet VERSION` builds the review sheet from the document alone, and a test denies it read access to the model-output tables. Sheets exist
locally for versions 1 and 3. **No human gold exists yet, so these are scoring tools, not results.**

| Measure, Phase 4O, existing gold | Result | Meaningful? |
|---|---|---|
| Accepted precision, citation, numbers, issuer | 0/0 | Unmeasured, never a pass |
| Accepted recall | 0/5 | No: its denominator is all expected rejections |
| Raw precision | 0/1 | No: third-party forecasts are outside the gold |
| Raw recall | 0/5 | No: same denominator |
| Indicators | 4/6 precision, 4/8 recall | Weak, one document |
| Key points covered | 1/6 | Indicative |

`research score-gold` reports precision, recall, numbers, period exactness and issuer accuracy for three views: accepted, raw and a labelled hypothetical of clean
claims. A zero denominator prints as unmeasured.

Precision counts a claim once per gold item, and a claim outside the gold or an emitted expected rejection counts against it. It is therefore only as meaningful as the gold is complete.

## Claim coverage

Counts on the Phase 4O summary, compared with the pre-model baseline, which is an AI reading.

| Measure | Summary | Baseline |
|---|---|---|
| Reported facts | 5 | 15 |
| Forecasts | 6, 4 with a value, 5 labelled third party | 7 |
| Interpretation | 7, including the outlook and assumptions | 7 |
| Decisions, guidance | 0, 0 | n/a |
| Sections cited | 4 of 7 | n/a |

Evidence is concentrated in sections 1 and 2. **Section 4 and the two table sections have no citations.** Sections 5 and 6 are tables, where leaving
numbers out is often correct under rule 13, so section 4 is the clear gap. Coverage was thin, at 20% of the output cap: the budget was not the limit. Whether low effort or the
prompt caused it cannot be separated from one run. `outlook-v5` addresses the prompt, and only a run can test it.

## Per-claim acceptance

Design only: [phase-4q-per-claim-design.md](phase-4q-per-claim-design.md). Whole-summary rejection stays.

## Internal draft security

Checked by test and on real data with loopback requests. The output was codes and counts only.

| Requirement | Evidence | Result |
|---|---|---|
| Off by default | Capability false; feed and detail 404, the same as an unknown path | **Pass** |
| Loopback only | Binds to `0.0.0.0` and a LAN address exit 2. Other `Host`, cross-origin and cross-site requests get 403, and so does a missing client header | **Pass** |
| Read only | POST and DELETE 405. `no-store`, `noindex`. `research_summary` unchanged after reads | **Pass** |
| Revoked route withheld | **Failed at PR #42.** The gate never checked that the approval which let a document in was still in force, so a revoked route's draft stayed visible. Fixed in PR #43, test-first. The real Treasury draft is unaffected: its route is approved | **Fixed** |
| Failed claims prominent | 8 of 18 claims carry their problems. Headline "failed checks, not approved"; tested in the page | **Pass** |
| Never labelled verified | `approved_for_publication`, `official_statistic` and `human_reviewed` false. The page never shows the checked, reviewed or published labels | **Pass** |
| No static or public exposure | Exporter isolation, `netlify.test.ts` and `scripts/e2e_static.sh` (see `progress.md`) | **Pass** |
| Allowlisted response | No raw output, hash, cost, parameter or owner note fields | **Pass** |
| No effect on verification | The stored status and review are unchanged by viewing | **Pass** |

**Disclosures.** PR #43 added a "Reports held" list to this mode: title, date and link for each report, with no document text. It widens what the mode lists, under
the same gate, not which drafts are visible. The Outlook header's line about approved research still describes published research, as Phase 4P recorded.

## Independent review

Codex was the intended reviewer, but the account's model access failed on both tries and it produced no review. A fresh Claude reviewer did the work instead, in a worktree with no `data/`, using invented text. It is independent of this
session's reasoning but is **not a second vendor**, and its model family is the same as the author's.

| Finding | Severity | Status |
|---|---|---|
| Comparison before a figure became its period | P0 | Fixed, failing-first |
| A second mention hid a third party's forecast | P0 | Fixed, failing-first |
| Heading supplied a period once a comparison was cut | P1 | Fixed |
| False rejections from over-broad "expected" | P1 | Fixed |
| Market issuer names and table rows | P2 | Fixed |
| Gold scoring: year-only periods, no-value items, duplicates, expected rejections, blank terms, repeated ids | P2 | Fixed |
| Review gate accepted a blank reviewer or a future date | P2 | Fixed |
| Bad stored output could echo text at the terminal | P2 | Fixed |
| Draft gate ignored a revoked route (from PR #42) | Baseline | Fixed |
| Malformed stored date, ties, incomplete decision items | P3 | Fixed |

**Accepted, not changed:**

- "Higher than the RBNZ expected" with the RBNZ as third-party issuer still passes. This predates Phase 4Q.
- `rules_for` gives current rules to an unknown label. Production callers name a known version, and a hosted request's consent binds the hash of what is sent.
- `RULES_SHA256` is enforced by tests, and only as a membership check at runtime.

## Bounded proposal for the next experiment

**Not approved and not built.** Treasury version 1 is consumed and is not reset.

| Item | Proposal |
|---|---|
| Purpose | Test whether `outlook-v5` removes added years and improves coverage |
| Document | Treasury version 3, prose pages 1 to 3 only. Tables and third-party data pages excluded |
| Requests | **1**, no retry, no fallback |
| Changed variable | The prompt. Effort stays low, the cap 12,000, the route unchanged. Version 3 differs from version 1, so this is **not** a clean before-and-after |
| Bound | About US$0.40 by the Phase 4O method, to confirm at freeze. Limit US$0.50, inside the US$4.49 lifetime remainder |
| Attempts | Uses the last of the 4 lifetime attempts, **which is also RBNZ's only remaining slot.** The owner decides |

**Scored against targets the owner fixes before the run, on human gold:**

- Complete, schema-valid JSON.
- `period_not_supported` from an added year: 0.
- Forecast issuer accuracy: 100%. Numbers among matched claims: 100%.
- Prose pages cited: 3 of 3. Recall reported with its denominator.

If the verifier rejects the summary, the raw measures still answer the question. It stays rejected and is not retried.

**Before any run, in order:**

1. Owner resolves `period-review-worksheet.html` and the Phase 4O human review.
2. Owner completes human gold for version 3 from `gold-worksheet-v3.html`, without opening any model output.
3. Owner checks the publication page and decides on third-party content.
4. The post-run key reading from Phase 4O is recorded.
5. A reviewed code change adds the experiment and version.
6. Fresh, version-specific, expiring consent bound to a new freeze.

## Verdict

| Decision | Verdict |
|---|---|
| Prompt v5 and `verify-4` | **GO WITH CONDITIONS:** owner review of the PRs, given the false acceptances the first version had. They run nothing |
| Internal draft mode | **GO**, loopback only, no broader visibility |
| Preparing the next experiment | **GO WITH CONDITIONS**, the six above |
| Running OpenRouter now | **NO-GO** |
| Per-claim acceptance | **NO-GO** until designed and independently reviewed |
| Economic intelligence, private and public display | **NO-GO** |
| RBNZ | **NO-GO** on this configuration |

No attempt was reset, no result changed, no threshold loosened, no OpenRouter request made, no security control weakened, and nothing published.
