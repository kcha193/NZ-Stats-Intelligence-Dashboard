# Phase 4Q: economic accuracy and evidence grounding

2 November 2026, Pacific/Auckland. Baseline: main `9332bd9`, including PR #41 and PR #42.

**Verdict: GO WITH CONDITIONS to prepare one bounded experiment. No run is authorised, and no new inference ran.** Economic intelligence,
private display and public display stay **NO-GO**. The Phase 4O rejection stands: no complete, verified summary exists.

This record holds metadata only: codes, counts and hashes. Worksheets, gold and diagnostics stay under ignored `data/phase-4q/`.

## Handling of reports and model outputs

The brief requires reports and model outputs to stay out of Claude Code's hosted context.

- **Model outputs:** never displayed to the agent. Local scripts printed codes, booleans, counts and masked token shapes only.
- **Reports:** this session had already read the full text of both FEUs and part of the RBNZ release, for the earlier Treasury assessment
  (`phase-4q-treasury-feu-refresh.md`), before this instruction arrived. That cannot be undone. The agent read no further report text on purpose, and
  the scratch copies were deleted. The shared session context means this diagnosis is not fully blind to the reports, which is one more reason for the human review.
- **Exposure after the instruction:** when the session resumed on 3 November, the tool automatically re-read the local FEU comparison note and the AI-written
  gold pack into the agent's context. Both hold report quotes, paraphrases or values the session had already read. Neither holds model output, and neither is human gold.
- **Worksheets:** written straight to ignored files, without being displayed.

## Root causes of the Phase 4O failures

Stage 1 tested each of the five rejected facts by code. "Year removed" reruns the verifier on a copy with only the year taken out.

| Fact | Year stated within 2 sentences | Baseline period | Extraction | Passes with year removed | Finding |
|---|---|---|---|---|---|
| 0 | No | No year | Quote found by a second extractor | No: a comparison in the clause | **Model-added year, plus the verifier's comparison limit** |
| 1 | No | Same figure and month, **different year**, by number match only | Found | Yes | **Model-added year.** It is not stated near the figure and may also be wrong. Needs a person |
| 2 | No | No year; month agrees | Found | No | **Model-added year, and no period in the cited sentence.** The sentence's only month is a comparison base. Needs a person |
| 3 | Only in the comparison's own period | Same year and month | Found | No: a comparison in the clause | **Year borrowed from the comparison base, plus the verifier's comparison limit.** Plausibly true, not stated for this figure. Needs a person |
| 4 | No | No year | Quote found. Sentence boundary differs between extractors | Yes | **Model-added year** |

| Category in the brief | Result |
|---|---|
| Model-invented years | **4 of 5** (facts 0, 1, 2, 4). The year is absent near the figure and equals the publication year. Whether the year is true is a separate question; it is not stated |
| Incorrectly inferred reference period | **1 of 5**, fact 2: month and year taken from outside the cited sentence |
| Genuine periods the verifier missed | **2 of 5 meet a real verifier limit**, facts 0 and 3: a comparison in the clause reads as an ambiguous period. Each also has the year problem, so neither fact is a clean false rejection. The limit is **kept**: see below |
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
| Verifier rejects a true period beside a comparison | Facts 0, 3 | Confirmed on synthetic text. **Not fixed**: it fails closed, and the attempted fix failed review twice |
| Verifier accepted a comparison's period as the figure's | No Phase 4O fact relied on this | Confirmed by failing test, a real false acceptance. Closed for "from", "compared with", "relative to" and "versus". Open under both versions for "above", "against", "vs", "since" and a leading "From N in" |
| Verifier accepted a third party's forecast labelled as the author's | Found on the 29 October pack | Confirmed by failing test, fixed |
| Five "IMF" labels on Phase 4O forecasts | Unresolved | Needs the human review. The verifier cannot settle them |

## Changes

### Prompt `outlook-v5`

Rules SHA-256 in full in `config/phase-4q-prompt.json`. **No request has used this prompt.**

- Dates and periods copied exactly as stated beside the figure. A missing year stays missing. Nothing is added from the publication date, page
  header, another sentence or reasoning. No period in the sentence means a null period.
- The base of a comparison is that other figure's period. If the clause also gives a comparison's period, `period` stays null rather than choosing, and the quote keeps the document's words.
- Facts and forecasts are never restated as each other.
- A reported forecast belongs to whoever made it, including "the MPC expects" and "markets expect". If the document does not say whose it is, it is left out.
- Coverage: each headline point and main heading gets its main figure or a statement. An unsupported claim is worse than a gap.

`outlook-v4` stays reproducible byte for byte, with a test against both recorded hashes. The Phase 4N experiment stays bound to it.

### Verifier `verify-4`

**`verify-4` only tightens.** `verify-3`'s rule alone decides who a figure is credited to, and `organisation_of` is unchanged. Each new check can only add a rejection, and there is no exception that lets a claim pass.

| New check | Test |
|---|---|
| A period the clause states only in a comparison is not the figure's period | `test_period_grounding.py` |
| Reported wording ("said it expected", "markets expect") blocks a claim by anyone else, only when `verify-3` wording credits nobody, and not inside a comparison | `test_verify_attribution.py` |
| Several third parties credited in one clause block the author label | `test_verify_attribution.py` |
| An author credit only inside a comparison ("more than we expected") cannot hide a third party | `test_verify_attribution.py` |
| A block at any evidence spot rejects the claim, whatever another spot credits | `test_verify_attribution.py` |

No threshold changed. One failed claim still rejects a summary. A market-named issuer is exempt from the market block only, which leaves it where `verify-3` put it. "Markets" on "Market pricing" therefore stays a `verify-3` false rejection, recorded here and not fixed.

