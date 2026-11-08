# Phase 4AB: historical AI summary remediation

8 November 2026, Pacific/Auckland. Baseline main and origin/main both
`352ef68ec6e100d2dddb781e154752c71a60d0d5`; clean checkout before work.

**Offline remediation. No inference, provider request, retry, production write,
permission change, public publication or merge.** Production was opened with SQLite
`mode=ro`. Private diagnostic HTML, redacted replay JSON, structural probes and
integrity fingerprints are kept in ignored `data/phase-4ab/`. This report contains
claim identifiers, codes, counts and structural findings, without source quotations
or model commentary.

## Decision

**GO WITH CONDITIONS for local internal presentation.** Claims with automated
errors are excluded from highlights; warnings and diagnostic evidence remain
visible. Both usable historical summaries still fail verification. No automated
pass is called economic accuracy, and no person needs to approve internal viewing.

There is no demonstrated new rule defect warranting `verify-6`. `verify.py`, the
contract and historical `verify-4`/`verify-5` semantics are unchanged. Known genuine
defects fixed in Phase 4V are reused as a separately identified derived assessment,
not backported into historical records. Remaining ambiguity stays excluded.

## Historical inventory and before/after evaluation

Only summaries 3 and 4 contain parsed output and an intact original response hash.
Summaries 1 and 2 are `provider_error`, with neither raw response nor parsed output.
They cannot be reconstructed or treated as recoverable. Their original failed
attempts and costs remain in the ledger.

Report dates and publication dates are different: summary 3 covers the 15 October
report, published 19 October; summary 4 covers the 29 October report, published
2 November. The UI displays the stored original publication date. Neither stored
`reference_period` is populated, so no document date is fabricated.

| Summary | Original stored result | Replay / presentation (`verify-5`) | Independent problems | No automated errors | Warnings | Excluded claims | Newly accepted / rejected |
|---|---|---|---|---|---|---|---|
| 1, RBNZ | `provider_error`, no usable response | Unavailable | Not assessable | Not assessable | Not assessable | Entire response withheld | Not assessable |
| 2, Treasury | `provider_error`, no usable response | Unavailable | Not assessable | Not assessable | Not assessable | Entire response withheld | Not assessable |
| 3, 15 October | `failed_verification`, label `verify-3`; compatibility replay `verify-4`: 8 errors, 6 warnings | Failed, 8 errors, 6 warnings | 8 rule findings; 7 grouped problems when the fiscal/horizon pair is one basis problem | 11/18: 10 clean, 1 warning-only | 4 claims carry warnings, including 3 excluded; 6 warning findings | 7/18 | 0 / 0 |
| 4, 29 October | `failed_verification`, `verify-4`: 13 errors, 25 warnings | Failed, 11 errors, 25 warnings | Strict non-guaranteed rule findings 10 → 8; grouping the possible date cascade too gives 9 → 7 | 17/24: 6 clean, 11 warning-only | 17 claims carry warnings, including 6 excluded; 25 warning findings | 7/24 | 0 / 0 |

The strict independent count is the diagnostics tool's count: total errors less
three guaranteed decision cascades. A possible cascade remains independent under
that convention. Grouped counts describe investigation work, not verified economic
truth. Summary 3's horizon/basis pair is one underlying basis problem, even though
the existing tool reports two criteria. Neither counting convention changes a
claim's acceptance.

### Error counts by code

| Code | Summary 3 original / replay | Summary 4 original / replay |
|---|---|---|
| `forecast_as_fact` | 0 / 0 | 3 / 3 |
| `period_not_supported` | 5 / 5 | 3 / 2 |
| `horizon_not_supported` | 1 / 1 | 0 / 0 |
| `fiscal_calendar_mismatch` | 1 / 1 | 0 / 0 |
| `issuer_not_in_evidence` | 1 / 1 | 0 / 0 |
| `missing_unit` | 0 / 0 | 1 / 1 |
| `decision_not_in_evidence` | 0 / 0 | 1 / 1 |
| `decision_instrument_not_supported` | 0 / 0 | 1 / 1 |
| `decision_rate_not_supported` | 0 / 0 | 1 / 1 |
| `decision_action_not_supported` | 0 / 0 | 1 / 1 |
| `decision_date_not_supported` | 0 / 0 | 1 / 1 |
| `vote_not_in_evidence` | 0 / 0 | 1 / 0 |

No verdict changes. Two errors disappear from already-failing claims in summary 4;
every excluded claim still has an error. Citation errors are zero in both replays,
which establishes quote location only, not the truth of the interpretation.

## Root-cause findings

