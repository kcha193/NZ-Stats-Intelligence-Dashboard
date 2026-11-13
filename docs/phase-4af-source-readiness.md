# Phase 4AF: bank source readiness

11 November 2026, Pacific/Auckland. Baseline `main` `a3a5449`.

**No live ingestion exists for any bank and no permission field was changed.** This page is the owner's working checklist
for deciding, bank by bank and decision by decision, what could be allowed. It is written from the registry's recorded
evidence (`config/research_sources.toml`, summarised in [phase-4ae-permissions-matrix.md](phase-4ae-permissions-matrix.md));
**no new web read was made**, so anything the registry marks `none`, `search` or `direct_blocked` is *not examined*, not
cleared. Public availability is not permission, robots permission is not copyright permission, permission to download is
not permission to parse, and a 403 or challenge is never worked around.

## 1. State by bank (from the registry)

| Bank | `review_status` | `content_policy` | Landing evidence | Robots | Terms | Verified on |
|---|---|---|---|---|---|---|
| ANZ New Zealand | needs_review | metadata_only | read (`direct`) | read (`direct`): no Disallow, names a sitemap | read (`direct`): all rights reserved; store solely for viewing; no public display or distribution; links need prior permission; silent on automated access | 2026-10-25 |
| ASB | needs_review | metadata_only | search results only (`search`) | read (`direct`): disallows `/content/dam/asb/documents/` (where report PDFs live) and about 200 named bots | not read (`none`) | 2026-10-25 |
| BNZ | needs_review | none | owner-supplied URL, not probed (`none`) | not examined (`none`) | not examined (`none`) | 2026-10-25 |
| Westpac New Zealand | needs_review | metadata_only | refused (`direct_blocked`): HTTP 403 | refused (`direct_blocked`): HTTP 403; PDFs are on a second host | not read (`none`) | 2026-10-25 |
| Kiwibank | needs_review | none | owner-supplied URL, not probed (`none`) | not examined (`none`) | not examined (`none`) | 2026-10-25 |

## 2. Evidence gaps, one decision at a time

Each of these is a separate registry decision; approving one never approves another. "Gap" is what is missing in the
recorded evidence for that decision, not a finding that it would be refused.

| Decision | What it covers | ANZ | ASB | BNZ | Westpac | Kiwibank |
|---|---|---|---|---|---|---|
| Automated discovery | the crawler listing a landing page | gap: terms silent on automation, links need prior permission | gap: listing is script-rendered, no verified mechanism, terms unread | gap: no evidence | gap: 403 on landing page and robots | gap: no evidence |
| Automated acquisition | the crawler downloading a report | gap: terms silent; robots allows | **refused by robots for PDFs** (`/content/dam/asb/documents/`); HTML report pages are not disallowed | gap: no evidence | gap: 403; PDF host `assets.dam.westpac.co.nz` needs its own robots read | gap: no evidence |
| Full-text storage (`content_policy = full_text`) | holding the whole text, not metadata | gap: "store solely for viewing" must be read against local analysis | gap: terms unread | gap: terms unread | gap: terms unread | gap: terms unread |
| Manual import (`manual_import`) | the owner saves a copy in a browser and imports it | gap: same reading of "solely for viewing" | gap: terms unread | gap: terms unread | gap: terms unread | gap: terms unread |
| Local model processing (`llm_processing = local_only`) | text read by a model on this machine | gap: not addressed by the terms | gap: terms unread | gap | gap | gap |
| Hosted model processing (`hosted`, plus a version-scoped consent and a `policy-*` scope) | text sent to an outside provider | gap: not addressed; a separate, stronger decision | gap | gap | gap | gap |
| Internal display | the loopback dashboard only | gap: "not displayed in public" is read as allowing private internal use; the owner must confirm | gap | gap | gap | gap |

**Table parsing** (Phase 4AF) is none of these: it is deterministic code run on a copy that is already held, adds no
processing destination, and needs exactly what holding and showing that copy needs (the route it came in by is still
permitted, and `content_policy = full_text`). The code enforces that and nothing weaker (`research tables extract` refuses
otherwise). If the owner reads a bank's terms as treating machine parsing as a separate use, that is a further decision and
no code change is needed: leave the source un-imported.

## 3. Bank-by-bank approval checklist

For each bank: the exact terms to read, the evidence to record, and the decision the owner still has to make. Nothing
below has been done; "record" means write the date, the page read and the wording in the registry entry's `access_notes`
and evidence fields, in a reviewed change.

### ANZ New Zealand

- **Terms to read.** The site terms on `www.anz.co.nz`: the clauses on reproducing and storing content "solely for viewing",
  on public display or distribution, and on links ("prior permission"). Re-read whether they say anything about automated
  access (the registry records that they do not) and about machine analysis of stored copies.
