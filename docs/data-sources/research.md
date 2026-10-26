# Institutional research sources: registry and runbook (Phase 3A)

Economic commentary from banks, the Reserve Bank, the Treasury and research consultancies is a **separate domain**
from the Stats NZ statistics. It lives in `backend/src/nzstats/research/` and the `research_*` tables. The Stats NZ
API, the dashboard and the public snapshot never read it. Assessment and design:
[2026-10-25-phase-3a-research-sources-assessment.md](../superpowers/specs/2026-10-25-phase-3a-research-sources-assessment.md).

**Status on 2026-10-26: no source is approved, so nothing is fetched automatically.** Every source in
`config/research_sources.toml` is either `restricted` or `needs_review`. Nothing runs on a schedule: each request is a
deliberate `nzstats research …` command.

## The registry

`config/research_sources.toml` records, per institution, the allowed hosts, path prefixes, landing pages, discovery
mechanism, polling notes, licence and terms, what was verified and how, and the human approval. The loader fails
closed. A source is fetched only when **all** of these hold:

- `review_status = "approved"`, with `approved_by`, `approved_on` and `approval_note`;
- `content_policy` is `full_text` or `metadata_only`, never `none`;
- for `full_text`, the terms were read directly (`terms_evidence = "direct"`).

| Key | Review | Content policy | Discovery (verified?) | What blocks approval |
|---|---|---|---|---|
| `rbnz` | restricted | none | RSS for news releases only (no) | Terms (read via search only) restrict automated access without written permission; robots.txt and pages gave the probe a 403 |
| `treasury` | needs_review | full_text | publications listing (no) | Licence page (CC BY 4.0 per search) not read directly; `/publications` gave the probe a 403 |
| `anz` | needs_review | metadata_only | Economic Outlook PDF links (yes) | Terms forbid public display and require permission for links: ask ANZ |
| `asb` | needs_review | metadata_only | full reports list (no; probably script-rendered) | Terms not read; robots.txt disallows the PDF folder `/content/dam/asb/documents/` |
| `westpac` | needs_review | metadata_only | economic reports page (no) | robots.txt and pages gave the probe a 403; terms not read; PDFs on a second host |
| `nzier` | needs_review | metadata_only | Consensus Forecasts tag listing (no) | Terms not read; some material is members-only |
| `bnz`, `kiwibank`, `infometrics`, `deloitte` | needs_review | none | none | Not probed (Infometrics' main products are subscription) |

A probe 403 came from a generic client, not the project User-Agent, so it is **not** proof that the dashboard would be
refused. It is recorded as `direct_blocked`.

## Approving a source (checklist)

1. Read the institution's terms of use and copyright page **directly** (not a search summary). Record what they say about
   automated access, storage and republication in `licence` and `access_notes`, and set `terms_evidence = "direct"`.
2. Read its `robots.txt` for every allowed host. Put any disallowed prefixes that matter into `blocked_path_prefixes` too.
   If robots.txt sets a `Crawl-delay` above 10 s, raise `crawl_delay_seconds` to match, or the fetcher refuses the host.
3. Pick the least content you need: `metadata_only` (title, date, link, series; **the document body is never downloaded**)
   unless the terms clearly allow storing the text, which is what `full_text` does.
4. Run a discovery dry run (one listing request, no documents, nothing written):

   ```sh
   scripts/run.sh research discover treasury
   ```

   Check that the candidates are the reports you expect. Fix `link_pattern` or the listing URL, and set `verified = true`.
5. Set `review_status = "approved"` and fill `approved_by`, `approved_on` and `approval_note` (what you read, when, and the
   basis for the decision). Commit the change so the approval is reviewable.
6. Ingest a small batch, then check health:

   ```sh
   scripts/run.sh research ingest treasury --limit 2
   scripts/run.sh research status
   ```

Run commands where the database lives (`scripts/run.sh …` or `docker compose exec nzstats nzstats research …`). A bare
`nzstats` from `backend/` resolves `./data` to the empty development database.

PDF documents need the optional extra: `pip install -e 'backend[research]'` (`pypdf`). Without it, PDF items fail with
`pdf_support_not_installed` and HTML items still work. The Docker image installs it. The registry is baked into the
image (`NZSTATS_RESEARCH_SOURCES_FILE`), so approving a source in `config/research_sources.toml` takes effect in the
container only after an image rebuild.

## Commands

| Command | Requests | Writes |
|---|---|---|
| `research sources` | none | none |
| `research discover KEY` | robots.txt and the listing pages only. Allowed for `needs_review` (the deliberate first probe), never for `restricted` or policy `none` | none |
| `research ingest KEY [--limit N] [--dry-run]` | approved sources only: listing pages, then up to `max_documents_per_run` (default 5) documents, least recently attempted first so a longer listing is covered over successive runs | publications, versions, sections, run, items, health |
| `research status` | none | none |

A refused command exits 1 and names the reason (`restricted`, `needs review`, `content policy none`) before any HTTP client exists.

## What a run does

1. **Gate**: no recorded approval means zero requests.
2. **Discover** from RSS/Atom, sitemaps (child sitemaps on allowed hosts only) or listing-page links matching
   `link_pattern`. XML with a DOCTYPE or entity declaration is refused. Candidates are deduplicated by normalised URL
   (tracking parameters removed).
3. **Fetch** through the shared polite fetcher: one request at a time, at least 10 s apart. Each institution has its own
   pacer file (`data/.research-pace-<key>`), so a block or Retry-After stops that institution only, never Stats NZ.
   Every URL and every redirect hop must be https on an allowed host and path, resolve to public addresses only, and be
   allowed by that host's robots.txt (a 401/403 robots.txt denies everything; a 404 allows; anything else denies the
   run). Bodies are capped at 20 MB, decompressed size included.