Class numbers refer to the owner's nine-category taxonomy. These findings combine
fresh read-only diagnostics and structural probes with the documented Phase 4V
minimal-pair evidence. They do not promote unresolved interpretations to fact.

| Summary / claim | Classification | Evidence and disposition |
|---|---|---|
| 4 `facts[0]`, period | 1, confirmed verifier false positive, already fixed in `verify-5` | The single-figure comparison-side rule removes only the period error. `forecast_as_fact` remains; no promotion. |
| 4 `facts[0]`, `facts[4]`, `facts[11]`, forecast | 3, ambiguous evidence | Each figure's clause matches forward wording; no accepted outturn wording or survey-result exception resolves it. An expectations measure can be a historical observation, but a lexical stem alone cannot establish that. Kept excluded. |
| 4 `facts[6]`, `facts[8]`, period | 3 and 8, ambiguous evidence / contract limit | The figure's context has competing periods; multiple quantities prevent safe comparison-side splitting. Never borrow a period from another figure. Kept excluded. |
| 4 `facts[9]`, unit | 8, contract limitation, manifested as 5 | The evidence has a foreign-dollar-per-barrel marker; the model's unit is null and the contract has no corresponding currency unit. Do not fill in NZD or rewrite the response. Kept excluded. |
| 4 `decisions[0]`, root | 3 and 7, ambiguous monetary-policy decision evidence | No cited sentence passes the adopted-decision rule. Forward wording before a decision verb and competing action language cannot establish a completed decision with the claimed metadata. Kept excluded. |
| 4 `decisions[0]`, instrument/rate/action | 9, guaranteed cascades | No accepted decision sentence remains against which to check these fields. Preserve each original finding. |
| 4 `decisions[0]`, date | 9, possible cascade | The date check depends on nearby date support as well as the rejected sentence. Grouping it is disclosed; the strict count does not subtract it. |
| 4 `decisions[0]`, vote | 1, confirmed verifier false positive, already fixed in `verify-5` | The citation contains a guarded colon vote notation. Existing colon-vote minimal pairs distinguish votes from times, ratios and wrong pairs. Only this finding disappears; the decision remains excluded. |
| 3 `facts[0]`, `facts[1]`, `facts[2]`, `facts[4]` | 2 and 4, unsupported claimed period | Each claimed year is absent from the verifier's nearby evidence context. `facts[0]` and `facts[2]` also hit comparison-basis support. A report's publication year is insufficient to infer the figure's reference year. Kept excluded. |
| 3 `facts[3]` | 4, wrong/unsupported comparison basis | The claimed period is available nearby but belongs to comparison context under the figure-binding rule. No supported correction to the original claim is inferred. Kept excluded. |
| 3 `forecasts[4]` | 4, year-basis error; two findings share one problem | Horizon support reports missing year basis and the separate fiscal/calendar check rejects it. No change to the forecast horizon. Kept excluded. |
| 3 `forecasts[5]` | 6, unsupported forecast attribution | The claimed third-party issuer is not supported near the cited forecast. This is not evidence that the document's author made it instead. Kept excluded. |

None of the unresolved rows is declared accurate. Demonstrating a true new false
positive would require a supported example, an unsupported twin, adversarial
counterexamples and differential evidence before introducing new rule semantics.
This phase does not weaken thresholds or create a rule specifically to clear a
historical warning.

## Deterministic presentation and audit history

`research/assessment.py` computes `presentation-1` on demand after the unchanged
internal draft eligibility gate. The API retains all original claim blocks and
provenance and adds a separate, explicitly pinned `verify-5` assessment. Its content
identity binds summary id, original response hash, parsed summary, exact section
content/metadata, publication context, verifier file hash and findings. The response
includes assessment time, evidence hash and original label/status. No assessment
table, migration, model request or write is needed. A hash mismatch yields no derived
assessment; highlights then fail closed.

Nested evidence problems map to their containing claim. Unknown or global errors
exclude all highlights; global warnings are retained on every affected presentation
claim. `executive_paths` contains only claims with no errors, including explicitly
warned claims. It is a presentation partition, not an accuracy rating.

The dashboard uses this derived partition for executive outlook, institutional
cards, historical previews, drivers/risks and economic figures/forecasts. A failed
outlook displays exactly: "No evidence-supported AI outlook is available for this
report." Warning statements keep their messages and are separated from statements
with no automated issue. Figures retain units, period, adjustment, measure, source
and forecast issuer/qualification; missing fields are stated as missing. Publication
dates remain the original dates, not replay dates.

The expandable **Claims requiring attention** panel preserves original claim text,
AI-cited evidence and source link, finding codes/messages, exclusion reason, verifier
and assessment date. The full original summary and its original check results remain
on the detail page. Exclusion is never described as repairing a claim. Even a clean
quote is labelled as cited by the AI, not independently confirmed.

