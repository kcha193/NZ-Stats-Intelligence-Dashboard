# Phase 4AG: ANZ permissions decision package

14 November 2026, Pacific/Auckland. For the owner. **Not legal advice, and not an authorisation.** Nothing in this phase
edited a permission field, contacted ANZ or fetched an ANZ page. The terms below are the registry's recorded reading
(verified 2026-10-25); the owner must re-read the current terms in a browser before relying on them.

## 1. What the record says today

| Item | Recorded state |
|---|---|
| Registry entry | `institutions.anz`: `review_status = needs_review`, `content_policy = metadata_only`, `manual_import = denied`, `llm_processing = denied`, `public_display = none`, `private_display = none`; no approver or date on any of them |
| Terms (`https://www.anz.co.nz/comms/website-terms-of-use/`) | "(c) ANZ Bank New Zealand Limited, all rights reserved"; reproduce and store **solely for viewing**; **not to be displayed or distributed in public**; links need **prior permission**; the registry records it as silent on automated access; whether machine analysis of a stored copy counts as "viewing" is **not addressed in the record** and must be read by the owner |
| Robots | read directly: no Disallow; names a sitemap |
| Routes | Economic Outlook page (HTML summary plus PDF links), quarterly PDFs `ANZ-QEO-YYYYMMDD.pdf`. The owner's brief says the research hub lists a forecasts workbook; **the registry has no record of it** and it was not evaluated |

## 2. Decisions, what each needs, and who can give it

"Owner" means a recorded, dated decision in a reviewed registry change. "ANZ" means a written reply from ANZ. Public
availability is not permission, and robots permission is not copyright permission.

| # | Decision | Sensible reading of the terms | Needs ANZ in writing? | What stays denied if unresolved |
|---|---|---|---|---|
| 1 | **Source terms and copyright.** May the owner keep a copy of one report for internal analysis? | "reproduce and store solely for viewing" is the only licence the registry records; whether analysis counts as "viewing" is a judgement | **Yes, recommended**: the terms are all-rights-reserved and do not address analysis | everything below |
| 2 | **Intended internal use.** A single-owner, loopback-only, local dashboard; no sharing, no public page, no snapshot | consistent with "not displayed or distributed in public" | Confirm in the same reply | public and private display stay `none` |
| 3 | **Saving a browser-obtained document.** The owner saves one PDF in a browser (a person, a normal visit) and imports it | probably "viewing" plus storage | Confirm | `manual_import` stays `denied`; no pilot |
| 4 | **Machine extraction of forecast figures.** Deterministic code reads numbers from the stored copy on this machine | not addressed by the terms; no new copy leaves the machine, but it is a use beyond reading | **Yes**: ask by name | tables are refused (`research tables extract` checks the route and `content_policy = full_text`) |
| 5 | **Local storage.** The raw PDF kept in the local artifact store and in local backups | "store" is permitted for viewing; backups are copies | Confirm | `content_policy` stays `metadata_only` |
| 6 | **Private dashboard presentation.** Extracted figures shown on the owner's loopback dashboard with page, row and cell evidence | internal; not public | Confirm in the same reply | the internal gate refuses without `full_text` |
| 7 | **Future automated acquisition.** A crawler fetching the PDFs under the 10-second delay | terms silent; links need prior permission | **Yes, separately**; not needed for the pilot | `review_status` stays `needs_review`; crawler stays off |
| 8 | **Future local or hosted model processing.** A model reading ANZ text, on this machine or at a provider | a different and stronger use; a hosted provider would receive ANZ's text | **Yes, separately**; not needed for the pilot, and not requested by this package unless the owner chooses | `llm_processing` stays `denied`; hosted stays denied |
| 9 | **The forecasts workbook.** Whether the XLSX on the research hub may be used the same way | unread | **Yes**: ask by name | no workbook route exists |

Independent of ANZ's answer, the owner decides whether to act on decisions 1 to 6 on their own reading. This package
recommends getting ANZ's reply first because the terms are unambiguous about "solely for viewing" and silent about analysis.

## 3. Recommended path

1. Send the request in section 5 (the owner sends it; this phase does not).
2. If ANZ replies yes to 1 to 6, or the owner decides to proceed on their own reading, record the decision (section 4).
3. Run the single-document pilot ([procedure](phase-4ag-pilot-procedure.md)).
4. Decide 7 to 9 separately, later, with their own evidence.

## 4. What recording a decision would change (not done)

All in one reviewed change by the owner, with the evidence in the note, for `anz` only:

```toml
# config/research_sources.toml  [institutions.anz]   (NOT APPLIED; shown for review)
manual_import = "approved"
manual_import_approved_by = "<owner>"
manual_import_approved_on = "<date>"
manual_import_note = "<where ANZ's reply or the owner's reading is recorded; scope: one saved PDF, internal, no model>"
content_policy = "full_text"
access_notes = "<append: date and clauses re-read; reply reference>"
# unchanged: review_status = needs_review, llm_processing = denied, public_display = none, private_display = none
```

The same change updates `PRE_APPROVAL_SHA256` in `backend/tests/research/test_phase_4x_readiness.py` with a key-by-key diff,
and updates `tests/research/test_phase_4ag_safety.py`, which today pins every real bank as denied. **A successful build never
does this.** Each of those pins fails loudly if a field changes without the owner doing it deliberately.

## 5. Draft request to ANZ (unsent)

> **Subject:** Permission request: internal, non-public analysis of ANZ Quarterly Economic Outlook
>
> Dear ANZ Economics and Markets Research team,
>
> I am a data scientist and I run a private, single-user research dashboard on my own computer. It is not published and not
> shared. I would like to use your Quarterly Economic Outlook for my own internal analysis, and I would like to check what the
> website terms of use permit before I do, as the terms reserve all rights and allow reproduction "solely for viewing".
>
> I would be grateful if you could confirm in writing whether the following are permitted:
>
> 1. Saving a copy of the Quarterly Economic Outlook PDF from my browser and keeping it on my computer and in my own backups.
> 2. Using software on my computer to read the published forecast figures (for example, the OCR, CPI inflation, GDP and
>    unemployment forecasts and their periods) from that saved copy, and keeping those figures with a reference to the page and
>    table they came from.
> 3. Displaying those figures, with attribution to ANZ and the report date, in a private dashboard that only I can open on my
>    own computer. Nothing would be placed on a public website, shared with others, or redistributed.
> 4. Whether the published forecasts workbook on your economic and markets research page may be used in the same way.
>
> I am **not** asking to retrieve your reports automatically, to publish or redistribute any content, or to send your content
> to any online service or AI provider. If I later wish to do any of those, I will ask separately.
>
> If any of this is not permitted, or is permitted only on conditions (for example, attribution wording or a limit on how long
> I keep copies), please let me know and I will follow them. I am happy to be told that the answer is no.
>
> Kind regards,
> [Name]
> [Contact details]

Placeholders `[Name]` and `[Contact details]` are for the owner to fill. The request deliberately keeps decisions 7 and 8 out so
a "yes" to this one cannot be read as more than it says.

## 6. Hard stops that remain whatever the answer

Automatic crawling, hosted or local model processing, public display, scheduling and any second bank stay disabled. A "yes" to
this request unlocks at most the single-document pilot.
