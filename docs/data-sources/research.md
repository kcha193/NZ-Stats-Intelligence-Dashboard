# Institutional research sources: registry and runbook (Phases 3A and 3B)

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

## LLM summaries and forecast claims (Phase 3B)

A stored document version can be summarised by a language model into a structured outlook (drivers, risks,
uncertainty, indicators) and explicit forecast claims. Every statement and claim cites `(version, section, page,
verbatim quote)`. The output is **interpretation of commentary, never an official statistic**, and it never reaches the
Stats NZ tables, the API or the public snapshot. Plan: [2026-10-25-phase-3b-llm-summaries.md](../superpowers/plans/2026-10-25-phase-3b-llm-summaries.md).

**Status on 2026-10-26: disabled.** No provider is configured and every source has `llm_processing = "denied"`, so
`research summarise` refuses. Nothing is scheduled.

### Two gates, both closed by default

1. **Source permission** (`config/research_sources.toml`): `llm_processing = "denied"` (default), `"local_only"` (a
   model on this machine only) or `"hosted"` (a hosted API as well). Sending text to a hosted model is processing by a
   third party: set `hosted` only after reading that the terms allow it, and record what they say in
   `llm_processing_note`. Any value but `denied` needs an approved `full_text` source. A version stored under another
   policy (its `licence_snapshot`) is refused too.
2. **Provider configuration** (environment only; the API key is never stored, logged or printed):

| Variable | Meaning |
|---|---|
| `NZSTATS_LLM_PROVIDER` | `disabled` (default), `anthropic`, or `openai_compatible` |
| `NZSTATS_LLM_MODEL` | required, for example `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, or a local model name |
| `NZSTATS_LLM_API_KEY` | required for `anthropic`; optional bearer token for `openai_compatible` |
| `NZSTATS_LLM_BASE_URL` | `openai_compatible` only: `https://…`, or `http://` on `localhost`, `127.0.0.1` or `::1`. Only a loopback URL counts as local; anything else is hosted. Refused for `anthropic` (fixed endpoint) |
| `NZSTATS_LLM_INPUT_USD_PER_MTOK`, `NZSTATS_LLM_OUTPUT_USD_PER_MTOK` | required prices per million tokens (0 for a local model) |
| `NZSTATS_LLM_MAX_RUN_USD` | worst-case spend allowed per run, retries included (default 1.00) |
| `NZSTATS_LLM_MAX_OUTPUT_TOKENS` | default 4000. Claude Opus 5.5 always thinks and its thinking counts as output: use 16000 |
| `NZSTATS_LLM_MAX_INPUT_CHARS` | default 60000; a longer document is refused (`input_too_long`), never truncated |
| `NZSTATS_LLM_TIMEOUT_SECONDS`, `NZSTATS_LLM_MAX_RETRIES`, `NZSTATS_LLM_MAX_DOCUMENTS` | defaults 120, 2, 5 |

The adapters call the Anthropic Messages API (`anthropic-version: 2026-10-21`, which rejects `temperature`, so none is
sent) or a `/chat/completions` endpoint (OpenAI, or llama.cpp, vLLM or Ollama on loopback) over plain HTTPS with httpx.
No vendor SDK is installed, so the Docker image is unchanged. Redirects are not followed and proxy variables are ignored.

### What a run does

1. Selects current versions (or `--version ID`, which may be superseded) whose source permits the provider's locality.
2. Frames the sections as untrusted data between delimiters with a random per-request boundary (prompt `outlook-v1`).
3. Skips a version already summarised for the same provider, model, prompt version, processing version (`3b-1`) and
   input hash. A provider error does not count, so it is retried next run as a new attempt.
4. Before **every** call, refuses if spent + worst-case cost of the call (input characters / 3 tokens, the full output
   cap) would exceed the run budget. Failed calls are charged with the usage the provider reported, or at the worst
   case unless the provider rejected them before generating (auth, bad request, rate limit, overload).
5. Retries timeouts, 408/409/429/5xx and network errors with backoff 2 s, 4 s … (at most 30 s), up to the retry limit.
6. Parses strictly (one JSON object; one code fence tolerated; duplicate keys, extra fields and oversized output
   rejected), verifies deterministically, and stores the summary, every call's usage and (verified only) the forecast
   claims in one transaction. Statuses: `verified`, `failed_verification`, `invalid_output`, `provider_error`.

### The verifier, and what it does not prove

