# Phase 4V: economic accuracy remediation without further inference

7 November 2026, Pacific/Auckland. Baseline main `e9ba52c` (PR #49 merged, no open PRs). **Offline only. No OpenRouter request, crawl, scheduler,
deployment, approval, permission change, ledger change or merge.** This file holds codes, counts and structure only: no Treasury text, model output or quoted claim.

## Verdict: GO WITH CONDITIONS

- The confirmed vote defect is fixed and independently tested, the other defects are fixed, safely classified or explicitly unresolved, `outlook-v6` is prepared,
  and an offline replay shows the effect on summary 4 without inference.
- **Summary 4 still fails.** The replay moves it from 13 to 11 errors and accepts no claim that was rejected before. A smaller number is not evidence that its economics are right,
  and nothing here was read by a person.
- Conditions: (1) `outlook-v6` is untested on a real model; its effect is unknown until a fresh, separately authorised experiment. (2) `verify-5` is checked on constructed
  sentences and one stored summary, not on a labelled sample of real documents. (3) Any further inference needs the separately reviewed policy in
  [phase-4v-future-inference-policy.md](phase-4v-future-inference-policy.md) (a proposal, not built).

## 1. Baseline (verified before any change)

| Check | Result |
|---|---|
| Main, open PRs | `e9ba52c`; no open PRs. PR #49 was already merged, so no documentation correction was needed |
| Summary 4, read-only | `failed_verification`, `unreviewed`, `outlook-v5`, `verify-4`, hash intact, **13 errors, 25 warnings**, 7 of 24 claims failed |
| Ledger | 4 reservations and 4 usage rows agree. Lifetime **US$0.6267107880**, remaining **US$4.3732892120**, attempts **4 of 4** (`LIFETIME_ATTEMPTS` unchanged) |
| Database hash | identical before and after every command that touched the real database (`21230f3e…`) |

A session summary carried over from before the run said 3 of 4 attempts and US$0.508462812. That was the pre-settlement state and is superseded by the figures above.

## 2. Verifier `verify-5`

`verify()` takes `version=`; `resolve_verifier()` maps a stored label to the rules that produced it. `verify-4` still runs exactly as before and is the baseline for every replay and differential test.

| Change | What it does | Evidence |
|---|---|---|
| **Colon vote** (confirmed defect) | Reads a vote written `4:3` or `4 : 3`, only inside a sentence about a vote, only between two single-digit counts that stand alone, never beside "ratio" or a clock suffix | `test_verify5_vote_notation.py`: correct pair accepted, wrong pair rejected, times, ratios, three-term and decimal colons ignored; each guard fails a test when removed |
| **Figure beside a comparison** | When the whole clause fails, a figure followed by a comparison word is checked on its own side alone, which must hold only that figure and support the whole claimed period | `test_verify5_comparison_period.py`, the Phase 4Q suite, and a property test that verify-5 only ever removes `period_not_supported` |
| **Another currency's dollar** | `US$`, `A$`, `C$`, `HK$` claimed as `nzd`, `nzd_million` or `nzd_billion` is `unit_mismatch` | `test_verify5_currency.py`. This was a verify-4 **false acceptance**, found while investigating the Brent unit error |

**A mistake caught on the way.** The first version of the comparison fix accepted a period that belonged to a different figure on the same side ("imports rose 4% in June with exports at 6.3% compared with 5.9% in September", claim 6.3 in June). The existing Phase 4Q period suite caught it. The single-figure guard was added back with its own tests, and the three Phase 4Q "known limit" tests now state exactly what changed.

**Display gates pin the stored verifier.** The internal draft and public gates re-run `verify()` when they display a summary. Without pinning, bumping the version would have silently re-graded summary 4 on the dashboard. Both gates and the three API provenance labels now use the row's stored `verifier_version`. Rows labelled `verify-3` or older keep the `verify-4` rules they were already shown under. The Phase 4S pilot freeze stays pinned to `verify-4`, so its recorded hash still reproduces.

**Differential test.** All 52 candidates in the synthetic corpus give identical errors and warnings under verify-4 and verify-5, except where one of the three changes applies. A colon twin of every dash vote in the corpus gets the dash verdict under verify-5.

## 3. Investigation of the remaining errors

| Group | Finding | Action |
|---|---|---|
| **A. Three period errors** | All three are the same shape: one figure with its own month, then "from" and a second figure with another month. One (`facts[0]`) is now supported by the figure's own side. The other two have a **second figure on the figure's own side**, so a month there may belong to either figure | One fixed. Two kept as conservative failures. Accepting them would reintroduce the false acceptance above |
| **B. Three `forecast_as_fact`** | The verifier already accepts a measured expectation that is worded as an outturn ("rose to 2.4%") and rejects the same noun worded as a forecast ("are for 2.4% in 2027"). The three real clauses cannot be settled by rules | **Unresolved, ambiguous.** No change. A rule written to pass the synthetic pairs cannot show it generalises without labelled real data, which this phase does not require |
| **C. Brent crude `missing_unit`** | **Corrects Phase 4U row 7.** The cited quote carries a US-dollar-per-barrel marker. The contract has no US-dollar unit, so `null` gives `missing_unit` and an invented unit gives `unknown_unit`. The model could not have stated it correctly. It is a **contract limitation**, not only a model omission | No verifier change. The currency fix above stops it being mislabelled `nzd`. `outlook-v6` says to leave such a figure out. A reviewed US-dollar unit is a separate contract change |
| **D. Five decision errors** | When no sentence passes the decision-wording rule, the instrument, rate and action errors follow **deterministically** (nothing is left to check). The date error follows only when the claimed date is not in nearby text | Grouped as one root cause with 3 guaranteed and 1 possible cascade. The verifier is **not** changed to hide them: that would lower the count without changing any acceptance |

## 4. Offline replay of stored summary 4

`nzstats research diagnose 4` (read-only; prints codes and counts only). Original `verify-4` against `verify-5`, same stored evidence:

| | verify-4 (stored) | verify-5 |
|---|---|---|
| Errors | 13 | **11** |
| Warnings | 25 | 25 |
| Claims failed / warning / clean (of 24) | 7 / 11 / 6 | 7 / 11 / 6 |
| Citation errors | 0 | 0 |
| Newly accepted claims | | **none** |
| Newly rejected claims | | none |
| `vote_not_in_evidence` | 1 | **0** (the confirmed false rejection) |
| `period_not_supported` | 3 | **2** |
| Independent root causes | 10 of 13 errors | |

Stored verification reproduces exactly; the output hash is intact. Both fixes removed an error from a claim that still has another (`facts[0]` still fails `forecast_as_fact`; `decisions[0]` still fails its root decision error), so the claim counts do not move. Of the 11 remaining errors: 4 are cascades of the decision root, 6 are conservative failures (3 `forecast_as_fact`, 2 `period_not_supported`, and the decision root itself), and 1 is the contract limitation. None is labelled valid.

## 5. Synthetic truth-labelled scorecard

46 constructed examples (22 supported, 19 unsupported, 3 ambiguous, 2 inexpressible). Truth is known because each sentence was written that way. `python -m tests.research.truth_corpus`.

| | verify-4 | verify-5 |
|---|---|---|
| **False rejections** (true claim rejected) | 7 of 22 | **3 of 22** |
| **False acceptances** (unsupported claim accepted) | 2 of 19 | **0 of 19** |
| Ambiguous accepted | 0 of 3 | 0 of 3 |
| Inexpressible accepted | 0 of 2 | 0 of 2 |

The 3 remaining false rejections are documented limits: a forward word before a decision verb, the base figure beside its comparison, and a true period on a clause that holds two figures. This measures constructed minimal pairs. It does not measure real documents or a real model, and an author-written corpus cannot show the rules generalise.

## 6. Prompt `outlook-v6` (prepared, not adopted)

Registered with a pinned hash. `PROMPT_VERSION` stays `outlook-v5`, no experiment names v6, v4 and v5 are byte for byte unchanged, and the JSON contract is unchanged. Changes: record a unit shown beside a figure (and leave out a figure whose unit is not in the list, never relabelling a currency); bind a period to its own figure or leave it null; a measured expectation is a fact and a forecast of an outcome is a forecast; an OCR decision is not commentary about expected moves; Treasury, RBNZ, IMF and market forecasts are attributed from the sentence; one decision sentence, with the vote or date as a separate evidence entry; accuracy over claim count.

Offline tests check the text, the registry, the unchanged contract and that every shape v6 asks for passes the verifier while the shapes it warns against are rejected. **They do not show that a real model follows v6 or becomes more accurate.** Only a fresh, separately authorised experiment can.

## 7. Internal dashboard compatibility

- Real database, read-only, through the Phase 4T gate: summary 4 shows 6 clean, 11 warning, 7 failed, `failed_automated_checks`, verifier `verify-4`, exactly as stored. Summary 3 is unchanged. Database hash identical.
- The dashboard shows only the stored result. The `verify-5` replay is a **new assessment** and appears only in the offline report and the `diagnose` output, labelled as such; nothing overwrites a stored result.
- Warnings and failed checks remain visible. The draft label, "not an official statistic" notice and bind checks are untouched. Public, private and snapshot gates, source permissions and the ledger are untouched, and their suites pass.
- No UX redesign. Frontend code is unchanged (555 unit tests pass).

## 8. Tooling

`nzstats research diagnose SUMMARY [--baseline V] [--proposed V] [--out FILE] [--include-text] [--json]` replaces the private Phase 4U script. It opens the database `mode=ro`, re-runs the stored verifier and checks it reproduces, replays a proposed one, and reports per claim id the codes, evidence location (section, page, offsets, sentence), before and after, root-cause clusters and a rule-computed label. Nothing is labelled valid. Claim text exists only with `--include-text`, only in the owner-only (0600) HTML report, never on the terminal or in JSON. The page has no script and no network resource.

## 9. Open items

- Real-model effect of `outlook-v6`: untested.
- `forecast_as_fact` (3) and the decision root error: ambiguous, kept as conservative failures.
- A US-dollar unit in the contract, and an `unknown`/`foreign` unit path: needs its own reviewed change.
- Table-cell units still check only for a `$`; the foreign-dollar rule applies to prose.
- The owner's optional read of summary 4 is not required and was not done.

## Verification

See the PR descriptions for the exact commands and results.
