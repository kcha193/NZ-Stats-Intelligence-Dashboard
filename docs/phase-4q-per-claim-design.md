# Phase 4Q: per-claim acceptance, design only

2 November 2026. **Nothing here is built or approved. A single failed claim still rejects the whole summary**, and
`test_one_unsupported_period_still_rejects_the_whole_summary` holds that rule in place.

## The question

Phase 4O discarded 11 claims with no verifier error because 7 other claims failed. Could individually verified claims be kept?

## What was measured

On the Phase 4O summary, under `verify-4`, counts only: 10 claims had no finding, 1 had a warning only, and 7 failed. `score-gold` reports
a `clean_claims_hypothetical` view, so the question can be answered with numbers once human gold exists. Until then its quality is
unmeasured, and the count of surviving claims says nothing about whether they are right.

## Why "keep the clean ones" is not safe yet

| Risk | Why it matters |
|---|---|
| "No problem found" is narrow | The checks test where a quote, number and period sit. They do not test economic meaning |
| Survivors may mislead | An outlook statement can pass while the facts behind it are removed, leaving a confident view with no support |
| Selection bias | Removing failed claims leaves a skewed picture. On Phase 4O, every reported fact would go and interpretation would stay |
| Attribution | The verifier's issuer checks are lexical. Phase 4Q closed one gap and others may remain |
| Failure as a signal | Many failures in one summary suggest a bad run. Per-claim acceptance hides that unless it is reported |
| Label drift | "Partly verified" reads as better than it is, and it could leak toward the private or public gates |

## Options

| Option | What changes | Assessment |
|---|---|---|
| A. Keep whole-summary rejection, add diagnostics | Nothing in any gate. Claim status appears in internal drafts and `score-gold` | **Current state, recommended for now** |
| B. Per-claim view in internal drafts only | Drafts could group claims by result. The status stays `failed_verification` | Possible after human gold shows clean-claim precision |
| C. A new accepted status with partial content | New status, contract and gate rules, and changes to private and public logic | Material verifier design change. Not recommended without independent review |

## Conditions before B or C

1. Human-reviewed gold on at least two documents, written without seeing model output.
2. Clean-claim precision and numerical accuracy measured on real denominators. The owner sets the thresholds before seeing results.
3. A rule for orphaned interpretation: a statement whose support was rejected does not survive.
4. A minimum-completeness rule, so a summary with most claims failed is rejected outright.
5. An independent review of the design and of its effect on every gate.

## What must not change

Internal drafts stay separate from the private and public gates. A summary with a failed claim never reaches either, and being listed as a
draft grants nothing. Option B would change only how the loopback draft page groups claims.
