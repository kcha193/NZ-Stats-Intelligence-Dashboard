# Phase 3A: economic research source foundation. Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A research-ingestion domain (`nzstats.research`) that discovers, fetches, extracts, validates, versions and stores institutional economic commentary, fully offline-tested, with every source gated by recorded human approval, and with no change to Stats NZ results or the public snapshot.

**Architecture:** Registry (TOML) → safe discovery → paced, allowlisted, robots-aware fetch → HTML/PDF extraction into sections → deterministic validation → one transaction per document into additive `research_*` tables. A Phase 3B contract module defines evidence-grounded LLM output and a deterministic verifier; no LLM call exists in 3A.

**Tech Stack:** Python 3.11+, httpx (existing `Fetcher`), stdlib `html.parser` / `xml.etree` / `zoneinfo`, `pypdf` (new optional extra `research`), pydantic, SQLite, pytest, ruff.

**Spec:** [../specs/2026-10-25-phase-3a-research-sources-assessment.md](../specs/2026-10-25-phase-3a-research-sources-assessment.md) (assessment and verified source evidence). Repo rules: `CLAUDE.md`.

## Global Constraints

- The 10 second minimum spacing and "never parallel requests" rule applies to research fetching too (`MIN_RESEARCH_DELAY_SECONDS = 10.0`). Tests never touch the network: `httpx.MockTransport` only.
- Nothing under `nzstats/research/` is imported by `adapters`, `pipeline`, `validate`, `stats`, `insights`, `scheduler`, `api`, `publish`; the research package imports only `sources.fetcher`, `sources.artifacts`, `store.db`, `domain`, `clock`.
- Migration `004_research.sql` is additive: no `ALTER`/`DROP`/`UPDATE` of an existing table.
- Timestamps stored in UTC ISO-8601; publication dates are NZ civil dates (`published_on`) with explicit precision; `reference_period` is never derived from a publication date.
- Error text stored in `research_run_item.detail` is a fixed vocabulary plus `type(exc).__name__`; never raw exception messages, never upstream text.
- Fixtures are **synthetic** and carry a `SYNTHETIC FIXTURE` marker: committing third-party report bodies would breach their terms. This is a stated deviation from "fixtures are real excerpts" (Stats NZ files are CC BY; these are not).
- Public publication stays disabled and unchanged. No research data in any snapshot.
- TDD: write the test, run it, watch it fail for the right reason, implement, run again.

## Review Focus

- An institution with `approved` status but a hostile redirect (to `http://`, another host, or a robots-disallowed path): refused, nothing stored. (Task 3, 4)
- A page that returns 200 with a login/teaser/challenge body: recorded `blocked`/`validation_failed`, never stored as the report. (Task 9)
- A changed document whose new extraction is much shorter (truncated PDF): previous version stays current. (Task 9)
- A date-only publication date near the NZ/UTC boundary and across the 27 Sept 2026 daylight-saving change. (Task 5)
- Re-ingesting identical content, an A→B→A revert, and the same text under a second URL. (Task 9)
- A research row present when the snapshot is exported: output byte-identical to without it. (Task 12)

---

### Task 1: Migration, rollback script and repository

**Files:** Create `backend/src/nzstats/store/migrations/004_research.sql`, `scripts/rollback/004_research_down.sql`, `backend/src/nzstats/research/__init__.py`, `research/store.py`; Test `backend/tests/research/test_migration.py`, `test_store.py`.

**Interfaces:** Produces `store.upsert_institution(conn, key, name, review_status, content_policy, now) -> int`; `store.upsert_publication(conn, inst_id, doc_key, url, title, series, categories, published: PublishedDate|None, now) -> tuple[int, bool]` (id, created); `store.current_version(conn, pub_id) -> sqlite3.Row|None`; `store.add_version(conn, pub_id, *, content_sha256, text_sha256, fmt, fetched_at, extractor_version, raw_artifact_id, sections, page_count, licence_snapshot, now) -> tuple[int, str]` where the string is `new|reactivated|unchanged`; `store.record_run(...)`, `store.record_item(...)`, `store.set_health(...)`.

