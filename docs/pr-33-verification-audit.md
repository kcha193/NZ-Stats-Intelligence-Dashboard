# PR #33 verification audit

1 November 2026. Starting head `19168a6d002e341b6f81f5092232e7534cc5edaa`;
14 resolved threads and one unresolved finding (`discussion_r4430846298`).

## Approach and root causes

1. Refresh the complete review history and establish the research-suite baseline.
2. Reproduce evidence-classification and cross-layer gaps before changing production code.
3. Apply shared rules, run the existing regressions and broader checks, then obtain an independent review.
4. Commit and push normally, resolve addressed threads, and request one fresh GitHub review per head.

The earlier fixes repeatedly switched between overly broad context and an insufficient quote. A year before
publication establishes age, not whether a number is an observation. A sentence can contain both a forecast
and its actual outturn; a policy sentence can contain an adopted rate, a prior rate, dissent and guidance.
These meanings must stay attached to the selected evidence.

The table classifier now checks aligned column labels/year markers, then the selected row, table context and
section heading. Explicit forecasts, previous forecasts, forecast revisions and assumptions cannot become
reported facts merely because their reference year has passed. Mixed labels without a local distinction are
ambiguous and refused. Revised actuals remain actuals. The forecast path uses the same table identity, so an
actual cannot be promoted into a forecast and a previous projection cannot become a current forecast.

Reference periods are assessed separately: completed quarters and June years can be current-year outturns;
calendar years cannot finish early. Fiscal pairs retain both years for column matching and their ending year
for completion. Fiscal/calendar and statistical-definition checks include the located table context.

Policy verification extracts the adopted clause once for action, resulting rate and maker checks. A reporter,
dissenter, previous rate or subsequent guidance cannot supply those fields. Dates and votes prioritise the cited
decision; nearby supplements exclude complete decisions describing other events. Stored summary identity is
additionally bound to the row's document version before either display gate
revalidates the evidence.

Historical comparisons must distinguish publication, capture, current activation and data availability. The
selected vintage's own definition and baseline are authoritative; missing inputs cannot trigger substitution
of an older answer. Existing storage does not timestamp bundle reactivations. Where multiple eligible bundles
have uncertain activation history, comparison is refused rather than inferred from current activation order.

## Verification-invariant matrix

Each row checks both false acceptance and false rejection. Existing tests are retained; new coverage targets
the interactions absent from earlier review cycles. All fixtures in this audit are synthetic or the existing
official-file excerpts in tests. No production database or stored institutional document was read.

| Area | Must reject / withhold | Must accept / retain | Coverage |
|---|---|---|---|
| Historical forecast identity | Previous forecasts/projections, including a past year or unknown publication date, as facts | Historical actual observations | `test_fact_evidence_kinds.py`, `test_verify_layout.py` |
| Forecast revisions | Revised predictions as actuals; superseded predictions as current forecasts | Current revised forecast; revised actual in its own category | `test_row_identity_scopes_mixed_actual_and_forecast_tables`, `test_forecasts_use_the_same_scoped_table_identity` |
| Mixed tables | Unlabelled actual/forecast mixture as an actual; forecast-labelled column | Explicit actual row/column, provisional column | Row/column parametrisations in `test_fact_evidence_kinds.py` |
| Table boundaries | Caption or figures from another table qualifying the selected cell | Actual table followed by forecast table | `test_following_table_does_not_reclassify_an_actual_cell` |
| Section versus figure | Section heading overriding explicit local evidence | Actual row/table inside forecast discussion | `test_actual_outturn_does_not_inherit_the_sections_forecast_heading` |
| Period completion | Future/incomplete or ambiguous current-year table actual | Completed June year, quarter and calendar year | `test_table_fact_current_year_requires_completed_historical_period` |
| Fiscal/calendar | Calendar label on June-year data and reverse | `2025/26` and explicit June 2026 year consistently referring to the completed fiscal period | Fiscal tests in `test_fact_evidence_kinds.py` and `test_verify_records.py` |
| Prose actual versus forecast | Earlier prediction as reported outturn | Actual alongside previous forecast, including comparison clause | `test_actuals_alongside_previous_forecasts_are_scoped_to_the_figure` |
| Value-bound reference periods | Neighboring year/month/quarter replacing an explicit local component, in facts or forecasts | Correct local period; a heading supplying a component the local clause omits | `test_reference_period_scope.py` |
| Policy action | Wrong/negated/ambiguous action; guidance as decision | Increase/decrease wording; adopted action after dissent | `test_decision_evidence_scope.py`, existing record regressions |
| Resulting policy rate | Previous, dissenting or guidance rate | Adopted rate in transition or basis-point move | `test_forward_guidance_rate_cannot_replace_the_adopted_rate`, `test_dissent_rate_cannot_replace_the_adopted_rate`, existing from/to test |
| Decision maker/instrument | Reporting institution as maker; overseas policy rate as OCR | Named RBNZ/MPC decision in another publisher's report | `test_reporting_institution_is_not_the_policy_decision_maker`, existing record tests |
| Dates/votes | Wrong explicit date/year; reversed division; omitted stated vote | Explicit/publication date and action-bound division | Existing `test_verify_records.py`, `test_review_regressions.py` |
| Forecast attribution | IMF/OECD/market forecast as author's; wrong named issuer | Author row in a third-party table; author's forecast about the RBNZ | Existing `test_verify_attribution.py` |
| Issuer scoring alignment | Annotation order changing issuer accuracy; matching roles hiding wrong value/unit/scenario | Identical author/third-party figures aligned to their annotated roles in either order; real mismatches still scored | New alignment parametrisations in `test_evaluate.py` |
| v1/v2 compatibility | v1 implicitly claiming third-party forecast as author's; incomplete v2 issuer | Stored v1 with empty new lists; complete v2 records | Existing `test_contract.py`, `test_verify_attribution.py` |
| Evidence integrity | Wrong version, absent quote/page, truncated sign or axis residue | Exact located quote, split minus sign, valid table units | Existing contract/layout/record tests |
| Statistical definitions | Unsupported adjustment/average; annual/quarterly mismatch | Caption-defined adjustment and annual rate at a named quarter | Existing record/layout tests; table context now shared with period checks |
| Vintage definition | Current metadata replacing selected historical basis | Selected vintage's adjustment/frequency snapshot | Existing `test_comparison_uses_the_selected_vintages_definition` |
| Vintage availability | Later release/correction; undated reactivation inferred historically | Original before correction; later unambiguous release | `test_official_compare.py` |
| Missing comparison inputs | Stale match from older vintage after missing/zero baseline | Latest eligible complete vintage with original rounding precision | New baseline regressions and existing comparison tests |
| Display identity | Row A displaying output/evidence for document B, even with identical text | Matching stored identities through both gates | `test_both_display_gates_reject_output_for_another_document_version` |
| Permission/display gates | Unreviewed, revoked, duplicate, superseded, purged, injected or disallowed-host material | Approved current summary only with separate current display/processing permission | Existing public/private/API suites |
| Private API isolation | Non-loopback, cross-origin, absent dashboard header, writes or disabled routes | Explicit local read with headers; no research in snapshots | Existing private API, bind, isolation and publish tests |