Existing loopback bind, Host/Origin/client-header protections, no-store responses,
permissions, withdrawal/rejection gates, no-approval internal access, opt-out,
public/private research and snapshot boundaries stay in place. Opening either view
runs deterministic checks only.

## Remaining limitations and accuracy risks

- The verifier establishes evidence placement and constrained wording, not
  independent statistical or economic truth. A clean AI interpretation can still
  be misleading; synthetic truth labels do not measure real-report generalisation.
- Comparison-period fields, explicit foreign-currency units and richer forecast
  measurement definitions require a separately reviewed contract change.
- The existing foreign-dollar guard covers prose. Table-cell currency association
  is a documented remaining limitation; no unit is invented in this presentation.
- Actual/unadjusted, seasonally adjusted and trend series, quarterly and annual
  changes, historical and forecast periods must remain distinct. Where the stored
  contract omits these fields, the UI cannot reconstruct them.
- No human reading or replacement interpretation is fabricated. The unchanged
  lexical verifier retains its known false rejections.

## Verification and review

The 46-example Phase 4V truth corpus remains unchanged: `verify-4` has 7/22 false
rejections and 2/19 false acceptances; `verify-5` has 3/22 and 0/19, accepts 0/3
ambiguous and 0/2 inexpressible cases. This phase adds presentation partition tests
across the same corpus; it claims no improvement in those verifier measures.

| Check | Result |
|---|---|
| Full backend suite | 5,933 passed; final API test file also rerun after adding the colon-vote history regression |
| Backend research, store and operations | 4,513 tests passed, covering verifier/differential/diagnostics/replay/internal API, immutable records, policy/ledger, migrations/rollback and integrity |
| Final internal API regressions | 29 passed, including a synthetic colon-vote replay whose new assessment passes while the original failed record stays identical |
| Frontend unit tests | 573 passed in 49 files; targeted Outlook/detail 74 passed after the final citation-label change |
| Typecheck and production build | Passed; existing bundle-size warning remains |
| Ruff lint and formatting | Passed; frontend lint passed with existing fast-refresh warning category |
| Responsive Outlook/internal browser tests | 21 passed, desktop/tablet/mobile; initial disclosure-locator failures fixed by targeting native `summary` elements |
| Final internal browser checks | 6 passed after adding visible derived error/warning totals |
| Synthetic public research browser tests | 18 passed, 3 expected screenshot-review skips |
| Static Outlook, network and security browser tests | 33 passed, 9 expected static/internal-route skips |
| Real-data copy, offline | Both usable summaries displayed; failed claims absent from highlights, citations/originals accessible, no overflow or page errors at three viewport sizes; zero external and non-read requests |
| Production integrity | All 33 tables matched baseline content fingerprints, including summaries, verification, statistical observations, ledger and policy events |
| Staged secret scan and diff checks | Gitleaks found no leaks; diff whitespace checks passed |

Security evidence is tied to concrete regressions:

| Requirement | Evidence |
|---|---|
| Failed claims never become clean executive insights | `test_assessment.py` checks nested/global errors and all 46 corpus examples; `executiveClaims` checks path partition, status and error severity again; responsive browser checks |
| Excluded claims remain available | Attention-panel unit/browser tests expand original claim/citation/reasons and navigate to the full original summary |
| Historical verification unchanged | API before/after row equality, write-denying SQLite authorizer and all-table production fingerprints |
| Unsupported decisions excluded | Same corpus includes future/ambiguous monetary decisions; synthetic browser attention fixture contains a failed decision |
| Foreign currency never relabelled NZD | Existing `verify-5` currency/differential suites and presentation corpus; unit/browser fixtures retain a foreign unit verbatim |
| Ambiguity never silently accepted | All three truth-labelled ambiguous cases remain excluded; unknown/global finding paths fail closed |
| Internal commentary local-only | Existing draft bind/Host/Origin/client-header tests; public/static browser regressions; real-copy public/private endpoints remain 404 |
| No inference on open | Existing no-inference/ledger regressions; read-only assessment path imports no provider client; real-copy browser sees zero external/non-read requests |
| Public and static routes unaffected | No public/static router or exporter change; research/public browser and static security/network suites pass |
| No human approval required | Existing auto-display/internal-access regressions and unreviewed synthetic/real-copy browser scenarios |

Independent local review was attempted but the reviewer could not start because
the account's usage limit was reached. That is not an independent approval. GitHub
Codex review is requested on the PR; its outcome and any hosted CI blocker are
recorded in the PR conversation. No review receives private diagnostic artifacts.
