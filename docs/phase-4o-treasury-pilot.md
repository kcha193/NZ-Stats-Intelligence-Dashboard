# Phase 4O: second controlled pilot, Treasury result

2 November 2026, Pacific/Auckland. Baseline: `26612a4`, main after merged
[PR #40](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/40).

**One real request ran. It returned complete, schema-valid JSON, and the verifier rejected the summary.** Truncation did not
recur. No economic claim was accepted, and nothing was approved or displayed. **RBNZ was not run and should not run on
this configuration.** **NO-GO for economic intelligence and private display.**

This record holds metadata only. Report text, model text, quotes, values, horizons, gold and consent records stay under
ignored `data/phase-4n/`.

## Authorisation and run

The owner replied with the exact Treasury-only approval, recorded locally at 2026-11-02 07:13:36 UTC with a 4-hour expiry. The
owner ran the single execute command, because the secret-file guard correctly keeps the agent out of `.env`.

| Control | Result |
|---|---|
| Source | `26612a4`, clean, all four CI jobs passed |
| Freeze | Not regenerated. Freeze `57554ecf…4449c95` and request `64de36f2…baf8aa5` were rebuilt offline with identical hashes |
| Sent body | Matches the frozen body hash |
| Backup | Fresh backup and restore passed inside the runner |
| Requests | Exactly 1, no retry, no fallback |
| Parameters after the result | None changed. No threshold changed |

## Before and after

| Measure | Phase 4M Treasury | Phase 4O Treasury |
|---|---|---|
| Prompt, effort, cap | `outlook-v3`, high, 6,000 | `outlook-v4`, low, 12,000 |
| HTTP, finish reason | 200, `length` | 200, `stop` (`end_turn`) |
| Input tokens | 16,460 | 16,693 |
| Output tokens | 6,000 | 2,455 (20% of the cap) |
| Reasoning tokens | 6,000 | 0, as reported |
| Final content | None | 5,970 characters, target under 20,000 |
| Latency | 56.1 s | 18.8 s |
| Reported cost | US$0.202379760 | US$0.126184608 |
| Complete JSON, schema valid | No, no | **Yes, yes** |
| Outcome | `provider_error` / `invalid_response` | **`failed_verification`** |

Requested and returned model and provider matched: `anthropic/claude-opus-5.5`, `Google`, requested route
`google-vertex/europe`. A provider label does not prove region.

## Economic quality

The verifier rejects a whole summary on any error, so the accepted set is empty. An empty denominator is unmeasured, never a
pass.

| Measure | Gate | Result | Status |
|---|---|---|---|
| Complete JSON, schema valid | Required | 1/1 | **Pass** |
| Verifier passed | Required | 0/1 | **Fail** |
| Accepted citation correctness | ≥95% | 0/0 | Unmeasured, cannot pass |
| Accepted numerical fidelity | 100% | 0/0 | Unmeasured, cannot pass |
| Accepted forecast issuer accuracy | 100% | 0/0 | Unmeasured, cannot pass |
| Items with a verifier error | Reported | 7/18 | 11 clean items were still rejected with the summary |
| Evidence references passing location checks | Reported | 19/19 | Literal location only, not meaning |
| Raw precision | Reported | 0/1 | 5 third-party forecasts fall outside the author-only gold |
| Raw recall | Reported | 0/5 | See the gold limitation below |
| Accepted precision | Reported | 0/0 | Unmeasured |
| Accepted recall | Reported | 0/5 | Fail |
| Indicator precision, recall | Reported | 4/6, 4/8 | Recorded |
| Key points covered | Reported | 1/6 | Low |

### Claims and rejections

| Item | Issuer label | Verifier result |
|---|---|---|
| `forecasts[0]` migration | Treasury | Warning: `horizon_without_period` |
| `forecasts[1]`, `[2]` GDP | IMF | Clean |
| `forecasts[3]` CPI, no value | IMF | Clean |
| `forecasts[4]` government debt, no value | IMF | **`horizon_not_supported`, `fiscal_calendar_mismatch`** |
| `forecasts[5]` other | IMF | **`issuer_not_in_evidence`** |
| `facts[0]`–`[4]` | n/a | **`period_not_supported` on all five**, plus 3 `source_not_named` and 2 `definition_not_stated` warnings |
| Outlook, 2 drivers, 2 risks, 2 assumptions | n/a | Clean |

There were no decisions or guidance items.

**Horizons and units.** One forecast horizon was rejected and one names no period. Each of the 4 forecasts with a value
kept its figure and unit in its evidence, by the verifier's literal checks. Two forecasts carry no value.

**Treasury versus IMF.** The bound gold has no third-party forecasts, so it cannot score the five IMF labels. A loose
comparison with the human baseline annotation, which has 3 Treasury and 4 IMF forecasts for this document, gives indicative
support only:

- 3 of the 4 forecasts with a value match a baseline item with the same issuer. The fourth has no baseline match and is the
  one rejected for its issuer.
- The two GDP forecasts name the IMF only in the preceding sentence, so a person must confirm them.
- The labels on `forecasts[3]` and `[4]` remain unconfirmed.

**Unsupported tables and historical comparisons: not exercised.** No claim cited a table cell, and there were no
`table_column_*` or `historical_not_forecast` results. This run neither proves nor weakens those checks.

## Diagnosis

Facts below are measured. The loose baseline comparison is indicative and needs the human review.

1. **The truncation fix worked on this document.** Output used 20% of the cap and the JSON closed normally.
2. **The main rejection is years on facts.** All five facts fail `period_not_supported`. Against the baseline, 3 matching
   items state no year, so the model appears to have added one; 1 states a different year; and 1 agrees, so that rejection
   may be false. Rule 3 forbids filling a forecast horizon, but no rule says the same for a fact's period. That is a likely
   prompt gap, and it needs confirming.
3. **The summary is thin.** It has 6 forecasts against 7 in the baseline, 5 facts against 15, and 2 of 7 baseline forecasts
   covered by value. It stopped far under its budget, with no reasoning reported. This is evidence against the hypothesis that
   low effort preserves recall, from one document.
4. **Rejection is all-or-nothing.** Seven flawed items discard 11 clean ones. This is the designed behaviour and it did not
   change.
5. **The gold cannot show a good accepted Treasury result.** Phase 4L keeps the four GDP/CPI table cells as expected
   rejections and the migration item as `horizon_not_supported`. That covers all five gold forecasts, so accepted recall
   against this gold is effectively capped at zero, and raw recall of 0/5 says little about extraction quality. The
   gold also omits the IMF forecasts.

No evidence here justifies loosening a verifier check, and none was loosened.

### Phase 4N hypotheses

| Hypothesis | Result on this one document |
|---|---|
| Low effort reduces reasoning enough | Supported |
| Revised rules reduce final tokens | Supported, though partly because the output contains fewer claims |
| The model respects the 20,000-character target | Supported |
| Low effort keeps recall and attribution quality | **Recall: evidence against. Attribution: unresolved** |

## Spend and attempts

| Item | Value |
|---|---|
| This request | US$0.126184608 |
| Experiment spent / remaining of US$1 | US$0.126184608 / US$0.873815392 |
| Lifetime spent / remaining of US$5 | US$0.508462812 / US$4.491537188 |
| Conservative bound reserved | US$0.4532308, settled on reported billing |
| Attempts | Treasury 2 of 2, consumed. RBNZ 1 of 2. Lifetime 3 of 4 |

The key reconciled exactly with the ledger at preflight. **A post-run key reading is outstanding**, and US$4.491537188 is the
expected remaining value.

Treasury cannot run again: the gate returns `attempt_consumed`. A further Treasury trial needs a reviewed code change and fresh
consent. Do not reset the ledger or change document identity to get around that.

## Security and privacy

- Against the fresh backup, only `research_llm_run`, `research_summary`, `research_llm_usage` and
  `research_llm_reservation` changed, each by one new row, across 32 tables. All Phase 4M rows are unchanged.
- The credential-pattern scan of the run directory found 0 hits in 12 files. All files are private to the owner.
- The agent did not read the key, the `.env` file, the model's text, quotes or gold values. The evaluation scripts
  printed only codes, counts and booleans, and the review packet was built without displaying its text.
- There was no crawling, scheduler, public deployment, source permission change or display. The source-level LLM setting
  stays `denied`; this request ran under per-version consent.
- The returned Google label does not prove upstream region or account settings. Rights and account controls are owner
  attestations, not an independent audit.

## Human review required

The local packet is `data/phase-4n/run-treasury-20261102/human-review.html`. It holds all 18 claims with their evidence,
verifier messages, the gold and the approved sections. **The summary is rejected and unreviewed, and review does not make it
displayable.** Three questions matter most:

1. Are the forecasts labelled IMF really the IMF's?
2. Are the years on the five rejected facts correct, or added by the model?
3. What important content is missing?

## RBNZ decision

**Not ready. Do not run it on this configuration.** It is the only slot left for RBNZ, and the same prompt rules and low
effort would probably repeat the fact-period and thin-coverage problems. Rerunning unchanged would measure little and could
consume the slot. The approval also never covered RBNZ, so it would need its own fresh consent and separate go-ahead.

Any new proposal should wait for the human review, then consider these options. None is built or approved:

- A rule that a fact's period is copied as written, with the year left out when the document omits it.
- Medium effort, if the review confirms low effort is the cause of the thin coverage.
- Added gold for third-party forecasts and accepted-eligible Treasury claims. A gold change needs owner review and must not be
  fitted to this output.
- Per-claim acceptance, which would be a material verifier design change needing its own review.

## Verdict

| Decision | Verdict |
|---|---|
| Truncation remediation | **Worked on one document** |
| Economic intelligence | **NO-GO** |
| Private display | **NO-GO** |
| RBNZ | **NO-GO on this configuration** |

No complete, statistically verified economic summary exists yet.