## Failure-first evidence

- Initial table/prose batch: 23 assertion failures before implementation (30 cases). Added reverse-classification
  tests then reproduced two more failures: actual as forecast and previous projection as current forecast.
- Policy scope: four assertion failures (seven cases): dissent-first action, guidance rate, dissent rate,
  and reporter as decision maker.
- Display identity: an approved row for one document displayed another document's output before the fix.
- Official comparisons: six assertion failures for missing/zero baselines and undated A→B→A / A→B→A→B history.
- Independent local review found two introduced false rejections: outlook/expectation table wording lost its
  fallback, and a reporter without the word "that" became a decision maker. Four parametrised failures were
  reproduced and corrected. Further policy probes cover an expectation before the decision and a previous
  decision's date; an ambiguous fiscal year cannot assume a June ending without evidence.
- The research browser integration exposed a pre-existing v2 caller gap: the synthetic demo seeder omitted
  forecast issuers. Its real subprocess regression failed before the caller was updated. All seeded public
  summaries now pass current verification with named authors; regenerated fixtures only update verifier versions.
- One pre-existing table-placement test used forecast evidence as a valid fact. Its fixture now explicitly
  states actuals; its no-error and wrong-column assertions remain. The rejected historical-forecast behaviour
  has separate regression coverage.

## Limits preserved

The verifier remains lexical and requires human review; it does not prove economic interpretation or
completeness. Repeated year-group headings remain unverifiable. Identical author/third-party forecasts without
evidence identities remain ambiguous in evaluation. Full activation reconstruction needs immutable timestamped
events; the refusal can conservatively affect a multi-bundle release after an unrelated global activation-counter
offset. This does not change stored statistics or any ingestion behaviour.

Contracts, schema, source registry, permissions and disabled-by-default preview settings are unchanged. No
institutional page, statistical endpoint or model was called. No merge or deployment is authorised by this audit.

## Verification and review record

The first fix batch passed 1,689 research tests (60 added cases). Backend Ruff lint/format, 524 frontend tests, types,
lint and build pass; frontend lint retains three existing Fast Refresh warnings and the build retains its
existing chunk-size warning. The regenerated API schema is unchanged. The synthetic research browser suite
passes 18 with three expected screenshot skips. Replay retains all recorded metric floors and 38/38 probes.
The existing Starlette/httpx deprecation warning remains.

### Fresh review iteration 1

Completed Codex review of `f6e6dece1b4b1314f5fa939772683e699b4bfc70` found one new P2:
`discussion_r4433342624`, issuer accuracy depended on the ordering of otherwise identical author and third-party
gold annotations. The alignment audit reproduced four failures, including adjacent unit/scenario ordering gaps.
Ten cases now exercise both gold and prediction orders, numeric priority, unit/scenario priority and real issuer
mismatches. Alignment prefers matching value, unit and scenario presence before using an annotated issuer role
as a tie-breaker. The replay retains its recorded floors and 38/38 probes. This fixes annotated-role ambiguity;
author-only gold without evidence identities retains the narrower limitation described above.

