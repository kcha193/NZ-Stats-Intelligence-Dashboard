# Phase 3A: economic research source foundation. Architectural and source assessment

Date: 2026-10-25. Branch `feat/phase-3a-research-sources`. Plan: [../plans/2026-10-25-phase-3a-research-sources.md](../plans/2026-10-25-phase-3a-research-sources.md).

Goal: begin the New Zealand Economic Intelligence Hub by ingesting institutional economic commentary (RBNZ, Treasury, banks,
research consultancies) **without** touching the Stats NZ statistical pipeline, its API, or the public snapshot.

## 1. Repository assessment

State at `main` (`2858bd2`): 3 categories ingested (migration, ECT, CPI), 155 formatted files, no open PRs (`gh pr list` is empty), so
nothing to conflict with. Schema is SQLite with additive numbered migrations (`store/migrations/001..003`), applied in one
transaction each by `store/db.py`.

### Reusable as-is

| Component | Why it is reusable |
|---|---|
| `sources/fetcher.py` `Fetcher`, `FilePacer` | Cross-process pacing, retry/backoff, `Retry-After`, block detection and a 30 minute cooldown, same-host redirect rule. One instance per institution gives per-source pacing and isolation. |
| `sources/artifacts.py` `ArtifactStore` | Content-addressed raw file store. |
| `domain.ErrorClass`, `IngestError`, `RequestRefused` | Shared failure vocabulary (`network`, `blocked`, `not_found`, `layout_changed`, `validation_failed`, `unexpected`). |
| `store/db.py` `connect`, `migrate`, `transaction` | Migration runner and explicit transactions. |
| `clock.py` | UTC instants and Pacific/Auckland presentation. |
| `publish/leaks.py`, `publish/contract.is_stats_nz_url` | Left untouched; used as a regression guard. |

### Deliberately **not** reused (the coupling to avoid)

| Stats NZ component | Why research must not use it |
|---|---|
| `release`, `series`, `vintage`, `observation` tables | A vintage is an official number published in a release; commentary has no series, period grid or revision semantics. Forcing it in would make `/api/overview`, `/api/releases`, the revision logic and the snapshot reconciliation see non-statistical rows. |
| `source_health` table | `HealthOut` and the public snapshot enumerate it. Research health lives in `research_source_health`. |
| `ingest_run` table | Keyed by `release_key`; `failing_releases` and the Data health page read it. Research has `research_run`. |
| `adapters/`, `validate/rules.py`, `pipeline/`, `scheduler/` | Statistical layouts, magnitude checks and release-day polling. Research has its own `nzstats.research` package; nothing under `nzstats.research` is imported by those packages, and a test enforces it. |
| `api/` and `models.py` | No research endpoint in 3A. Adding one changes the OpenAPI document and the generated `schema.d.ts`, which is a backward-compatibility risk with no consumer yet. |

### Two small, backward-compatible changes to shared code

`Fetcher` gains optional constructor arguments, both defaulting to the old behaviour:

* `max_bytes`: stream the body and abort above the cap (a hostile or broken server cannot make us buffer an unbounded response).
* `url_check`: called with every redirect target, so research can re-apply its host allowlist, https-only rule and robots rules
  on each hop (today a same-host redirect may downgrade to `http://`).

### Publication path (Step 6 findings)

* `publish/contract.py` `SOURCE_HOSTS = ("stats.govt.nz", "www.stats.govt.nz")`; `validate.py` requires every source URL in every
  payload to satisfy `is_stats_nz_url` (https, Stats NZ host, no userinfo).
* The snapshot is closed by construction: `export_snapshot` runs the API in process and writes only a fixed set of kinds; the
  validator rejects files not in the manifest, requires fixed files, round-trips every payload through its response model and
  scans for leaks. Research rows live in tables the API never reads, so **they cannot reach a snapshot today**. This is a property
  to preserve and test (Task 12), not to rely on silently.
* `kind_of(path)` raises `KeyError` for an unknown directory, so a stray `research/…json` in a snapshot crashes the validator rather
  than reporting an error. It still fails closed; Task 12 pins the behaviour and reports it as a finding.

## 2. Source verification (probed 2026-10-25)

