# Phase 4AE: Multi-Bank Economic Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show ANZ, ASB, BNZ, Westpac and Kiwibank research as evidence-linked, deterministic forecast comparisons in the local Economic Outlook page, with every bank still permission-denied until the owner approves it.

**Architecture:** Reuse the existing research pipeline, draft gate and comparison/consensus/history/evaluation functions unchanged. Add a thin bank layer: per-bank series adapters, a read-only view over gated clean claims, a wrapper that partitions by adjustment and report kind before calling the existing analytics, per-series source states, internal-only routes on the existing draft router, and a dashboard section. No new tables expected.

**Tech Stack:** Python 3.12+ (venv is 3.14), FastAPI, Pydantic v2, SQLite, pytest, ruff; React 19, TypeScript, Vite, ECharts, TanStack Query, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-10-phase-4ae-bank-research-design.md` (approved 2026-11-10). Baseline: `86a4515`, backend 5932 passed / 5 skipped.

## Commands

Run from the worktree root. `MAIN` is the main checkout (`/Users/kevinchang/vault/projects/NZ-Stats-Intelligence-Dashboard`); the venv's editable install points there, so a worktree needs `PYTHONPATH`:

```
PYTEST: PYTHONPATH=$PWD/backend/src $MAIN/backend/.venv/bin/python -m pytest <path> -v     (addopts already has -q; never use nohup)
RUFF:   $MAIN/backend/.venv/bin/ruff check backend && $MAIN/backend/.venv/bin/ruff format --check backend
FRONT:  cd frontend && npm test && npm run typecheck && npm run build
```

Do not run these through `source …/activate` compound commands in the worktree session; call the venv binaries directly.

## Global Constraints

- No permission, approval, `content_policy`, `llm_processing`, `manual_import`, `public_display` or `private_display` field changes for any institution. Only the descriptive registry edits in Task 1.
- No live request to any bank, no OpenRouter or other hosted request, no deployment, no scheduler or cron entry for banks, no public/private display of bank content.
- The 10 second crawl delay is a hard constraint; never run real-site checks.
- Bank routes exist only on `internal_drafts_router`; never in `api.py`, `private_api.py`, the snapshot, the static build or `schema.d.ts`.
- Committed frontend tests and fixtures use fictitious banks ("Example Bank A", "Example Bank B", "Example Bank C") and obviously synthetic values. Backend tests use real bank keys only to assert refusal; happy paths use a synthetic registry with fake keys, a fake host and an injected adapter mapping.
- No synthetic values in production code paths. No copyrighted report text committed.
- Missing data stays missing: no interpolation, extrapolation, carry-forward or gap filling.
- A claim enters bank analytics only if its draft claim status is `clean`. Warnings and failures are excluded with a fixed reason code.
- Never merge: quarterly with annual, calendar with fiscal, average with end-of-period, market pricing with an institution's own forecast, the author's with a third party's forecast, seasonally adjusted with unadjusted or unstated.
- Consensus wording: 2 contributors = "Two-bank comparison" (mean, median, range); "consensus" and standard deviation from 3; outlier flags from 5; every group says "not a market consensus". Treasury and RBNZ are markers, never contributors.
- Only `outlook`-kind reports feed consensus, divergence and revisions.
- Error and exclusion text is fixed strings or codes, never exception messages or document text.
- Opening any bank route makes zero provider calls and zero fetches.
- Store timestamps in UTC; present in Pacific/Auckland. Never plot monthly and year-ended series on one axis.
- Strict TDD: watch each new test fail first. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

Inputs the spec implies but its sections do not enumerate; each has a pinning test in the task named.

1. A bank document with no publication date: never enters consensus or revisions, listed as excluded (Task 5).
2. One bank, one date, two documents giving different values for the same forecast: excluded as a conflict, never averaged (Task 5).
3. A bank section reading like an instruction to a model: the draft gate withholds it, the bank view shows nothing from it (Task 4).
4. A bank document quoting another bank's or the IMF's forecast: never counted as the quoting bank's own (Task 4).
5. A forecast of `0.0` or a negative value (an OCR cut path, `-0.25`): kept and shown with its sign; zero is not treated as missing (Tasks 3 and 5).

## File Structure

Create (backend, all under `backend/src/nzstats/research/`):
- `banks.py`: series adapters. `bank_forecast.py`: `NormalizedForecast` and derivations. `bank_view.py`: gated read-only view. `bank_analytics.py`: partition wrapper, naming, divergence. `bank_models.py`: response allowlist. `bank_status.py`: source states, metrics, exit code. `bank_api.py`: routes, mounted by `drafts_api.internal_drafts_router`.
Modify: `drafts_api.py` (mount), `cli.py` (`bank-status`; metrics in `_health`), `health.py` (bank metrics), `config/research_sources.toml`, `tests/research/test_registry.py:103-105`.
Tests (backend): `tests/research/test_bank_{registry,adapters,forecast,view,analytics,status,api,privacy,e2e}.py` and `tests/research/bank_support.py` (synthetic registry, adapters, document builders).
Frontend: `src/api/bank.ts` (hand-written types and hooks, mirroring `src/api/drafts.ts`), `src/components/outlook/bank/*` (`BankOutlook.tsx`, `BankCards.tsx`, `BankForecastTable.tsx`, `BankConsensusChart.tsx`, `BankRevisions.tsx`, `BankDivergence.tsx`, `BankEvidence.tsx`, `BankHealth.tsx`), `src/charts/bankConsensus.ts`, `src/pages/EconomicOutlook.tsx` (mount), tests beside each.
Docs: `docs/phase-4ae-bank-research.md`, `docs/phase-4ae-bank-runbook.md`, `docs/phase-4ae-permissions-matrix.md`, `docs/data-sources/research.md`, `docs/progress.md`, `CLAUDE.md`.

Deviation from spec 4.2(1), narrowed on reading the code: adapters do not do date extraction or listing parsing. The registry's `url_date_regex` and `dates.py` already do dates, and `parse_html_links` already parses listings; an adapter only identifies the series, its report kind and cadence, and canonicalizes URLs.

---

### Task 1: Registry descriptive edits and permission pin

**Files:**
- Modify: `config/research_sources.toml` (BNZ and Kiwibank blocks, `expected_publication_days` for ANZ/ASB/Westpac), `backend/tests/research/test_registry.py:103-105`
- Create: `backend/tests/research/test_bank_registry.py`, `backend/tests/research/bank_support.py` (Task 2 extends it)

**Interfaces:**
- Produces: `BANK_KEYS = ("anz", "asb", "bnz", "westpac", "kiwibank")` in `backend/tests/research/bank_support.py`.

- [ ] **Step 1: Write the failing tests** in `test_bank_registry.py`: `test_every_bank_is_refused_everywhere` parametrized over `BANK_KEYS` asserts on the real registry: `not automated_access_allowed`, `not manual_import_allowed`, `not source_permitted`, `llm_refusal(hosted=True) is not None`, `display_level().value == "none"`, `private_display_level().value == "none"`, `content_policy is not ContentPolicy.FULL_TEXT`. `test_bnz_and_kiwibank_landing_urls`: BNZ `allowed_hosts == ("www.bnz.co.nz",)` and `landing_urls == ("https://www.bnz.co.nz/institutional-banking/research/publications",)`; Kiwibank `landing_urls == ("https://www.kiwibank.co.nz/business-banking/thrive-hq/kiwi-economics/",)`; both `landing_evidence == "none"`, both still `needs_review`/`content_policy none`. `test_cadence`: `expected_publication_days` is 100 (anz), 10 (asb), 10 (westpac).
- [ ] **Step 2: Run** `PYTEST backend/tests/research/test_bank_registry.py`. Expected: FAIL on the landing-URL and cadence tests (the refusal test passes).
- [ ] **Step 3: Edit the TOML** with those values; BNZ `access_notes` becomes "Owner-supplied landing URL (2026-11-10), not probed; no access, terms or robots evidence; nothing is approved." Same note style for Kiwibank. Rewrite `test_unprobed_sources_do_not_invent_landing_pages` to `test_bnz_stays_refused_with_owner_supplied_url` (assert the URL above and `not bnz.automated_access_allowed`).
- [ ] **Step 4: Run** `PYTEST backend/tests/research/test_bank_registry.py backend/tests/research/test_registry.py`. Expected: PASS.
- [ ] **Step 5: Commit** `git add config/research_sources.toml backend/tests/research/ && git commit -m "feat: record owner-supplied BNZ and Kiwibank landing URLs; pin all banks refused"`.

### Task 2: Bank series adapters

**Files:**
- Create: `backend/src/nzstats/research/banks.py`, `backend/tests/research/test_bank_adapters.py`, `backend/tests/research/bank_support.py`

**Interfaces:**
- Produces: `ReportKind = Literal["outlook","weekly","commentary","other"]`; `@dataclass(frozen=True) class Series: key: str; name: str; report_kind: ReportKind; cadence_days: int; url_pattern: str | None; title_pattern: str | None`; `@dataclass(frozen=True) class BankAdapter: key: str; series: tuple[Series, ...]` with `series_of(self, url: str, title: str) -> Series | None` and `canonical_url(self, url: str) -> str`; `ADAPTERS: Mapping[str, BankAdapter]` (anz, asb, westpac populated; bnz and kiwibank absent); `adapter_for(key: str, adapters: Mapping[str, BankAdapter] = ADAPTERS) -> BankAdapter | None`; `report_kind_of(key: str, url: str, title: str, adapters=ADAPTERS) -> ReportKind` (returns `"other"` when no adapter or no series matches).
- Series: ANZ `economic_outlook` (outlook, 100 days, url pattern from the registry's QEO regex) and a `weekly` series is NOT invented (no evidence); ASB `quarterly_economic_forecasts` (outlook, 100) and `economic_weekly` (weekly, 10), patterns from the registry's report-page regex; Westpac `weekly_commentary` (weekly, 10).
- `bank_support.py` produces: `synthetic_registry(tmp_path) -> dict[str, Institution]` with fake keys `bank_a`, `bank_b`, `bank_c` (kind `bank`, host `research.example.test`, `content_policy full_text`, `manual_import approved` with approver/date/note, `llm_processing local_only`), `SYNTH_ADAPTERS: Mapping[str, BankAdapter]` for them (outlook series 100 days, weekly series 10 days), plus the pre-existing `Treasury`-like `ref_central`/`ref_gov` markers (kinds `central_bank`, `government`).

- [ ] **Step 1: Write failing tests**: `test_adapter_for_known_and_unknown` (`adapter_for("anz")` not None; `adapter_for("bnz") is None`; injected mapping respected); `test_series_of_matches_registry_url_shapes` (ANZ `https://www.anz.co.nz/content/dam/anzconz/documents/economics-and-market-research/2026/ANZ-QEO-20260813.pdf` -> `economic_outlook`; Westpac `.../Weekly-Commentary_191026_report_19Oct26.pdf` -> `weekly_commentary`); `test_report_kind_defaults_to_other`; `test_canonical_url_strips_fragment_query_and_trailing_slash`; `test_adapters_hold_no_permission_fields` (dataclass field names contain none of `approved`, `permission`, `llm`, `display`).
- [ ] **Step 2: Run**; expected FAIL (module missing).
- [ ] **Step 3: Implement** `banks.py` per the Interfaces; compile patterns once.
- [ ] **Step 4: Run**; expected PASS. Ruff clean.
- [ ] **Step 5: Commit** `feat: bank series adapters`.

### Task 3: NormalizedForecast and derivations

**Files:**
- Create: `backend/src/nzstats/research/bank_forecast.py`, `backend/tests/research/test_bank_forecast.py`

**Interfaces:**
- Consumes: `api_models.ForecastOut`, `compare.basis_of(indicator, label, horizon, unit) -> str | None`.
- Produces: `Adjustment = Literal["seasonally_adjusted","unadjusted","not_stated"]`; `derive_adjustment(label: str, quote: str) -> Adjustment` (phrases: "seasonally adjusted"/"s.a."/"sa" -> seasonally_adjusted; "unadjusted"/"non-seasonally adjusted"/"actual" -> unadjusted; both or neither -> not_stated, case-insensitive, whole words); `derive_geography(indicator: str, label: str, horizon: str, unit: str | None) -> str` ("New Zealand" unless `basis_of` yields a part-of-series word, then that text as written); `class NormalizedForecast(BaseModel)` (frozen, `extra="forbid"`) with fields `forecast: ForecastOut`, `institution_key: str`, `document_version_id: int`, `claim_path: str`, `report_kind: ReportKind`, `forecast_author: str | None`, `geography: str`, `measure: str`, `adjustment: Adjustment`, `extraction_method: Literal["llm_verified"] = "llm_verified"`, `verifier_version: str`, `raw_value: float | None`, `conversions: tuple[str, ...] = ()`.

- [ ] **Step 1: Write failing tests**: adjustment table (label "GDP growth, seasonally adjusted" -> seasonally_adjusted; label says SA but quote says "unadjusted" -> not_stated; neither -> not_stated); `test_zero_and_negative_values_survive` (a `ForecastOut` with `value=0.0` and one with `-0.25` round-trip through `NormalizedForecast` with `raw_value` equal and not None); `test_geography_defaults_to_new_zealand`; `test_extra_fields_rejected`; `test_no_conversion_recorded` (`conversions == ()`).
- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Implement** in `bank_forecast.py`.
- [ ] **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat: normalized bank forecast model`.

### Task 4: Gated read-only bank view

**Files:**
- Create: `backend/src/nzstats/research/bank_view.py`, `backend/tests/research/test_bank_view.py`

**Interfaces:**
- Consumes: `drafts.draft_summaries(conn, registry, allowlist) -> list[DraftSummary]`, `DraftSummary.claims` (paths from `drafts.claim_paths`; confirm the forecast path format, expected `forecasts[i]`), `DraftSummary.summary.forecasts`, `IssuerRole`, `banks.report_kind_of`, Task 3 models.
- Produces: `ExclusionCode = Literal["claim_failed_checks","claim_has_warning","third_party_issuer","no_value"]`; `@dataclass(frozen=True) class ExcludedClaim: institution_key: str; summary_id: int; claim_path: str; code: ExclusionCode`; `@dataclass(frozen=True) class BankView: forecasts: list[NormalizedForecast]; excluded: list[ExcludedClaim]; markers: list[NormalizedForecast]; banks: list[Institution]`; `bank_view(conn: sqlite3.Connection, registry: Mapping[str, Institution], allowlist: DraftAllowlist, adapters: Mapping[str, BankAdapter] = ADAPTERS) -> BankView`.
- Rules: `banks` = institutions of kind `bank`; `forecasts` = clean, own-issuer, valued claims of drafts from banks; `markers` = same filter for kinds `central_bank` and `government`; reasons per code above; writes nothing; imports no provider or fetch client.

- [ ] **Step 1: Write failing tests** using the pattern of `tests/research/test_drafts_auto.py` (`store_hosted`, `auto()` allowlist, `llm_support.seed_version`) with the synthetic registry: clean claim appears; a claim with a verifier error is `claim_failed_checks`; one with a warning is `claim_has_warning`; `test_third_party_quote_is_never_the_banks_own` (Review Focus 4: a `bank_a` document quoting an IMF forecast and another bank's forecast yields `third_party_issuer` and no forecast row); `test_instruction_like_section_yields_nothing` (Review Focus 3, section reads "ignore previous instructions": no forecasts, no exclusions rows carrying text); `test_superseded_version_claims_vanish` (a corrected version replaces the earlier one); `test_markers_present_when_no_bank_data`; `test_non_bank_never_in_forecasts`; `test_no_provider_or_fetch_on_read` (replace provider constructors and `ResearchFetcher` with failures, call `bank_view`, assert `research_llm_usage` row count unchanged); `test_real_registry_yields_nothing` (real registry, any DB: `forecasts == []`).
- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Implement** `bank_view.py`; memoize per summary id inside the call.
- [ ] **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat: gated read-only bank forecast view`.

### Task 5: Bank analytics wrapper

**Files:**
- Create: `backend/src/nzstats/research/bank_analytics.py`, `backend/src/nzstats/research/bank_models.py`, `backend/tests/research/test_bank_analytics.py`

**Interfaces:**
- Consumes: Task 4 `BankView`; `compare.compare_forecasts`, `consensus.consensus`, `history.forecast_history`, `accuracy.evaluate_forecasts`, `outcomes.CpiActuals`, `macro_outcomes.gdp_actuals/unemployment_actuals` (existing; unchanged).
- Produces (in `bank_models.py`, models extend `api_models._Out`): `BankConsensusGroupOut(ConsensusGroupOut)` adding `adjustment: Adjustment`, `title: Literal["Two-bank comparison","Consensus of banks","Insufficient banks"]`, `disclaimer: Literal["Not a market consensus."]`; `BankConsensusOut(groups, markers: list[ForecastOut], excluded: list[BankExclusionOut])`; `DivergenceOut(group_key, indicator, adjustment, horizon_label, spread: float, median: float, banks: list[DivergenceBankOut(key, name, value, distance_from_median)])`; `BankExclusionOut(institution_key, summary_id, code: str)` where code extends Task 4 codes with `not_outlook_report`, `no_publication_date`, `conflicting_forecasts`.
- Produces (in `bank_analytics.py`): `partition_by_adjustment(forecasts: list[NormalizedForecast]) -> dict[Adjustment, list[ForecastOut]]`; `bank_comparison(view: BankView) -> list[tuple[Adjustment, ForecastComparisonOut]]`; `bank_consensus(view: BankView) -> BankConsensusOut`; `bank_revisions(view: BankView) -> list[tuple[Adjustment, ForecastHistoryOut]]`; `bank_divergence(c: BankConsensusOut) -> list[DivergenceOut]` (groups with `n >= 3` only, ranked by spread descending); `bank_evaluation(view: BankView, conn: sqlite3.Connection, indicator: str) -> ForecastEvaluationOut`.
- Rules: filter to `report_kind == "outlook"` first (others listed `not_outlook_report`); consensus/revisions exclude undated (`no_publication_date`); same-bank same-date conflicting values are excluded by the existing `compare.resolve` and surfaced as `conflicting_forecasts`; group title by contributor count per Global Constraints.

- [ ] **Step 1: Write failing tests**: `test_adjusted_and_unadjusted_never_aggregate` (same indicator/horizon/unit, two banks SA and one unadjusted -> two partitions, no group mixing); `test_title_thresholds` (2 -> "Two-bank comparison" with `std_dev is None`; 3 -> "Consensus of banks" with std_dev; 1 -> "Insufficient banks" with `median is None`); `test_weekly_forecast_listed_not_aggregated`; `test_undated_excluded` (Review Focus 1); `test_same_date_conflict_not_averaged` (Review Focus 2: two documents same bank/date values 2.0 and 3.0 -> neither in contributors, `conflicting_forecasts` listed); `test_zero_and_negative_are_contributors` (Review Focus 5: values 0.0, -0.25, 0.5 give median 0.0, min -0.25); `test_divergence_requires_three_and_ranks`; `test_markers_not_contributors`; `test_revision_across_vintages` (two outlook vintages of one bank, one group -> one revision with signed change); `test_evaluation_uses_first_published_actual_and_skips_lookahead` (reuse the CPI actuals fixtures from `tests/research/test_accuracy.py`); `test_pure_no_llm` (patch provider modules to fail).
- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Implement**; partition by calling the existing functions once per adjustment; do not modify them.
- [ ] **Step 4: Run** this file plus `test_compare.py test_history.py test_accuracy.py`; expected PASS (existing untouched).
- [ ] **Step 5: Commit** `feat: bank analytics over gated clean forecasts`.

### Task 6: Source states, metrics and bank-status

**Files:**
- Create: `backend/src/nzstats/research/bank_status.py`, `backend/tests/research/test_bank_status.py`
- Modify: `backend/src/nzstats/research/health.py` (add `bank_metrics`), `backend/src/nzstats/research/cli.py` (`bank-status`, `--json`; include metrics in `research health --json`)

**Interfaces:**
- Consumes: `registry`, `banks.BankAdapter`, tables `research_publication`, `research_document_version`, `research_summary`, `research_source_health`, `research_run`, `research_run_item`.
- Produces: `State = Literal["ok","stale","missing","blocked","unsupported","permission_denied"]`; `@dataclass(frozen=True) class SeriesStatus: series_key: str; state: State; newest_published_on: str | None; ingested_at: str | None; analysed_at: str | None; last_checked_at: str | None`; `@dataclass(frozen=True) class BankStatus: key: str; name: str; state: State; series: tuple[SeriesStatus, ...]`; `bank_status(conn, registry, now: datetime, adapters=ADAPTERS) -> list[BankStatus]`; `bank_status_exit(statuses: list[BankStatus]) -> int` (0 when all `ok`/`permission_denied`/`unsupported`; 1 when any permitted bank is `stale`/`missing`/`blocked`); `bank_metrics(conn, registry, since: datetime) -> dict[str, BankMetrics]` with `BankMetrics(discovery_ok: int, discovery_failed: int, new_documents: int, updated_versions: int, blocked: int, extraction_failures: int, verification_failures: int, missing_expected: int)`; CLI `nzstats research bank-status [--json]` exits via `bank_status_exit`, exit 3 when it cannot run.
- Precedence: `permission_denied` > `unsupported` > `blocked` > `missing` > `stale` > `ok`; bank state = worst of its series; stale judged per series against `Series.cadence_days`.

- [ ] **Step 1: Write failing tests**: real registry -> all five `permission_denied`, exit 0, and BNZ/Kiwibank report `permission_denied` (not `unsupported`: permission outranks); synthetic permitted bank without adapter -> `unsupported`; permitted + adapter + no publications -> `missing` (exit 1); newest outlook older than 100 days but a fresh weekly -> bank `stale` (a weekly cannot mask the outlook); health state `blocked` from `research_source_health` -> `blocked`; the four dates are separate fields; `test_output_has_no_document_text` (JSON contains only keys/states/dates/counts: assert against a sentinel string planted in a section); metrics counts from seeded runs.
- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Implement**; open the DB read-only in the CLI path (as `status` does).
- [ ] **Step 4: Run** this file and `test_health.py test_cli.py`; expected PASS.
- [ ] **Step 5: Commit** `feat: bank source states, metrics and bank-status command`.

### Task 7: Internal routes and privacy of the API

**Files:**
- Create: `backend/src/nzstats/research/bank_api.py`, `backend/tests/research/test_bank_api.py`, `backend/tests/research/test_bank_privacy.py`
- Modify: `backend/src/nzstats/research/drafts_api.py` (include the bank router inside `internal_drafts_router`)

**Interfaces:**
- Consumes: Tasks 4 to 6, `drafts_api._refuse_unless_local_dashboard`, `_HEADERS`, `load_allowlist`, `ALLOWLIST_FILE`.
- Produces: `bank_router(gate: Callable[[Request], None], load_registry: RegistryLoader, adapters=ADAPTERS) -> APIRouter` with `GET /internal/bank-intelligence/{summary,forecasts,revisions,consensus,evaluation,freshness}`; `evaluation` takes `indicator` in `{cpi_inflation, gdp, unemployment}`; `summary` returns per-bank cards `{key, name, state, report_name, published_on, stance: {text, claim_status, label: "AI interpretation"} | null}`; responses carry `Cache-Control: no-store`; models from `bank_models.py`.

- [ ] **Step 1: Write failing tests**: routes return 404 when internal drafts are disabled; refuse non-loopback Host/Origin/`Sec-Fetch-Site` exactly as the draft routes do (copy the matrix of `test_drafts_api.py`); response bodies contain no `raw_output`, `output_json`, reviewer names or exception text; `test_routes_absent_from_public_and_private_apps` (OpenAPI paths of the public research router and private router contain no `bank-intelligence`; `schema.d.ts` unchanged); `test_zero_provider_calls_on_every_route` (patch constructors; hit all six routes; usage rows unchanged); all-five-denied registry returns `state == "permission_denied"` cards and empty forecasts with HTTP 200.
- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Implement** and mount inside `internal_drafts_router` only.
- [ ] **Step 4: Run** the two files plus `test_drafts_api.py test_api.py`; expected PASS.
- [ ] **Step 5: Commit** `feat: internal bank-intelligence routes`.

### Task 8: Frontend data layer and static isolation

**Files:**
- Create: `frontend/src/api/bank.ts`, `frontend/src/api/bank.test.ts`
- Modify: `frontend/src/api/static.test.ts` (add case)

**Interfaces:**
- Produces: hand-written types mirroring `bank_models.py` (`BankCard`, `BankForecast`, `BankConsensusGroup`, `Divergence`, `BankStatusRow`, `BankExclusion`) and hooks `useBankSummary()`, `useBankForecasts()`, `useBankRevisions(indicator)`, `useBankConsensus(indicator)`, `useBankEvaluation(indicator)`, `useBankFreshness()` following the pattern of `src/api/drafts.ts` and `hooks.ts`; each hook is disabled in static mode.

- [ ] **Step 1: Write failing tests**: hooks request exactly `/internal/bank-intelligence/<name>`; in static mode (`mode.ts`) none issues a request; types compile against a fictitious fixture ("Example Bank A").
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/api`; expected FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** same command plus `npm run typecheck`; expected PASS.
- [ ] **Step 5: Commit** `feat: frontend bank-intelligence data layer`.

### Task 9: Cards, forecast table, filters, states

**Files:**
- Create: `frontend/src/components/outlook/bank/{BankOutlook,BankCards,BankForecastTable}.tsx` and `.test.tsx` beside each

**Interfaces:**
- Consumes: Task 8 hooks. Produces: `<BankOutlook />` (section shell: heading "Bank outlooks", the notice "AI-generated analysis for internal use. Claims are checked automatically against source documents but may contain errors. Not independently reviewed.", filters by bank and indicator, renders children) and the two components.

- [ ] **Step 1: Write failing tests** (Vitest + Testing Library, fictitious banks): one card per bank showing name, report name, publication date, freshness chip and the AI-interpretation label; a `permission_denied` bank shows the state and one sentence, no stance; table is a real `<table>` with `<caption>`, `scope` headers, one column per bank, missing cells render "–" with an accessible name "not forecast", never blank; unit and target period shown in each row; indicator and bank filters change rows; a value of `0.0` renders "0.0%" and `-0.25` renders with its sign; wording never contains "verified", "reviewed" or "approved" (assert across the rendered text); empty state names which of: server has internal analysis off, no bank permitted, no document, nothing eligible.
- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Implement** using the existing design tokens and components (`Segmented`, `StatusBadge`, `QueryBoundary`).
- [ ] **Step 4: Run** `npx vitest run src/components/outlook/bank`; expected PASS.
- [ ] **Step 5: Commit** `feat: bank cards and forecast table`.

### Task 10: Charts: consensus, revisions, divergence

**Files:**
- Create: `frontend/src/charts/bankConsensus.ts` (+`.test.ts`), `frontend/src/components/outlook/bank/{BankConsensusChart,BankRevisions,BankDivergence}.tsx` (+tests)

**Interfaces:**
- Produces: `bankConsensusOption(group: BankConsensusGroup, markers: BankForecast[], theme): EChartsOption`; `bankRevisionOption(series: BankRevisionSeries[], theme): EChartsOption`. Follow `src/charts/forecasts.ts` and `forecastTrack.ts`.

- [ ] **Step 1: Write failing tests**: option builder: one dot per contributing bank, median line and range band only when `n >= 2`, band and "Consensus" wording only at `n >= 3`, markers drawn as distinct symbols and absent from the median; groups of different `basis` or `adjustment` never share an option; no interpolation (`connectNulls: false`, gaps stay gaps); `-0.25` plotted below zero; every chart component renders a text alternative (a visually hidden table of the same values) and the title carries the unit and period; divergence list renders only groups with `n >= 3`, ranked by spread, with signed distance; revision chart one line per bank across vintage dates, never joining different targets.
- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Implement.** Record the colour choices and run the dataviz validator; paste its result into `docs/progress.md` in Task 14.
- [ ] **Step 4: Run** `npx vitest run src/charts src/components/outlook/bank`; expected PASS.
- [ ] **Step 5: Commit** `feat: bank consensus, revision and divergence views`.

### Task 11: Evidence drawer, health table, page wiring, browser checks

**Files:**
- Create: `frontend/src/components/outlook/bank/{BankEvidence,BankHealth}.tsx` (+tests), `frontend/e2e/bank-outlook.spec.ts`
- Modify: `frontend/src/pages/EconomicOutlook.tsx` (render `<BankOutlook />` after `<EconomicIntelligence />`), `frontend/src/pages/EconomicOutlook.test.tsx`

**Interfaces:**
- Consumes: Tasks 8 to 10. Produces: `<BankEvidence forecast={...} onClose />` (drawer: quote, document title, page or section ordinal, issuer, verifier version, claim status; keyboard operable, focus trapped and restored, Escape closes) and `<BankHealth rows={...} />` (table: bank, state with plain text not colour alone, four separate dates, per-series rows).

- [ ] **Step 1: Write failing tests**: drawer opens from a table cell, shows the quote and verifier, closes on Escape and returns focus; health table shows the four dates as separate columns and each state's text; `EconomicOutlook` renders the bank section only when the internal-drafts feed is available, and the static render never mounts it (existing parity spec stays green); Playwright spec (stub `/internal/bank-intelligence/*` and the drafts feed with `page.route`, fictitious banks; follow how existing specs enable internal mode, `grep -rn internal-drafts frontend/e2e`) asserts 375 px width has no horizontal scroll, the table is keyboard reachable, and dark mode renders (`colorScheme: "dark"`).
- [ ] **Step 2: Run** unit tests; expected FAIL. Playwright run waits for Step 4.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm test && npm run typecheck && npm run build`, then `npx playwright test bank-outlook` (venv on PATH, fresh build); expected PASS.
- [ ] **Step 5: Commit** `feat: bank evidence drawer, health table and page wiring`.

### Task 12: Isolation and privacy regression

**Files:**
- Create: `backend/tests/research/test_bank_isolation.py`; modify `backend/tests/research/test_bank_privacy.py` (from Task 7)

- [ ] **Step 1: Write failing tests**: seed a DB with synthetic bank claims then (a) `export-snapshot` and `validate-snapshot --for-publish` output contains no bank key, name or value; (b) the public research API and private API return no bank item; (c) import-graph test: nothing under `nzstats/pipeline`, `scheduler`, `sources`, `adapters`, `insights`, `stats`, `api` (other than the draft mount) imports `nzstats.research.bank_*` or `banks`; (d) a grep test over `frontend/src`, `frontend/e2e`, `frontend/src/api` fixtures and `scripts/` finds none of the five real bank names beside a digit within 40 characters; (e) a failure in one synthetic bank's ingest (raise inside its fetcher) leaves the other bank's run recorded `ok`; (f) no scheduler job or cron entry mentions a bank key.
- [ ] **Step 2: Run**; expected FAIL for (c) only if a stray import exists, otherwise the tests pass on first run and each must be shown failing once by temporarily introducing the violation (record this in the commit body).
- [ ] **Step 3: Fix** any real violation found in production code.
- [ ] **Step 4: Run** `PYTEST backend/tests/research/test_bank_isolation.py backend/tests/research/test_bank_privacy.py`; expected PASS.
- [ ] **Step 5: Commit** `test: bank isolation and privacy regressions`.

### Task 13: Offline end-to-end replay

**Files:**
- Create: `backend/tests/research/test_bank_e2e.py`

- [ ] **Step 1: Write the test** `test_offline_replay`: temp DB and synthetic registry (`bank_a`, `bank_b`, `bank_c`, plus `ref_central`); import two vintages of synthetic outlook documents per bank via `manual_import.import_document`; fake provider returns scripted `OutlookSummary`s (one deliberately wrong number in `bank_b`'s second vintage); run summarise through the existing path; load the app with internal drafts on; assert via the six routes: correct forecasts in the table; the wrong claim excluded with `claim_failed_checks` and absent from consensus; three banks give "Consensus of banks"; a revision appears for the second vintage; a later Stats NZ CPI actual seeded in the DB produces an evaluation row using the first-published actual; `permission_denied` for the real bank keys is untouched; provider call count equals only the scripted summarise calls, and zero during route reads; a replay from scratch yields byte-identical route JSON (determinism).
- [ ] **Step 2: Run**; expected FAIL, then fix production gaps the test exposes (each as its own small commit with its own failing test first).
- [ ] **Step 3: Run** `PYTEST backend/tests/research/test_bank_e2e.py`; expected PASS.
- [ ] **Step 4: Commit** `test: offline end-to-end bank replay`.

### Task 14: Documentation

**Files:**
- Create: `docs/phase-4ae-bank-research.md`, `docs/phase-4ae-bank-runbook.md`, `docs/phase-4ae-permissions-matrix.md`
- Modify: `docs/data-sources/research.md`, `docs/progress.md`, `CLAUDE.md` (one sentence in the opening paragraph and the commands block)

- [ ] **Step 1: Write failing test** `backend/tests/test_phase4ae_docs.py` modelled on `test_phase4f_docs.py`/`test_runbook_docs.py`: the three docs exist; the matrix names all five banks with their registry state and evidence date; the runbook covers discovery, ingestion, dry run, manual import, reprocessing, health, permission failure, backup/restore, revocation; docs contain no document text and state "no live ingestion".
- [ ] **Step 2: Run**; expected FAIL.
- [ ] **Step 3: Write the docs.** Matrix evidence is the registry's 2026-10-25 evidence; BNZ and Kiwibank and unread terms are "not examined" (no web reads were authorised). Section "External prerequisites" copies spec section 12. Record the dataviz validator result and the baseline (5932 passed, 5 skipped).
- [ ] **Step 4: Run** the docs test; expected PASS.
- [ ] **Step 5: Commit** `docs: Phase 4AE design evidence, runbook and permissions matrix`.

### Task 15: Verification, independent review and pull request

- [ ] **Step 1: Full gates**, each with its output read before any claim (superpowers:verification-before-completion): backend `PYTEST backend/tests` (expect baseline plus new tests, 0 failures), RUFF, `npm test`, `npm run typecheck`, `npm run build`, `npx playwright test`, `scripts/e2e_static.sh`, the repo's dependency audit commands (`pip-audit` or `npm audit` as documented in `docs/progress.md`), and confirm `git diff origin/main -- frontend/src/api/schema.d.ts` is empty and that `python ../scripts/dump_frontend_fixtures.py` (run from `backend/`) produces no diff (public API unchanged, so `gen:api` and fixture regeneration are not required).
- [ ] **Step 2: Independent review** (superpowers:requesting-code-review, then the `code-review` skill on the branch, plus `ecc:security-reviewer` for the route and isolation changes). Fix every confirmed HIGH/CRITICAL; fix proportionate others; never weaken a test.
- [ ] **Step 3: Finish** with superpowers:finishing-a-development-branch: push the branch and open a PR to `main` (do not merge). PR body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- [ ] **Step 4: Report** per the owner's 13-point delivery format, stating plainly that live ingestion is not enabled or evidenced for any bank.

---

## Self-review

Spec coverage: 4.1 reuse (Tasks 4 to 7 call, never modify, existing code); 4.2(1) Task 2 (narrowed, noted); 4.2(2) Task 1; 4.2(3) Task 4; 4.2(4) Task 5; 4.2(5) Task 7; 4.3 no migration (Task 4 reads lineage through existing tables; if a gap appears, stop and write migration `015` with rollback note before continuing); 5 Tasks 3 to 5; 6 verifier checks per bank-style text: covered by Task 13 plus `verify-5` existing tests (add a verifier test only where Task 13 exposes a gap); 7 Task 5; 8 Tasks 8 to 11; 9 Tasks 7 and 12; 10 Task 6 and 14; 11 milestones map: A done, B Tasks 1 to 2 and 6, C Tasks 3 to 5 and 7, D Tasks 8 to 11, E Tasks 12 to 15; 12 Task 14. Names checked across tasks: `BankView`, `NormalizedForecast`, `ExcludedClaim`, `BankStatus`, `bank_view`, `bank_consensus`, `adapter_for`, `report_kind_of`.