4. **Extract**: HTML with the stdlib parser (main, then article, then body; scripts, forms, navigation, hidden elements
   and invisible characters removed; sections at h1–h3). PDF with `pypdf` in a resource-limited child process, one
   section per page so every reference has a page number. Encrypted PDFs are refused.
5. **Validate** (fail closed): login walls, paywall teasers and bot challenges are never stored; text below
   `min_text_chars` is rejected; a new version under half the stored length is treated as truncated.
6. **Store** each document in one transaction: a publication with a stable `doc_key`, a version per distinct text (a
   revert reuses the old version), and sections with offsets and pages. Raw bytes go to the content-addressed store.

Publication dates come from the page, then the file name, then the listing, and a disagreement of more than a day is a
warning. A date-only value is a New Zealand civil date with no invented time. `reference_period` is never derived
from a publication date.

## Outcomes and health

| Item outcome | Meaning |
|---|---|
| `new`, `updated`, `reactivated`, `unchanged` | stored as a new publication, a new version, a revert to an earlier version, or no change |
| `duplicate` | the same text is already stored under another URL; linked by `duplicate_of_id` and the exact matched version (`duplicate_of_version_id`, so a later revision of the original does not change it), no copy kept |
| `link_only` | `metadata_only` source: publication recorded, body not downloaded |
| `skipped_robots`, `skipped_unsafe` | refused before any request |
| `failed` | recorded with an error class and a fixed-vocabulary detail; the previous version stays current |

Health per institution (`research_source_health`) is `ok`, `degraded` (some items failed), `failing` (all items or
discovery failed) or `blocked` (403, challenge page or robots refusal; the run stopped). A block starts a 30 minute
cooldown for that institution.

## Licensing and publication rules

- Raw documents and extracted text are stored only locally, and only for `full_text` sources. Nothing from the research
  tables is published: the snapshot exporter does not read them, and the validator rejects any unknown file kind.
- Test fixtures are synthetic and marked `SYNTHETIC FIXTURE`. Never commit third-party report text.
- All extracted text is untrusted data. It is never rendered as HTML and never followed as instructions; Phase 3B
  prompts frame it as quoted data.

## Residual risks

- **DNS rebinding.** Closed for real requests: the research client resolves each host once per request, refuses any
  non-public answer (including NAT64, 6to4, IPv4-compatible and site-local forms) and connects to that exact
  address, keeping the original name for the Host header, TLS server name and certificate check. It ignores proxy
  environment variables, because a proxy resolves names itself. What remains is that the allowlisted hosts themselves
  are trusted, and that this path was checked by unit tests and by reading `httpcore`, not against a live TLS server.
- **PDF parser limits.** The child process has a timeout and CPU, memory and output limits, but macOS ignores the memory
  limit. Linux, where the container runs, enforces it.
- **Heuristic walls.** Login, paywall and challenge detection uses a fixed list of phrases near the top of the page. A
  teaser page with unusual wording and enough text could pass. The shrink guard and human approval limit the damage;
  check the first ingest of every newly approved source by hand.

## Rollback

The tables are additive and nothing outside `research_*` references them. To remove them (this deletes stored commentary):

```sh
scripts/backup.sh                       # Docker deployment; without Docker: scripts/run.sh backup data/backups/before-rollback.db
sqlite3 data/nzstats.db < scripts/rollback/004_research_down.sql
```

Stop (or downgrade) every process that runs the new code first: starting it again re-applies migration 004 and recreates
the empty tables. The script drops the tables but not the `raw_artifact` rows or the files under `data/raw`; those hold
third-party document bytes, so delete them too if the source's terms no longer allow storing them. Changing a source to
`restricted` or `metadata_only` likewise does not remove what was already stored.