- [ ] Tests: `test_migration_is_additive_on_populated_db` (ingest fixtures through 003, snapshot row counts and `sqlite_master` of old tables, migrate, compare), `test_no_foreign_key_from_old_tables_to_research`, `test_rollback_script_removes_only_research_objects`, `test_unique_text_per_publication`, `test_revert_reuses_version_and_repoints_current`, `test_section_ordinals_unique_per_version`.
- [ ] Implement the SQL (schema in the assessment §3) and repository functions; run `pytest backend/tests/research backend/tests/store -q`.
- [ ] Commit.

### Task 2: Registry and the verified source file

**Files:** Create `research/registry.py`, `config/research_sources.toml`; Test `tests/research/test_registry.py`.

**Interfaces:** Produces `ReviewStatus`, `ContentPolicy`, `Mechanism` (StrEnum), `Discovery`, `Institution` (frozen; fields in the assessment table plus `approved_by/approved_on/approval_note`, `evidence`, `verified_on`), `Institution.automated_access_allowed(self) -> bool`, `load_registry(path: Path|None=None) -> dict[str, Institution]`, `PRIORITY = ("rbnz","treasury","anz","asb","westpac")`.

- [ ] Tests: all ten keys present; priority order; every host is lowercase, no IP literal/wildcard/`testing-` host; every `landing_urls`/discovery URL is https on an allowed host; `approved` without approver/date/note is rejected; `approved` + `content_policy = none` rejected; `restricted` never allows access; no shipped source is `approved`; duplicate keys rejected; crawl delay below 10 rejected; ASB lists `/content/dam/asb/documents/` as a blocked prefix; RBNZ is `restricted`; ANZ is `metadata_only`.
- [ ] Implement loader with fail-closed validation; write the TOML from the assessment table (unprobed fields stay empty, never guessed).
- [ ] Commit.

### Task 3: URL safety and robots

**Files:** Create `research/safety.py`; Test `tests/research/test_safety.py`.

**Interfaces:** `UnsafeUrl(ValueError)`; `normalise_url(url: str) -> str`; `HostPolicy(allowed_hosts, resolver=None)` with `check(url) -> str`; `RobotsRules.parse(text: str, agent: str) -> RobotsRules` with `allowed(url_path_query: str) -> bool`, `crawl_delay: float|None`; `RobotsRules.DENY_ALL`, `ALLOW_ALL`.

- [ ] Tests: http rejected; userinfo rejected; port 8443 rejected; `localhost`, `127.0.0.1`, `[::1]`, `169.254.169.254` rejected; host not on list (including look-alike `www.anz.co.nz.evil.test`, `anz.co.nz@evil.test`) rejected; resolver returning a private address rejected; trailing dot/uppercase normalised; robots: group selection (specific agent beats `*`), longest match wins, `Allow` beats `Disallow` on ties, `*` and `$` wildcards, empty `Disallow` allows, comments/CRLF/BOM, Treasury and ASB real rule excerpts behave as recorded.
- [ ] Implement; commit.

### Task 4: Fetcher hooks and `ResearchFetcher`

**Files:** Modify `sources/fetcher.py` (two optional ctor args); Create `research/fetch.py`; Test `tests/sources/test_fetcher_limits.py`, `tests/research/test_fetch.py`.

**Interfaces:** `Fetcher(..., max_bytes: int|None=None, url_check: Callable[[str], None]|None=None)`; `ResearchFetcher(inst, client, *, pacer, sleep, clock, now, resolver=None, max_bytes=...)` with `get(url, *, expect=()) -> FetchResult`, `robots_for(url) -> RobotsRules`.

- [ ] Tests (existing fetcher tests must stay green untouched): oversized body aborts with `unexpected` and nothing buffered beyond the cap; `Content-Length` over cap rejected before reading; default path unchanged; `url_check` runs on each redirect hop and an `http://` downgrade is refused; research: robots 403 → deny all and source marked access-restricted, 404 → allow all, 5xx → deny this run, disallowed path never requested (assert `site.requests`), robots fetched once per host per run, a host outside the allowlist never requested, per-institution cooldown does not block another institution or Stats NZ.
- [ ] Implement; commit.

### Task 5: Publication dates

**Files:** Create `research/dates.py`; Test `tests/research/test_dates.py`.

**Interfaces:** `PublishedDate(on: date, at: datetime|None, precision: Literal["instant","day","month"])`; `parse_published(text: str, *, now: datetime) -> PublishedDate`; `date_from_url(url: str, regex: str, fmt: str) -> PublishedDate|None`; `DateParseError(ValueError)`.

