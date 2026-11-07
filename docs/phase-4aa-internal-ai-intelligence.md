# Phase 4AA: internal AI Economic Intelligence without human approval

8 November 2026, Pacific/Auckland. Baseline: main `b73e488` (PR #53 merged).

**No OpenRouter request, crawl, permission change, ledger change, historical record change or deployment.** The real-database
check below ran on a copy, offline (`--offline`), and printed ids, categories, counts and fixed labels only.

## The change

The owner reads the Economic Outlook page alone, on their own machine. Phase 4T already let unreviewed AI summaries be shown
through the internal draft gate (`research/drafts.py`, `auto_display`). Phase 4AA makes that the normal local experience:

| Before | Now |
|---|---|
| Drafts needed `scripts/run.sh --internal-drafts` on every start | A normal loopback start shows them when `data/internal-drafts.json` sets `auto_display` |
| The page showed internal drafts **and** an empty published-research section | One section, **AI Economic Intelligence**; published research appears only if any is published |
| The empty state listed three publication conditions, including "A person approves it" | The empty state says why nothing is shown (below); no approval checklist anywhere |
| Notice: "AI-generated research draft. Automated checks may miss errors. Not independently reviewed." | "AI-generated analysis for internal use. Claims are checked automatically against source documents but may contain errors. Not independently reviewed." |

### Human-review requirements removed from internal viewing

None of these is needed to read an eligible analysis on the local dashboard:

- a reviewer's approval (`review_status`), a publication decision or `public_display` permission;
- a human gold annotation (already optional since Phase 4T);
- a per-summary entry in `data/internal-drafts.json` (already optional with `auto_display`);
- passing every automated check: failed claims are shown, marked "Failed automated checks", with their reasons.

### What still excludes an output (unchanged gate)

Rejected by a reviewer, withdrawn by the owner, an unusable or incomplete response, a stored output whose hash does not match, a
response not from a reviewed route with the recorded privacy settings, a purged, superseded or duplicate document, a source whose
content policy, approval or host does not allow it, an output that no longer parses, and a document section that reads like
instructions to a model. A newer summary of the same document version replaces an older one.

## The page

1. **Latest economic outlook**: the newest current analysis, its overall view and uncertainty, each with its check result.
2. **Latest institutional commentary**: Treasury and the Reserve Bank, newest report each, or why there is no analysis.
3. **Key economic drivers and risks**, labelled as AI interpretation.
4. **Reported economic facts and institutional forecasts**: figures as the report states them (not the official series) and forecasts
   by issuer, third parties marked.
5. **Historical commentary**: analyses of reports the institution has since superseded.
6. **Source evidence and automated verification**: per analysis, errors and warnings, verifier, prompt and model, and an expandable
   list of every flagged claim with its reasons; the reports held. The full claim-by-claim evidence stays on the draft page.

Official Stats NZ observations remain the indicators at the top of the page. Wording never calls an analysis verified, reviewed or
approved; "no automated issue detected" is described as not verification.

When nothing can be shown, the section says which applies: automatic display is off (named-list mode), no document has been
imported, an AI response was unusable, an analysis exists but is withheld by the gate (new `withheld` flag on each held report, a
content-free boolean), or no analysis has been generated. If the server has internal analysis switched off (opt-out, no opt-in, a
non-loopback bind, the static site), the page shows the published-research view; its empty state no longer lists approval conditions.

## Startup

```sh
scripts/run.sh                         # loopback; shows AI analysis when data/internal-drafts.json sets auto_display
scripts/run.sh --no-internal-drafts    # this start only: no AI analysis, routes not mounted
scripts/run.sh --internal-drafts       # as before: force on (named list or auto_display), loopback only
```

`nzstats serve` resolves the switch before building the app: an explicit flag wins; otherwise it is on only when the bind is loopback
**and** the owner's file parses **and** sets `"auto_display": {"enabled": true, ...}`. A missing, malformed or named-list-only file
leaves it off. A non-loopback bind (the container's `0.0.0.0`) is never refused because of the opt-in; drafts simply stay off. To
turn the default off for good, remove `auto_display` from the file.

Unchanged: loopback-only bind for the draft routes (`--internal-drafts` on `0.0.0.0` still refuses to start), the Host, Origin,
`Sec-Fetch-Site` and dashboard-header checks, read-only routes, `no-store` headers, the static site (never asks for drafts), the
snapshot exporter (never includes research), and the Docker command.

## Independent boundaries kept

Opening the page starts no model request: a test replaces every provider's constructor and `summarise` with a failure and reads
the feed and a draft, and the usage table is unchanged. Treasury and RBNZ rights, per-document checks, `run-policy` confirmation,
ZDR and data-collection settings, spending and attempt limits, the append-only audit and the public and private gates are untouched.

## Verification (8 November 2026)

- Backend: serve opt-in, opt-out, malformed file, non-loopback and conflicting flags; no inference on open; `withheld` flag;
  updated notice. Full backend suite 5,880 pass; Ruff check and format pass; `npm audit --omit=dev` 0 vulnerabilities.
- Frontend: 562 unit tests (consolidated view, failed checks visible, no approval wording, empty-state reasons, off and static
  modes ask for no draft), typecheck, build. Lint has warnings only, of the existing fast-refresh kind.
- Playwright: default suite 186, synthetic published research 18 (3 skipped), static site and live/static visual parity 315
  (36 skipped).
- Real data, copy, offline, `scripts/run.sh` with no flag: capabilities `internal_drafts: true`; Treasury summaries 4 and 3 shown,
  both `failed_automated_checks`, not human reviewed; RBNZ report `unusable_response`; no checklist, no approval wording, no page
  errors, no horizontal scroll, no external request. `--no-internal-drafts`: capability false, drafts route 404. Public and private
  research routes 404. Usage rows unchanged (4). Screenshots are kept in ignored `data/phase-4aa/screens/` because they contain
  Treasury text.
