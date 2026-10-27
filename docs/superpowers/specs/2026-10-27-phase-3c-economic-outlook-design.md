# Phase 3C: Economic Outlook experience (design)

Date: 2026-10-27. Branch: `feat/phase-3c-economic-outlook`. Builds on Phase 3A (research sources, PR #11) and Phase 3B
(evidence-verified LLM summaries, PR #12), both merged. Plan: [2026-10-27-phase-3c-economic-outlook.md](../plans/2026-10-27-phase-3c-economic-outlook.md).

## 1. Goal and non-goals

One page, `/economic-outlook`, that puts the latest verified Stats NZ indicators beside institutional commentary and
explicit forecasts, with every institutional statement traceable to its document, version, model and human review.

Not in scope: changing any source's access, LLM or display settings; running a live LLM; fetching any research source;
publishing research to the Netlify site; new official series (GDP, labour market, OCR are not Stats NZ series this
dashboard ingests, and none is invented); authentication.

## 2. State of the repository (inspected 2026-10-27)

- `main` at `8424c9e` (PR #12 merged). No open PRs.
- Research domain (`nzstats.research`) is isolated by AST tests: no Stats NZ package (including `api` and `publish`)
  imports it; `cli.py` is the only wiring point.
- Migration 006 stores append-only summaries (`status`: verified, failed_verification, invalid_output,
  provider_error), forecast claims (verified summaries only), usage, and human reviews (`review_status`: unreviewed,
  approved, rejected; only verified can be approved; rejection is final). `raw_output` and `review_note` are private.
- Registry: ten institutions. RBNZ `restricted`; nine `needs_review`. No source is approved, so no source can be
  fetched, summarised or displayed. `public_display` exists (`none | link_only | excerpt`, approved sources only) but is
  unused and has no approval record of its own.
- The snapshot exporter runs `create_app` over a copy of the database; the validator refuses any file kind it does not
  know, so research data cannot enter a snapshot today.
- The API has no authentication. Anything a route returns is public to whoever can reach the port.

## 3. Permissions: three separate decisions

| Decision | Field(s) | Governs | Default |
|---|---|---|---|
| Ingestion | `review_status`, `content_policy`, `approved_by/on`, `approval_note` (existing) | Whether we may fetch and store the document | not approved |
| LLM processing | `llm_processing`, `llm_processing_note` (existing) | Whether its text may go to a model | `denied` |
| Public display | `public_display` + new `public_display_approved_by`, `public_display_approved_on`, `public_display_note` | What this site may show about it, to anyone | `none` |

`public_display` levels, each including the one before:

- `none`: nothing about the source is shown.
- `link_only`: title, institution, publication date and a link to the original. No AI text, no forecasts.
- `summary` (new): plus the AI interpretation (outlook, drivers, risks, uncertainty), forecast claims and evidence
  *locations* (section and page). No verbatim text from the document.
- `excerpt`: plus the short verbatim quotes the verifier matched (each at most 600 characters, at most five per item).

Loader rules (fail closed): any level but `none` needs an approved source and all three public-display approval fields;
`summary` and `excerpt` also need `content_policy = "full_text"`. Serving `summary` or `excerpt` also needs
`llm_processing != "denied"` in the current registry: revoking LLM permission withdraws the AI text.

The current registry is authoritative at serve time, not the `licence_snapshot` stored with each version: tightening a
permission takes effect on the next request. No setting in `config/research_sources.toml` changes in this phase.

## 4. Publication approval (per summary)

Human review (Phase 3B) says "this summary faithfully reflects its evidence". Publication is a separate, later decision:
"this summary may be shown publicly". Migration 007 adds `research_summary_publication`, an append-only log of
`publish` / `withdraw` decisions with approver, a required note and a UTC timestamp. Triggers: `publish` needs a
verified, approved summary; rows are immutable. The latest decision wins. CLI:
`nzstats research publish ID --approver NAME --note TEXT` and `research withdraw ID --approver NAME --note TEXT`.

## 5. Eligibility (enforced server-side, `research/public.py`)

A summary appears in any public response only if **all** hold, evaluated on every request:

1. Public research is enabled for this process (`NZSTATS_PUBLIC_RESEARCH=1`; default off).
2. Its institution is in the current registry with `public_display != none` (and the level checks in section 3).
3. `status = 'verified'`, `review_status = 'approved'`, latest publication decision `publish`.
4. It is the newest such summary for its document version, the version is the publication's current version (not
   superseded) and the publication is not marked a duplicate. Older summaries and versions are *superseded*.
5. Its stored output parses as `OutlookSummary`, every evidence reference names this version, and the **current**
   verifier re-run on the stored sections reports no errors and no `injection_suspected_section` warning. This catches
   evidence that is missing (sections gone), stale (verifier rules tightened since) or incomplete.
6. Its document URL is https on one of the institution's allowed hosts. Otherwise the item is dropped.

Anything that fails is silently absent: the public response never explains *why* a specific summary is missing (that
would reveal unpublished material). The CLI explains it to the operator (`research summaries` shows publication state).

## 6. Read-only API (`research/api.py`, wired by `cli.py` only)

The router lives in the research package; `create_app` gains a generic `routers=` argument and the CLI's `serve` and
`openapi` commands pass the research router. The snapshot exporter calls `create_app` without it, so research can never
reach a snapshot through the exporter. When public research is disabled every research route answers exactly like an
unknown API path (`404 {"detail": "not found"}`).

| Route | Returns |
|---|---|
| `GET /api/research/feed` | `ResearchFeedOut`: items (newest first by default), `total`, `limit`, `offset`, facets (institutions, topics, indicators present). Query: `q` (≤ 100 chars, case-insensitive match on title, institution and visible AI text), `institution`, `topic`, `indicator`, `sort` (`newest`, `oldest`, `institution`), `limit` (1–50, default 20), `offset` (≥ 0). |
| `GET /api/research/summaries/{id}` | `ResearchDetailOut` for an eligible summary, else 404. |
| `GET /api/research/forecasts` | `ForecastComparisonOut`: comparable groups and excluded claims with reasons. Query: `indicator`, `institution`, `horizon` (a horizon key). |

Never in a response: `raw_output`, document sections or full text, reviewer names, review or publication notes, error
text, model parameters, usage or cost, run records, file paths. Review appears as "human-reviewed on <date>" only.
Model provenance: provider, model, prompt, processing and verifier versions, created date. Every item carries
`interpretation_label` ("AI interpretation of the document. Not an official statistic.") and `not_official_statistic`.
At `link_only` the item has no statements or forecasts; below `excerpt`, evidence has location fields only (`quote` is
null).

## 7. Forecast comparability (`research/compare.py`, pure functions)

Claims are compared only within a group that shares all of: indicator, normalised unit, statistical basis, horizon key
and kind (central forecast or a named scenario; scenarios are never grouped with central forecasts). Rules are
deterministic and conservative; anything unrecognised is listed as not comparable with a plain-English reason.

- **Unit**: the verifier's fixed vocabulary (`percent`, `percentage_points`, `percent_of_gdp`, ...). Missing unit or
  value: not comparable ("states a direction only" / "no unit stated").
- **Basis** from the indicator label (and horizon wording). A basis is stated, never assumed; contradictory wording
  (two change cadences, an average and an end-of-period figure, real and nominal) has no basis. CPI `annual_change`
  (annual / year to), `annual_average_change` or `quarterly_change`; core, underlying, excluding-X and tradables
  measures are other series and not compared. GDP is `real_` or `nominal_` plus `annual_average_change`,
  `annual_change` or `quarterly_change`, and only when the label says real / nominal (or constant / current prices):
  "GDP growth" alone is not compared, and per-capita, potential and trend measures are excluded. Unemployment
  `rate_average`, `rate_end`, or `rate` (a quarter or month, which is itself the point in time) / `rate_timing_unstated`
  (a longer span with no stated timing); a peak or trough is excluded. OCR `level_end` (end of / by), `level_average`
  (average) or `level` (as stated). Other indicators only when the label names a basis, with `real_` / `nominal_`
  when stated. No basis: "statistical basis not stated clearly enough to compare".
- **Horizon key**: `year_to:2027-03` (year to / ended / ending March 2027), `quarter:2027-03` (March 2027 quarter,
  Q1 2027), `calendar:2027` (2027, calendar 2027), `month:2026-12` (December 2026, end of 2026). Split years such as
  "2026/27" stay as written (`split:2026/27`) because June and March years are both called that; relative horizons
  ("next year") are not comparable.
- Within a group, each institution's latest vintage (publication date) is the comparison value; earlier vintages are
  returned as `earlier_vintages`. A group with one institution is shown, labelled "only one institution".

The official observation shown beside a CPI annual-change group is the latest Stats NZ CPI annual change from the
existing overview data, drawn as a distinct reference mark labelled with its period and publication date. Text states
that the observation is not a forecast and does not test any institution's explanation. No other indicator has an
official series here, and the UI says so.

## 8. Experience

Navigation: "Outlook" becomes a primary destination (Home, Outlook, Stories). One page in four bands, then a detail page.

- **A. Economic pulse.** Inflation (CPI annual change), consumer spending (ECT retail, monthly) and migration (net,
  year ended) from `/api/overview`: value, unit, observation period, publication date, a one-sentence deterministic
  interpretation built from the published comparison, a freshness status (current / next release due / may be out of
  date, from frequency and the release calendar), and a link to each dashboard. Indicators without data are omitted.
- **B. Institutional research.** Search, institution and topic filters, sort, and a group-by control (date,
  institution, topic). Each item: institution, title, publication date, processing badges (AI summary,
  evidence-verified, human-reviewed, published), the outlook, and a disclosure for drivers, risks and uncertainty.
  Link to the original and to the detail page. Empty state: an explanation of the publication rules, not an error.
- **C. Forecast comparison.** Indicator control (GDP, CPI, OCR, unemployment, plus any others present), institution
  and horizon selectors, central versus scenario toggle. A dot plot per comparable group (one row per institution,
  value axis from zero for levels and rates, filled marks for central, hollow for scenarios), a table with the same
  data (keyboard and screen-reader route), units and basis in the heading, vintage per row, and a "not comparable"
  list with reasons.
- **D. Research detail** (`/economic-outlook/research/:id`). Institution, publication date, original URL, document
  version and fetch date, the AI interpretation (clearly labelled), statements with evidence references, forecast
  claims with qualifications and scenarios, model and verifier provenance, review and publication dates.

Visual rules: existing tokens, type scale, `Segmented`, `Term`, ECharts wrapper and dataviz palette (one accent; the
forecast chart uses the navy series colour for central marks and the muted ink for the official reference; validated
with the dataviz validator). No new animation. Upstream text is rendered by React (escaped); chart tooltips use
`escapeHtml`; external links are https only and open with `rel="noopener noreferrer"`.

## 9. Static site

Research is not published to Netlify in this phase. `/economic-outlook` is a prerendered route; in static mode the
research routes resolve to "not published" (404) exactly as the live app does with research disabled, so the parity
spec covers the page. `/economic-outlook/research/*` is served the app shell. The snapshot contract, `KNOWN_KINDS` and
the validator are unchanged; a test asserts research files are still refused. A future opt-in would need its own
snapshot kinds, an explicit `--with-research` flag, a per-source allowlist and the same eligibility function.

## 10. Testing

Backend: registry levels and approval fields; migration 007 triggers; publication store; every eligibility rule
(unreviewed, rejected, failed verification, withdrawn, superseded summary, superseded version, duplicate, revoked
display or LLM permission, missing sections, tampered quote, injection warning, bad URL); feed filters, search,
sorting, pagination bounds; detail per display level; field-level leak checks; disabled-by-default 404s; comparability
(units, bases, horizons, scenarios, vintages); CLI publish and withdraw; isolation (api and publish still never import
research); snapshot still refuses research.

Frontend (vitest): pulse interpretation and freshness, comparison chart option (escaping, zero baseline, marks), page
states (loading, empty, populated synthetic, error), display levels in detail, filters and keyboard use.

Playwright: live app with research disabled (empty state, nav, responsive), a research-enabled run over a synthetic
registry and database (feed, filters, comparison, detail, keyboard, no horizontal scroll at three sizes, screenshots),
and the static suite with the new route in parity, site and no-horizontal-scroll checks.

All synthetic research fixtures use fictional institutions and say `SYNTHETIC FIXTURE`.