The adjacent positive-case audit also preserves completed current-year observations described simply as
"historical GDP growth"; explicit "historical forecasts" still take precedence. Its regression failed before
the classifier was corrected. The second fix batch adds 11 cases (71 total additions; 1,700 research cases).

### Fresh review iteration 2 and focused policy audit

Completed review of `03c938f1d363f121934bab94a974cc5328f226d8` found two P2s:
`discussion_r4433360168` and `discussion_r4433360176`. The earlier clause extraction had not applied field scope
consistently to dates and votes: both still accepted any matching value in the nearby passage. This was the
same context-binding defect, so the follow-up audited both primary fields and fallback support together.

Twenty-one failures reproduced across 30 new cases. Explicit dates and vote divisions in the selected event now take
precedence. Fallback supplements retain undated vote sentences and member preferences but exclude complete
neighbouring decisions, preventing both borrowed fields and false missing-vote errors. Coverage includes
neighbours before/after the citation, ISO/written dates, valid/incorrect dates and votes, an unvoted current
decision, a separate valid vote supplement and forward guidance naming a later meeting date. The latter date
cannot override the adopted decision's date. Member preferences in the cited decision remain available to
the vote check while excluded from action/rate matching. A focused independent review also caught date/vote
metadata before a semicolon being discarded; six failing-first cases now preserve meeting dates and vote
prefixes from the selected event. Date/vote checks use that event, while action/rate/maker checks use its narrower
adopted clause. Total additions: 101 cases; research suite: 1,730 cases.

### Period-scoping closure, 1 November 2026

The latest completed review of `6b97c3d63b191ce64c8a7cfdf6076a6088e27489` left one P2,
`discussion_r4433397249`: a reported fact could borrow a neighbouring figure's year. The same scoped
check now serves forecast horizons. It selects the value's own sentence and clause, then its explicit
period components; missing components may come from a compatible section heading or explicit,
unambiguous context applying to the figures. An adjacent independent numerical assertion cannot supply
the period. Conflicting candidate periods and fiscal/calendar evidence fail closed.

The 58-case regression file covers both paths, both neighbour orders, shortened and multi-sentence quotes,
paired figures, years/months/quarters, fiscal/calendar conflicts, valid inheritance and contradictory context.
Against the fetched head, 32 cases fail and 26 pass. Against the fix all 58 pass. Existing paired-forecast,
market-pricing and chart-residue regressions exposed compatibility cases during verification: month matching
now recognises month names rather than words such as "Markets", and year parsing preserves source lines.
The split-sign fixture now states its date in its heading rather than borrowing another index's period;
its sign and truncation assertions are retained. Four final failing-first cases also preserve fiscal-pair
heading inheritance and require inherited fiscal basis even when the year is already explicit. Total stabilisation additions: 159 cases.

Final local verification: research 1,788 passed; full backend 3,546 passed on Python 3.12;
Ruff lint/format passed. Frontend 524 tests, types, lint, build and unchanged API schema passed,
including schema generation against current Python 3.12 dependencies. Browser integration:
live 174 passed; synthetic research 18 passed / 3 skips; static/parity 315 passed / 24 skips.
Offline replay retained all metric floors and 38/38 labelled probes. Staged and PR-range Gitleaks
passed. Existing Starlette/httpx deprecation, Fast Refresh and build-size warnings remain.

#### CI diagnosis and remaining external/tooling blockers

Run [41244466427](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/41244466427)
for the fetched head failed backend, frontend and static-site before any steps ran. Each annotation states
that account payments/spending limits prevented starting the job. Docker was skipped. `--log-failed`
returns "log not found" because no job steps ran. There is no test or workflow failure evidence in that run,
and retrying it cannot resolve account billing.

Separately, local `npm audit --audit-level=low` fails on
[GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249), through
`openapi-typescript@7.13.0 -> @redocly/openapi-core@1.34.20 -> minimatch@5.1.9`.
This is a development-tool dependency, but the workflow requires this audit, so it will block the frontend
job once billing permits it to start. The published compatible Redocly 1.x updates still depend on the
flagged version. Testing an override to 2.72.1 removed the advisory but broke API type generation with
`ERR_PACKAGE_PATH_NOT_EXPORTED` for `lib/ref-utils.js`; that incompatible override was reverted.
The suggested downgrade to `openapi-typescript@6.7.6` was also tested in a temporary tool environment;
it produces a 5,345-line generated-schema diff, so it is a separate migration rather than a scoped
version bump. A supported toolchain update or an explicit owner-approved exception is still required. The audit was
not weakened. Local Docker validation remains unavailable because no daemon is running.

This task starts a new bounded review sequence: one current-head request, with at most two further
cycles if actionable findings require fixes. Earlier reviews are historical and are not restarted.

See the PR conversation for the full-backend result, remote head SHA, head-specific CI and completed review
receipts. Hosted infrastructure failure is a blocker to COMPLETE, even when local checks pass.