Method: one `robots.txt` and one landing page per priority source from a generic client (not the project User-Agent), plus search
results for URL discovery. **A 403 to the probe client is not proof that the project's descriptive User-Agent would be refused**; it is
recorded as "not verified" and the source stays gated. Evidence grades: **direct** = fetched and read; **search** = reported by a
search-engine summary, not read on the page; **none**.

| Institution | robots.txt | Landing / listing | Discovery mechanism found | Terms / licence | Result |
|---|---|---|---|---|---|
| **RBNZ** | 403 (direct) | 403 (direct). Publications live under `/research-and-publications/publications` (search) | RSS `https://www.rbnz.govt.nz/feeds/news` is for **news releases only** (search; not fetched). No publications feed found. MPS/FSR dates are published in advance (search) | Terms page `/about-our-site/terms-of-use` reportedly allows reuse with attribution, but restricts automated scraping except public search engines obeying robots.txt, or with prior written permission (**search**) | `restricted`: no automated access until written permission or a direct read of the terms says otherwise |
| **Treasury** | 200, direct. Drupal rules; disallows `/publications/search`, `/admin`, `/user/*`; no Sitemap, no Crawl-delay | `/publications` 403, `/sitemap.xml` 403, `/copyright` 403 (direct) | Unverified. PDFs at `/sites/default/files/YYYY-MM/<name>.pdf` (search) | Crown copyright under **CC BY 4.0** unless indicated, third-party material excluded, at `/copyright-and-licensing` (**search**; the page itself 403'd) | `needs_review`: best candidate for full text once one throttled probe with the project User-Agent succeeds and the licence page is read |
| **ANZ** | 200, direct. `User-agent: *` with **no Disallow**; `Sitemap: https://www.anz.co.nz/sitemap.xml` | 200, direct: `/about-us/economic-markets-research/` lists series (Economic Outlook, Data Wrap, Economic News, Property Focus, Agri Focus, Truckometer, etc.) as HTML pages | **No RSS.** Series pages are HTML. The Economic Outlook page shows an HTML summary and PDF links named `…/2026/ANZ-QEO-20260813.pdf` (date in the filename). No login needed. Release schedule PDF published | `© ANZ Bank New Zealand Limited. All rights reserved.` Terms (direct): may reproduce and store "solely for the purposes of viewing"; "You may not display or distribute the content of any of these pages in public"; "do not create a link … without the prior permission of ANZ"; nothing on scraping or research content | `needs_review`, `metadata_only`: permission needed even for links; no body extraction |
| **ASB** | 200, direct. Disallows **`/content/dam/asb/documents/`** (where PDFs such as `/content/dam/asb/documents/reports/economic-weekly/…pdf` live), plus ~200 named bots | Guessed `/economics-research` is 404. Real pages (search): `/documents/economic-research.html`, `/documents/economic-research/full-reports-list.html`, report pages like `/documents/economic-research/quarterly-economic-forecasts/<slug>.html` and `…/economic-weekly/<slug>.html`. The full-list page was truncated for the probe (probably script-rendered) | **Not verified.** No RSS seen; "Register for email updates". HTML report pages are crawlable, PDFs are not | Terms at `/documents/terms-and-conditions.html` not read | `needs_review`; PDFs `restricted` by robots; HTML only |
| **Westpac NZ** | 403 (direct) | 403 (direct). Landing (search): `/business/business-base/economics/economic-reports/` | Weekly Commentary PDFs on a **different host**: `assets.dam.westpac.co.nz/is/content/wnzl/dist/all-of-bank/economic-reports/weekly-commentary/Weekly-Commentary_191026_report_19Oct26.pdf` (search; date in the filename, two formats: `DDMMYY` and `DDMonYY`) | Not read | `needs_review`; needs both hosts in its allowlist and a robots check on each |
| **BNZ** | not probed | not probed | none | none | `unverified` (landing URL not established; **not guessed**) |
| **Kiwibank** | not probed | Commentary hub under `https://www.kiwibank.co.nz/business-banking/thrive-hq/kiwi-economics/commentary-insights/` (search) | none | none | `unverified` |
| **NZIER** | not probed | Publications `https://www.nzier.org.nz/publications/<slug>` and tag listing `…/publications/tag/consensus-forecasts`; PDFs under `https://www.nzier.org.nz/hubfs/Public%20Publications/…` (search). Free public Consensus Forecasts | HTML listing; mechanism unverified | none | `needs_review` (candidate once terms are read; may contain subscriber-only material) |
| **Infometrics** | not probed | Insights hub `https://economics.infometrics.co.nz/reports`, articles `…/article/<slug>` (search). A `testing-economics` subdomain also appears in search and must **not** be allowlisted | none | Quarterly Economic Monitor and regional forecasts are described as subscription products | `needs_review`: paywall risk; public media releases only |
| **Deloitte NZ** | not probed | `https://www.deloitte.com/nz/en/services/consulting-financial/services/deloitte-access-economics.html`; NZ perspectives under `/nz/en/…/perspectives/` (search) | No NZ-specific recurring outlook series confirmed (the "Business Outlook" series found is Australian) | none | `unverified` |

### What this means

1. **No source is cleared for automated full-text ingestion today.** Of the five priority sources, one is restricted (RBNZ), one is
   promising but unreachable from the probe (Treasury), one is open technically but legally link-restricted (ANZ), one is
   partially disallowed by robots (ASB) and one returned 403 (Westpac).
2. The framework therefore ships **fully built and fully tested offline, with every source gated** by an explicit human approval
   recorded in `config/research_sources.toml` (`review_status = "approved"` with `approved_by`, `approved_on`, `approval_note`). The
   loader rejects an `approved` source without them.
3. `content_policy` is separate from approval: `full_text` (store extracted text and sections), `metadata_only` (title, date, URL,
   series; the document body is **never downloaded**), `none` (no automated access). Unknown or contradictory settings fail closed.
4. Dates are mostly in filenames or page text, so date parsing is per-source configured and conservative: a date-only value is a
   civil date in Pacific/Auckland with precision `day`; midnight is never invented.

## 3. Target architecture

```
config/research_sources.toml ──► research/registry.py ──► Institution (frozen, validated)
                                         │
 research/discover.py  (rss | sitemap | html_links | manual)      ← candidates (url, title?, date hint?)
        │   every URL: research/safety.py HostPolicy + RobotsPolicy
        ▼
 research/fetch.py ResearchFetcher ──► sources/fetcher.Fetcher (per-institution pacer file, max_bytes, url_check)
        ▼
 research/extract_html.py | extract_pdf.py ──► Extracted(title, sections[], text_sha256, warnings)
        ▼
 research/validate.py  (deterministic, fail-closed)
        ▼
 research/store.py ──► research_* tables (one transaction per document; previous version stays current on any failure)
        ▲
 research/contract.py  (Phase 3B contract: evidence refs, forecast claims, provenance, deterministic verifier; no LLM calls)
```

Separation: **parsing** (extract_*) produces text and structure only; **deterministic validation** decides whether text may be stored;
**LLM interpretation** (Phase 3B) consumes stored sections and is verified against them by `contract.verify_summary`. LLM output is a
different table family and never writes to `series`, `observation` or `vintage`.

### Data model (migration `004_research.sql`, additive)

| Table | Purpose |
|---|---|
| `research_institution` | key, name, and the registry policy in force when last synced (review status, content policy) |
| `research_publication` | stable identity `doc_key` (`<institution>:<host><path>`, scheme, query, fragment and trailing slash removed), canonical URL, title, series, categories, `published_on` (NZ civil date), `published_at` (UTC instant, nullable), `published_precision`, `reference_period` (nullable; **never derived from the publication date**), `first_seen_at`, `last_seen_at`, `current_version_id`, `content_status` (`extracted`, `link_only`), `duplicate_of_id` |
| `research_document_version` | one per distinct extracted text: `content_sha256` (raw bytes), `text_sha256`, format, `fetched_at`, `extracted_at`, `extractor_version`, `raw_artifact_id`, char/page counts, `licence_snapshot` |
| `research_section` | `(version_id, ordinal)`: heading, text, `page_start`, `page_end`, `char_start`, `char_end`, `text_sha256`; the evidence anchors Phase 3B cites |
| `research_run` and `research_run_item` | every attempt and each URL's outcome, with error class and a sanitised detail (no raw exception text) |
| `research_source_health` | per institution: state, last checked / success, consecutive failures |

Timestamps: `published_*` (the institution's), `fetched_at`/`extracted_at`/`first_seen_at` (ours, UTC), `superseded_at` on a version
(revision). A revert A→B→A reuses version A (unique on `(publication_id, text_sha256)`) and re-points `current_version_id`.

Phase 3B tables (summaries, model provenance, forecast claims) are **designed, not created** (see the Phase 3B plan); creating empty
tables now would fix a schema before a consumer exists.

Rollback: nothing outside `research_*` references them, so `scripts/rollback/004_research_down.sql` (drops them and the
`schema_version` row) is safe. A test applies it and proves the Stats NZ tables, API and snapshot export are unchanged.

## 4. Risks and how Phase 3A answers them

| Risk | Answer |
|---|---|
| Licensing / terms | Per-source `review_status` and `content_policy`, default-deny; ANZ and RBNZ shipped as `metadata_only`/`none`; no report body is committed to Git (fixtures are synthetic and labelled) |
| robots.txt | Own parser with `*`/`$` and longest-match rules, fetched per host through the paced fetcher; 401/403 means deny all, 404 means allow, 5xx/network means deny this run; registry can also pin disallowed prefixes |
| SSRF and redirects | Exact-host allowlist, https only, port 443, no userinfo, no IP literals, resolved addresses must be global, every redirect hop re-validated |
| Hostile content | Size, page and character caps; `<!DOCTYPE`/`<!ENTITY` rejected before any XML parse; HTML never rendered or executed; control characters stripped; all text flagged `untrusted` for 3B prompt framing |
| Paywall or teaser pages stored as the report | Minimum text length, login/paywall/challenge markers, shrink guard against the previous version |
| Last-known-good | One transaction per document; any failure records a `research_run_item` and leaves `current_version_id` unchanged |
| Stats NZ regression | Separate package and tables, import-boundary test, full existing suite, snapshot invariants re-run |
| PDF parser attack surface | `pypdf` is pure Python, capped by size/page/char limits; residual risk (decompression bombs) documented, with subprocess isolation listed for 3B |
| Crawl load | 10 s minimum spacing (same floor as Stats NZ), per-institution pacer file and cooldown, `max_documents_per_run` default 5, no scheduler wiring in 3A |

## 5. Implementation notes (2026-10-26)

Where the build differs from the plan, and why:

| Plan | As built | Reason |
|---|---|---|
| `doc_key` = `<institution>:<host><path>` | `<institution>:<host><path>[?query]` with tracking parameters removed and the rest sorted | Two reports that differ only by `?id=` must not collide |
| `Fetcher(url_check=...)` constructor argument | `Fetcher.get(url, url_check=...)` | The check is per request; Stats NZ calls pass nothing and are unchanged |
| PDF sections split at heading-like lines | One section per page (`pdf-1`) | Heading detection from PDF text is unreliable; exact page references matter more for evidence. A table- and heading-aware `pdf-2` is a Phase 3B option |
| `pypdf` in process, capped by size and pages | `pypdf>=6` in a child process (`python -I`) with a timeout, CPU, address-space and file-size limits; stderr discarded, reply size checked | Security review: per-stream decompression caps do not bound total memory or CPU, and unbounded child output could be buffered |
| Reject `<!DOCTYPE`/`<!ENTITY` before parsing | Byte check, then an expat pre-scan whose DOCTYPE/entity handlers refuse | Security review: a UTF-16 body hid its DOCTYPE from the byte pattern |
| Sitemap dates as a date source | Not used | `lastmod` is a modification time, not a publication date |
| Dry run records a run | A dry run writes nothing | A probe of an unapproved source should leave no trace beyond logs |
| Validator: report `kind_of` crash as a finding | Fixed: unknown kinds are a reported validation error | Tightens validation; nothing that was valid fails |

Not done in 3A: no source approved, no real document ingested, no Docker image change for the `research` extra, no
scheduler wiring. See the Phase 3B plan for what must precede summarisation.

