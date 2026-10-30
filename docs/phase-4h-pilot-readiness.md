# Phase 4H — live on-open acceptance and institutional economic commentary pilot

Status: **planning and owner-gated acceptance only**. Prepared 31 October 2026 (Pacific/Auckland) from main `2da9caf343db7ffe9ca0c0e731d95af300ccaceb`. The Phase 4G on-open refresh is merged, but its first real Stats NZ check has **not been verified** by this plan. Institutional research remains **NO-GO for live ingestion** until the source-specific permission and access gates are satisfied.

## Decision and boundaries

The owner wants a **local, on-open dashboard**, not a periodic ingestion scheduler. Netlify, public deployment, Docker, RBNZ acquisition, bank scraping and paid LLM calls are outside this pilot. This document grants **no permission** to fetch any institution, alter `config/research_sources.toml`, enable research display, connect a model provider or change production data. Do not merge this planning PR automatically.

The two independent acceptance paths are:

1. **Phase 4G live acceptance** — make one explicitly owner-approved live Stats NZ check on the owner's Mac; verify the existing on-open logic, backup and official-series identity. It uses the already merged code, not this branch.
2. **Phase 4H Treasury feasibility** — independently review licence, each chosen publication's copyright, robots/access rules and approved acquisition route. Then, and only then, request a *separate* bounded live pilot approval.

### Stage A — First real Stats NZ on-open acceptance (owner's Mac only)

**Gate A0: backup before a possible schema migration.** At last audit production was at schema 10 or 11, while Phase 4G adds migrations 012 and 013. The new `scripts/run.sh backup --bundle` goes through the CLI and may migrate its database *before* backing it up; do not use it as the sole pre-migration backup of an unmigrated production database.

Use an already verified pre-4G backup, or first take a read-only SQLite online backup plus the full raw tree without starting the new runtime. An example, from the repository root after stopping other dashboard processes, is:

```sh
DEST="data/backups/pre-4g-$(date +%F-%H%M)"
mkdir -p "$DEST"
python3 - "$DEST/nzstats.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("file:data/nzstats.db?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[1])
src.backup(dst)
assert dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
dst.close()
src.close()
PY
cp -R data/raw "$DEST/raw"
PYTHONPATH=backend/src python3 - "$DEST" <<'PY'
import hashlib, sys
from pathlib import Path
from nzstats.store.backup_check import verify_backup

dest = Path(sys.argv[1])
report = verify_backup(dest / "nzstats.db", raw_dir=dest / "raw",
                       live="data/nzstats.db", allow_older_schema=True)
if not report.ok or report.count_differences:
    raise SystemExit(f"Backup verification failed: {report.problems}; counts: {report.count_differences}")

def hashes(root):
    if not root.is_dir():
        raise SystemExit(f"Missing raw directory: {root}")
    return {p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}

if hashes(Path("data/raw")) != hashes(dest / "raw"):
    raise SystemExit("Raw tree does not match the live copy")
print(f"Verified backup at schema {report.schema_version}; row counts and raw hashes match")
PY
```

The verifier checks SQLite integrity, foreign keys, schema objects for the recorded version and referenced raw files; the additional comparisons require matching live row counts and the complete raw tree. It does not migrate either database. Keep other dashboard processes stopped throughout the copy and verification. If verification fails, **STOP**; preserve the original database and files. This copy is a preflight backup, not a Phase 4F manifest bundle. Do not assume copying `nzstats.db` directly is sufficient while SQLite WAL is active.

**Gate A1: deliberate live access.** The user must explicitly authorise the first live check against Stats NZ before opening the normal dashboard. Once approved:

```sh
scripts/run.sh status --json        # read-only; may report schema behind
scripts/run.sh                     # local server; on-open default
# Now open http://localhost:8000 in a local browser.
```

Browser opening triggers a bounded network check; simply starting the server or reading status does not. The check uses the existing 10-second minimum pacing, recent-check/cooldown limits and single-flight protection. The first check may make approximately four calendar requests plus bounded downloads for eligible missing releases. Observe the header and `GET /api/refresh/status`; do not manually send an unprotected POST or bypass its origin checks.

**Gate A2: reconcile outcome.** Collect exact commit/schema, timestamps in NZDT, URLs/host categories (not secrets), logical GETs vs HTTP attempts, discovered/missing/ingested/unchanged/pending, failures, and beginning/ending counts. Verify that zero new releases means no new vintages or changed historical observations. If new releases were validated, independently reconcile published figures and version/provenance, confirm verified pre-refresh backup and refresh the dashboard. If blocked, interrupted or invalid, preserve last-known-good and report NO-GO without repeated retries.

