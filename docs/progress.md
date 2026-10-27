# Progress and verification record

Last updated 2026-10-27. Phase 3C (economic outlook) is on `feat/phase-3c-economic-outlook` (not merged). Phase 3B
(PR #12), Phase 3A (PR #11) and the Netlify static publication (PR #10) are merged to `main`; the static site is not
deployed. Earlier entries below are historical.

## Phase 3C: economic outlook, 27 October 2026

`/economic-outlook`: an economic pulse of the latest verified Stats NZ indicators, the institutional research feed,
forecast comparison and a detail page per summary. **With the shipped settings no research is shown**: every source's
`public_display` is `none` and the research API is off (`NZSTATS_PUBLIC_RESEARCH` unset), so the page shows the pulse and
an explanation. Spec: [2026-10-27-phase-3c-economic-outlook-design.md](superpowers/specs/2026-10-27-phase-3c-economic-outlook-design.md).
Plan: [2026-10-27-phase-3c-economic-outlook.md](superpowers/plans/2026-10-27-phase-3c-economic-outlook.md). Runbook:
[data-sources/research.md](data-sources/research.md#public-display-and-the-economic-outlook-phase-3c).

- **Permissions**: public display is a third, recorded decision per source (`public_display` none, link_only, summary,
  excerpt, with its own approver, date and note), separate from fetching and LLM processing; then per summary, human
  review (3B) and a separate publish/withdraw log (migration 007, append-only). No source setting changed.
- **One gate** (`research/public.py`), re-run on every request: states, newest summary of the current non-duplicate
  version, current registry display level, the crawler's URL policy for the document link, and re-verification with the
  current verifier (missing, changed or injection-like sections fail closed). AI text drops to link-only while the
  source's LLM permission would not allow the model that wrote it.
- **API** (`research/api.py`): feed (search, filters, sort, pagination, facets), detail and forecasts; allowlist models;
  read-only connection; registry reread per request (unreadable means nothing is shown); 404 like an unknown path while
  off. Wired by `cli.py` only, so the snapshot exporter cannot serve it; OpenAPI changes are additions only.
- **Comparison** (`research/compare.py`): grouped only by indicator, unit, statistical basis, horizon and kind (central or
  the same named scenario). Ambiguous GDP growth wording, relative horizons, missing units and direction-only claims are
  listed with a reason. The official CPI annual change is drawn as a reference beside CPI groups only.
- **Frontend**: Outlook is a primary destination. Charts use the dataviz-validated navy (forecasts) and amber (official
  observation) pair; validator results: light `#2b66a8,#c75f0c` and dark `#4a8ccb,#d47a36` pass every check (worst CVD
  delta E 21.8 light, 21.0 dark). A grey reference colour failed the chroma and normal-vision checks and was not used.
- **Found and fixed during the work**: string comparison of display levels ("excerpt" < "link_only"); the automated
  security review found that the public URL check missed traversal and encoded or case-folded blocked paths, and that a
  hosted model's text survived a change to local-only permission (both fixed with tests); a data directory with `?`,
  `#` or `%` could change the read-only SQLite URI; the observation label collided with axis ticks; link-only entries
  showed AI processing badges.

### Verification

| Command | Outcome |
|---|---|
| `cd backend && pytest` | **2012 passed** (142 new; main's 1870 pass, two `serve` test stubs updated to accept and check the new `routers` argument) |
| `ruff check .` / `ruff format --check .` | Passed |
| `cd frontend && npm test` / `npm run typecheck` / `npm run build` | 416 passed (42 files; 33 new) / passed / built |
| `npm run gen:api` | `schema.d.ts` gains the research models and routes; no existing type changed |
| `npx playwright test` (live app, research off) | 108 passed (15 new) |
| `npx playwright test -c playwright.research.config.ts` (SYNTHETIC published research) | 15 passed at desktop 1440, tablet 768 and mobile 390; with `OUTLOOK_SCREENSHOTS=dir` the 3 screenshot captures run too (18 passed) |
| `scripts/e2e_static.sh` (static site incl. visual parity of `/economic-outlook`) | 252 passed, 3 skipped (the API-only check) |
| Snapshot exported from a database holding published synthetic research, with `NZSTATS_PUBLIC_RESEARCH=1` | 60 files, no research content (`grep` for research, synthetic and institution keys finds nothing) |
| Visual review (light and dark, three sizes) | `docs/screenshots/phase-3c/`; no horizontal scroll at any size |
| Live requests to any research source or LLM provider | **None** |

Limitations: research comparison and feed are exercised only with synthetic data, because no source is approved; there
is no authentication, so the API must stay off on any network-reachable deployment until display permissions exist;
the dot plot starts at zero for every unit, which compresses close levels such as the OCR; the comparison does not equate
"2026/27" with a June or March year; searching re-verifies every published summary per request (fine for tens, not
thousands).

### PR #13 review round 1 (Codex, head b4039c6): statistical basis of forecast comparison

- P2, real vs nominal GDP: `Real GDP, annual average growth` and `Nominal GDP, annual average growth` produced one group key,
  so institutions were compared across different statistics and one measure hid the other as an "earlier vintage". GDP now
  needs a stated price basis (`real` / `nominal`, or constant / current prices) and carries it in the basis, the stable
  group key and the label ("Real terms, annual average change"). "GDP growth" alone is no longer assumed real: it is
  excluded with the reason. Contradictory wording and per-capita, potential and trend measures are excluded too.
- P2, unemployment timing: every percentage was `rate`. Now `rate_average`, `rate_end`, `rate` (a quarter or month, which is
  itself the point in time) and `rate_timing_unstated` (a longer span with no timing, flagged in the note); a peak or trough
  is excluded, and an average and an end-of-period wording together has no basis.
- Same defect class, adjacent indicators: CPI core / underlying / excluding-X / tradables series were grouped with headline
  CPI and contradictory cadence wording silently took one reading; OCR average + end wording took "average". Both now have
  no basis. Other indicators gain the `real_` / `nominal_` prefix when the label states it.
- Group keys and `basis` values changed for GDP and unemployment; the only consumer that branches on a basis is the CPI
  official-observation reference (`annual_change`, unchanged). The synthetic seed now states "real" in the quoted text and
  label; frontend research fixtures were regenerated (the unrelated `cpi.json` regeneration noise was discarded).
- No research permission, gate, registry, snapshot or LLM setting was touched.
- Note: GitHub Actions for b4039c6 never started ("recent account payments have failed or your spending limit needs to be
  increased"), so CI evidence for this PR is local until billing is fixed.

### PR #13 review round 2 (Codex, head 8fa1784): the measure is part of the basis

- P2, net vs gross debt: every `percent_of_gdp` claim became `share_of_gdp`, so `Net core Crown debt` and `Gross Crown debt`
  shared a key. The same gap existed for any indicator that is only a topic (wages, house prices, fiscal balance). Those
  indicators now carry the measure the label names in the basis and group key (`share_of_gdp:net-core-crown-debt`,
  `annual_change:house-prices`); the measure is the label's words minus units, cadence, forecast and price-basis wording,
  and a label naming no measure is excluded. GDP, CPI, OCR and unemployment name one series and are unchanged. The basis
  label shows the measure as plain alphanumeric words only. Different phrasing of one measure still groups ("Net core Crown
  debt (% of GDP)"); a differently worded but equivalent measure does not, which is the conservative direction.
- Tightened in the same round: government debt must say net or gross (exactly once; `Crown debt`, `Core Crown debt` and
  `Net and gross Crown debt` are excluded, and core vs total Crown stays in the key); a fiscal-balance label made only of
  `fiscal`/`budget`/`balance`/`surplus`/`deficit` is excluded (OBEGAL, operating and cash balance stay separate groups);
  a tenor ("2 year", "90-day") is one token of the measure so `2 year` and `2 month` never meet. Interest-rate levels
  were already excluded (no stated change basis); a test now pins that. Wages, house prices and employment keep the
  measure-in-key rule only: the label does not let us say more, and unequal wording is never grouped.

## Phase 3B: evidence-grounded LLM economic intelligence, 26 October 2026

Structured summaries (outlook, drivers, risks, uncertainty, indicators) and explicit forecast claims for stored research
document versions, every claim cited to `(version, section, page, verbatim quote)`, verified deterministically and
gated by human review. **Disabled by default**: no provider is configured and every source has
`llm_processing = "denied"`. Plan (revised): [2026-10-25-phase-3b-llm-summaries.md](superpowers/plans/2026-10-25-phase-3b-llm-summaries.md).
Runbook: [data-sources/research.md](data-sources/research.md#llm-summaries-and-forecast-claims-phase-3b).

- **Permission**: per-source `llm_processing = denied | local_only | hosted` with a required note; anything but
  `denied` needs an approved `full_text` source. Only a loopback base URL counts as local.
- **Providers**: Anthropic Messages (`anthropic-version: 2026-10-21`; no sampling parameters, which that version
  rejects) and an OpenAI-compatible `/chat/completions` adapter (OpenAI or a local server), both over httpx with no
  vendor SDK, so dependencies and the Docker image are unchanged. A deterministic `FakeProvider` for tests and
  evaluation cannot be selected by configuration.
- **Limits**: input cap (a longer document is refused, never truncated), output tokens, timeout, bounded retries with
  backoff, per-run budget checked against the worst-case cost of every call, documents per run. Failed calls are
  charged with reported usage, or at worst case unless rejected before generation.
- **Verifier** (`research/verify.py`, `verify-2`): 26 error and warning rules, each with a test that fails when the rule
  is removed (checked by disabling each rule in turn). Every report carries the scope statement that passing is not a
  check of economic accuracy. Prompt-injection regressions: injected text stays inside random-boundary delimiters, and
  outputs that obey it (invented quote, verbatim instruction as evidence, another version) fail.
- **Storage** (migration `006_research_summaries.sql`): runs, append-only summaries (idempotent key: version, provider,
  model, prompt and processing version, input hash, attempt), claims for verified summaries, usage per call, review
  log; triggers enforce immutability, approve-verified-only and final rejection. Rollback script for 006; the full
  research rollback drops 006 first.
- **CLI**: `research summarise [KEY] [--version ID] [--limit N] [--dry-run]`, `summaries`, `summary ID`,
  `approve ID --reviewer`, `reject ID --reviewer --note`. Output is escaped line by line.
- **Found and fixed during the work**: a fabricated quote containing the number supported a value (now only found
  quotes count); a value quoted as the previous forecast ("down from 2.5% previously") passed (`superseded_value`);
  clause offsets drifted after ", and"; "43.1% of GDP" passed as plain percent. The automated security review found two
  more, both fixed with tests: truncated or refused responses were charged as free against the budget, and the unit
  field was printed without escaping.

### Model quality evaluation (replay, prompt `outlook-v2`, verifier `verify-2`)

Twelve synthetic, hand-annotated cases in `backend/tests/research/eval_set/` (OCR path, annual versus quarterly CPI,
June-year versus calendar-year GDP and debt for 2026/27, central and scenario forecasts, a historical outturn beside the
forecast, a forecast revised across two versions, paged PDF, OCR-scanned text, fractions and separators, prompt
injection, a relative horizon, a narrative outlook). 13 simulated model outputs and 29 labelled probes.
`python ../scripts/evaluate_research_llm.py` from `backend/`.

**This is a replay of hand-written simulated outputs. It measures the parsing, verification, gating and metric code,
not a real model.** No live provider was run: none is configured or approved, and running one costs money.

| Metric | Value |
|---|---|
| Forecast precision / recall, raw model output | 0.909 / 0.909 (20 of 22) |
| Forecast precision / recall, accepted after the verifier gate | 0.941 / 0.727 (16 of 17; 16 of 22) |
| Numerical fidelity (aligned claims with the gold value and unit) | 0.950 |
| Scenario versus baseline (aligned claims) | 1.000 |
| Indicator classification precision / recall / F1 | 0.941 / 0.941 / 0.941 |
| Citation correctness (evidence references without a reference error) | 0.953 |
| Summary completeness (gold key points covered) | 0.870 |
| Items with a verifier error | 0.105 |
| Model outputs passing verification | 10 of 13 |
| Planted errors detected / clean probes wrongly rejected | 29 of 29 as labelled (detection 1.000, false rejection 0.000) |
| Mean tokens per synthetic document (estimated, 3 characters per token) | 1,957 input, 299 output |
| Mean cost per synthetic document (estimate) | Opus 5.5 $0.0138, Sonnet 5.5 $0.0069, Haiku 5.5 $0.0003 |
| Latency | not measured (replay) |

What the numbers show: the gate trades recall for precision. One wrong claim (an outturn reported as a forecast, a
missing unit, a tidied OCR quote) rejects the whole summary, so three summaries and their correct claims were dropped.
Limitations: the set is small and synthetic and the simulated outputs were written by the same author as the gold
labels; a misclassified indicator whose keywords overlap (a current-account *deficit* filed as the fiscal balance)
passes; recall misses are invisible to the verifier; OCR noise causes false rejection when a model tidies the quote;
real report tables are not represented. The replay metrics are regression floors (`RECORDED_BASELINE`).

### Verification

| Command | Outcome |
|---|---|
| `cd backend && pytest` | **1713 passed** (188 new; the 1525 on `main` pass unchanged) |
| `ruff check .` / `ruff format --check .` | Passed (202 files) |
| `cd frontend && npm test` / `npm run typecheck` / `npm run build` | 383 passed (38 files) / passed / built (frontend unchanged) |
| `npm run gen:api` | `src/api/schema.d.ts` regenerated with **no diff**: the OpenAPI contract is unchanged |
| `npx playwright test` (live app) | 93 passed |
| `scripts/e2e_static.sh` (static site incl. visual parity) | 234 passed |
| Real database copy (schema 5), exported with `main` and with this branch | Same `snapshot_id` (`945d201a29c4`); 213 of 216 files byte-identical, the other three differ only in `generated_at`; `validate-snapshot --for-publish` **valid** |
| Clean Python 3.12 venv, `pip install 'backend[research]'` | Installs; `research summarise` refuses with no provider (exit 1); migration 6 applies; no new dependency (`pyproject.toml` and Dockerfiles unchanged from `main`) |
| Docker image build and `scripts/smoke_docker.sh` | **Not run: the Docker daemon is not running here.** The smoke script now also checks that `research summarise` refuses and `research summaries` runs in the image |
| Live requests to any research source or LLM provider | **None.** Provider tests use `httpx.MockTransport`; the pipeline and evaluation use `FakeProvider` |

## Phase 3A: economic research source foundation, 26 October 2026

A separate research domain for commentary from RBNZ, the Treasury, banks and consultancies. Stats NZ ingestion, the API,
the schema of existing tables and the public snapshot are unchanged. Assessment (with verified source evidence and
implementation notes): [2026-10-25-phase-3a-research-sources-assessment.md](superpowers/specs/2026-10-25-phase-3a-research-sources-assessment.md).
Plan: [2026-10-25-phase-3a-research-sources.md](superpowers/plans/2026-10-25-phase-3a-research-sources.md). Runbook:
[data-sources/research.md](data-sources/research.md). Next: [Phase 3B plan](superpowers/plans/2026-10-25-phase-3b-llm-summaries.md).

- **Registry** (`config/research_sources.toml`): all ten institutions, with hosts, landing pages, discovery mechanism,
  polling, licence and evidence grades. Approval fails closed (approver, date, note; `full_text` needs terms read directly).
  **No source is approved**: RBNZ is `restricted`, the other nine are `needs_review`, four with content policy `none`.
- **Fetching**: `ResearchFetcher` over the shared `Fetcher`, with two opt-in hooks that leave the Stats NZ path unchanged:
  a response cap (decoded size, so gzip bombs count) and a per-hop URL check. Every URL and redirect hop must be https,
  on an allowed host and path, resolve only to public addresses, and pass that host's robots.txt. Each institution has its
  own pacer file and cooldown; the 10 s minimum spacing applies.
- **Discovery** (RSS/Atom, sitemaps, listing links), **extraction** (stdlib HTML parser; `pypdf` in a resource-limited
  child process, one section per page), **validation** (walls, challenges, too short, truncated versus previous) and
  **storage** (migration `004_research.sql`: publications, versions, sections, runs, items, health; one transaction per
  document; reverts reuse versions; duplicates linked).
- **Phase 3B contract** (`research/contract.py`): strict output models and `verify_summary`. No LLM is called; only
  `DisabledProvider` exists, and no vendor SDK is imported anywhere.
- **CLI**: `nzstats research sources|discover|ingest|status` (also through `scripts/run.sh research …`).
- **Fixtures are synthetic** (`SYNTHETIC FIXTURE`), a stated deviation from "real excerpts": the reports are not CC BY, so
  their text is not committed.
- **Found and fixed**: `validate_snapshot` crashed with `KeyError` on a manifest entry of unknown kind (a stray
  `research/x.json`). It now reports an error. Three automated security-review findings were fixed with regression
  tests: PDF parsing moved out of process; the child's output is bounded; DTDs are refused after decoding, not only by
  byte pattern (a UTF-16 DOCTYPE got past the first version).
- **Side effect noticed**: `npm run gen:api` builds the app on `backend/data` and migrated that empty development database
  to schema 4. The real database (`data/nzstats.db`) was never opened for writing: it is still at schema 1–3.

| Command | Outcome |
|---|---|
| `cd backend && pytest` | **1348 passed** (267 new; the 1081 existing tests pass, one updated earlier in `3117d42` to derive the schema version instead of hard-coding 3) |
| `ruff check .` / `ruff format --check .` | Passed (189 files) |
| `cd frontend && npm test` / `npm run typecheck` / `npm run build` | 383 passed (38 files) / passed / built (frontend unchanged) |
| `npm run gen:api` | `src/api/schema.d.ts` regenerated with **no diff**: the OpenAPI contract is unchanged |
| `npx playwright test` (live app) | 93 passed |
| `scripts/e2e_static.sh` (static site incl. visual parity) | 234 passed |
| Real database copy: `export-snapshot` then `validate-snapshot --for-publish` | 216 files, 3.14 MB, 43 published releases, origin production, **valid** |
| Same copy exported with `main` and with this branch | Same `snapshot_id` (`13e4c7cff0e9…`); 214 of 216 files byte-identical, the other two differ only in `generated_at` |
| Live requests to any research source | **None.** All research tests use `httpx.MockTransport`; no source is approved |
| Docker image builds | **Not run: no container runtime here.** The image now installs the `research` extra and sets `NZSTATS_RESEARCH_SOURCES_FILE`; `scripts/smoke_docker.sh` checks both. CI could not run (see below) |

Review round 1 (27 findings reviewed; Codex was unavailable, so an independent Claude security reviewer and the automated
security hook were used). Fixed with regression tests: decompression-bomb memory (peak 616 MB to under 20 MB) and
truncated compressed bodies; DNS rebinding (connection pinned to the checked address, no proxy); NAT64, 6to4,
IPv4-compatible and site-local addresses; percent-encoded, case and `//` bypasses of blocked prefixes and robots rules;
redirects that replaced a document with another page; run-aborting inputs (deep JSON-LD, malformed URLs, unknown XML
encoding or charset, out-of-range dates, extractor errors); NaN crawl delay, non-positive limits and `--limit -1`;
approval without terms evidence; the registry file and `pypdf` missing from the Docker image; the PDF child's inherited
environment. Left for later (minor, documented or latent): purge command for revoked sources, read-only `status`,
`duplicate_of_id` never cleared, challenge-page cooldown not persisted, `captcha` heuristic, candidate ordering,
cross-host redirects between two allowlisted hosts, owner-password PDFs.

Review round 2 (of the round-1 fixes) found two regressions and several gaps, all fixed with tests: unbounded buffering of
bytes after the end of a compressed stream (and a silently ignored second gzip member), robots query-string rules failing
open after canonicalisation, non-ASCII and `%2F` path forms, raw deflate, multicast and IPv4-translated addresses, raw
exceptions from malformed registry numbers, cosmetic-redirect false positives, and error statuses hidden by odd bodies.
Still open and minor: a redirected candidate uses a per-run slot every run, no total read deadline on a trickling body, a
refused pin is retried before failing, and the PDF child's startup failures are reported as limit errors.

Review round 3 (Codex on PR #11, eight findings) fixed with regression tests: the raw-deflate fallback is one-shot (invalid
bytes such as `07 00` no longer loop forever while holding the pacing lock); oversized 403/429/5xx responses are still
classified (block cooldown, Retry-After, retry) without reading the body; a challenge page found by validation (HTTP 200)
now starts the institution cooldown for this fetcher and, through the pacer, for other processes; discovery resolves
relative links against the final URL after redirects; a batch longer than `max_documents_per_run` rotates (never-attempted
reports first, then least recently attempted, from `research_run_item`; the cap and `--limit` still apply and every fetched
report is still revision-checked); the three publication date columns change together; and `duplicate_of_id` is cleared when
a publication gets its own version. The percent-encoded robots finding was already fixed by the round-2 canonicalisation
and now has explicit tests. Three round-1 "left for later" items (`duplicate_of_id`, challenge cooldown, candidate ordering) are
therefore closed.

Review round 4 (Codex on `508b213`): a raw-deflate stream split after its first byte was rejected because the fallback only
applied within the first chunk; undecided leading bytes are now replayed into the headerless decoder (fixed, tested at every
split point). A duplicate recorded only the original's publication, so revising the original changed what the duplicate
matched; additive migration `005` stores the exact matched version (`duplicate_of_version_id`) and the rollback script drops it
with the other research tables.

Review round 5 (Codex on `b9aaef9`): robots wildcard rules were translated to a regex and a hostile `robots.txt` could make
repeated `*` backtrack exponentially (a 25-wildcard rule hung the matcher); they are now matched segment by segment, with the
old regex kept as a test oracle. An HTTP 200 challenge page on an HTML listing with no links counted as an empty successful
listing; it is now a block (cooldown published, run ends `blocked`), and any block seen during discovery, including a 403 on
the listing, ends the run `blocked` instead of `failed`.

Before Phase 3B: approve at least one `full_text` source (the Treasury is the likeliest; read its licence page directly and
run `research discover treasury`), ingest real documents, decide whether any
source's terms allow sending its text to an LLM provider. Details in the Phase 3B plan.

## Public static site on Netlify, 24 October 2026

Adds a second, optional delivery path; the Docker app, ingestion, adapters, validation, scheduling, schema, revision
semantics and every calculation are unchanged. Design and audit:
[2026-10-24-netlify-static-publication.md](superpowers/specs/2026-10-24-netlify-static-publication.md). Operator guide:
[netlify-deployment.md](netlify-deployment.md). **Nothing is deployed; the publisher is disabled until `PUBLISH_ENABLED=1`.**

- Backend `nzstats.publish`: `export-snapshot` (runs this API in process over a read-only database copy, so every number is
  the API's own), `validate-snapshot`, `snapshot-id`, `check-site`, `publish-site`. Reconciles each point with the
  database, vets `unavailable_reason`, restricts source links to https stats.govt.nz, scans for leaks, refuses fixtures.
- Fixture provenance is a `FIXTURE_DATA` file plus SQLite `user_version` set by any runtime with an injected fetcher
  (content cannot tell: the ECT and CPI fixtures are byte-identical to real downloads, found by checking the real DB).
- Frontend: `vite build --mode static` reads the snapshot through an adapter answering the same URLs (calendar windowing
  and release filters in the browser, manifest/snapshot consistency, unavailable state). Last-updated strip, canonical
  share links, per-route titles, build-time page metadata (title, description, canonical, Open Graph, JSON-LD, sitemap,
  robots), neutral noindex shell for dynamic addresses, snapshot-aware Health and empty-state copy.
- `netlify.toml`: explicit client routes (real 404 elsewhere), CSP and security headers, cache rules. Checked against
  Netlify's own local dev server (netlify-cli 24.11.3) as well as `scripts/serve_static.py`.
- Real local database exported read-only: 216 files, 3.1 MB, 43 published releases, valid with `--for-publish`; site built
  from it passes `check-site` in production mode; Lighthouse (mobile) accessibility 99, best practices 100, SEO 100.
- Found and fixed from review: ingestion error text reachable through `unavailable_reason`; fixture flag only in a file;
  `PUBLISH_ENABLED` only in the shell script; token visible to the build; `$` replacement patterns in page metadata;
  publisher state advanced before the live check; shared manifest request carrying one caller's abort signal.
- Decisions: favicon replaced (it was the Vite scaffold logo); one share card, no per-story images; release analysis
  pages are not indexed.

| Command | Outcome |
|---|---|
| `cd backend && pytest` | 1073 passed (999 before; 74 new in `tests/publish`) |
| `ruff check .` / `ruff format --check .` | Passed |
| `cd frontend && npm test` | 383 passed (38 files; 332 before) |
| `npm run typecheck` / `npm run lint` / `npm run build` / `npm audit` | Passed; lint shows only the existing vendor warnings; 0 vulnerabilities |
| `npx playwright test` (live app, existing suite) | 93 passed; one mobile timing flake seen once in a heavily loaded run, 12/12 on repeat |
| `scripts/e2e_static.sh` (static site: all existing specs plus routing, network, security/CSP, export, stamp and live-versus-static parity at 3 viewports) | 233 passed first run; parity then tightened to 0.05% and 24/24 passed |
| Docker image builds (`Dockerfile`, `Dockerfile.publisher`) | **Not run here: no container runtime on this machine.** `Dockerfile` is unchanged; CI builds both |
| Real Netlify deploy | **Not run, by design.** First deploy is a draft deploy per the runbook |

## Visual stories 2.0, 24 October 2026

Frontend only: no change to ingestion, adapters, validation, scheduling, schema, revision semantics or API contracts.
Audit, decisions and limitations: [visual-stories-v2.md](superpowers/specs/visual-stories-v2.md).

- Display face (Geist, already installed) for headlines and key figures; Plex for reading text. Feature and sunken
  surfaces, category rules from the validated chart colours (no new chart colours), muted text darkened to about 5.6:1
  on tinted surfaces.
- Homepage: masthead, economy at a glance (`Story.glance`, built by the CPI, ECT and migration builders), art-directed
  lead, varied story collection (`arrangeCollection`), topic entrances, grouped indicators behind a disclosure, then
  releases and data quality. The duplicate net-migration trend chart left the homepage.
- `StoryGraphic` replaces the unlabelled thumbnails: line, signed columns, diverging bars and pair/dumbbell, labelled
  with published values at true pixel size, with text alternatives.
- Navigation: Home, Stories, "Explore data" disclosure (Menu on phones); footer lists every page.
- Story pages: key-term explainers, record band, related stories, previous/next; remount per story so a chart variant
  never carries over. Story charts: latest retail month emphasised, tradables end labels with values, migration peak
  labelled "YE".
- Exports: display face for headline, statistic and chart title; landscape dek when it fits whole.
- Glance wording follows the sign of both years: a widening net loss is "Larger than a net loss of ...", never "Up from"
  (found in final diff review, fixed test-first).
- `playwright.config.ts` reads `E2E_PORT` (default 8765); 8765 was held by another local app during this work.

| Command | Outcome |
|---|---|
| Baseline before changes | `npm run build` passed; before screenshots captured from that build |
| `cd frontend && npm test` | 332 passed (31 files) |
| `npm run typecheck` / `npm run lint` / `npm run build` | Passed; lint shows the 3 existing vendor Fast Refresh warnings; existing bundle-size warning |
| `E2E_PORT=8775 npx playwright test` (offline seeded DB) | 93 passed (desktop, tablet, mobile): 81 existing (3 selectors updated for the new homepage) plus 12 new |
| Visual review | Two critique passes, before/after at 390, 768, 1280, 1440 light, 390 and 1440 dark; no horizontal overflow; reduced motion renders identically |
| Backend | Not run: no backend file changed |

## Visual storytelling layer, 23 October 2026

Frontend only: no change to ingestion, adapters, validation, scheduling, schema, revision semantics or API contracts.
Design and decisions: [visual-storytelling-redesign.md](superpowers/specs/visual-storytelling-redesign.md).

- Editorial homepage: masthead, featured story (newest verified release) with its chart, latest stories, then every
  existing panel (KPIs, featured release, trend, upcoming and latest releases, freshness).
- `/stories` feed (category filter in the URL) and `/stories/:id` story pages. Identifiers are `<template>-<period>`;
  an older period resolves to a "superseded" notice, never to newer numbers. A release Stats NZ has published but this
  site has not verified (for example the September 2026 CPI) is called out on the story page.
- Eight deterministic stories from existing payloads: CPI annual inflation, contributions (pp), tradables; ECT retail
  monthly change, industry movements; migration year-ended net, arrivals versus departures, citizenship. Migration
  series are combined only within one release bundle. Builders omit a story when inputs are missing.
- Presentation PNG export at exactly 1200 × 675 and 1200 × 1500 (chart re-rendered off-screen from the on-page option),
  plus share link. Layout is unit-tested for bounds, overlap and never cutting the headline, statistic or source.
- One accent ink token (chart navy; 5.9:1 light, 9.5:1 dark). Chart colours are the previously validated set; none added.
- `formatNumber` no longer signs a value that rounds to zero ("+0.00" beside "0.00" on the contribution chart).
- Fixture drift found, not changed: regenerating fixtures adds the CPI workbook URL to `cpi.json` `sources`
  (backend change from PR #5 round 3). Only the two new citizenship fixtures were committed.

| Command | Outcome |
|---|---|
| Baseline before changes | 163 frontend tests, typecheck, lint (3 vendor warnings), build; backend pytest, ruff, format passed |
| `cd frontend && npm test` | 226 passed |
| `npm run typecheck` / `npm run lint` / `npm run build` | Passed; lint shows the 3 existing vendor Fast Refresh warnings; existing bundle-size warning |
| `npx playwright test` (offline seeded DB) | 81 passed (desktop, tablet, mobile), including PNG dimension and drawn-text checks |
| Backend `pytest`, `ruff check`, `ruff format --check` | 999 passed; ruff and format passed (backend code unchanged) |

### PR #7 review round 1 (Codex, head 6377324)

Five findings, all frontend story builders; each fixed test-first (watched failing, then passing).

- `figures.ts`: contribution horizons are derived from blocks that are available and non-empty, quarterly first; the
  initial selection is always one of them, a stale selection falls back to the first, and a release with neither renders
  an empty labelled figure instead of throwing. The control is hidden when only one horizon exists.
- `cpi.ts`: evidence keys use the persisted `cpi.contrib.q.<slug>` / `cpi.contrib.a.<slug>` (`contributionKey`, checked
  against the keys the API's own analysis cites). The annual contribution the story mentions now has an evidence row.
- `cpi.ts`: direction comes from the displayed headline. Groups with the opposite sign pull against it (positives when
  prices fall); a headline that rounds to zero attributes no direction; contributions that round to zero at two decimals
  are neither. The headline and the annual sentence say "downward" when the change is negative.
- `ect.ts`: rise and fall clauses are built from positively and negatively signed industries only ("was the only
  industry to rise", nothing invented when a group is empty); an all-unchanged month says so.
- `migration.ts`, `common.ts`: release status comes from the matching release summary, with a "Corrected release"
  caveat first so the card badge, source panel and PNG export all carry it. Known limit: with no matching summary (for
  example the overview payload does not list that release) status falls back to `published`.

### PR #7 review round 2 (Codex, head ae84207)

- `ect.ts`: industry evidence rows carry each source point's own status (the August comparison points are `unknown`
  in the real file, not `final`); the story is `provisional` when a latest industry value is.
- `Story.tsx`: the "newer release" notice considers only `published` and `corrected` releases (`lib/releaseStatus.ts`,
  shared with the Calendar), so a past-due `scheduled`, `delayed` or `unavailable` row is never presented as published.
- `useStories.ts`, `Stories.tsx`, `Story.tsx`: a category's stories appear once its own sources settle, and the feed and
  story pages wait only for the category they need. Ready categories render while others load ("Still loading: ..."),
  a deep link to a still-loading category waits instead of saying "not found", and migration stories are held back until
  the release summaries that carry their status have loaded. The homepage still waits for all sources so its featured
  story does not change under the reader.

### PR #7 review round 3 (Codex, head 9eff876)

- `cpi.ts`: contribution evidence rows are `unknown`, as the adapter stores them (`ObsStatus.UNKNOWN`), not `final`.
  Known limit: the index-based evidence rows (annual, tradables) still say `final`; the API exposes a status only for
  the reference period, so earlier periods cannot be checked from the payload.
- `cpi.ts`: the annual and tradables deks follow the sign of each displayed rate ("0.5% lower", "fell 1.1%",
  "were unchanged") instead of assuming a rise.
- `migration.ts`: a zero net year reads "Arrivals and departures were balanced", and a zero year earlier reads
  "no net change", not "a no net change".
- `StoryExport.tsx`, `exportLayout.ts`: the PNG attributes the dashboard at the story address (it printed the Stats NZ
  page there) and cites the release page in the source line.
- Not changed, deliberately: the homepage lead (`Overview.tsx`) still waits for every story source. Its featured story
  is "the newest verified release", so showing it before a slower category settles could present an older release as
  the newest and then swap it. The rest of the homepage does not wait.

### PR #7 review round 4 (Codex, head c63c739)

- `migration.ts`: each story takes its provenance, release status and bundle from its own series. A citizenship pair
  that comes from an earlier release (the latest omitted the chart) is built and labelled with that release instead of
  being dropped; arrivals and departures, and net with citizenship, are still combined only within one bundle.
- `Story.tsx`, `useStories.ts`: a story page whose category failed to load shows an error with a retry (failed requests
  only), not "Story not found". The newer-release notice also ignores releases already ingested here (`has_analysis`),
  so it never says "not verified" about data the site holds.

Round 1 verified locally: `npm test` 256 passed (30 new), `typecheck`, `lint` (same 3 vendor warnings), `build`, Playwright 81
passed; backend `pytest` 999 passed, `ruff check` and `ruff format --check` clean (backend unchanged).
Round 2: `npm test` 269 passed, `typecheck`, `lint`, `build`, Playwright 81 passed.
Round 3: `npm test` 279 passed, `typecheck`, `lint`, `build`, Playwright 81 passed.
Round 4: `npm test` 286 passed, `typecheck`, `lint`, `build`, Playwright 81 passed.

## CPI September 2026 release-day failure, 22 October 2026

PR #5 merged at 14:46 NZDT; the September quarter release (10:45 NZDT) had already failed ingestion on every attempt since 11:24 NZDT
(runs 4 to 14, `layout_changed`, "CPI percentage chart rows are missing or renamed"; release `published`, no CPI vintages stored).
**Root cause (confirmed by offline reproduction on the stored September artifacts):** the quarterly percentage chart's CSV header
starts with `Category` instead of `Quarter`, and `CpiAdapter._reconcile` skipped every chart not starting with `Quarter,`, so the
quarterly row was never found. Not a scheduling, deployment, access or upstream-data problem: calendar discovery, polling, fetching
(HTTP 200 for the page, three CSVs and the workbook) and the CSV parser all worked, and with only that header cell patched the whole
bundle parses and reconciles (74 series). A running `nzstats serve` (started 18:46 NZDT from this checkout, scheduler on) retried the
release at startup and failed identically.

Fix (branch `fix/cpi-september-chart-header`): percentage rows are matched by row label only; row width, quarter labels and values are
still checked. Regression tests failed first (7 failures against the unfixed adapter, all passing after): `tests/adapters/test_cpi_parse.py`
(real September page and files; official 0.7 / 3.7 reconciliation; renamed header on the June page; a wrong rate under the new header
still fails as `validation_failed`) and `tests/pipeline/test_cpi_september_2026.py` (June then September through ingestion, API and
health; idempotent re-ingest; a failed September leaves June served; a missing workbook never blocks the headline). New fixtures
`cpi_2026-09_*` come from the artifacts already stored locally (no new Stats NZ request). **Live September ingestion into the running
database has not been performed**; see the recovery steps in [cpi-release-runbook.md](cpi-release-runbook.md).

## Phase 2B — CPI and inflation, 19 October 2026

Implemented the CPI adapter, validation, API, release analysis and `/inflation` dashboard on `feat/phase-2b-cpi`, with Overview, Latest Releases,
Calendar and Data health integration. Verified against real December 2025, March 2026 and June 2026 releases (benchmarks 1.5/4.1, 2.7/4.9,
0.6/3.4 reconcile). Offline release-day rehearsal passes. **The September 2026 quarter release (22 October 2026) has not been ingested.**
Verification: 965 backend tests, 163 frontend tests and 48 Playwright checks passed; Ruff, TypeScript, lint and build passed
(re-run after the PR #5 review round below).
Details, decisions, limitations: [phase-2b-cpi.md](phase-2b-cpi.md); operation and fallback: [cpi-release-runbook.md](cpi-release-runbook.md).

### PR #5 review round 1, 21 October 2026

- #4312128553 (P2): `_underlying()` let NaN/infinity from the optional workbook through (`abs(nan - x) > tol` is False, so the
  reconciliation did not reject it) and the general validator then failed the whole bundle. The optional boundary now validates the
  returned tables (series set, quarter-end periods, finite numeric values, history, reconciliation that fails closed on NaN) and
  drops the optional series with a warning. Malformed tables that used to raise (empty series, missing series) are covered too.
- #4312128556 (P2): a workbook arriving after the first ingestion changed the bundle digest, so every series got new vintages and
  the release became `corrected`. Required series are now compared independently of optional ones, in both directions.
  Enrichment adds only the optional vintages under the stored bundle identity and leaves status alone.
- Round 2 findings on `8be4ce5` (automatic review, so no manual trigger): #4334244713 (P2) the digest fast path returned a bare
  `unchanged`, hiding an optional failure after enrichment (an enriched bundle keeps its required-only digest); it now returns the
  optional warnings, which the ingest run records. #4334244723 (P2) series `source_url` came from the first listed download while
  ingestion fetches the `-corrected` one; `pick_downloads` moved to `sources/release_page.py` and the adapter uses it, so the
  cited file is the one the values came from. Neither changes a statistic or a bundle digest (source URLs are not part of identity).
- Round 3 finding on `6a4cba8`: #4334350633 (P2) underlying series had no `source_url`, so the workbook (or a corrected workbook)
  never appeared in the dashboard sources. The adapter now resolves the workbook with the same corrected-file precedence and
  stores it on those definitions. As with the CSVs, a source URL change alone (identical values) is not a new bundle.
- Round 4 findings on `f8f3985` (both in earlier branch code, found by the whole-PR review): #4334468788 (P2) a published-percentage
  row that was narrower than its header, or blank at the reference quarter, was silently accepted because `zip(strict=False)` dropped
  the cell while the row still counted as present, so the newest index value went unreconciled. Rows must now match the header width
  and carry a value for the reference quarter, otherwise the release is rejected as a layout change. #4334468798 (P2) correction
  rows formatted every value with zero decimals, so 1359.64 -> 1359.92 read 1,360 -> 1,360; CPI corrections now use index 2 dp,
  percentage points 3 dp, percent 1 dp (other categories are unchanged).
- Round 5 finding on `9b9e190`: #4334565185 (P2) CPI's annual and quarterly all-groups headline metrics share one `series_key`, which
  `ReleaseAnalysis.tsx` used as the React key for the KPI cards and metric rows (duplicate sibling keys). Both sites now use a
  composite series-key and label key. This is the fifth and last automatic fix cycle allowed in this session.
- Tests (failed first): workbook NaN/inf/-inf/1e999 (including a real rewritten xlsx cell) and structural cases; recovery, loss, true
  correction, reverted correction, enrichment after a correction, a revised optional measure, a simulated concurrent enrichment, and a
  dashboard API check. The September 2026 release (22 October 2026, 10:45 NZDT) remains un-ingested.

## PR #3 — ECT publication coverage remediation, 18 October 2026

Review findings #4305426410 and #4305426414 share incomplete coverage validation. Quarterly
mandatory indicators are now required even when no ECTQ rows exist. Every previously observed
supported series must remain present, and its previously published periods must be retained.
The check covers historical, intermediate and latest periods while allowing numerical revisions.
ECT coverage comparisons include the latest stored vintage of the same publication for corrected
re-ingestion; historical backfills still exclude later publications. Migration keeps its existing
strictly earlier-publication comparison. No current-month quarter-end requirement was introduced.

The existing uncommitted empty-quarterly regression was preserved and observed failing first.
Official-fixture pipeline regressions also reproduced acceptance of absent quarterly data, missing
optional series and lost latest periods before the fix. The matrix exercises complete fixtures,
missing mandatory series, first/latest/intermediate observations, incompatible metadata, valid
quarterly numerical corrections, idempotent re-ingestion, monthly publication without a new quarter,
new quarterly coverage and out-of-order backfill. Failed ingestion leaves existing series, vintages,
observations and vintage measurement definitions unchanged; raw failed-download artifacts remain
available for audit. An independent diff review found no actionable correctness defects.

Verification: **720 backend tests**, **129 frontend tests** and **42 Playwright checks** passed.
Ruff lint/format, TypeScript, frontend lint, production build and `git diff --check` passed.
The existing TestClient deprecation, three UI Fast Refresh warnings and bundle-size warning remain.

## PR #3 — Follow-up review findings, 18 October 2026

The new-commit automatic Codex review of `891a759` is counted as review round 1 of this
remediation's two-round limit. Its two P2 findings were reproduced with failing tests:

- #4306413400: the first ingestion had no prior vintage, so retained-period checks alone could
  accept stale quarterly series. Quarterly series must now reach the latest completed quarter
  implied by the reference month (including December for January/February). Official August
  and September archive regressions and all twelve month boundaries cover this contract.
  First-ingestion pipeline tests verify stale or absent quarterly data cannot create vintages.
- #4306413404: historical correction rows selected the latest publication's metadata. They now
  use the compared bundle's retained definition, or the previous bundle's for a withdrawn series.
  Two migration-fixture regressions cover corrected and withdrawn historical series viewed
  after a newer publication changes its label and unit. Numerical compatibility checks remain.

Independent review of the follow-up diff found no actionable blockers. Final local verification:
**738 backend tests** and **42 Playwright checks** passed; Ruff lint/format and diff checks passed.
Frontend code is unchanged from the preceding 129-test/type/lint/build verification. Exact-HEAD
CI/review results are recorded in the PR; no merge or deployment was performed.

## Phase 2A — Electronic Card Transactions, 18 October 2026

Implemented the ECT adapter through the existing registry, ingestion transaction, raw artifact store,
health projection and calendar-aware scheduler. Added bounded ZIP/CSV parsing, strict measurement
metadata and structural validation, embedded-chart/percentage reconciliation, and scoped CLI backfill
(`--series-slug`, `--until`). No new runtime dependencies or other Phase 2 categories.

Controlled live verification ingested official August and September releases into the local ignored
database. September exposes **96 series**, **288 adjusted retail months**, **321 actual retail months**,
**96 adjusted retail quarters**, and **110 genuinely revised retail observations** against August.
All requested September benchmarks reconcile within documented source rounding tolerances.
[Official source verification, reconciliation table and limitations](data-sources/ect.md).

Migration 003 snapshots measurement definitions per vintage. Series, bundle, API and revision reads
follow retained metadata; incompatible comparisons are withheld. Existing migration calculations are
preserved. Old test fixtures that delete vintages now also remove their dependent metadata, and
concurrent-migration tests expect schema 3.

The `/electronic-card-transactions` page includes compact KPIs, monthly/quarterly spending histories,
actual/adjusted/trend and group controls, 1/3/5-year/full ranges, signed industry rankings, actual
industry composition, evidence-linked findings, source/methodology notes and CSV/PNG exports.
Overview, navigation, release analysis, calendar links and data health recognise ECT.
Every dashboard series is read from one release bundle. Chart colours reuse the previously validated
palette; signed labels and a zero line distinguish industry movements. Desktop/tablet/mobile layouts
were inspected through Playwright screenshots; the history axis keeps readable year labels.

Verification (offline fixtures except the deliberate paced source check):

| Command | Outcome |
|---|---|
| `cd backend && .venv/bin/pytest` | 691 passed; migration regression suite included |
| `cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .` | Passed |
| `cd frontend && npm test` | 129 passed |
| `npm run typecheck` | Passed |
| `npm run lint` | Passed; three existing Fast Refresh export warnings in vendor UI components |
| `npm run build` | Passed; existing ECharts bundle-size warning |
| `npx playwright test` (venv on PATH; isolated E2E data directory) | 42 passed: desktop, tablet, mobile |
| `python scripts/dump_frontend_fixtures.py --ect-only` | Passed; official fixture data regenerated |
| Local live-captured DB/API check | Integrity OK; ECT, release, overview and health endpoints HTTP 200 |
| `git diff --check` | Passed |

Backend checks use local Python 3.14.6. The existing FastAPI/Starlette TestClient deprecation warning
remains. Initial regression failures were stale schema/dependent-fixture assumptions and the old
migration-only freshness assertion; those tests were updated, with focused reruns before final regression.

Changed file groups: `adapters/ect/{adapter,series}.py`; `store/repo.py` and migration 003;
`runtime.py`, `pipeline/ingest.py`, `cli.py`, `catalog.py`; `insights/ect.py` and vintage-aware shared
insights; `api/routes.py`, `models.py` and generated frontend API types; `ElectronicCardTransactions.tsx`,
ECT charts, `Overview.tsx`, `ReleaseAnalysis.tsx`, `App.tsx` and `Layout.tsx`; backend/frontend/browser
tests and captured official fixtures; fixture-generation/seed scripts; README, source registry and plan.

Self-review completed against the request and final diff; no subagents were used. An independent
Python/statistical review is recommended before merging. Before deployment, back up SQLite, rebuild
the image/UI, apply migration 003 on startup and run the existing scheduler. A real Docker-host rollout
and unattended observation of the next publication remain operator checks; neither was performed here.
Post-publication corrections still need explicit re-ingestion. Earlier overwritten definitions cannot
be reconstructed during upgrade; revised `R` source statuses remain conservative `unknown` values.

## Independent audit remediation — 16 October 2026

Remediated all ten Phase 1 audit findings in four logical batches: data integrity (validation,
corrections and statistical identity); reliability (durable pacing and concurrent schema startup); UI
(freshness, uncertainty, calendar and correction presentation); and security/operations (dependency
removal, safe reprocessing and CI). See the
[resolution matrix and full verification report](phase-1-remediation.md) for F01–F10, RED/GREEN evidence,
commands, remaining risks and deployment gaps. Historical records below describe their original state;
the F05/F07 limitations listed on 15 October are superseded by this remediation.

Production-version Python 3.12 verification: **651 backend tests passed**, **96.5% statement coverage**.
Frontend: **120 tests passed**. Browser regressions: **39 passed** across 1440, 768 and 390 px, including
calendar focus restoration, corrections, freshness and uncertainty labels. Typecheck, lint, build and
API/fixture generation passed. The unused shadcn CLI removal reduced `npm audit` from seven high
findings to **zero vulnerabilities**; the app's five CSS variants retain their MIT notice locally.
A fresh final backend/frontend/browser run passed. The
[implementation CI run](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/actions/runs/38833986960)
passed backend, frontend and Docker jobs for `4f68ec2`; see PR #2 checks for subsequent commits.

Replayed the preceding audit's full cached official June/July/August 2026 sources with no external
requests: all **24 headline values** retained; legacy-compatible re-ingestion kept **164 releases,
771 vintages, 29,395 observations** unchanged. Malformed HTTP-200 input retained the last good bundle.
The online backup CLI was checked while an isolated API remained running. Linux CI also passed the offline
Docker named-volume restart/recreation, scheduler startup and backup checks; local Docker execution
remains unavailable because there is no daemon. Production bind-mount ownership and a complete unattended live
publication remain deployment checks. Existing warning classes are unchanged.

Next: review the new remediation PR and its latest-head checks, then obtain a **fresh independent Codex audit**.
No merge, deployment or Phase 2 work is included. Unrelated local launcher/README work is preserved.

## Review completion cycle — 15 October 2026

Continued PR #1 from `3c2ed2b` (CI green, 59 of 61 threads resolved, Codex quota exhausted).

Earlier on 15 October (`2bcb809`..`3c2ed2b`, Codex rounds not recorded above): every derivable rolling
total and the required citizenship series are validated; country totals reconcile for every stored
month; country provisional flags come from the month; truncated calendar envelopes, non-finite standard
errors and a release-month response missing either group are rejected; and a release that reverts to an
earlier bundle (A -> B -> A) reactivates it. That last change adds schema migration
`002_vintage_activation.sql` (`vintage.activation`, backfilled from `id`). "Latest" now orders by
activation, and existing databases migrate on start.

This cycle, each fix has a test that failed first:

1. Concurrent artifact writes (#4280133530). Both writers used `<sha>.tmp`, so the slower `os.replace`
   raised `FileNotFoundError` and recorded a valid ingest as failed. Each writer now uses its own
   `mkstemp` file, and the files keep mode 0644 so host backups can read them.
2. Paired charts mixed bundles (#4280133522). Arrivals/departures and the monthly/year-ended net panels
   combined independently cached series. For example, `mig.ry.net` cached by the Overview before a new
   release could sit next to a fresh `mig.m.net`. All three paired charts now compare release and
   capture time. A mismatch reloads both series once; if it persists, the pair is not combined and the
   page says why.
3. Redirects skipped the crawl delay (independent review). httpx followed redirects inside one pacer
   turn, so the hops went out with no 10 s gap and could leave the host. The fetcher now follows up to
   five same-host hops, each paced, and records the final URL.
4. Blocks stopped only one release (independent review). After a 403 or a challenge page, batch loops
   kept requesting other URLs. The fetcher now refuses every request for 30 minutes. This is per
   process: a CLI run started during the cooldown still makes its first request.
5. The Overview trend title quoted a provisional value with no period or status. It now states both, as
   the Migration charts do.
6. Truncated history passed validation (#4280291084, #4280291091). A monthly file cut to its latest 12
   months, or a year-ended chart left with only its latest column, kept a correct latest value. It passed
   every check and replaced the full history as the live vintage. Real files start in 2001 (monthly
   2001-01, year-ended 2001-12, June and July 2026). A series whose coverage now starts later than its
   previous vintage is a `coverage` error, and the adapter loads the previous vintage of every required
   and optional series. An isolated blank interior cell is still accepted, as decided in rounds 8 and 12.
   Not verified: whether any 2024–2025 release started later than its predecessor; if one did, its
   backfill now fails visibly instead of passing.

Verification: **523 backend** (ruff lint/format clean, 99 files), **115 frontend** (typecheck, build;
lint has the 3 known shadcn warnings), **18 Playwright** (desktop and mobile). Playwright ran on port
8766 through a temporary config because an unrelated local process held 8765. Compose config validates.
There is no local Docker daemon; the GitHub Actions `docker` job builds the image and checks
`/api/health`.

**Live scheduler milestone not verified.** No `nzstats serve` was running on 14 October. Every local
database still shows *International migration: August 2026* as `scheduled`, with no ingest run after
11 October. Stats NZ was not contacted to compensate. As captured on 11 October, the next opportunity is
*September 2026*, scheduled for 12 Nov 2026 10:45 NZDT (confirm in the calendar first).

Known and not changed (independent review, Medium): `_bundle_digest` hashes every chart's title and CSV.
An editorial retitle, or an edit to a chart the adapter does not read, therefore creates a new vintage
with identical values and marks the release `corrected` on the next re-ingest. Values stay correct. The
fix (hashing only the charts the adapter reads) changes every stored digest, which gives each release
one extra vintage once. It needs a decision rather than a quick patch. Also known: 429 `Retry-After` is
ignored (paced retries); explicit `?base=` newer than `compare` returns inverted revisions (the UI never
sends it); no `fsync` before the artifact rename.

## Focused retry, backfill and provenance cycle — 14 October 2026

Continued PR #1 from `93211ff`, preserving the uncommitted fixes already in its
worktree. This is one implementation and review cycle for comments #4255168462,
#4255168469 and #4255168477. The ingestion-health model is unchanged.

- Unresolved `unavailable` releases remain eligible at any age, with at most one
  ingestion attempt per Auckland calendar day. Eligibility uses the job's explicit
  clock and persisted attempts. The minute watcher excludes these releases;
  recovery and rescheduling restore the existing lifecycle behaviour. The blocked
  cooldown, HTTP pacing and network retry handling remain intact.
- Backfill validates inclusive `YYYY-MM` reference-period bounds before any
  request/write; invalid or reversed bounds raise `ValueError`, and missing
  reference periods are excluded. Publication-month discovery scans through the
  current Auckland month (or `until`, if later) to find delayed publications,
  filtering references to the same interval used by ingestion. For example, a
  June-only request discovers June's August publication without fetching July's
  release files. Calendar request failures still appear in the outcome list.
- Country totals, rankings and nullable provenance come from the same selected
  release bundle, including corrections. The API, generated frontend types and
  fixtures agree. Captions show the actual release URL, publication date and
  capture time; CSV adds the period bounds, denominator, series key, release key,
  timestamps, bundle digest and derivation note, retaining formula protection.
- Shared `ChartCard` PNG export composes the chart bitmap with wrapped plain-text
  title, question, source URL, publication date, capture time and caveat. Export
  status is announced accessibly. Wide provenance tables scroll within a named,
  keyboard-accessible region. No upstream HTML is interpreted.
- Baseline reproduction in an isolated archive of `93211ff`: **25 backend and
  4 frontend failures**. Additional failing regressions exposed cold discovery
  of a later publication and table overflow on desktop/mobile; both pass after
  their focused fixes. Added **33 backend cases**, **3 frontend tests** and one
  Playwright scenario running on both viewports.
- Full local verification: **437 backend**, **101 frontend**, **18 Playwright**
  pass. Ruff lint/format (97 files), TypeScript, frontend lint, production build,
  API generation and fixture regeneration pass. Exported mobile PNG visually
  inspected; browser assertions check caption text, bitmap pixels and bounds,
  and downloaded CSV provenance. Existing warnings: Starlette/httpx deprecation,
  three UI Fast Refresh exports, large chart bundle.
- Independent read-only review found no actionable issues across retry frequency,
  boundaries, same-bundle consistency, corrected/withdrawn data, API types and
  PNG/CSV provenance. Publication-month scanning, sparse-file zero rows and the
  nullable contract were checked and retained for the reasons above.
- Local Docker image/startup checks remain unavailable: no daemon. Final-head
  backend/frontend/Docker CI is required before resolving review threads. Remote
  CI and the single final Codex review are recorded on PR #1; this record does
  not claim remote results in advance.

## Focused ingestion-health cycle — 13 October 2026

Continued PR #1 from `e087c40`, with one implementation/verification cycle and no
merge. The [behavioural specification](superpowers/specs/2026-10-13-ingestion-health.md)
was written before the regression tests and implementation.

- `failing_releases()` now ranks meaningful outcomes by run ID after excluding
  neutral observations. Current release status determines whether a 404 is a gap.
- Repository outcome/status writes refresh health, covering discovery publication,
  valid rescheduling and scheduler exhaustion without pipeline imports. Neutral
  observations and status-only recalculation preserve both source timestamps.
- No schema, polling schedule, observations or vintage changes. A successful
  release cannot mask another release's unresolved failure.
- New database/lifecycle suite: **47 failed / 41 passed before**, **88 passed after**.
  Existing published-404 coverage already passed at the starting commit; extended
  coverage confirms published/corrected/unavailable gaps and recovery.
- Full backend: **404 passed**. Ruff lint and format pass (96 files). Frontend:
  **98 passed**, lint/typecheck/build pass; generated API types unchanged.
  Playwright: **16 passed** on desktop/mobile. Compose configuration validates.
- Local Docker build/start unavailable: no daemon. Final-head GitHub Actions must
  supply the container build/start check. Existing non-blocking warnings remain:
  Starlette/httpx deprecation, three UI Fast Refresh exports, large chart bundle.
- Focused independent review found no actionable defects. Final-head CI and the
  single final GitHub Codex review are recorded on PR #1 after push; this local
  verification record does not claim their result in advance.

## Status

| Phase | State |
|---|---|
| Phase 1: core dashboard and International migration | **Built and verified except two items that need a Docker host and a date** (below). Not merged. |
| Phase 2: inflation, labour, GDP, housing, retail and trade, Data Explorer, Revision Explorer, comparisons | Not started |
| Phase 3: deeper release comparison, preferences, report export, optional grounded commentary, audit | Not started (the spec forbids starting before Phase 2 is verified) |

**Not done, so not claimed:**

1. **Docker image build and `docker compose up` have not been run.** The machine used has the Docker CLI and
   Compose 5.3.1 (`docker-compose config` validates the file) but no Docker daemon. The Dockerfile's key steps
   were simulated instead: a clean Python 3.12 venv, `pip install` from a copy containing only `backend/pyproject.toml`
   and `backend/src`, then `nzstats serve --no-scheduler` with the container's environment variables, serving
   `/api/health` (200), `/` (the built SPA) and `/migration` (SPA fallback). The CI `docker` job builds the image
   and checks `/api/health`; the first Docker host must also run the Compose quick start in the README.
2. **Live scheduler check is pending.** The August 2026 release (14 Oct 2026) was missed: no scheduler was
   running (see the 15 October cycle). Next: September 2026, scheduled 12 Nov 2026 10:45 NZDT. To close it: start `nzstats serve` against a data directory with
   history before 10:45 and confirm the release is ingested within the polling window (Data health page or
   `nzstats health`). The scheduler logic itself is unit-tested (offsets, window expiry, catch-up, blocked back-off).

## Verification evidence (2026-10-12, this machine)

| Check | Command | Result |
|---|---|---|
| Backend lint and format | `cd backend && ruff check . && ruff format --check .` | `All checks passed!`, 95 files formatted |
| Backend tests | `cd backend && pytest -o addopts=""` | **313 passed** |
| Frontend types | `cd frontend && npm run typecheck` | clean |
| Frontend tests | `cd frontend && npm test` | **13 files, 98 passed** |
| Frontend build | `cd frontend && npm run build` | built |
| Frontend lint | `npm run lint` (oxlint) | 3 warnings, all in generated `components/ui/*` (fast-refresh exports) |
| End to end | `cd frontend && npx playwright test` (Chromium, desktop 1440x900 and Pixel 7) | **16 passed**: overview, migration charts and CSV download, route reload and JSON 404, release analysis and print, no horizontal scroll on `/`, `/migration`, `/calendar`, `/health` |
| Compose file | `docker-compose config` | valid |
| Container-style install | clean venv, non-editable install, container env vars | health 200, SPA served |

## Real-site integration check (the only step that contacted stats.govt.nz)

Run 2026-10-12 against a scratch data directory, 10 s between requests, User-Agent
`NZStatsDashboard/0.1 (self-hosted)` (no contact address was sent; see rulings).

- `nzstats discover`: 222 releases seen, no errors.
- `nzstats backfill` (2024-06 onward): **first run ingested 17 of 26 releases; 9 failed with `layout_changed`.**
  Nothing was stored for the failures, the other 17 were intact, and Data health showed the errors.
- Root causes, from the stored real pages and files (not guessed):
  1. The adapter found the year-ended charts by title prefix, but editors retitle them from release to release: a
     leading space, "Est migration by citizenship, roll...", "years ended", and in two releases the footnote
     "Estimates from August 2024 onwards are provisional..." typed into the title field. The CSV header ("Year ended")
     plus the series row labels is stable and matched exactly one direction chart on all 26 pages.
  2. The September 2025 page has no year-ended citizenship chart at all.
  3. The June 2024 files repeat identical aggregate rows 2 or 3 times (Sep to Nov 2022). The repeated value equals the
     official chart value (Sep 2022 arrivals 12,561), so exact copies are collapsed; conflicting duplicates still fail.
- Fixes (each with tests that failed first): charts found by content; the citizenship chart is optional (warning, and the
  series gets no vintage from that release); exact duplicate rows collapsed.
- After the fix, the 9 releases were re-ingested from the real site: **all 26 releases from 2024-06 are ingested**;
  source health `ok`; `mig.ry.net` has 26 vintages and `mig.ry.net.nz` has 25 (September 2025 has none, by design).
- Real values were compared with the official July 2026 headline ("net gain of 20,300 (± 1,800) in the July 2026 year,
  compared with 9,600 (± 200)"): stored year-ended net 20,350 and 9,592; arrivals 134,434 minus departures 114,084 =
  20,350; monthly net 5,170 (± 545); provisional starts at 2025-04, 16 months, as Stats NZ labels them. Revisions between
  the June and July 2026 vintages are real (for example April 2026 net: -99 then 44).
- Every one of the 26 releases has an analysis page through the API.

## Chart and design review

- Palette validated with the `dataviz` validator (categorical chart-1 to chart-4): light on `#ffffff` `#2b66a8, #c75f0c,
  #2a8a6c, #7b52b5` and dark on `#1c1917` `#4a8ccb, #d47a36, #3a9c7e, #8e78cf`, all checks pass (worst adjacent
  colour-blind separation 10.2 light and 8.9 dark, which the direct labels and legends cover; normal-vision floor 22.3
  and 20.5). The plan's starting hexes failed and were adjusted within their hue families.
- Overview, Migration, Release analysis, Calendar (list, month, filtered) and Data health were screenshotted on real
  fixture data at 1440 px (light and dark) and 390 px, and print output was checked. Defects found and fixed: lowercase
  months in titles, an awkward revision title, an empty gap on the Overview, x-axis label overlap, mobile horizontal
  overflow (grid min-width and an unwrapped control row), a select showing a raw value, and upcoming releases listed last.
- Per-chart checklist (question, encoding, unit, zero baseline, provisional distinction, latest-point label, source and
  date, caveat, export) passed for all six migration charts; the country chart is entirely "provisional" shaded because
  every 12-month window includes provisional months, which its caveat states.

## Whole-branch review

A fresh Opus reviewer read the whole branch. It found two Critical and four Important issues (and 20-odd Minor ones).
All six were fixed, each with a test that failed first:

1. A release without the year-ended citizenship chart ingested but had no analysis, which would blank the Overview.
2. The crawl delay was per process, so the CLI run beside the server could send requests less than 10 s apart, and a lost
   ingest race could mark an unchanged release `corrected`. Now a `flock` file shared through `data/` paces all processes
   (checked with two real processes) and `corrected` is decided inside the write transaction.
3. Raw exception text reached stored and served error detail on the network and parse paths.
4. The country ranking's prior-period change used a partial window for periods over 12 months.
5. Releases were marked `unavailable` after blocks, network errors or parser failures, and polled again minutes after a block.
6. First `docker compose up` on plain Linux needs `./data` owned by UID 10001 (now in the quick start).

The Minor findings are not fixed; they are listed under remaining work. Two automated post-commit security reviews also
found CSV formula injection (twice) and unescaped tooltip HTML; both are fixed with tests.

## Codex review round 1 (PR #1, commit 2c73d9b)

Four P2 findings, each validated against the code and fixed with a test that failed first:

1. Vintage digest ignored page-embedded charts (#4245952768). The digest now covers the downloaded files plus every
   chart's title and CSV body on the release page (never the surrounding HTML, so nonces and markup cannot cause false
   revisions). A corrected chart, or the optional citizenship chart appearing later, yields a new vintage.
   Upgrade note: the digest value changed, so a database ingested before this commit gets one extra vintage with
   identical values (marked `corrected`) on the first manual re-ingest of each release. No such database exists outside
   development; if one does, re-seed it.
2. An `unavailable` release ignored a calendar reschedule (#4245952774). A later scheduled time now returns it to
   `delayed` with the new time, which resets its polling attempts (see round 2 for the final rule).
3. `/api/calendar?to=9999-12-31` returned 500 (#4245952779). `date.max` is now an unbounded upper bound. `from=0001-01-01`
   had the same defect through the UTC conversion and is fixed alike.
4. Delayed releases sorted as past (#4245952785). The calendar's upcoming predicate is now `scheduled` or `delayed`,
   also applied to the Scheduled status filter.

## Codex review round 2 (PR #1, commit 261f80c)

Three further findings, each validated and fixed with a test that failed first:

1. Default revision base used insertion order (#4246141419, P1). `revision_view` required `vintage_id < compare.vintage_id`,
   so ingesting an older release after a newer one (backfill or retry) made `/api/revisions/{key}` return 404. The base is
   now the vintage immediately before `compare` in publication order.
2. A stale second feed could rewind a reschedule (#4246141425). `discover()` stores the ICS result and then the month
   result, and neither is reliably fresher (the ICS refreshes daily, the month endpoint is undocumented). The slot of an
   unpublished (`scheduled`, `delayed`, `unavailable`) release now only moves later, so it converges on the latest slot any
   feed reported in either read order. This replaces round 1's "earlier slot becomes scheduled" rule: a pull-forward is not
   applied until the calendar lists the release as published, which sets its actual time.
3. Migration script and version marker were not atomic (#4246141437). The script, the `schema_version` insert and `COMMIT`
   now run in one `BEGIN IMMEDIATE` script and roll back on any failure, so a failed migration leaves no partial schema.
   Not changed: two processes migrating a brand-new database at the same instant still race (the loser fails and retries on
   its next start); this predates the review.

## Codex review round 3 (PR #1, commit 9b82eb4)

Two findings, both on the deferred-minor list from the whole-branch review, validated and fixed with tests that failed first:

1. Driver-share wording ignored signs (#4246208518). Net is arrivals minus departures, so same-direction moves offset and a
   share of their "combined movement" credited the larger side for a net change that is only the difference. The
   statement is now made only when arrivals and departures do not move the same way (then |change in net| is exactly the
   sum of the two and the share is exact) and says so. The real July 2026 release (arrivals up, departures down) keeps its
   61%. Frontend fixture regenerated: one sentence changed.
2. The backend series CSV wrote upstream text unguarded (#4246208524). All text cells, including the upstream release title,
   now get the same leading-quote guard as the frontend export (`'` before a first significant `= + - @`, or a leading
   tab/CR/LF, after skipping whitespace and invisible characters). Numeric cells are untouched.

## Codex review round 4 (PR #1, commit 1b1e888)

Three findings, validated and fixed with tests that failed first:

1. Backfill dropped discovery failures (#4246272300). A month whose calendar request failed left no trace: the run printed
   its successes and exited 0. Each failed month is now returned as a `failed` outcome (`calendar_month:YYYY-MM`) and the
   CLI exits 1 and prints its detail. The month listing for months with no releases must answer 200 with empty lists;
   a 404 is a failure.
2. A later successful month cleared an earlier failure (#4246272308). The `calendar_month` health is now one verdict per
   discovery or backfill run: `ok` only if every requested month succeeded, otherwise `degraded` with every error joined.
3. Country ranking mixed vintages (#4246272317). Each place series was read from its own latest vintage, so a place the
   newest country file omits kept an older release's value (real fixtures: Togo, 2025-10 = 1 in June, absent in July).
   Every place is now read from the same ingested bundle as the latest arrivals total (release plus bundle digest, so a
   corrected bundle that drops a place is handled too); a place absent from that bundle counts as zero, as the ranking
   note already states. Stored data and vintages are untouched. Places absent from the latest bundle now appear as zero
   rows (visible in the regions list); only the top countries are shown.

## Codex review round 5 (PR #1, commit e9a777e)

Three findings, validated and fixed with tests that failed first:

1. The CLI exited 0 when a release was `not_available` (#4246379621). `ingest` and `backfill` now exit 1 for `failed` and
   for `not_available`, since a requested release that was not ingested is a gap.
2. The Published filter hid corrected releases (#4246379625). Published now includes `corrected`, as Scheduled includes `delayed`.
3. Month navigation showed blank months (#4246379631). The month view now requests the month it shows (`from`/`to` are the first
   and last day), defaults to the current Pacific/Auckland month, and keeps the navigation visible with an explanation when a
   month holds no matching releases. The list view still uses the API's default window.

## Codex review round 6 (PR #1, commit ec224f6)

Two findings, validated and fixed:

1. A corrected release's analysis mixed bundles (#4253628351). Each series was read from its newest vintage for the release,
   so after a page-only correction that removed the optional citizenship chart (detectable since round 1) the analysis kept
   the old bundle's citizenship series. The analysis now reads every series from the release's newest bundle, and an
   optional series that bundle lacks is unavailable. The previous-release comparison is unchanged: it only reads the required
   series, which every bundle contains. Test failed first.
2. README and troubleshooting still said a page-only chart correction is not detected and told operators to delete vintages
   (#4253628355). Both now state the digest covers the files and the embedded chart data; only the parser-fix limitation remains.

## Codex review round 7 (PR #1, commit c6bdfda)

Two findings, validated and fixed with tests that failed first:

1. A later success cleared another release's failure (#4253658288). `release:<slug>` health was last-write-wins, so a failed
   June followed by an unchanged July left the source `ok` over a data gap. Health is now derived from the releases whose
   most recent ingest run failed: `degraded` with each such release named (first three, then a count) until that release
   itself succeeds. A release that failed and is never retried keeps the source degraded, which is deliberate.
2. An all-blank optional citizenship series caused a 500 (#4253658294). The parser kept a series whose cells were all blank
   or `..` as a vintage with no observations, and the analysis took `max` of an empty mapping. The adapter now omits an empty
   optional series (validation warns it was not published) and the analysis loader treats an empty optional series as
   unavailable, which also covers vintages stored before this fix. Required series must still hold data.

## Codex review round 8 (PR #1, commit 07a126d)

Three findings, all from partially blank year-ended chart cells, validated and fixed with tests that failed first:

1. The citizenship insight could pair figures from different periods (#4253711085). It is now emitted only when the NZ and
   non-NZ series end in the same period.
2. The citizenship chart could combine different vintages or periods (#4253711087). It now declines to combine the two series
   unless both come from the same release and ingest, and quotes both values for the latest period they share, naming it.
3. A streak could bridge a missing month (#4253711094). `_streak` now ends at the first non-adjacent pair of periods.

Not changed: validation still accepts a required year-ended series with an isolated blank cell inside the chart. The two
consumers that assume adjacent months (the streak and the citizenship pair) now cope; a continuity rule for the rolling
series is not added without evidence of such a gap in a real file.

## Review round 9 and provisional-status audit (PR #1, commit f925eb6)

Two Codex findings, then a cross-layer audit of how provisional status travels from the Stats NZ file to the screen.

Findings, each fixed with tests that failed first:

1. The combined monthly/year-ended chart dropped year-ended statuses (#4253748549). The API already carries them
   (derived: provisional while any of the twelve months is; 16 points from 2025-04 in the real July file). The chart now keeps
   the full year-ended points, flags them in its tooltip, shades a labelled "Provisional" band on that panel, and exports
   separate `monthly_status` and `year_ended_status` columns.
2. The provisional sentence treated first-to-last as a range (#4253748554). It now names exactly the provisional months:
   a range only for consecutive months, otherwise each run is listed, with evidence for every run boundary. The
   `provisional_window` validation warning is unchanged.

Audit method: traced status through the parser (`with_rolling_status`), validation, storage, API, insights, charts, tooltips, titles,
captions and CSV exports, and checked the real June and July files. Facts established: arrivals, departures and net carry
identical monthly statuses in both files; the real data holds no `unknown` statuses; required series always share one bundle.

Additional defects found and fixed, each with a regression test:

- Chart titles quoted a provisional latest value with no status (trend, arrivals/departures, citizenship). They now add
  ", provisional" (or ", status unknown").
- Arrivals/departures and citizenship CSVs had one `status` column for two series and dropped periods present in only
  one. Each series now has its own status column and no period is dropped.
- The country ranking's prior window could be built from provisional months with no flag, in the API, the CSV and the change
  figures. `CountryRank.prior_provisional` (null when the prior window is withheld) and a CSV column now say so.
- The year-ended series caveat and `docs/data-dictionary.md` did not state that the year-ended status is derived. Both do.
- The release summary's provisional insight covered monthly estimates only, so year-ended figures quoted elsewhere in the
  narrative were unflagged. It now says year-ended totals that include a provisional month are provisional too.

Examined, no defect demonstrated, not changed: tooltips and bar opacity on the single-series charts; the revisions chart
and table (statuses are exported and tabulated); vintage pairing of required series (one bundle by construction, and
validation rejects a bundle without them); a validation rule for monthly statuses disagreeing across arrivals, departures
and net (they never do in real files, but year-ended statuses are derived from net, so such a rule is a candidate if
Stats NZ changes the files).

## Review round 10 (PR #1, commit 03d70a6)

Three findings, validated and fixed with tests that failed first:

1. The provisional band covered final months between provisional ones (#4254034473). This was the same root cause as the
   wording finding of round 9 (a first-to-last span treated as contiguous), and the stacked panel added in round 9 had it
   too. A shared `provisionalRuns` now builds one band per run of consecutive provisional periods for both charts; a
   `grep` for first/last provisional spans found no other consumer. The `provisional_window` validation warning now says the
   months are "spanning" a range rather than implying the range is provisional.
2. The Overview requested a series that does not exist on a first run (#4254034477). After `discover` and before the first
   backfill the trend got a 404 and showed an error panel. A 404 now shows a note that the trend appears once the first release
   is ingested; other failures still show the error panel.
3. Unexpected discovery failures aborted without recording health (#4254034483). `attempt` caught only `IngestError`, so e.g.
   an undecodable calendar body raised past the health update. Other exceptions are now logged in full, recorded as an
   `unexpected` degraded error naming only the exception type, and the run continues (also for backfill months).

## Review round 11 (PR #1, commit 4c43b00)

One finding, validated and fixed with a test that failed first:

- The calendar's "last successful check" took the newest success of either feed (#4254067563). With the ICS refreshed and the
  month feed failing, it reported the current run as a success and, because the attempt time equalled it, hid the last-attempt
  warning. The calendar is complete only with both feeds, so its last success is now the oldest of the feeds' last successes
  (empty while a feed that has been tried has never succeeded); the last attempt stays the newest. An ICS-only installation
  reports the ICS time. This was the only place that aggregated freshness across feeds; the Overview lists each source
  separately.

## Review round 12 (PR #1, commit d048bb2)

Two findings, validated and fixed with tests that failed first:

1. The citizenship chart's same-vintage check passed on stale data (#4254096575). When a corrected release dropped both
   optional series, each series' latest vintage was still the superseded one, so the two matched each other. This is the same
   "latest vintage per series" root cause as the country ranking and the release analysis, which already read one bundle.
   The series API now marks a vintage `superseded` when its release was re-ingested into a newer bundle without that series,
   and the chart declines to show superseded series. Data from an older release that a newer release simply lacks is not
   superseded and keeps its own release label. Audit of every consumer of per-series latest or previous vintages: the
   analysis, ranking and revisions are bundle-based or single-series; the only client-side pairings are of required series
   (always one bundle) and this guarded optional pair.
2. A blank interior chart cell closed the gap on the category axis (#4254096579). The line, bar and stacked charts now use a
   continuous month axis, so a month without an observation keeps its place and the line breaks there. Ingestion is not
   changed to reject such gaps: no real file has one, and rejecting would block a release rather than show it honestly.

## Review round 13 (PR #1, commit 74294a6)

Two findings, validated and fixed with tests that failed first:

1. Calendar freshness was still derived from per-feed timestamps (#4254126251). Round 11 changed the aggregation (oldest
   success, newest attempt), but timestamps recorded per feed cannot describe one refresh: a normal successful run showed a
   later "last attempt" than its "last success", and alternating single-feed successes produced a success time although no
   refresh completed. Discovery now records one `calendar_refresh` health row per run, healthy only if every feed in that run
   succeeded, and the calendar API reports that row. Backfill does not update it (it never reads the ICS feed).
2. Revision responses reported `superseded=false` regardless (#4254126260). `VintageOut.superseded` no longer has a default and
   `vintage_out(conn, v)` always computes it, so no construction site can omit it. Its meaning is now exact and tested: a
   vintage is superseded when a newer bundle of its release does not include the series (withdrawn). A series the newer bundle
   revised is not superseded: its older vintage is the original of a revision. The revisions chart notes a superseded comparison.

## Review round 14 (PR #1, commit 260ea47)

Two findings, validated and fixed with tests that failed first:

1. `nzstats ingest --release-key` exited 0 for a release with no adapter (#4254166732): it was neither ingested nor recorded.
   `skipped_no_adapter` now counts as a gap in the exit code. Catch-up and backfill only select releases that have an
   adapter, so the outcome can only come from an explicit key.
2. A 404 on a release already `published` or `corrected` left `release:<slug>` health untouched (#4254166737). Missing files
   are expected only before publication, so for a published or corrected release `not_available` now refreshes health and
   `failing_releases` counts the latest `not_available` run as failing; it recovers when the release ingests again.

## Remaining work

Before merging or calling Phase 1 shipped:

- Run `docker compose up -d --build` on a Docker host and follow the README quick start (including `chown` of `./data`).
- Run the live scheduler check at the next migration release (12 Nov 2026 10:45 NZDT as captured).
- Set `NZSTATS_CONTACT` in `.env` (Kevin's choice; not sent so far). Review Stats NZ's terms before any public hosting.
- Decide the bundle-digest scope (15 October cycle) before merge or as the first follow-up.

Deferred Minor findings (small, none blocks use):

- Reprocessing: parser fixes are not applied to stored releases whose files and charts are unchanged
  (add `nzstats ingest --reparse`); nothing re-checks a release after it has data, so `corrected` only follows a manual re-ingest.
- Discovery aborts on non-`IngestError` failures.
- API: `/api/releases` loads all rows before paging; the vintage kind is missing from `ReleaseAnalysis` and `CountriesOut`.
- Analysis: the citizenship chart title omits its period.
- Frontend: revision and chart data tables need `overflow-x-auto`; `/releases/abc` renders blank; the calendar month grid has
  no grid keyboard behaviour and the importance filter has no Low option; TanStack Table is installed but unused.
- Hygiene: the `.env.example` contact is a placeholder address; the shadcn CLI is a
  runtime dependency; add a Python lock file for reproducible images.
- CI does not run the Playwright suite or the frontend lint.

## ECT independent-audit remediation (branch `fix/ect-audit-remediation`)

Audit of `b4c8823` (GO WITH CONDITIONS): official reconciliation passed (18,426 points, 0 mismatches). Fixed:

- F1 (MEDIUM): a consistent x10 scaling of core actual levels was accepted. Added fail-closed `consistency` validation
  (`actual_value_inconsistencies`): actual retail/core/total vs industries, quarterly industries vs months, count x mean.
  Tolerances come from measured residuals in the official files (see `docs/data-sources/ect.md`): strict additivity holds
  only from 2017-01 for monthly aggregates, and quarterly aggregates are not recomputed by Stats NZ, so those use a 1% guard.
- Metadata compatibility (reproduced): definition wording was part of revision/correction compatibility and of the ECT bundle
  digest, so a wording-only edit withheld revisions and re-minted all vintages as a "correction". Wording is now editorial;
  compatibility is unit, frequency, adjustment and `definition_id`. Bundles stored under the old digest still match.
- F2: sentences rewritten ("Seasonally adjusted retail card spending decreased 0.4% in September 2026 ..."); chart
  captions show Auckland time (PNG exports keep the exact ISO instant as provenance).
- F3: history chart gains a Zoomed (default) / From zero scale, with the non-zero axis stated in the chart, caption and
  exports; industry charts size to their labels at 390px.

Not done: percentage-change companion chart; checks on seasonally adjusted/trend levels (not additive by design).

## Resume steps for Phase 2

1. Read `docs/superpowers/specs/2026-10-11-nz-stats-dashboard-design.md` §12 and `docs/data-sources.md` ("Adding a source").
2. Pick one category (Consumers price index is the natural first: `consumers-price-index` is already in `catalog.py`).
   Verify its official files and release page manually and record them in `docs/data-sources.md` with the date. Do not guess.
3. Capture real fixture excerpts (see `scripts/capture_fixtures.py`) and probe how far back vintages exist
   (`scripts/probe_vintages.py`); set the backfill window from evidence.
4. Write the adapter (`adapters/<category>/`) test-first with a layout-drift case; add validation rules grounded in the real
   files; register it in `runtime.py`; move the category out of `INACTIVE_CATEGORIES`.
5. Reuse `ChartCard` and the option builders; add the Data Explorer and Revision Explorer once two categories exist.
6. Run the real-site integration check again for the new category and expect surprises: the Phase 1 run found three.
