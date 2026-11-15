# Phase 4AI: ANZ authorization reassessment under the owner's personal-research use

15 November 2026, Pacific/Auckland. **Not legal advice, and not a licence.** This records the owner's reasoning for one narrowly
scoped decision. An approval field in this application records that decision; it does not create a right ANZ has not given.
Nothing in this phase fetched an ANZ page, imported or parsed ANZ material, or changed `main`.

## 1. Use being assessed

The owner states, and this assessment relies on it:

- a personal research project, run by one person on their own computer, for private economic research, quantitative analysis
  and learning;
- unrelated to the owner's employer (ASB Bank) and not used for any banking or commercial activity;
- nothing published, shared, redistributed or exposed through a public API, snapshot or hosted service.

The use assessed is the Phase 4AG single-document pilot only: one ANZ Quarterly Economic Outlook PDF, saved by the owner in a
browser, kept on this computer and its local backups, read by deterministic local code (`pdf-words-4`, `tables-13`), shown on
the owner's loopback dashboard with ANZ attribution and the report date.

## 2. Evidence

| # | Evidence | Source and how it was obtained | Confidence |
|---|---|---|---|
| E1 | Registry record (2026-10-25): "reproduce and store **solely for viewing**; not to be displayed or distributed in public; links need prior permission"; silent on automated access | `config/research_sources.toml`, direct read by an earlier phase | as recorded |
| E2 | Current wording of the copyright clause: "You may electronically reproduce and store the contents of the ANZ website solely for the purposes of viewing the ANZ website, **or saving ANZ website content, for your own personal use**." Governed by New Zealand law. All other rights reserved. | `https://www.anz.co.nz/comms/website-terms-of-use/` as indexed by a web search on 2026-11-15; **not** a direct read of the page | medium: the owner must confirm in a browser (condition C1) |
| E3 | Copyright Act 1994 s 43: fair dealing with a work for the purposes of research or private study does not infringe copyright. Fairness turns on the s 43(3) factors, as commonly summarised: purpose; nature of the work; whether it could be obtained in reasonable time at an ordinary commercial price; effect on the potential market for or value of the work; amount and substantiality of any part copied. Guidance: the individual doing the research relies on it, research may be privately or commercially motivated, one copy at a time, and later publication is outside it | secondary guidance (Copyright Licensing NZ, university library guides); the statute text at legislation.govt.nz and NZLII refused automated retrieval (HTTP 403) | medium: verify the section text in a browser |
| E4 | New Zealand has no general text-and-data-mining exception | general knowledge; not relied on | not relied on |
| E5 | The report PDF itself may carry its own disclaimer or copyright notice that is narrower than the website terms | not read: no ANZ PDF is held | **unknown** (condition C2) |

## 3. Analysis

**3.1 ANZ's current terms.** E1 understated the licence. If E2 is accurate, the terms expressly permit saving website content
"for your own personal use", which covers keeping one browser-saved PDF on the owner's computer. "Personal use" is undefined.
Its natural reading includes a single person's private research and analysis on their own machine. It plausibly excludes use for
an employer or for any commercial purpose, which the owner's stated scope already excludes. The terms still forbid public
display and distribution, and links need prior permission. The pilot does neither. The registry stores the document's URL as
provenance metadata, not as a published link.

**3.2 Section 43.** Section 43 is an independent defence if the personal-use licence is read narrowly. Each factor favours the
pilot:

- the purpose is private research by the individual;
- the work is published and given away free;
- it is obtainable at no cost, so no sale is displaced;
- nothing is redistributed, so there is no market effect.

Against the pilot: the whole PDF is stored, not an extract. That is mitigated because only one copy is kept for the research.
Backups are additional copies; they stay on the owner's own machine and are removed by the same purge. Fair dealing is a
defence to infringement. It does not override a contract term, which is why 3.1 matters more.

**3.3 Facts versus expression.** Copyright protects expression, not facts or ideas. A single forecast figure is unlikely to be a
work by itself. But New Zealand's originality threshold is low, and a forecast table can be protected as a compilation. ANZ's
prose analysis is clearly protected. The extractor keeps figures with page, row and cell references, not prose. That lowers the
risk; it does not remove it. Extracting a whole forecast table may be a substantial part, qualitatively. 3.1 and 3.2, not the
fact/expression distinction, carry the pilot.

**3.4 Manual download versus crawling.** A person saving a PDF in a browser is the use the terms contemplate (E2). Automated
fetching is a different act: the terms are silent on it, and links need prior permission. It stays off. `review_status` stays
`needs_review`, so `automated_access_allowed` is false and no crawler can run.

**3.5 Deterministic extraction versus AI use.** Local deterministic parsing creates no copy outside the owner's computer and
sends nothing to a third party. A hosted model would send ANZ's text to a provider, which is a distribution the personal-use
reading does not cover. A local model is a separate decision. `llm_processing` stays `denied`.