- [ ] Tests: `13 August 2026`, `13 Aug 2026`, `August 2026` (month), ISO date, ISO with `+12:00`/`+13:00`/`Z`; `2026-09-26T12:30:00Z` → `on == 2026-09-27` (NZ) and `at` in UTC; across the 27 Sept 2026 DST change; naive datetime treated as NZ local; future beyond 1 day rejected; before 2000 rejected; `ANZ-QEO-20260813.pdf` and `Weekly-Commentary_191026_report_19Oct26.pdf` filename dates; invalid day (`31 Feb`) rejected; date-only never produces `at`.
- [ ] Implement; commit.

### Task 6: HTML extraction

**Files:** Create `research/extract.py` (types, limits, text normalisation), `research/extract_html.py`; Test `tests/research/test_extract_html.py`; fixtures `tests/fixtures/research/*.html` (synthetic).

**Interfaces:** `Section`, `Extracted`, `ExtractionLimits`, `extract_html(body: bytes, content_type: str, limits: ExtractionLimits) -> Extracted`; `EXTRACTOR_VERSION = "html-1"`.

- [ ] Tests: title from `og:title` then `<title>` then `<h1>`; published hint from `article:published_time`, `<time datetime>`, JSON-LD `datePublished`; `<main>`/`<article>` preferred, nav/header/footer/script/style/form/aside removed; sections split at h1–h3 with ordinals; charset from header, meta and BOM, invalid bytes replaced; control characters and zero-width/bidi marks stripped, NFC; script content and HTML comments never appear in text; prompt-injection text is kept verbatim as text (flagged `untrusted=True`) and not interpreted; deeply nested/unclosed tags and a 5 MB page are bounded by limits; `text_sha256` stable across whitespace-only changes.
- [ ] Implement with `html.parser`; commit.

### Task 7: PDF extraction

**Files:** Create `research/extract_pdf.py`; Test `tests/research/test_extract_pdf.py`; helper `tests/research/pdf_support.py` building minimal valid PDFs.

**Interfaces:** `extract_pdf(body: bytes, limits: ExtractionLimits) -> Extracted` (one `Section` per page group split at heading-like lines, always with `page_start/page_end`); `EXTRACTOR_VERSION = "pdf-1"`.

- [ ] Tests: text and page numbers preserved; encrypted PDF → `blocked`; image-only PDF (no text) → `validation_failed("no_text_layer")`; truncated/garbage bytes → `layout_changed`; non-PDF with PDF content-type rejected by magic bytes; page and char caps enforced; missing `pypdf` yields a clear `unexpected("pdf_support_not_installed")` (monkeypatched import).
- [ ] Implement; commit.

### Task 8: Discovery

**Files:** Create `research/discover.py`; Test `tests/research/test_discover.py`; synthetic RSS, Atom, sitemap and ANZ/Westpac/NZIER-shaped listing fixtures.

**Interfaces:** `Candidate(url, title, published_hint, series)`; `parse_rss`, `parse_sitemap`, `parse_html_links(body, base_url, link_pattern)`; `discover(inst, fetcher) -> list[Candidate]` (deduplicated by `normalise_url`, host-checked, robots-checked, capped).

- [ ] Tests: RSS 2.0 and Atom parsed; `<!DOCTYPE`/`<!ENTITY` bodies rejected (billion-laughs sample) before parsing; sitemap index not followed off-host; link pattern selects only matching URLs; relative and protocol-relative links resolved; `javascript:`/`data:`/`mailto:` dropped; duplicate and tracking-parameter variants collapse; off-allowlist links dropped and counted; manual mechanism returns nothing without network.
- [ ] Implement; commit.

### Task 9: Validation and ingest orchestration

**Files:** Create `research/validate.py`, `research/ingest.py`; Test `tests/research/test_ingest.py`, `test_validate.py`, `tests/research/support.py` (fake institution site).

**Interfaces:** `validate_document(inst, extracted, published, previous: PreviousVersion|None, now) -> None` (raises `IngestError`); `run_institution(conn, artifacts, inst, fetcher, *, now_fn, dry_run=False, limit=None) -> RunResult`; `RunResult.items: list[ItemOutcome]`, `ItemOutcome.outcome in {"new","updated","unchanged","reactivated","duplicate","link_only","skipped_robots","skipped_unsafe","failed"}`.

