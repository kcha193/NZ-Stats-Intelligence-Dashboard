# Phase 4P: internal draft mode

2 November 2026, Pacific/Auckland. The owner asked to see research output in the dashboard for internal use, accepting
that it need not be fully accurate, and chose to keep the labelled draft presentation after a one-off local view.

**This changes a project rule.** Until now, a summary that failed verification or had no reviewer approval was never shown,
labelled or not. It can now be shown in one narrow case: on this machine, behind its own switch, when the owner has named
it, and with its failed checks visible.

## What it does

`nzstats serve --host 127.0.0.1 --internal-drafts` adds an "Internal drafts" section to the Economic Outlook page and a
draft page at `/economic-outlook/draft/{id}`. Each claim is marked "Failed checks", "Warning" or "No problem found" in words,
with the verifier's reason. A banner says the summary is unapproved and may have failed checks. The "Evidence checked",
"Human reviewed" and "Published here" badges never appear.

Phase 4Q adds a "Reports held" list in the same mode: each current report's title, institution, publication date and link, newest
first, whether or not a summary exists. A draft says when its institution has published a newer report. The list carries no
document text. See `phase-4q-treasury-feu-refresh.md`.

## The gate

`research/drafts.py` is the one gate, and `research/drafts_api.py` the only routes. A summary is shown only when all of these
hold, rechecked on every request:

| Rule | Why |
|---|---|
| The owner's list names it by id and exact output hash | A deliberate decision per output, which a different output cannot inherit |
| Its status is `verified` or `failed_verification` | A provider error or invalid output has nothing meaningful to show |
| No reviewer has rejected it | A rejection withdraws it |
| The document is current, not purged and not a duplicate | Same as the other gates |
| The institution is in the registry with `content_policy = "full_text"` and an allowed document address | Quotes are shown |
| No section reads like instructions to a model | The text may be manipulated |

The checks are rerun on each request, so the stored status is not trusted. `research summary ID` prints
`internal draft: yes`, or why not.

### The list

`data/internal-drafts.json` is git-ignored. A missing file means no drafts. A malformed file shows nothing.

```json
{"drafts": [{"summary_id": 3, "output_sha256": "<64 hex>", "approved_by": "<name>", "approved_on": "2026-11-02", "note": "<why>"}]}
```

Find the hash with `SELECT output_sha256 FROM research_summary WHERE id = ?`. Delete the entry to withdraw a draft.

## What does not change

- **Verifier and thresholds:** unchanged. Failed claims still fail, and a failed summary stays `failed_verification`.
- **Review status:** being listed is not a review. Summaries stay unreviewed until someone reviews them.
- **Public and private gates:** `public.py` and `private.py` are untouched and admit no draft. Being listed grants neither.
- **Source permissions:** no access, LLM, `public_display` or `private_display` setting changes. Every source stays as it was.
- **Snapshots and the public site:** the exporter's app has no draft routes and the static reader has no draft data. The route
  exists in the public bundle and says "This draft is not available".

## Protections

- Off by default. Without the flag, the routes answer exactly like an unknown path.
- Any non-loopback bind is refused, with no override, including the public-research acknowledgement.
- Requests need a loopback `Host`, a same-origin `Origin` and `Sec-Fetch-Site` when sent, and `X-NZStats-Client: dashboard`.
- GET only, over a read-only connection, with `no-store` and `noindex`.
- The response model is an allowlist. Raw model output, hashes, parameters, usage, cost and the owner's note have no field.
- Model text is rendered as text by React.

## Limits

- **Rights rest on the owner.** The list records the owner's decision to view their own processed copy on their own machine.
  It is not a licence review, and it does not permit showing anyone else. The dashboard has no login, so this is why
  the mode is loopback only.
- **"No problem found" is narrow.** It means the automated checks raised nothing. They test where a quote, number, unit and
  horizon sit in the document, not whether the summary is economically right.
- **The Outlook header still describes published research.** Its line "checked against each document and approved by a
  person" applies to the published feed. The draft section says plainly that it does not apply to drafts.
- **Draft routes are not in the published API.** Their frontend types in `frontend/src/api/drafts.ts` are hand-written and
  must follow `drafts_api.py`.

## Verification

Backend: `test_drafts.py`, `test_drafts_api.py`, plus bind, capability, CLI and exporter isolation tests. Frontend:
`DraftDetail.test.tsx` and `netlify.test.ts`. Layout was checked in a browser on synthetic data at desktop and phone
widths. The real Treasury draft was checked structurally, without reading its text: 18 claims, 7 failed, 1 warning, 10 clean,
no false badges, no outside requests, no console errors.

## Rollback

Stop passing `--internal-drafts`, and delete `data/internal-drafts.json` to withdraw every decision. There is no migration and
no database write.
