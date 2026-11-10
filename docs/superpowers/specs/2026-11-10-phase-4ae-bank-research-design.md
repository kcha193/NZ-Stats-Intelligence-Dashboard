# Phase 4AE: multi-bank economic intelligence (design)

10 November 2026, Pacific/Auckland. Baseline: `origin/main` `86a4515` (PR #57). Branch `feat/phase-4ae-bank-research`.
Status: **draft for the owner's approval; nothing is built.** Written under the Superpowers brainstorming skill from the
owner's planning brief, which is the approval for the scope and guardrails below. Items marked **(my call)** are
decisions I made; the owner should read those first.

## 1. Intent

Let the owner read, in the existing local Economic Outlook page, what ANZ New Zealand, ASB, BNZ, Westpac New Zealand
and Kiwibank say about the economy and what each forecasts, side by side, with revisions and a descriptive consensus,
each number traceable to a stored source passage.

The platform already ingests, versions, summarises, verifies and compares institutional research (Phases 3A to 4AD) for
Treasury and the Reserve Bank. This phase extends that platform to five more institutions. It is not a new application,
ingestion framework, permission system or verifier.

## 2. The fact that shapes everything: no bank is permitted today

Read from `config/research_sources.toml` (no permission, approval, content-policy or LLM field changes in this phase;
descriptive fields change as listed in 4.2). All five are `review_status = "needs_review"`,
`manual_import = denied`, `llm_processing = denied`, `public_display = none`, `private_display = none`.

| Bank | Content policy | Landing page (registry) | Evidence on file (registry, 2026-10-25) | What blocks live use |
|---|---|---|---|---|
| ANZ | metadata_only | anz.co.nz/about-us/economic-markets-research/ | robots read (no Disallow); terms read: all rights reserved, store solely for viewing, not for public display, links need prior permission; silent on automated access | No approval. Terms restrict linking and onward use. Ask ANZ before even metadata links. |
| ASB | metadata_only | asb.co.nz/documents/economic-research.html | robots read: disallows `/content/dam/asb/documents/` (where report PDFs live); terms not read; listing page script-rendered | No approval. PDFs are robots-blocked, so only HTML report pages could ever be reachable. |
| BNZ | none | none in registry (brief gives institutional-banking/research/publications) | Nothing examined, no allowed host | No approval, no host, no evidence. |
| Westpac | metadata_only | westpac.co.nz/business/business-base/economics/economic-reports/ | robots and landing returned 403; terms not read; PDFs on `assets.dam.westpac.co.nz` (needs its own robots check) | No approval; access refused by the site to the probe. |
| Kiwibank | none | kiwibank.co.nz/.../commentary-insights/ (brief gives .../kiwi-economics/) | Nothing examined (search result only) | No approval, no evidence. |

Consequences, which are binding on the design:

1. **No live acquisition, discovery, storage or processing of any bank is possible or attempted.** Every bank is
   refused by the existing gates (`Institution.refusal_reason`, `import_refusal`, `llm_refusal`, `holds`). The draft
   gate also requires `content_policy = full_text`, which no bank has.
2. The whole capability is built and proven **offline against synthetic documents and a synthetic test registry**, and
   ships with every real permission field unchanged, so every bank shows a "permission denied" state on the dashboard.
3. Live readiness is reported as a list of external prerequisites per bank (section 12), never as done.
4. This phase never edits a permission field, approval field, `content_policy` or `llm_processing`. Only descriptive
   fields change (section 4).

## 3. Goals, non-goals, anti-goals

Goals
- A per-bank source definition for each of the five, and a bank-specific adapter for listing parsing, report series and
  date extraction, exercised only by synthetic fixtures.
- Normalized, evidence-linked forecasts for OCR path, CPI inflation, GDP growth and unemployment, drawn only from claims
  that pass automated verification.
- Deterministic, LLM-free analytics over those forecasts: comparison, consensus, revisions, divergence, forecast versus
  actual, freshness.
- An internal dashboard section that handles valid, missing, stale, blocked and permission-denied data.
- Per-bank health and operational runbooks.

Non-goals
- Any live request to a bank, any paid or hosted inference, any deployment, any permission change, any unattended
  polling, any public or private-preview display of bank content.
- A deterministic PDF table parser (**my call**: deferred; section 6). A new LLM prompt or contract version.
- NZD/USD, house prices, swap rates, employment growth (the brief says optional; the existing verifier supports the
  indicators, but they are not given dashboard treatment).
- An accuracy ranking of banks (the existing rule of a minimum matched sample stays; it will almost certainly not be met).

Anti-goals (a failure even if the tests pass)
- A bank number on screen that a reader could mistake for verified, official or consensus when it is not.
- Any path by which bank text, summaries or forecast values reach the public API, the snapshot, the Netlify build, or a
  committed fixture.
- A second claim store, verifier, permission model or comparison engine.

## 4. Architecture: reuse, with five thin additions

Rejected alternatives
- **B. New `bank_forecast` tables fed by a bank-specific pipeline.** Duplicates `research_forecast_claim`, the verifier
  and versioning; creates a second place where a permission can be forgotten.
- **C. A generic source-plugin framework.** Five sources do not justify it.
- **Chosen A.** Existing pipeline unchanged; add a bank adapter table, a read-only forecast view over gated claims, bank
  analytics settings, a health classification and a dashboard section.

Pipeline (existing parts in plain type, new in **bold**):

```
registry (permissions, per source) -> discover/fetch or manual_import -> publication / version / section
 -> summarise (policy-gated, route/version/budget specific) -> verify (verify-5)
 -> draft gate (research/drafts.py, loopback)  -> **bank forecast view** (clean claims only)
 -> existing compare_forecasts / consensus / forecast_history / evaluate_forecasts (bank-scoped settings)
 -> **/internal/bank-intelligence/* (read-only)** -> **Economic Outlook "Bank outlooks" section**
```

### 4.1 Reuse unchanged
`registry.py` and its gates; `fetch.py` (robots, pacing, redirect and host safety); `discover.py` parsers; `ingest.py`
(versioning, content-hash dedup, corrected and replaced documents, last-known-good, per-institution run and health rows);
`manual_import.py`; `extract*.py`; the contract (`OutlookSummary`, v2) and `verify.py` (`verify-5`, issuer attribution via
`issuers.py`); `summarise.py`, `policy*.py`, `hosted.py`, `openrouter.py` (no bank is added to any policy or consent);
`drafts.py` gate and its caveats; `compare.py`, `consensus.py`, `history.py`, `evaluate.py`, `outcomes.py`,
`macro_outcomes.py` for comparison, revisions and actuals; `health.py`; `research_*` tables.

### 4.2 Additions
1. **`research/banks.py`: one frozen `BankAdapter` per bank, in a dict keyed by registry key** (no plugin machinery).
   Holds: report series identities (e.g. ANZ "Quarterly Economic Outlook", Westpac "Weekly Commentary"), the series
   cadence (feeds `expected_publication_days`), how a listing page is parsed beyond `html_links` where the registry
   pattern is not enough, date extraction from URL or page, canonical-URL normalization, and a `report_kind`
   (`outlook | weekly | commentary | other`) per series, with that series' expected cadence in days. Adapters contain
   no permission data. Lookup is `adapter_for(key, adapters=ADAPTERS)`: the mapping is an injectable parameter, so tests
   with a synthetic registry pass their own adapters and the real `anz`/`asb` keys are used in tests only to assert
   refusal. A bank without an adapter is `unsupported` (section 10). `bank_view` does not need an adapter: a claim
   from a document with no known series has `report_kind = other`.
2. **Registry descriptive data (the only `research_sources.toml` change).** BNZ: `allowed_hosts = ["www.bnz.co.nz"]`,
   `landing_urls = ["https://www.bnz.co.nz/institutional-banking/research/publications"]`. Kiwibank: `landing_urls =
   ["https://www.kiwibank.co.nz/business-banking/thrive-hq/kiwi-economics/"]` (the owner's URL replaces the
   search-result URL). Both with `landing_evidence = "none"` and an `access_notes` line saying the URL is owner-supplied
   and unprobed. These fields scope a hypothetical future crawl; with `review_status = needs_review` and `content_policy =
   none` they permit nothing. The registry test that pins BNZ to no hosts (`tests/research/test_registry.py`) is
   rewritten to pin "still refused", and BNZ's "none is guessed" note is updated. `expected_publication_days`: ANZ 100,
   ASB 10, Westpac 10 (the most frequent series each publishes, used by the existing `research health`); per-series
   cadence for `bank-status` lives in the adapter. **(my call)**
3. **`research/bank_view.py`: a read-only, per-request view.** Calls `draft_summaries(...)` (so every draft gate check
   applies), keeps institutions of kind `bank`, keeps only claims whose draft status is `clean`, and returns
   `NormalizedForecast` records (section 5). It writes nothing and never calls a provider.
4. **Bank-scoped analytics.** A thin module that calls `compare_forecasts`, `consensus`, `forecast_history` and
   `evaluate_forecasts` on those records, adding: contributor threshold for the word "consensus" (section 7) and
   divergence. It does not modify the existing functions' public behaviour.
5. **Routes `/internal/bank-intelligence/{summary,forecasts,revisions,consensus,evaluation,freshness}`** mounted by the
   existing `internal_drafts_router` only (same loopback bind, Host/Origin/Sec-Fetch checks, `no-store`); response models
   are a new allowlist. Not mounted anywhere else.

### 4.3 Schema
Expected: **no migration.** Lineage institution -> publication -> version -> section/page -> claim -> forecast ->
comparison is already expressible: `research_publication`, `research_document_version`, `research_section`,
`research_summary`, `research_forecast_claim.evidence` (JSON of version, section, page, quote). Normalized forecasts are a
pure function of stored rows plus a verifier re-run, so reprocessing is deterministic. If the implementation plan's
first task (a lineage query test) shows a gap, a single additive migration `015` is allowed, with a rollback note,
and the plan must say so before any code is written.

Verifier results are not stored per claim today; drafts re-run the verifier on every request. The bank view does the same,
once per request, memoized per summary id. Performance is acceptable at expected volumes (tens of summaries); the plan
adds a measurement.

## 5. Forecast normalization

`NormalizedForecast` (pydantic, frozen, `extra=forbid`), all from stored data; nothing derived by a model:

institution key and name; publication id, document version id, `document_title`, `report_kind`; `published_on`
(vintage) and ingestion/analysis timestamps; `forecast_author` (the issuer; `author` or `third_party` with name);
`indicator`; `geography` (default Aotearoa New Zealand, otherwise stated); `measure` (the document's definition as
written) and `basis` (from `compare.basis_of`); `kind` = `forecast` (an observation is a `ReportedFact`, never in this
table); `target_period` (the document's horizon string) and its parsed `horizon_key`; `value` as reported, `unit`,
`frequency`; `adjustment` (as stated, else `not_stated`); `scenario` (None = central); `evidence` (version, section
ordinal, page, quote); `verifier` (version, claim status, always `clean` here); `extraction_method` (`llm_verified`);
`raw_value` and `conversions` (empty list unless a documented conversion applied).

How it reaches the existing analytics: `NormalizedForecast` wraps the existing internal `ForecastOut` (`.forecast`) and
adds the fields above. The analytics receive the wrapped `ForecastOut` values; `ForecastOut` and every public response
model are **not** extended. Constructing a `ForecastOut` internally exposes nothing.

`ForecastClaim` stores no adjustment, measure or geography, and `compare.py` ignores seasonal-adjustment wording when
grouping (`_STATED_WORDS`) while region words do separate groups. So, deterministically and in the bank layer only:
`measure` is the claim's `indicator_label` as written; `adjustment` is `seasonally_adjusted`, `unadjusted` or
`not_stated` from fixed phrases in the label and the evidence quote (a conflict between them is `not_stated`);
`geography` is "New Zealand" unless `compare.basis_of` shows a part-of-series word, which is then shown as written. The
bank analytics wrapper **partitions each existing comparison group by `adjustment`** and calls the existing functions
per partition, so a seasonally adjusted and an unadjusted figure (or either and an unstated one) are never aggregated
together; the group is labelled with its adjustment. Existing functions are unchanged. (Resolves the review question
of option a, b or c in favour of b, in the wrapper.)

`report_kind` rule **(my call)**: only claims from an `outlook`-kind report enter consensus, divergence and revisions,
because a weekly note is not a forecast round. Claims from `weekly`, `commentary` and `other` reports still appear in
the forecast table, labelled with their report kind, and are listed in the aggregates' exclusions with a fixed reason.
The wrapper applies this filter before calling the existing functions.

Rules (all deterministic, all tested):
- **No conversion in v1** other than what `compare.py` already does to *label* a basis. Quarterly versus annual, calendar
  versus fiscal, average versus end-of-period, market pricing versus an institution's own view, and the author's versus a
  third party's forecast are never merged: they land in different comparison groups, as today.
- A claim attributed to a third party (`IssuerRole.THIRD_PARTY`) is never counted as the bank's own forecast.
- Missing stays missing: no interpolation, extrapolation, carry-forward or filling a gap in a comparison table.
- A claim with any verifier error or warning is excluded and listed with its fixed reason code (warnings excluded:
  **my call**, conservative; the draft page still shows them with their caveats).
- The OCR "projected path" is a set of per-quarter end-of-period rates; each is its own forecast with its own target
  quarter. Market pricing of the OCR is a third-party/market issuer and stays apart.

The three evidential tiers the owner described map to: *directly extracted numeric forecast* (not built, see below),
*model-extracted forecast passing evidence checks* (`NormalizedForecast`), *narrative interpretation* (outlook, drivers,
risks shown as AI interpretation, never in forecast tables), and *unsupported or failed* (listed as excluded, never
aggregated).

**Deterministic table parser deferred (my call).** It needs a separate claim store because `research_forecast_claim`
requires a `summary_id`, and PDF table text extraction is the riskiest part of the work. Recommended as the first item of
the next phase; `extraction_method` is reserved for it.

## 6. AI analysis

No new prompt, contract version or provider. `outlook-v5` / contract v2 / `verify-5` apply; a bank can only be summarised
after the owner separately sets `llm_processing`, approves a version-scoped hosted consent (`hosted.py`) and adds a
`policy-*` scope for it. The Treasury authorization is not widened. In this phase all model calls use the fake provider on
synthetic text. The verifier checks listed in the brief (value, sign, unit, comparison period, horizon, author,
page/section, attribution, forecast versus observation) are already covered by `verify-5`; the plan includes a test per
item against bank-style synthetic text, and fixes `verify.py`/`issuers.py` only for a demonstrated gap (with a new
verifier version if behaviour on stored rows would change).

## 7. Analytics (deterministic, no LLM)

- **Comparison**: `compare_forecasts` groups on indicator, unit, basis, horizon and kind; unchanged.
- **Consensus**: the existing 180-day staleness and "consensus-document exclusion" rules apply. **Naming rule
  (my call):** a group with 2 contributors is titled "Two-bank comparison" and shows mean, median, range; the word
  "consensus" and the standard deviation appear from 3 contributors; outlier flags from 5 (existing thresholds). The
  group always lists contributors and exclusions with reasons, and states "not a market consensus". Treasury and RBNZ
  are shown as reference markers, never as contributors. Markers come from a second pass over the same gated drafts
  for institutions of kind `central_bank` and `government`, `clean` claims only, and appear even when no bank has data.
- **Revisions**: `forecast_history` per institution and group, unchanged; a change of measure is reported as a
  definition change, not a revision.
- **Divergence**: new, a pure function over a consensus group with n >= 3: spread (max minus min) and each bank's signed
  distance from the median, ranked; shown only for groups that pass the threshold.
- **Forecast versus actual**: `evaluate_forecasts` with the existing CPI, GDP and unemployment actuals from stored
  Stats NZ vintages; first-published actual and latest actual are reported separately; nothing published on or after the
  outcome is scored. OCR outcomes are out of scope (no authorized RBNZ observation source). No ranking unless the existing
  matched-sample rule is met.
- **Freshness**: per bank, four separate dates (published, ingested, analysed, last checked) and one state from
  `missing | stale | blocked | unsupported | permission_denied | ok`, defined in section 10.

## 8. Dashboard

Extends `EconomicOutlook` inside the AI Economic Intelligence area, with the existing caveats unchanged and no wording
that says verified, reviewed or approved. The section is a sibling of the existing Treasury/RBNZ content and appears
only when the server has internal drafts on (the existing switch).

Default view for a non-economist, top to bottom:
1. **Banks at a glance**: one card per bank: plain-English stance (AI interpretation, labelled), report name and
   publication date, freshness chip. A bank with no data shows its state and one sentence why.
2. **Forecast table**: rows = indicator and target period, columns = banks, cell = value with unit, a dash for missing
   (never blank, never filled); an indicator filter and a bank filter; each cell opens evidence.
3. **Consensus chart**: ECharts dot plot of the banks' values per target period with median and range band, with the
   Treasury/RBNZ markers; hidden under 2 contributors, retitled under 3 (section 7). Different bases are different charts.
4. **Revision history**: line per bank across vintages for one indicator and target.
5. **Divergence**: ranked list, groups with n >= 3 only.
6. **Evidence and verification** drawer: claim, quote, document, page or section, issuer, verifier version, check results,
   excluded claims with reasons.
7. **Source health**: the section 10 table.

Accessible tables (real `<table>`, captions, header scopes), chart text alternatives, keyboard-operable drawer, 375 px
layout without horizontal scroll, `prefers-color-scheme` dark mode, chart colours validated with the dataviz validator
and recorded in `docs/progress.md`. Follows the project dials (variance 5, motion 2, density 7). Wireframes are in the
plan; no visual companion was used because the owner asked for no interruptions.

## 9. Privacy and isolation (testable claims)

- Bank routes exist only on the draft router; absent from `api.py`, `private_api.py`, the static build and the OpenAPI
  schema of a non-internal start. Tests: route table with internal drafts off; `export-snapshot` and `validate-snapshot`
  on a database holding synthetic bank claims contain no bank string; `scripts/e2e_static.sh` and the parity spec pass;
  a grep test over `frontend/src`, fixtures and `dist/` for bank-content markers.
- **Committed frontend fixtures and tests use fictitious bank names** ("Example Bank A") and obviously synthetic values;
  real bank names never appear next to numbers in committed data. Backend tests may use the real registry keys only to
  assert refusal, and a synthetic registry (temporary TOML, fake keys, fake host) to exercise the happy path.
- Opening any page makes zero provider calls and zero fetches (the 4AA test pattern: replace constructors and clients
  with failures, read every new route, assert no usage rows).
- Diagnostics (health, metrics, runbook output) contain ids, counts, states and fixed codes, never document text.

## 10. Operations

Source states, computed read-only and in this precedence: `permission_denied` (registry gates refuse the route; the real
state of all five today) > `unsupported` (no adapter or no verified discovery) > `blocked` (permitted but the site
refused or a challenge was seen; recorded by ingest) > `missing` (permitted, supported, nothing stored) > `stale`
(newest publication of a series older than that series' cadence in the adapter; judged per series, so a weekly note
cannot mask a missing quarterly outlook) > `ok`. Bank state is the worst of its series.

Exit codes of `bank-status` **(my call)**: 0 when every bank is `ok`, `permission_denied` or `unsupported` (a source
off by choice is not a fault, as for the scheduler); 1 when any permitted bank is `stale`, `missing` or `blocked`;
3 when the command cannot run. There is no 2 (no critical state is defined for a read-only report).

- **Metrics** added to `research health` output: discovery success, new documents, updated versions, blocked sources,
  extraction failures, evidence verification failures, missing expected releases, all per institution.
- **CLI**: reuse `research discover|ingest|import|summarise|health` with `--dry-run` and `--offline`. One new read-only
  command, `nzstats research bank-status [--json]`, prints the section 10 table (exit 0/1/2 as `status` does).
- **Isolation**: ingestion for one institution cannot raise into another (existing per-institution try and run rows);
  the Stats NZ pipeline and scheduler never import `research.banks`. No scheduler entry, no cron, no on-open refresh for
  banks. Bounded retry and cooldown are the existing fetcher/health behaviour.
- **Runbook** `docs/phase-4ae-bank-runbook.md`: discovery, ingest, dry run, manual import, reprocess, health, permission
  failure, backup and restore (existing `backup --bundle`), source revocation (existing purge flow).

## 11. Verification and milestones

Strict RED-GREEN-REFACTOR; each test is watched failing first. Milestones and exit gates:

- **4AE-A** audit, this design, the plan, baseline (backend baseline green before any change).
- **4AE-B** `banks.py`, registry descriptive edits, parser fixtures, state computation, `bank-status`, health metrics.
- **4AE-C** `bank_view.py`, `NormalizedForecast`, divergence, bank-scoped consensus naming, routes and models,
  `npm run gen:api`, fixtures regenerated per CLAUDE.md.
- **4AE-D** frontend section, unit tests, Playwright (including `playwright.research.config.ts` style synthetic run),
  accessibility and 375 px checks.
- **4AE-E** offline end-to-end replay, privacy regression tests, docs, independent review (code-review skill plus
  security pass), fix confirmed HIGH/CRITICAL, PR (not merged).

Required gates at the end: `pytest`, `ruff check`, `ruff format --check`, a type check where the repo has one,
`npm test`, `npm run typecheck`, `npm run build`, Playwright, `scripts/e2e_static.sh`, dependency audit as the repo does it.

Offline end-to-end replay: temporary database and registry; synthetic ANZ-like and ASB-like documents imported via
`manual_import` under a synthetic approved registry entry; fake provider returns a scripted `OutlookSummary` including a
deliberately wrong claim; assert the right claim appears in the forecast table and consensus, the wrong one is excluded
with a reason, a second vintage produces a revision, a later Stats NZ actual produces an evaluation row, and the dashboard
routes return it with zero provider calls.

## 12. External prerequisites for any live bank (not done, not requested by this phase)

For each bank the owner must independently: read robots.txt and the terms in a browser and record evidence and date;
obtain written permission where the terms require it (ANZ linking and use; automated access generally); approve
`review_status`/`content_policy` and, separately, `manual_import`, `llm_processing` (with a version-scoped hosted consent
if hosted), and private display; ASB: choose an HTML-only route because PDFs are robots-blocked; Westpac: check the
`assets.dam.westpac.co.nz` host; BNZ and Kiwibank: establish the official research page and its terms. Scheduling any
bank is a further separate approval.

## 13. Left to the builder
Module and class names beyond those given; test layout; exact adapter parsing per bank beyond what synthetic fixtures need;
chart option details; wording of fixed reason codes (must be fixed strings, not exception text).

## 14. Owner decisions
Open (changes the permissions-matrix deliverable, not the code): may I refresh the matrix's robots.txt and terms evidence
by reading each bank's public pages with a plain web-read tool (not the project crawler or its User-Agent, no
downloading of reports)? Default if unanswered: **no**; the matrix keeps the registry's 2026-10-25 evidence and marks
BNZ, Kiwibank and unread terms "not examined".

My calls to confirm or reverse (each is cheap to change before the plan): table parser deferred; claims with warnings are
excluded from aggregates; "Two-bank comparison" below 3 contributors; only `outlook` reports feed aggregates and
revisions; registry cadence values; `bank-status` exit codes; Treasury/RBNZ markers from a second clean-only pass.