**How this was reached.** Two earlier versions also accepted true figures beside a comparison. Independent review broke both with concrete false acceptances, so that part was removed rather than patched a third time. A third review then showed "only tightens" was still false, through credit shared across evidence spots and a market exception. Both are gone.
The removed part had changed no Phase 4O result, and the brief says not to weaken rules to raise acceptance.

**Evidence, on invented sentences only, comparing against the `verify-3` source.** 30,960 period cases: 0 newly pass, 1,264 newly rejected. 429 issuer cases: 0 newly pass, 17 newly rejected. 13,728 cases with two evidence quotes: 0 newly pass, 919 newly rejected. That covers the shapes tried, and it is not a proof. The comparison script is local and not in this repository.

**Known limits.** A true figure beside a comparison in one clause stays rejected, as under `verify-3`. `outlook-v5` asks for a null period in that shape, which a test confirms passes. Accepting a stated period there needs its own reviewed design. The wordings left open in the table above behave the same under both versions, so they are not regressions.

### Measured effect, offline, no model

| Measure | `verify-3` | `verify-4` |
|---|---|---|
| Phase 4O summary, recomputed | 8 errors; 10 clean, 1 warning, 7 failed | **Identical** |
| Facts passing with only the year removed | 2 of 5 | 2 of 5 |
| 29 October pack: corruptions caught, of those measurable | 57/59 | **59/59** |
| 29 October pack: wrong issuer caught | 2/4 | **4/4** |
| 29 October pack: true claims rejected | 9/26 | 9/26 |

The 59/59 covers only the probe's fixed corruptions, so it is not evidence that nothing was weakened; the differential above is. The pack is an AI reading of one document, not human gold. The rejected true claims: 5 `period_not_supported`, 3 `forecast_as_fact` (some claims have more than one code), 1 second-hand decision and 1 unit the contract lacks. None were changed, because they fail closed and need a person's view.

The stored Phase 4O row is untouched and still records `verify-3`. Internal drafts rerun the checks, so the draft page now names `verify-4`, with the same counts.

## Gold evaluation proposal

The Phase 4O gold could not show a good result: all five forecasts were expected rejections, and third-party forecasts were excluded.

`research/gold_extension.py` adds an extension with four separately scored groups: accepted-eligible, expected rejection, ambiguous and third-party forecast.
It is refused unless a reviewer is recorded, the name is not an AI tool's, the date is not in the future, and it attests it was written without seeing model output. Those are attestations, which code cannot prove.

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

Codex was the intended reviewer, but the account's model access failed on both tries and it produced no review. Fresh Claude reviewers did the work over three rounds, each in a worktree with no `data/`, using invented text. An automated security review also ran on the pushed commits, twice.
These are independent of this session's reasoning but are **not a second vendor**: their model family is the author's. **The final design's review is recorded in `progress.md`.**

| Finding | Severity | Status |
|---|---|---|
| A comparison could become a figure's period (both earlier designs) | P0 | Removed by the tighten-only design |
| A mention could hide a third party's forecast (both earlier designs) | P0 | Fixed, failing-first |
| Heading or neighbouring sentence could supply a period once a comparison was cut | P1 | Removed |
| `Market Economics Ltd`, `Financial Markets Authority` treated as the market | P1 | Fixed: closed list |
| False rejections from broad "expected", sector markets and "Reserve Bank of New Zealand" | P2 | Fixed |
| "Only tightens" was false: credit shared across evidence spots, and a market exception (third round) | Not graded here | Fixed: credit and blocks are now separate, and the exception is gone |
| A comparison's base could take the compared figure's period, a reported third party could lose to the author's voice, and the comparison guard crossed punctuation (security review) | Not graded here | Fixed, failing-first |
| Gold scoring could flatter: years, units, duplicates, broad items, no-value items, ties, the gold's order | P2 | Fixed |
| Review gate accepted a blank reviewer, an AI's name or a future date | P2 | Fixed |
| Draft gate ignored a revoked route (from PR #42) | Baseline | Fixed |
| Malformed date disabled the draft's historical check | P2 | Fixed: withheld |
| Bad stored output could echo text at the terminal | P2 | Fixed |

**Accepted, not changed:**

- "Higher than the RBNZ expected" with the RBNZ as third-party issuer still passes. This predates Phase 4Q.
- `rules_for` gives current rules to an unknown label. Production callers name a known version, and a hosted request's consent binds the hash of what is sent.
- `RULES_SHA256` is enforced by tests, and is only a membership check at runtime.
- A draft withheld for instruction-like text still has its title in "Reports held".
- A future-dated stored report would be marked newest.
- Repeated claims no longer raise numerical accuracy, but they still count toward period exactness and issuer accuracy.

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

The recorded comparison limit means a claimed period beside a comparison would still reject the whole summary. If the verifier rejects the summary, the raw measures still answer the question. It stays rejected and is not retried.

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
| Prompt v5 and `verify-4` | **GO WITH CONDITIONS:** owner review of the PRs. They run nothing |
| Internal draft mode | **GO**, loopback only, no broader visibility |
| Preparing the next experiment | **GO WITH CONDITIONS**, the six above |
| Running OpenRouter now | **NO-GO** |
| Per-claim acceptance | **NO-GO** until designed and independently reviewed |
| Economic intelligence, private and public display | **NO-GO** |
| RBNZ | **NO-GO** on this configuration |

No attempt was reset, no result changed, no threshold loosened, no OpenRouter request made, no security control weakened, and nothing published.