Errors (they block approval): quote not verbatim in the cited section, wrong version, unknown section, page outside the
section, spliced or truncated quotes, evidence that reads like an instruction to a model, a value or any other number
not in a found quote, a value quoted as the previous forecast, missing or unknown unit, unit not stated next to the
number (including a share of GDP reported as plain percent), horizon not stated near the quote, fiscal versus calendar
year, quarterly versus annual change, a historical observation reported as a forecast, a scenario reported as the
baseline (or an invented scenario name), direction contradicting the wording, and an indicator that contradicts its
label. Warnings: weak lexical support, more certainty than the evidence, an indicator missing from the list, a horizon
with no period, a section that resembles instructions to a model.

**Passing means the deterministic checks found nothing. It is not a check of economic accuracy, completeness or
interpretation**; every inspect screen and stored report says so. Known blind spots, from the evaluation: an indicator
misclassified into a category whose keywords also match (a current account *deficit* filed as the fiscal balance), a
missed forecast (recall), a misread table row, and OCR-garbled text, where a model that tidies the quote is rejected.

### Commands

| Command | Calls a model | Writes |
|---|---|---|
| `research summarise [KEY] [--version ID …] [--limit N]` | yes, if both gates allow | summary, usage, claims, audit run |
| `research summarise … --dry-run` | no | nothing; prints the worst-case cost per document |
| `research summaries [--status S] [--review R]` | no | nothing |
| `research summary ID` | no | nothing; evidence, errors, warnings, scope statement, usage |
| `research approve ID --reviewer NAME [--note TEXT]` | no | review decision (verified summaries only) |
| `research reject ID --reviewer NAME --note TEXT` | no | review decision (final) |

Summaries are append-only (database triggers): content never changes, rows are never deleted, a new prompt or model
adds rows, a rejection is final, and only `verified` summaries can be approved. Every decision is kept in
`research_summary_review`. Model text is printed with control characters escaped.

### Review checklist

Read each claim's quote in context (`research summary ID` shows version, section and page). Check the horizon and its
basis (June year, quarter, annual average), whether the figure is a forecast or an outturn, baseline or scenario, the
unit, and whether a newer version of the document exists (`superseded` is shown). Reject with a note saying what was
wrong; summarise again to replace it.

### Cost

Prices from the Claude API model table (cached 2026-10-06; check before relying on them), per document:

| Model | Typical (16.5k input, 4k output tokens) | Worst case at the defaults (20k input estimate, 16k output) |
|---|---|---|
| `claude-opus-5-5` ($4 / $20 per MTok) | about $0.15 | $0.40 |
| `claude-sonnet-5-5` ($2 / $10) | about $0.07 | $0.20 |
| `claude-haiku-5-5` ($0.10 / $0.50) | under $0.01 | $0.01 |
| local model on loopback | $0 (hardware only) | $0 |

The synthetic evaluation documents are short (about 1,900 input tokens including the 5,000-character rules and
schema), so their replay cost is about $0.014 per document on Claude Opus 5.5 pricing. Ten real reports a week stay
under $5 at the worst case on Claude Opus 5.5 with the default run budget of $1.00 per run.

### Evaluation

`python ../scripts/evaluate_research_llm.py` (from `backend/`) replays the synthetic, hand-annotated set in
`backend/tests/research/eval_set/` through parsing, verification and the metrics: no network, no cost. `--live` sends
the same synthetic documents (never third-party text) to the configured provider; it costs money, so run it
deliberately and record the model, prompt version and results in `docs/progress.md`. The replay metrics are regression
floors in `nzstats.research.evaluate.RECORDED_BASELINE`.

### Rollback (Phase 3B only)

`sqlite3 data/nzstats.db < scripts/rollback/006_research_summaries_down.sql` removes the summary tables and keeps the
Phase 3A research tables (back up first, as below). The full research rollback below also removes them.

## Rollback

The tables are additive and nothing outside `research_*` references them. To remove them (this deletes stored commentary):

```sh
scripts/backup.sh                       # Docker deployment; without Docker: scripts/run.sh backup data/backups/before-rollback.db
sqlite3 data/nzstats.db < scripts/rollback/004_research_down.sql   # also drops the Phase 3B tables (006)
```

Stop (or downgrade) every process that runs the new code first: starting it again re-applies migration 004 and recreates
the empty tables. The script drops the tables but not the `raw_artifact` rows or the files under `data/raw`; those hold
third-party document bytes, so delete them too if the source's terms no longer allow storing them. Changing a source to
`restricted` or `metadata_only` likewise does not remove what was already stored.