**3.6 Employment context.** The owner works for a competitor bank. This does not change 3.1 to 3.5, but "for your own personal
use" is the hinge of the licence, so it must stay true in practice:

- run it on a personal device, not an employer device or network;
- never use its outputs in, or bring them to, employment work;
- check any employer outside-interests or conflict policy (the owner's own call).

## 4. Finding

**The narrowly scoped, local, single-document pilot can reasonably proceed without separate written permission, subject to
conditions C1 to C4.** If E2 is confirmed, the basis is ANZ's own personal-use licence, with s 43 as an independent fallback.

Material uncertainty remains in four places:

1. The exact current terms wording (E2 came from a search index, not a direct read).
2. The PDF's own notice (E5), which could be narrower than the website terms and would then govern.
3. Whether "personal use" extends to machine analysis. This is a reasonable reading but not stated.
4. Compilation copyright in a full forecast table.

None is resolved by this document. A written reply from ANZ (the Phase 4AG request) would resolve all four and is still
worth sending, but it is not a precondition of this scope.

## 5. Conditions before any ANZ document is imported (owner)

**Recorded 15 November 2026:** the owner re-read ANZ's website terms in a browser and the Important Notice of the November 2026
Economic Outlook, and confirmed both support this scope (C1, C2). The owner authorised manual import of one personally obtained
Quarterly Economic Outlook PDF for local deterministic numerical extraction and private analysis only, as a project-level decision,
not a representation that ANZ has granted a licence. C3 and C4 are the owner's continuing undertakings.

| # | Condition | If not met |
|---|---|---|
| C1 | Open the terms page in a browser. Confirm the "saving ANZ website content, for your own personal use" wording. Record the date. | stop; revert to the Phase 4AG request |
| C2 | Open the chosen PDF. Read its disclaimer and copyright notice before importing. If it forbids reproduction or storage for any purpose, or limits use beyond the website terms, stop. | stop; send the Phase 4AG request |
| C3 | Use stays within section 1: one PDF, local, loopback display, no model, no sharing, no snapshot | outside scope; separate decision |
| C4 | Personal device; outputs never used in employment work | outside scope |

## 6. Registry change (branch `proposal/phase-4ai-anz-personal-scope`; for review, not merged)

`config/research_sources.toml`, `[institutions.anz]` only, checked key by key against `main` `5fe3db1`:

| Field | Before | After |
|---|---|---|
| `content_policy` | `metadata_only` | `full_text` |
| `manual_import` | absent (denied) | `approved` |
| `manual_import_approved_by` / `_on` / `_note` | absent | owner, 2026-11-15 (set to the actual decision date), note naming this document and the scope |
| `licence` | "store solely for viewing" | adds "or saving website content, for your own personal use" |
| `review_status`, `llm_processing`, `public_display`, `private_display`, `approved_by` | unchanged | unchanged: crawler, model and both display gates stay off |

Pins (12 files; 14 tests failed against the change before their update, confirming they guard the fields):

- New: `tests/research/bank_support.py` adds `assert_anz_holds_only_the_personal_scope`. It pins ANZ to exactly this scope:
  - manual import approved, by this approver on this date, with this note;
  - `full_text`;
  - `needs_review`, with no crawler and no source approval;
  - model refused, hosted and local;
  - public and private display `none`;
  - manual-route documents held, crawled ones not.
- Updated: `test_phase_4ag_safety.py`, `test_bank_registry.py`, `test_table_isolation.py`, `test_registry.py`,
  `test_bank_api.py`, `test_bank_status.py`, `test_bank_e2e.py`, `test_table_e2e.py`, `test_phase4ae_docs.py`,
  `test_phase4af_docs.py`.
  - Every other real bank remains pinned as fully refused.
  - `PRE_APPROVAL_SHA256` moves to `71269a71…` with the key-by-key record in its comment.
- Mutation checks:
  - switching ANZ's crawler on fails 6 tests;
  - opening ASB's manual import fails the suite (registry validation plus pins).

Operational effect once applied: `nzstats research bank-status` reports ANZ `missing` (exit 1, attention) until the one report
is imported. It reports `ok` while that report is under 100 days old, then `stale`. This is the designed behaviour for a
permitted source.

## 7. Revocation

Revocation steps, lightest first, as in the Phase 4AG procedure, step 10:

1. Turn `auto_display` off.
2. Revert this registry change. Import and `tables extract` refuse again, and `holds("manual")` drops the held figures from view.
3. Run `nzstats research purge anz --version N --apply` to remove the text and figures.

## 8. Next action

1. Owner: complete C1 and C2. Record the C1 date and the C2 reading in the note, and change `manual_import_approved_on` if the
   decision date differs. Recompute the pin only if the date changes.
2. Owner: approve the branch for commit and PR (no merge without review).
3. After merge: run the Phase 4AG pilot procedure from step 1 (backup), with this document as step 0's decision record.
