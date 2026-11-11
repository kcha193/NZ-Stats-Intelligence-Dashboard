# Phase 4AE: bank research permissions matrix

10 November 2026, Pacific/Auckland. Baseline main `86a4515`.

**No bank is permitted for any use. No live ingestion, discovery, storage or processing of bank material has happened or is
possible, and this phase changed no permission field.** Everything in the bank capability was built and proven offline on
synthetic documents. Evidence below is the registry's record (`config/research_sources.toml`); **no new web read was made in
this phase**, so anything the registry marks `none` or `search` is *not examined*, not "cleared".

Discovery, acquisition, storage, local model processing, hosted model processing and display are separate decisions in the
registry. Public availability is not permission. Robots permission is not copyright permission. Permission to download is not
permission to send content to an outside AI provider. A 403 or challenge is never worked around.

## State by bank

| Bank | `review_status` | `content_policy` | Landing page (registry) | Robots | Terms | Verified on |
|---|---|---|---|---|---|---|
| ANZ New Zealand | needs_review | metadata_only | anz.co.nz/about-us/economic-markets-research/ | read (`direct`): no Disallow, names a sitemap | read (`direct`): all rights reserved; store solely for viewing; not for public display or distribution; links need prior permission; silent on automated access | 2026-10-25 |
| ASB | needs_review | metadata_only | asb.co.nz/documents/economic-research.html | read (`direct`): disallows `/content/dam/asb/documents/` (where report PDFs live) and about 200 named bots | not read (`none`) | 2026-10-25 |
| BNZ | needs_review | none | bnz.co.nz/institutional-banking/research/publications (owner-supplied 2026-11-10, **not probed**) | not examined (`none`) | not examined (`none`) | 2026-10-25 |
| Westpac New Zealand | needs_review | metadata_only | westpac.co.nz/business/business-base/economics/economic-reports/ | refused (`direct_blocked`): HTTP 403 to the probe | not read (`none`) | 2026-10-25 |
| Kiwibank | needs_review | none | kiwibank.co.nz/business-banking/thrive-hq/kiwi-economics/ (owner-supplied 2026-11-10, **not probed**) | not examined (`none`) | not examined (`none`) | 2026-10-25 |

## What each separate decision stands at

For all five banks: automated discovery **refused**; automated acquisition **refused**; local storage by the crawler
**refused**; owner-supplied manual import **denied** (`manual_import = denied`); local model processing **denied**
(`llm_processing = denied`); hosted model processing **denied**; internal display **none** (`private_display = none`, and the
internal draft gate also requires `content_policy = full_text`, which no bank has); public display **none**. A test pins every
one of these (`backend/tests/research/test_bank_registry.py`).

## Unresolved, per bank

- **ANZ.** The terms restrict linking and onward use; ask ANZ before approving even metadata links. Terms say nothing on
  automated access. No RSS; series pages are HTML with PDF links.
- **ASB.** Report PDFs are robots-blocked, so only HTML report pages could ever be reachable. The reports listing page is
  script-rendered; no discovery mechanism is verified. Terms not read.
- **BNZ.** No evidence of any kind. Establish the official research page, read robots and terms.
- **Westpac.** Robots and the landing page returned 403. Report PDFs are on a separate host (`assets.dam.westpac.co.nz`), which
  needs its own robots check. Terms not read.
- **Kiwibank.** No evidence of any kind. The owner-supplied URL replaces an earlier search-result URL; neither was fetched.
- **RBNZ and Treasury** keep their own, separate manual-import and processing arrangements; nothing here widens them.

## External prerequisites for any live bank (not done; not requested by this phase)

For each bank the owner must independently: read robots.txt and the terms in a browser and record the evidence and date;
obtain written permission where the terms require it; approve `review_status` and `content_policy`, and, separately,
`manual_import`, `llm_processing` (with a version-scoped hosted consent if hosted) and private display; add a policy scope if a
paid request is ever wanted. Scheduling any bank crawl is a further, separate approval. Until then the dashboard shows each
bank as "No access granted".
