# Phase 3D: real economic intelligence and forecast evaluation

Date: 2026-10-28. Status: design and audit. 3D-A (pilot readiness) and 3D-B (forecast evaluation) are separate PRs.

## 1. Audit

### Repository state

- `main` at `ffed629` (merge of PR #13). PRs #11, #12 and #13 (Phases 3A, 3B, 3C) are merged. No PR is open.
- Backend suite on `main`: 2215 passed locally (Python 3.12 venv, 2026-10-28).
- Schema through migration 007: Stats NZ tables (`release`, `series`, `vintage` with `activation`,
  `vintage_series_definition`, `observation`), and the research domain (`research_institution`, `research_publication`,
  `research_document_version`, `research_section`, run and health tables, 005 duplicate version, 006 append-only
  summaries, claims, usage and reviews, 007 append-only publication decisions). Triggers make summaries, claims, usage,
  reviews and publication decisions immutable; only a verified summary can be approved, and only an approved, verified
  summary can be published.
- Research pipeline: registry gate (`review_status`, `content_policy`, `terms_evidence = "direct"` for any approval),
  polite fetcher (10 s floor, robots, SSRF-safe resolver), HTML and PDF extraction into sections with pages,
  Phase 3B summaries with a 26-rule deterministic verifier, human review, Phase 3C per-summary publication and one
  public gate (`research/public.py`) behind `NZSTATS_PUBLIC_RESEARCH=1`. Comparison (`research/compare.py`) groups
  forecasts only on a stated basis; it shows each institution's latest vintage and lists earlier ones.
- Nothing is approved in `config/research_sources.toml`: RBNZ `restricted`; Treasury, ANZ, ASB, Westpac and NZIER
  `needs_review`; the rest `needs_review` with policy `none`. Every source has `llm_processing = "denied"` and
  `public_display = "none"`.

### GitHub Actions failures (PR #13 and `main`)

Every run since **2026-10-24 00:33 UTC** (PR #8 onwards, including all of #10 to #13 and the `main` merges) failed in
3 to 5 seconds. The jobs list zero steps and no runner name, and each carries the annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased.

This is an **infrastructure (billing) failure, not a code failure**: no job started, so no test, lint or build ran on
GitHub. The last green run was `main` on 2026-10-22 23:54 UTC. All verification since then is local. The fix is an
account billing action, which is out of scope here. A second notice is informational only: `ubuntu-latest` moves to
Ubuntu 26 from 2026-10-19; when billing is restored, watch the first run for image changes (Playwright's
`--with-deps` packages are the likeliest casualty).

## 2. Phase 3D-A: real-data readiness and pilot

### Pilot institution: the Treasury

The Treasury is the only candidate that could plausibly support every gate: Crown copyright under CC BY 4.0 is the
stated basis for New Zealand government content (NZGOAL), it publishes forecast tables (HYEFU, BEFU), and it is not
under the RBNZ restriction. Each permission is assessed separately.

| Decision | Evidence held | Status | What would change it |
|---|---|---|---|
| 1. Automated discovery and fetching | `robots.txt` read directly on 2026-10-25 (Drupal rules; disallows `/publications/search`, `/admin`, `/user/*`; no crawl delay). `/publications` and `/sitemap.xml` returned 403 to a generic probe (`direct_blocked`). | **Not granted** | The terms of use read directly and saying nothing against automated access; one throttled discovery probe with the project User-Agent, authorised by Kevin. |
| 2. Extraction and local storage | Licence statement known only from a search summary (`terms_evidence = "search"`). A direct read of `https://www.treasury.govt.nz/copyright-and-licensing` on 2026-10-28 returned **HTTP 403** (no content). | **Not granted** | The licence page read directly (in a browser by Kevin, or an emailed confirmation), confirming CC BY 4.0 covers the publications and what is excluded (third-party material, logos, data sourced from others). |
| 3. LLM processing (local versus hosted) | None beyond the licence summary. CC BY 4.0 allows adaptation by anyone, so a hosted model would be third-party processing that the licence does not forbid, but that is an inference, not a reading. | **Not granted** (`denied`) | Decision 2 plus an explicit judgement recorded in `llm_processing_note`. `local_only` is the lower-risk first step; `hosted` additionally needs the paid-call authorisation in section 2.3. |
| 4. Public summary and excerpt publication | None. CC BY 4.0 permits sharing adaptations with attribution and an indication of changes, if the licence applies to the specific document. Third-party data inside Treasury forecasts tables may be excluded. | **Not granted** (`none`) | Decision 2, a per-document check for third-party exclusions, an attribution format, and a separately recorded `public_display` approval. `link_only` first. |

**Activation blocker.** No source can be legally activated today. The Treasury's terms have not been read directly
(the page refuses automated readers, and this project does not work around a refusal), and nothing has been
authorised. Per the brief, no approval is inferred from the CC BY summary and no permission setting was changed. RBNZ
stays `restricted`.

**To unblock (Kevin):** read the Treasury copyright and licensing page in a browser; record what it says about
automated access, storage, third-party processing and republication in `licence` and `access_notes`; set
`terms_evidence = "direct"`; then authorise one discovery probe (`nzstats research discover treasury`). Each later
gate is a separate, recorded decision (checklist: `docs/data-sources/research.md`).

### What 3D-A builds (offline, testable without any source)

1. **Readiness report** (`nzstats research readiness [KEY]`): evaluates the four decisions above from the current
   registry and environment, with the evidence fields behind each one, the first blocker, and pilot pipeline state
   (stored versions, summaries by status and review, published count). No network, no writes.
2. **Extraction quality assessment** (`research/quality.py`, `nzstats research quality VERSION`): deterministic
   checks on a stored version's sections: empty or near-empty sections and pages, missing pages, replacement and
   control characters, alphabetic ratio, glued words (OCR or column merge), repeated header and footer lines,
   numeric density. Grades `ok`, `review` or `poor` with reasons. Heuristic thresholds, documented, for a human to
   act on; it never blocks ingestion.
3. **Real-model evaluation** (`research/pilot_eval.py`, `nzstats research evaluate --annotations FILE`): measures
   stored real summaries against a human annotation file kept outside git (`data/`), because it is derived from
   third-party text. Metrics: forecast precision and recall (raw and accepted), numerical fidelity, scenario
   accuracy, indicator F1, citation correctness, unsupported-item rate, verified rate, and cost and latency from
   `research_llm_usage`. It calls no model. Its report is labelled "real documents, real model" and is never merged
   with the synthetic replay baseline (`RECORDED_BASELINE`).
4. **Pilot runbook** in `docs/data-sources/research.md`: the ordered steps from terms review to a published
   `link_only` item, each with the command, the gate it needs and the stop condition.

### Paid calls and budgets

A live summary run or `--live` evaluation needs Kevin's explicit permission in this session, a configured provider,
and `NZSTATS_LLM_MAX_RUN_USD`. Neither was given, so no model was called. The existing per-run budget check (worst
case before every call) is unchanged.

## 3. Phase 3D-B: historical forecast intelligence

Design detail and statistical decisions: `2026-10-28-phase-3d-b-forecast-evaluation.md` (on the 3D-B branch). In
outline:

- **Forecast history**: identity = (institution, indicator, unit, statistical basis, horizon, central or named
  scenario). A vintage is one publication's claim; later vintages supersede earlier ones but are kept. A change of
  value under the same identity is a revision; the same institution, indicator and horizon under a different basis
  is a **measure change**, never a revision. Two different values for one identity in one document are a conflict and
  are not used.
- **Standardisation**: reuses the Phase 3C basis rules unchanged. Nothing is converted; ambiguous wording stays
  non-comparable.
- **Outcome matching**: CPI only (the official series this site ingests). Annual change (through the year) and
  annual average change from the unadjusted all-groups index; quarterly change only when the claim states seasonal
  adjustment or its absence. Horizons must name a quarter. First-published and latest values are taken from the
  stored release vintages. A forecast published on or after the release date of its outcome is excluded (look-ahead).
  GDP, unemployment and OCR stay "no official series here".
- **Accuracy**: signed and absolute error per matched forecast; MAE and RMSE only from four or more outcomes in a
  horizon band; cross-institution ranking only on a matched sample (same target and horizon in quarters) of at least
  eight; otherwise an explicit insufficient-data state. Revisions are reported separately from accuracy.
- **Consensus**: central forecasts only, one per independent institution (aggregators such as a consensus survey
  excluded), contributions within 180 days of the newest; mean, median, range; standard deviation from three; outliers
  from five (median ± 3 scaled MAD). Always labelled descriptive, not calibrated, not a model.
- **API**: new read-only research routes behind the same `NZSTATS_PUBLIC_RESEARCH=1` switch, built only from
  `public_summaries`. Nothing enters the static snapshot.
- **Frontend**: vintage timeline and revision chart, forecast versus actual, consensus and disagreement, explicit
  unavailable and insufficient states, methodology notes; a dot plot axis that need not start at zero (positions, not
  lengths) with a minimum span so close OCR levels separate without exaggerating small differences.

## 4. Publication and security (both workstreams)

Unchanged: three per-source gates, per-summary review and publication, research off by default, no research in
snapshots, no unauthenticated write route. 3D-B adds read-only routes under the existing switch and gate only.
Static research publication is not proposed.
