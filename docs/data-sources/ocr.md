# Official Cash Rate: access assessment

Status on 28 October 2026: **blocked. No OCR data is acquired, stored, served or published.** Design:
[Phase 4C spec](../superpowers/specs/2026-10-28-phase-4c-macro-data-design.md).

## What the official source is

The OCR is set by the Reserve Bank of New Zealand (RBNZ). Its decisions and the historical rate are published on
www.rbnz.govt.nz, as statistical tables distributed as `.xlsx` files and in monetary policy announcements.

## Evidence on access (no request was made to RBNZ in Phase 4C)

| Evidence | Source | Strength |
|---|---|---|
| robots.txt and pages returned HTTP 403 to the project's probe | Phase 3A probe, 25 Oct 2026 (`config/research_sources.toml`, `rbnz`) | Direct, but about the publications pages |
| Terms of use (`/about-our-site/terms-of-use`) restrict automated access without prior written permission, except search engines obeying robots.txt | Search summary only (Phase 3A) | Indirect: the page has never been read directly |
| The terms page is the copyright reference for RBNZ statistics; statistics are `.xlsx` files; repeated automated downloads may require RBNZ to whitelist an IP address on request | Third-party R package documentation (CRAN `RBNZ`), web search 28 Oct 2026 | Indirect, not RBNZ's own words |

There is therefore no documented decision that permits automated access to the OCR statistics, and the evidence that
exists points the other way. The restricted institutional-commentary crawler (`research/`) is not used for this and its
safeguards are unchanged.

## What was built instead

- `nzstats/ocr/model.py`: decisions with separate announcement and effective dates, the rate in force on a date,
  changes in basis points, month-end and calendar-day monthly-average observations (only for wholly covered months).
- `nzstats/ocr/parse.py`: a strict CSV contract (`announced_on,effective_on,ocr_percent,change_bp,decision,source_url`)
  for decisions taken from an approved source; it refuses any file marked `SYNTHETIC`.
- Tests on `backend/tests/fixtures/ocr_SYNTHETIC_decisions.csv`: invented decisions dated 2031, so they cannot be mistaken
  for history. Tests also prove the module has no network code and that no production module reads the fixture.

Nothing wires the module into ingestion, the API, the snapshot or a page. The Economic Outlook states that OCR forecasts
cannot be evaluated because no official OCR series is ingested.

## Why the dates matter

A decision announced on a Wednesday usually takes effect the next day. A month with a decision has a month-end rate that
differs from its average rate. A forecast "for the OCR in March" therefore needs to say whether it means the decision,
the rate in force at month end, or the average; the outcome matcher will match only the stated one.

## To unblock (owner decision required)

1. Read RBNZ's terms of use and any statistics licence directly in a browser and record what they say, with the date.
2. Choose an access method the terms permit: a manual download of the official table by a person, written permission
   for automated access (possibly with IP whitelisting), or an official API if one exists.
3. Record the decision here and in `docs/progress.md`, then add an adapter that converts the official table into the
   contract above, test it on a real excerpt, and only then wire it into ingestion.
