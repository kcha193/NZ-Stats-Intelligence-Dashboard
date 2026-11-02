# Phase 4Q: Treasury FEU refresh and offline accuracy checks

2 November 2026, Pacific/Auckland. Baseline: main `9332bd9`, after merged PR #42.

**The Fortnightly Economic Update dated 29 October 2026 is imported as its own document, and the dashboard names it the newest
Treasury report by its publication date. No OpenRouter request or summarisation run has processed it, and no AI summary of it is
stored.** The pipeline cannot send it: the source's LLM setting stays `denied`, and the pilot code refuses this version.

**One AI system has read it.** The Claude Code session doing this work read the full text of this report and the 15 October report,
through Anthropic's service, to do the owner's requested assessment, comparison and gold pack. That is outside the project's
hosted-processing gate and is not an approval under it.

This record covers the Treasury priority within Phase 4Q, and adds the first offline accuracy harness. The owner's wider Phase 4Q
brief, received afterwards, requires reports and model outputs to stay out of Claude Code's hosted context. This work happened before
that instruction. No model output was read, then or since. The wider work is recorded separately.

This record holds metadata only. Report text, quotes, values, gold and the comparison stay under ignored `data/`.

## Import

| Field | Earlier report | New report |
|---|---|---|
| Document date, publication date | 15 October, 19 October 2026 | 29 October, 2 November 2026 |
| Publication, version | 1, 1 | 3, 3 |
| Content SHA-256 | `63aaa9df…5483073` | `f39f10d7…3f4e6` |
| Text SHA-256 | `d5f72d5e…8dc4b` | `d2092d5b…3f57a5` |
| Pages, sections | 7, 7 | 5, 5 |
| Extraction | `review`: 4 undecodable characters | `review`: 3 undecodable characters, all bullet glyphs on page 1. No number or quote is affected |

- **Route:** the owner saved the PDF in Chrome. macOS download metadata records the Treasury address. `research import` ran after
  a verified backup. No crawler, spoofed client or scripted browser touched the site. An automated read of the publication page
  returned HTTP 403, and that refusal was respected.
- **Dates:** the owner stated the publication date. PDF metadata (created 2 November 2026, 11:35 NZDT) and the series' Monday cadence
  are consistent with it. The agent could not read the publication page.
- **History:** against the backup, the import added rows only: 1 raw artifact, 1 publication, 1 version, 5 sections, 1 audit row, and
  updated the institution's `synced_at`. All LLM tables are row-for-row identical, so the Phase 4O summary, attempts and spend stand.

## Rights

| Question | Finding |
|---|---|
| Is manual import permitted? | Yes. The owner's registry decision of 2026-10-31 stands, and no permission changed |
| Item-specific notice in the PDF? | None, by text extraction and by rendering every page |
| Publication page read? | **No, HTTP 403.** The owner should check it in a browser |
| Third-party content? | Yes: charts and tables credit other organisations, including a commercial data vendor. Crown crest on page 1 |
| Does that block storage? | No. It does block treating the whole report as freely displayable or sendable |

## Dashboard

Under `serve --internal-drafts` only (loopback, no change to any gate), the Outlook page gains **Reports held**: every current
report by title, institution and publication date, newest first, with "Newest" per institution. A report with no summary is listed
as such. A draft now says when its institution has published a newer report. Details: `phase-4p-internal-drafts.md`.

"Newest" comes from `published_on`, never import order. Undated reports are listed last and are never newest. The list shows no document
text. The public site, static snapshot, public gate and private gate are unchanged.

## Accuracy checks

`research check-gold --pack FILE` (`research/gold_check.py`) runs offline and calls no model:

- **Gold check.** Binds to a version's id and both hashes, so gold for one report cannot score another. Tests dates, each quote on
  its page, value and period inside the quote, issuer near the quote, and relative dates resolved from the document date.