Do not confuse a technically successful calendar check with verification of an unseen new release. Keep the two outcomes distinct.

### Stage B — Treasury research feasibility, **no crawling yet**

Current registry: `treasury` is `needs_review`, with `content_policy=full_text` but `terms_evidence=search`, `llm_processing=denied`, `public_display=none`; the previous automated access probes returned 403. All ten institutional sources lack live approval, and previous production audits reported empty research tables.

**New external-source information reviewed in preparing this plan** (these links can be checked in a browser, but are not evidence that the owner's crawler can access them):

- [Treasury copyright and licensing](https://www.treasury.govt.nz/copyright-and-licensing): most Crown-owned material defaults to CC BY 4.0; exceptions for non-Crown content, logos, trademarks and design. Review each report's own copyright notice. Copyright re-use permission is **not** an automatic-access permission.
- [Treasury research and commentary](https://www.treasury.govt.nz/publications/research-and-commentary): current commentary series include Fortnightly Economic Updates and Rangitaki; Monthly Economic Indicators are listed among discontinued series.
- [Fortnightly Economic Updates](https://www.treasury.govt.nz/publications/research-and-commentary/fortnightly-economic-updates): use this **specific recurring collection** as the pilot discovery target, rather than a general `/publications` crawl.
- [15 October 2026 update](https://www.treasury.govt.nz/publications/feu/fortnightly-economic-update-15-october-2026): signed 15 October, issued 19 October; page has an HTML summary and linked PDF. Verify original report's per-item rights and source/date. Do not treat the HTML summary as the full paper.

**Gate B1: independent rights/access review.** Have the owner review the exact official terms in their browser; record retrieval date and URL, exact relevant passages, the individual report's rights, any applicable access restrictions, all required hosts' `robots.txt`, and a no-bypass request policy. Some browsing clients can read pages while a project HTTP client gets 403; this does not authorise bypassing a block or robots restrictions. Do not change `terms_evidence`, `review_status`, `manual_import` or `llm_processing` based only on this planning document. Request approval before the first controlled project-client discovery probe.

**Gate B2: choose route only after review.** Options: approved, rate-limited metadata discovery and storage; approved full-text acquisition if licensing/robots/access permit; separately approved owner-supplied manual import if website access is blocked but local storage rights exist. The existing `research discover`, `research ingest --limit 2`, `research readiness`, `research quality`, `research manual-import` and audit tools should be reused. No live institution request until the owner grants the specific route and the registry gates are satisfied.

**Gate B3: model-processing decision.** No LLM provider configured and all `llm_processing` gates are denied. The pilot can assess source metadata and extraction without LLM calls. If a legal route supports model processing, prefer an explicitly approved local model first; require independent annotations for 2–3 papers, run a dry-run, verify every claim/number/quote/source offset, compare to Stats NZ with the correct data vintage and avoid lookahead. Never enable a hosted provider or paid call implicitly.

**Gate B4: private UX.** Only after validated ingestion and review should the local Economic Outlook surface the Treasury's latest dated, source-linked findings. Distinguish institutional opinion, forecast and official statistic. Preserve `public_display=none`; do not enable the public research API to make a private pilot visible. If the current research routes require a review-gated private preview, design and test it separately with loopback-only and explicit approval. Never publish research in static snapshots.

### Acceptance and review

- **A is GO** only for a completed, bounded live check with independent data/provenance reconciliation and verified backup; otherwise record GO WITH CONDITIONS or NO-GO with exact evidence.
- **B is GO for a controlled pilot** only when access, storage and source-specific permission are documented and approved, robots are respected, a bounded single-source path is available, and no restriction is silently relaxed. A planning document or CC BY licence alone is insufficient.
- **No expansion** to ANZ, ASB, Westpac, BNZ, Kiwibank, NZIER, Infometrics, Deloitte or RBNZ under this authorisation.
- Hosted Actions remain blocked by billing until a workflow actually executes; local tests are distinct evidence.
- Any implementation should be a separate narrow PR with failing-first tests and independent statistical/security review.
- Preserve the original public-release NO-GO report as historical evidence; Netlify is out of scope for these stages.

## Next operator handoff

Run the Stage A preflight and obtain consent for the one live check on the owner's Mac; this remote GitHub planning PR cannot execute against the owner's live database. In parallel, complete B1 as a read-only, source-specific rights review; do not run a Treasury crawler until the approval gates are documented.