- [ ] Tests: a not-approved or `none`-policy institution makes **zero** requests; `needs_review` allows discovery-only dry run; `metadata_only` stores a publication with `content_status='link_only'` and never requests the document URL; `full_text` happy path HTML and PDF; unchanged re-run adds no version; changed text adds version 2 and marks version 1 superseded; revert A→B→A reactivates; same text at a second URL → `duplicate` with `duplicate_of_id`; 403/login/paywall/challenge body → recorded failure, health degraded, previous version still current; truncated text (<50% of previous) rejected; below `min_text_chars` rejected; 404 on a known document → recorded, content kept; network failure retried then recorded; `Retry-After` honoured; cooldown after a block stops the run; one bad document does not stop the rest; `max_documents_per_run` honoured; publication date from page vs URL vs sitemap disagreeing by more than a day is recorded as a warning on the item and the page value wins; `reference_period` stays NULL; `research_run_item.detail` never contains upstream text; the run is atomic per document (inject a failure mid-write and assert no partial version).
- [ ] Implement; commit.

### Task 10: Phase 3B contract and deterministic verifier

**Files:** Create `research/contract.py`; Test `tests/research/test_contract.py`.

**Interfaces:** pydantic models `EvidenceRef(version_id, section_ordinal, page|None, quote)`, `ForecastClaim(indicator, horizon, value, unit, direction, qualification, evidence)`, `OutlookSummary(...)`, `ModelProvenance(provider, model, prompt_version, processing_version, parameters, input_text_sha256, created_at)`, `LlmLimits`, `Provider` Protocol, `DisabledProvider`; `verify_summary(summary, sections: Mapping[int, str]) -> list[str]` (empty means every claim is supported).

- [ ] Tests: quote must be a verbatim (whitespace-normalised) substring of the cited section; a forecast number absent from its quote is reported; unknown section ordinal reported; claim without evidence rejected by the model; `DisabledProvider` raises; no import of `anthropic`/`openai`/network modules from the package (AST test); output is labelled `not_official_statistic=True` and has no path into `series`/`observation`.
- [ ] Implement; commit.

### Task 11: CLI

**Files:** Modify `cli.py` (a `research` command group); Test `tests/research/test_cli.py`.

**Interfaces:** `nzstats research sources`, `research discover KEY`, `research ingest KEY [--limit N] [--dry-run]`, `research status`. Exit non-zero on refusal or failed items; refusal text names the reason (`restricted`, `needs review`, `policy none`).

- [ ] Tests: `sources` lists all ten with status; `ingest rbnz` refuses without any request; `ingest` on an approved fixture institution (injected fetcher) succeeds; `status` shows health. Existing CLI tests untouched.
- [ ] Implement; commit.

### Task 12: Protect the publication path and Stats NZ behaviour

**Files:** Test `tests/research/test_isolation.py`, `tests/publish/test_research_isolation.py`.

- [ ] Tests: AST import-boundary test (no Stats NZ package imports `nzstats.research`); with research rows present (a full publication, version and sections), `export_snapshot` output is byte-identical (same `snapshot_id`) to export without them; `is_stats_nz_url` rejects ANZ/Treasury/RBNZ URLs; a stray `research/x.json` listed in a snapshot manifest yields a validation error, not an uncaught exception (fix `kind_of` handling if it crashes); API `health`, `overview`, `releases` JSON identical before and after research ingest; `FIXTURE_DATA`/provenance behaviour unchanged.
- [ ] Commit.

### Task 13: Docs, packaging and verification

**Files:** Modify `pyproject.toml` (extra `research = ["pypdf>=5"]`, add to `dev`), `.github/workflows/ci.yml` only if needed, `docs/architecture.md`, `docs/data-sources.md`, `docs/netlify-deployment.md` (secure extension), `docs/progress.md`; Create `docs/data-sources/research.md` (runbook), `docs/superpowers/plans/2026-10-25-phase-3b-llm-summaries.md`.

- [ ] Run: `cd backend && pytest && ruff check . && ruff format --check .`; frontend `npm test && npm run typecheck`; `scripts/e2e_static.sh` and snapshot export/validate if the environment allows; record exact results in `docs/progress.md`, including what could not be run.
- [ ] Open a focused PR from `feat/phase-3a-research-sources`; do not merge or deploy.