- **Verifier probes.** True claims, then corrupted copies, through the real verifier. A corruption counts only when its true claim
  passed. These measure the checks, not any model.

Claude Code wrote the pack for version 3 before any pipeline summary existed. **It is an AI reading, not human gold, until the owner reviews it.** `research evaluate` prints "human annotation" for every annotation file, so read that label with this in mind. Nothing is reused from the 15 October gold.

### Result on version 3

| Measure | Result |
|---|---|
| Gold check: 26 items, 4 relative dates | 0 problems |
| True claims accepted | 17/26 (forecasts 4/4, views 2/2, facts 11/19, decision 0/1) |
| Corruptions caught, of those measurable | 57/59 |
| Corruptions not measurable, because the true claim was rejected | 45 |
| Caught by type | wrong value 15/15, wrong page 17/17, foreign evidence 17/17, wrong period 3/3, added year 3/3, wrong issuer **2/4** |

Hand-written claims on one document. These are small denominators, and they are not a model score.

### Findings

1. **Issuer gap (most important).** Both misses relabel a third party's forecast as Treasury's own, and the verifier accepts it. In
   a Treasury report, that is the error that turns a central bank's or market's view into Treasury's. The checks catch the reverse.
   Until this is closed, "no problem found" says nothing about who holds a forecast.
2. **Phase 4O's period rule would not be enough.** `period_not_supported` rejected 5 of 19 true facts whose period was copied word for
   word, with "ambiguous or contradictory period" where a sentence holds a second period. Copying the period, the proposed Phase 4O
   option, would not clear those. Whether each should fail closed needs a person.
3. **Outturns next to forecast words.** `forecast_as_fact` rejected 3 true facts whose sentence also mentions an expectation.
4. **A decision reported second-hand cannot pass.** The verifier reads a vote written with a dash, not with this report's colon, does not treat its wording as a
   decision, and correctly finds no decision date near the quote. The right source for this decision is RBNZ's own stored release.
5. **Contract units.** No unit exists for a price per barrel, so one true fact fails `missing_unit`.

**No threshold, verifier rule or prompt changed.** These are measurements for a reviewed proposal, not grounds for loosening anything.

### Official data

Stats NZ figures in the report were compared by hand with the local official series. Most agree. Four could not be reconciled and
are recorded locally as unresolved, not as Treasury errors, because definition or method may differ. OCR claims were compared with the
stored RBNZ release, and two of Treasury's phrases go beyond that release's wording.

## Phase 4O findings carried forward

| Phase 4O finding | Status after this work |
|---|---|
| Truncation fix worked on one document | Unchanged, not retested |
| Gold could not show a good accepted result | Addressed for version 3: 4 forecasts, including third-party ones, can be accepted |
| Fact-period rejections | Sharpened: finding 2 |
| Treasury versus IMF labels unresolved | Sharpened: finding 1 |
| Summary thin at low effort | Unchanged, not retested |
| Human review of the rejected output | **Still pending** |
| Post-run key reading | **Still outstanding** |

## Before any hosted processing of this report

Nothing below is approved or built.

1. Owner approval specific to version 3: its hashes, approved sections and a fresh freeze. The consent for version 1 cannot apply.
2. A reviewed code change. `pilot.PILOT_VERSIONS` covers versions 1 and 2 only, and `freeze` on version 3 refuses (tested on a copy).
3. A rights decision on third-party content, possibly excluding the table pages.
4. Close or accept finding 1 first, or a run cannot show whose forecast is whose.
5. Spend check: lifetime attempts stand at 3 of 4, and the last one is also RBNZ's only remaining slot.

Any resulting summary stays unverified or a labelled internal draft until its gates are met. Naming it in `internal-drafts.json` remains
a separate owner decision per output hash.

## Verification and rollback

Backend, frontend, browser and gate results are in `progress.md`. To undo the import, use `research purge` with the version, or restore
the local backup `data/backups/pre-feu-2026-10-29-20261102T081515Z`.