- **Evidence to record.** Date and URL of the terms read; the verbatim clauses; ANZ's written reply to a request that names
  the intended use (internal, local, no public display; automated retrieval or a hand-saved copy; local parsing of figures).
  Robots was read directly with no Disallow and a sitemap named; re-record the date.
- **Owner's pending decision.** (a) Whether a hand-saved copy parsed locally for internal analysis is "viewing". (b) Whether
  to ask for permission for automated retrieval. (c) Only if (a) is yes: `manual_import` and `content_policy = full_text`.
  Local and hosted model processing stay separate and denied.
- **Formats and paths once permitted.** Quarterly Economic Outlook PDFs named `ANZ-QEO-YYYYMMDD.pdf` under
  `/content/dam/anzconz/documents/economics-and-market-research/YYYY/` (adapter `economic_outlook`, expected every 100
  days); an HTML summary page links them. Path: owner-saved PDF -> `research import` -> `research tables extract` ->
  internal dashboard. A crawler path exists in the registry but is not approved.

### ASB

- **Terms to read.** `/documents/terms-and-conditions.html` (the registry's pointer; unread). Also whether HTML report pages
  under `/documents/economic-research/` carry their own terms.
- **Evidence to record.** The terms clauses; a browser check of the reports listing and where the quarterly forecast report
  appears; confirmation that PDFs are only reachable under the robots-disallowed path.
- **Owner's pending decision.** Automated PDF acquisition is refused by robots, so the only candidate path is a hand-saved
  copy, which needs the terms read first. HTML report pages are a different format (see section 4).
- **Formats and paths once permitted.** Report pages under `economic-weekly`, `quarterly-economic-forecasts` and
  `economic-insights` (HTML); PDFs under `/content/dam/asb/documents/` (robots-disallowed to bots). Table parsing needs a PDF
  with a text layer; HTML tables are not read by this phase.

### BNZ

- **Terms to read.** Everything: the site terms, the research publications terms, and robots.txt.
- **Evidence to record.** That `https://www.bnz.co.nz/institutional-banking/research/publications` (owner-supplied, never
  fetched) is the official page; the report series and cadence; the format (PDF or HTML); robots and terms with dates.
- **Owner's pending decision.** Whether to establish evidence at all. Until then the entry stays `none` throughout.
- **Formats and paths once permitted.** Unknown. No adapter series is defined beyond the registry's descriptive fields.

### Westpac New Zealand

- **Terms to read.** Site terms (unread). Robots for **both** `www.westpac.co.nz` and `assets.dam.westpac.co.nz`.
- **Evidence to record.** A browser read of both robots files and the terms. The 403 to the probe is recorded as a refusal and
  is not retried by a script or a changed client.
- **Owner's pending decision.** Whether to read the terms and robots in a browser and decide on that basis; there is no
  automated route to try.
- **Formats and paths once permitted.** Weekly commentary PDFs on `assets.dam.westpac.co.nz` (names carry dates as DDMMYY and
  DDMonYY); weekly notes are shown but never feed consensus or revisions (only quarterly outlooks do).

### Kiwibank

- **Terms to read.** Everything, as for BNZ.
- **Evidence to record.** That `https://www.kiwibank.co.nz/business-banking/thrive-hq/kiwi-economics/` (owner-supplied,
  never fetched) is the official page; the report series, cadence and format; robots and terms with dates.
- **Owner's pending decision.** Whether to establish evidence at all.
- **Formats and paths once permitted.** Unknown.

## 4. Formats and ingestion paths, once permitted

| Path | Needs | Reads | Notes |
|---|---|---|---|
| Hand-saved PDF -> `research import` -> `research tables extract` | `manual_import` approved and `content_policy = full_text` | tables with a text layer, deterministically | the recommended first path; no model |
| Same PDF -> `research summarise` | plus `llm_processing` (and for hosted, a version-scoped consent and a `policy-*` scope) | prose, by a model, checked by `verify-5` | independent of the table path; both can disagree, which is reported |
| Crawler (`research ingest`) | `review_status = approved`, a non-`none` content policy and the 10 second crawl delay | what the listing links to | not approved for any bank; scheduling is a further approval |
| HTML report pages | as above | text only; **HTML tables are not parsed** | a future extension, not built |
| Image-only or scanned PDF | n/a | nothing: reported as `no_text_layer` | OCR of bank reports is not authorised |

Recommended first pilot: [phase-4af-first-bank-pilot.md](phase-4af-first-bank-pilot.md). How the tables are read and what
they cannot read: [phase-4af-pdf-tables.md](phase-4af-pdf-tables.md). Operating it: [phase-4af-runbook.md](phase-4af-runbook.md).
