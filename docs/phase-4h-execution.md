# Phase 4H execution: live on-open acceptance and two-document research baseline

Executed 31 October 2026 (Pacific/Auckland) on the owner's Mac from main `3ce76e4`, tracking
[issue #31](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/issues/31). Plan:
[phase-4h-pilot-readiness.md](phase-4h-pilot-readiness.md). Local operation only: no scheduler, Netlify, Docker,
institutional crawling, model call or registry change. No report text is in this file or in git; annotations and
evidence stay under the git-ignored `data/` directory.

## Stage 1: live Stats NZ on-open acceptance

**Verdict: GO WITH CONDITIONS.** The live calendar check, discovery, pacing, single-flight/reuse rules, status
reporting and dashboard behaviour are verified against the real site. Live parsing of an unseen new release, its
pre-refresh backup and the chart refetch after new data are **not** verified, because nothing was due. Next supported
release: labour market statistics (September 2026 quarter), 4 Nov 2026 10:45 NZDT.

### Preflight (before any write)

Production was already at schema 13 (migration 013 was applied by the 31 Oct 09:33 check), so no migration was
pending. Checks, all read-only on the live database:

| Backup | Result |
|---|---|
| `pre-4g-013-20261030T201559Z` (unmigrated, schema 12) | `verify_backup(allow_older_schema=True)` ok: integrity, foreign keys, schema-12 objects, 0 missing raw; its 43 raw files are a hash-identical subset of live (live adds the two research imports) |
| `pre-treasury-import`, `post-rbnz-import` (bundles) | `verify_bundle` ok; `post-rbnz-import` raw tree identical to live; row differences only `refresh_run` +1, `ops_process` +1 |
| **`pre-4h-acceptance-20261030T224601Z`** (new) | SQLite online backup from a `mode=ro` connection plus a full raw copy; integrity ok, schema 13, 0 count differences, 45/45 raw files hash-identical (content-addressed names equal their SHA-256) |

The recorded order-independent content comparisons with the schema-12 pre-4G backup found observations (76,402),
vintages (791), series (450) and ingest runs (22) unchanged. Releases (212) differed in `updated_at` from calendar
re-sightings, so their full-row digests are not identical. The 43 original raw files are a hash-identical subset of
the 45 live files; the two additions are the manually imported research documents. This file-level comparison does
not establish equality of the whole raw-artifact table or its content digest. The newer schema-13 pre-4H backup had
matching row counts and all 45 raw files hash-identical to live, as recorded above; matching counts alone do not
establish matching table content digests.

The owner's own launch (`Start Dashboard.command`, which opens the browser) had already run `refresh_run 3` at
11:38:56 NZDT, before this verification: 4 requests, nothing found, only timestamps changed. It is recorded here and
was not counted as the controlled check.

### The controlled check (`refresh_run 4`)

After the 30-minute reuse window from run 3 had passed and the live tables were reconfirmed identical to the new
backup (only the process heartbeat had moved), the dashboard at `http://localhost:8000` was opened once in a headless
Chromium. The DevTools browser profile was locked by another instance, so the project's Playwright browser was used.
The page's own code sent the guarded POST; nothing else was sent except read-only status GETs.

| Item | Value |
|---|---|
| Server | PID 54267, `nzstats serve --host 127.0.0.1 --port 8000`, mode `on_open`, scheduler off, main `3ce76e4` |
| Page opened | 12:11:10 NZDT (23:11:10Z) |
| Check started / completed | 12:11:10 / 12:12:02 NZDT; `trigger=open`, `state=completed`, `error_class=null` |
| POST `/api/refresh` | exactly 1, HTTP 200, `X-NZStats-Client: dashboard` |
| Logical GETs (`requests`) | 4 (calendar only), all to www.stats.govt.nz |
| HTTP attempts (pacer journal) | 4, at 23:11:31, :41, :52 and 23:12:02Z; gaps 10.3, 10.7, 10.3 s; no retry, block or `Retry-After` state |
| Discovered / ingested / unchanged / pending / failures | 0 / 0 / 0 / none / none |
| Header | *Checking for updates…*, then *Data is up to date* |
| `data_version` | `a791` before and after, so no chart refetch was due; every chart rendered at once from stored data |
| Pre-refresh backup | none created (correct: nothing to ingest) |
| After | observations, vintages, series, raw artifacts (45 files), ingest runs and research tables content-identical to the newer pre-4H backup; only `release.updated_at`, `source_health.last_checked_at/last_success_at` and the new `refresh_run` row changed. `nzstats status --json`: ok, no findings |

Latest statistics held after the check (from `/api/refresh/status`): CPI September 2026 quarter (published 22 Oct),
electronic card transactions September 2026 (16 Oct), GDP June 2026 quarter (17 Sep), international migration
August 2026 (14 Oct), labour market June 2026 quarter (5 Aug). There was no statistical change to reconcile; Stage 3
reconciles the stored values against both research documents.

Evidence (git-ignored): `data/phase-4h/acceptance/` (browser log of every API call, header states, screenshots).

Conditions: (1) observe the first on-open check after 4 Nov 10:45 NZDT to verify a real new-release download,
validation, pre-refresh backup and chart refetch, and reconcile the release independently; (2) hosted CI remains
billing-blocked, so local results are the only test evidence.

## Stage 2: the two imported research documents

Verified read-only against `data/nzstats.db` after the verified backup.

| Check | Treasury FEU, 15 Oct 2026 (version 1) | RBNZ "OCR held at 2.75%", 28 Oct 2026 (version 2) |
|---|---|---|
| Import file, raw artifact and DB `content_sha256` | all `63aaa9df…5483073` | all `ee38b509…1191290` |
| Raw artifact row | id 44, 1,027,500 bytes, `application/pdf` | id 45, 87,826 bytes, `text/html` |
| Acquisition / manual-import audit row | `manual`, outcome `new` | `manual`, outcome `new` |
| Independent re-extraction with the shipped extractor | `pdf-1`: same `text_sha256`, 7/7 sections identical (text, pages, offsets) | `html-1`: same `text_sha256`, 15/15 sections identical |
| Section offsets | contiguous (2-character separators), lengths sum to `char_count` 28,037 | contiguous, sum to 17,203 |
| Pages | 7 of 7 covered, one section per page | not applicable (HTML) |
| `research quality` | `review`: 4 private-use characters | `ok` |

`research sources`, `readiness treasury|rbnz`, `health --json`, `status` and `orphans` (0 unreferenced files) ran
against `./data`. Both sources: crawler not granted (`needs_review`), storage granted (manual import only),
`llm_processing = denied`, `public_display = none`, no provider configured, `NZSTATS_PUBLIC_RESEARCH` off, no summaries.
`health` reports no findings. All ten institutional crawlers stay gated.

Both `research_manual_import.note` values contain a literal `<date>` placeholder rather than the browser download date.
The audit row is append-only, so this is recorded here and not edited.

### PDF bullet-glyph warnings

The four characters are U+F0A7 (Unicode category Co, private use): the list-bullet markers of the four headlines on
page 1, emitted by a symbol font without a Unicode map. Each starts a line and is followed by a space. None touches a
number, date, word or offset, so the economics are unaffected and the original file and stored version are unchanged.

The investigation found one genuine defect, in the **quality report**, not the extraction: the same four characters
were reported twice, as `undecodable_characters` and as `control_characters`, because Python treats private-use code
points as non-printable. There are no control characters in either document. Fixed failing-first in
`research/quality.py`: private-use characters are counted once, as undecodable; genuine control characters are still
flagged beside them; a new `control` metric is reported. The grade is unchanged (`review`), so nothing is weakened.

Extraction hazards that the heuristics do not detect, recorded for model evaluation (no fix proposed now; each needs
real-layout evidence before a parser change):

- Page 2's IMF table: the column headers (real GDP, inflation; actual/forecast) are detached and appear after the rows,
  so a row of six numbers carries no column labels in reading order.
- Chart axis labels leak in as runs of loose numbers on pages 1–4.
- One negative value is split across a line break (`-` at a line end, `7%` on the next), so a quote or number match on
  `7%` alone would lose the sign.
- RBNZ section 0 is the website's "browser issue" banner (page chrome, not content).

## Stage 3: independent reference annotations and pipeline assessment

The baseline was written from the stored sections before any model output exists (none can: `llm_processing` is
denied). Every item is anchored to an exact quote with section, page and character offsets; the builder fails if any
quote is missing.

| File (git-ignored) | Purpose | SHA-256 |
|---|---|---|
| `data/phase-4h/annotations/baseline-2026-10-31.json` | full taxonomy, 46 anchored items, Stats NZ reconciliation | `693fce86…09c8f57836b` |
| `data/annotations/phase-4h-evaluate.json` | `research evaluate` gold set (validated by the CLI: "annotated but never summarised: versions 1, 2") | `74d4d9fd…eb0c066bcc` |

| Category | Treasury | RBNZ |
|---|---|---|
| Reported facts (official or third-party data, with source) | 15 | 7 |
| Institutional interpretations | 7 | 5 |
| Forecasts and assumptions (tagged by issuer) | 7 (3 Treasury, 4 IMF) | 2 |
| Monetary policy decisions | 0 | 2 (4–3 vote to hold at 2.75%) |
| Policy guidance (conditional, not a forecast) | 0 | 1 |

Gold forecasts for scoring are each document's **own** forecasts only: Treasury's Pre-election Update GDP and
inflation for 2026 and 2027 and net migration of 21,900; RBNZ's 4.4% annual CPI for the December 2026 quarter.

### Comparison with Stats NZ (vintage published by the document's date, no look-ahead)

| Document figure | Document | Stats NZ as of document date | Series |
|---|---|---|---|
| CPI annual, June 2026 qtr | 4.1 | 4.1 | `cpi.index.nsa.all_groups` |
| CPI quarterly SA, June 2026 qtr | 1.5 | 1.5 | `cpi.index.sa.all_groups` |
| GDP qpc SA, March / June 2026 qtrs | 0.9 / 0.2 | 0.9 / 0.2 | `gdp.production.cv.sa.pct_qoq` |
| GDP annual average, June 2026 qtr | 1.7 | 1.7 | `gdp.production.cv.nsa.pct_annual_avg` |
| Unemployment / participation SA, June 2026 qtr | 5.6 / 70.7 | 5.6 / 70.7 | `hlfs.rate.*.sa` |
| Employment qpc SA, June 2026 qtr | 0.4 | 0.4 | `hlfs.level.employed.sa` |
| LCI salary and wage rates annual, June 2026 qtr | 2.0 | 2.0 | `lci.all_wages.pct_yoy` |
| Net migration, year to Aug 2026 / Jan 2026 | 20,500 / 12,700 | 20,503 / 12,734 (rounded) | `mig.ry.net` |
| RBNZ: CPI annual, Sept / June 2026 qtrs | 3.7 / 4.1 | 3.7 / 4.1 | `cpi.index.nsa.all_groups` |
| RBNZ: tradables annual, Sept / June 2026 qtrs | 4.3 / 4.9 | 4.3 / 4.9 | `cpi.index.nsa.tradables` |
| RBNZ: non-tradables annual, Sept 2026 qtr | 3.3 | 3.3 | `cpi.index.nsa.non_tradables` |

All 16 comparable figures match. Treasury's **monthly** net migration (July 3,190; August 1,530) does not match the
stored unadjusted monthly series (5,154; 2,193). The document does not state its adjustment basis, so these are a
basis mismatch, not an error, and must not be compared. Several cited figures have no stored series (building
consents, visitor arrivals, export volumes, CPI excluding fuel, REINZ, survey data); a preview must label them as the
institution's figures.

### Offline pipeline assessment

`pytest tests/research`: **1,446 passed**, offline (extraction, prompt, provider adapters, 26-rule verifier, gating,
evaluation). The deterministic layers are sound for a pilot. Gaps for these two documents:

1. `ForecastClaim` has no issuer. The FEU quotes IMF forecasts next to Treasury's; a model could attribute IMF numbers
   to Treasury and the verifier would pass (the quote and number exist). Add an `issuer` field (institution or named
   third party) and a verifier rule before the pilot.
2. The contract has no place for a **policy decision** (the OCR hold and 4–3 vote) or for reported facts versus
   interpretation; decisions would be forced into `outlook` statements or misread as forecasts.
3. Number matching must keep a sign split across a line break and must refuse numbers from detached table rows
   without a column label; extend the verifier's number spans or mark such sections.

## Recommended local-model pilot (needs owner approval; nothing configured)

- **Runtime:** `llama.cpp`'s `llama-server` with locally downloaded open weights, bound to `127.0.0.1`, set as
  `NZSTATS_LLM_PROVIDER=openai_compatible` and `NZSTATS_LLM_BASE_URL=http://127.0.0.1:<port>/v1` (the code already treats
  only a loopback URL as local). Avoid wrappers that can route to hosted models from a loopback address (for example
  Ollama's `-cloud` model tags). Verify no outbound connections during the run (e.g. `lsof -i` or a firewall rule).
- **Model:** an instruction-tuned open-weights model of roughly 20–35B parameters with a context of at least 32k
  tokens (the FEU is about 28k characters, roughly 9k tokens), quantised to fit memory; record the exact weights file
  hash, quantisation and runtime version in the provenance.
- **Registry change for each source:** `llm_processing = "local_only"` with `llm_processing_note`, as a reviewed edit.
  Treasury (CC BY 4.0) and RBNZ (reproduction permitted with acknowledgement) both plausibly allow local processing;
  record the owner's reading of each. Never `hosted`.
- **Run:** `research summarise treasury --dry-run`, then `--limit 1` per source; `research summary ID`.
- **Acceptance (against this baseline):** zero verifier errors; every number in a statement or forecast traces to a
  quote in the cited section; no IMF forecast attributed to Treasury; RBNZ hold and vote stated as a decision, not a
  forecast; forecast recall of the 6 gold forecasts with numerical fidelity 1.0; citation correctness at least 0.95;
  no number taken from chart-axis residue; reviewer approval before any display.

## Stage 4: private Economic Outlook preview (design only)

`public_display = none` stays in force and the public research API stays off. A private preview is a separate,
reviewable feature with its own approval; it is **not** built in this change because no summary can exist yet and
the permission model has no private-display decision.

Design:

1. **Separate route family, separate switch.** `/api/private/research/*`, mounted only when the operator starts
   `nzstats serve` with `--private-research` (default off). Never in snapshots, static builds or the container.
2. **Loopback and same-origin only.** Reuse the Phase 4G refresh guard: loopback `Host`, matching `Origin`,
   `Sec-Fetch-Site: same-origin` when sent, a custom request header, no CORS; refuse to start on a non-loopback bind.
3. **New per-source decision** `private_display` (`none`/`summary`), recorded with approver and date, separate from
   `public_display` and from `llm_processing`. Its gate mirrors `research/public.py` (one function, rechecked per
   request): verified, reviewer-approved, current non-duplicate version, allowed host, still passing the current
   verifier, no instruction-like section.
4. **Presentation:** institution name and logo-free text attribution, report title and date, issue date, link to the
   original, licence line; every statement with its evidence (section, page, quote); badges for **Forecast**,
   **Institutional view**, **Policy decision** and **Official statistic (Stats NZ)**; Stats NZ comparisons only at the
   vintage the report could see, linked to the dashboard series.
5. **Tests:** gate unit tests, request-guard tests, browser tests proving it is absent unless switched on, and a
   snapshot test proving no research reaches the static site.

Approvals required before building or activating it are listed below.

## Outstanding owner decisions

1. **Local-model processing:** approve `llm_processing = "local_only"` for Treasury and RBNZ (separately), the runtime
   and the model. Hosted providers stay disabled.
2. **Contract changes before the pilot:** forecast issuer, policy-decision record, verifier rules for signs and table
   rows (a separate PR with failing-first tests).
3. **Private preview:** approve the design above and a new `private_display` decision; build in its own PR with
   security review.
4. **Treasury and RBNZ automated access** remains refused (`needs_review`); RBNZ requires prior written permission.
5. Optional: whether to record the manual-import download dates that the audit notes omit (as a new note, not an edit).

## Verification of this change

- Failing-first: the two new `test_quality.py` cases fail on main's `quality.py` and pass with the fix.
- Backend (Python 3.14 venv): **3,203 passed**; `tests/research` 1,446 passed; Ruff lint and format clean.
- `research quality` on production after the fix: Treasury `review` (4 undecodable, no control characters), RBNZ `ok`.
- No frontend, API model or schema change, so frontend and browser suites were not rerun.
- Hosted Actions remain billing-blocked; Docker is out of scope.
