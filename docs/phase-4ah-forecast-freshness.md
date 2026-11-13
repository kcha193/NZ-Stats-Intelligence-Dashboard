# Phase 4AH: forecast freshness, ANZ authorisation decision and pilot verdict

14 November 2026, Pacific/Auckland. Branch `feat/phase-4ah-forecast-freshness` from main `5934060` (PR #60 merged).
[Design](superpowers/specs/2026-11-14-phase-4ah-forecast-freshness-design.md),
[plan](superpowers/plans/2026-11-14-phase-4ah-forecast-freshness.md).

**No live ingestion exists for any bank and no permission field was changed.** Nothing was fetched, imported or
processed for ANZ; no hosted or local model was called; nothing was paid for, deployed, scheduled or written to
production data. `config/` has no diff and the `PRE_APPROVAL_SHA256` pin is unchanged.

## Verdict

| Workstream | Verdict |
|---|---|
| A. Forecast freshness | **Fixed and verified** (no migration) |
| B. ANZ authorisation | **Not authorised.** No ANZ reply and no owner decision is recorded; source permissions unchanged |
| C. First real ANZ pilot | **BLOCKED at step 0** of the [pilot procedure](phase-4ag-pilot-procedure.md); not started |
| D. Independent review | see [review record](#independent-review) |
| E. Verification | see [verification](#verification) |

## A. Forecast freshness

### The defect (Phase 4AG's documented gap)

A refused table cell stores a code and a position (`research_table_rejection`: page, table, row, column), never an
indicator or horizon. The existing rule that stops a bank's older figure standing in for an unusable newer one
(`newer_claim_unusable`) works by identity, so it could not see a refused cell. Reproduced failing-first: an August
report gives June CPI 2.6; the November report's June cell carries a footnote marker and is refused; the comparison then
showed **2.6 (August) as the bank's latest June forecast and the consensus used it**. The same happened for an ambiguous
refused table, a printed dash, and a newer report held but not yet read.

### The fix

Freshness is judged per document, because the refused cell's identity is unknown and is not guessed.

1. `table_view.document_states` classifies each current, dated bank **outlook** report (a bank, not purged, current
   version, not superseded, not a duplicate):
   - `incomplete`: its current table extraction refused a cell, or printed an own forecast without a value (in either
     display mode: the refusal is a fact about the report);
   - `not_read`: it may not be shown (route revoked, content policy or host), its tables were read only by an older
     interpreter (even if a summary was admitted), or nothing usable was read (never extracted, refused by the reader,
     which stores nothing, or no own figure and no admitted summary);
   - `incomplete_scenario`: only `scenario_table` / `scenario_row` / `scenario_column` refusals;
   - `read` otherwise. Table figures count as read only in the owner's automatic mode, as for the figures themselves;
     without usable tables an admitted summary is the reading (Phase 4AE model path).
2. `bank_analytics._prepare(..., current=True)` (comparison, consensus, divergence) excludes a bank's figure when the
   bank has a strictly newer `incomplete` or `not_read` report (`incomplete_scenario`: scenario groups only) and no
   eligible figure of the same identity (bank, adjustment, comparison group) is dated on or after that report. Codes:
   `newer_report_incomplete`, `newer_report_not_read`, each with fixed reason text; the dashboard's existing left-out
   list shows them with no frontend change.
3. Revisions and evaluation use `current=False`: every accepted vintage stays in the history, and a forecast published
   before an outcome is still scored on its own date and horizon band.
4. `GET /internal/bank-intelligence/forecasts` gains an additive `vintages` list: per bank, `latest_published_on`,
   `latest_accepted_on`, the newest report's `state` and `current`.

No schema change: immutable rows, rejection evidence and older interpreters' extractions are untouched. No rule,
tolerance or permission changed. Version gate unchanged: reader `pdf-words-4`, interpreter `tables-13`.

### Cases tested (`tests/research/test_table_freshness.py`, plus one API test)

| Case | Outcome |
|---|---|
| Newer valid forecast | newer figure current; older is an earlier vintage; revision 2.6 to 2.4 kept |
| Newer invalid forecast (footnoted cell) | older June figure excluded from comparison and consensus; still in revisions; September (restated) is an ordinary revision |
| Ambiguous rejected table | older CPI hidden; OCR (restated on a clean page) current; no identity inferred |
| Duplicate publication | no state; nothing changes |
| Corrected publication | superseded original ignored; unread correction blocks; once read, the correction is current |
| Withdrawn publication (purged through the purge workflow) | no state; the older figure is the latest again |
| Missing forecast (dash) | `incomplete`; older figure for that horizon excluded |
| Multiple target horizons | restated horizon current, unrestated horizon excluded |
| Still newer restating report | older figure is an earlier vintage, no exclusion |
| Scenario-only refusal; newer weekly note; undated newer report; revoked route | central figures unaffected / no state |
| Older interpreter only; no table at all; named (non-automatic) mode | `not_read` |
| Latest published versus latest accepted | clean: current; refused cell: not current; unread: accepted date older |

### Limits (accepted, stated)

- **Over-hiding is the chosen direction.** A newer report with any blocking refusal hides every older figure it does
  not restate, not only the refused cell's. Real reports often have unmapped rows (for example exchange rates), so in
  practice a bank's current view becomes its newest report's accepted figures. That is the fail-closed reading of
  "the bank's latest forecast".
- Only strictly newer reports trigger the rule; two reports on the same day are not compared.
- A model summary that omits a measure counts as read, and so does a held PDF never table-extracted whose summary was
  admitted (Phase 4AE behaviour; bank model processing is not authorised, so no bank summary exists).
- An undated figure is treated as older than any dated report: a newer unread report blocks it in the current views.
- `latest_accepted_on` is the newest outlook figure that survives the analysis's own rules (conflicts, unusable newer
  claims), before freshness is applied.
- `document_states` reads each report's latest extraction with a few queries per report on every internal request;
  acceptable at a handful of bank reports, to batch if volumes grow.
- A table figure dropped by an unresolved reconciliation with a model claim does not mark its report incomplete (no
  bank claims exist while `llm_processing` is denied).
- The newer report's own figures are never inferred to replace the refused cell.

## B. ANZ authorisation decision summary

| Question | Evidence | Finding |
|---|---|---|
| Is ANZ source use recorded? | `config/research_sources.toml` `[institutions.anz]`: `review_status = needs_review`, `content_policy = metadata_only`, `manual_import`, `llm_processing` denied, `public_display`/`private_display = none`, no approver or date; the last commit touching the file is `e2c05a9` (BNZ/Kiwibank landing URLs, all banks pinned refused) | **No** |
| Is an ANZ reply or owner decision recorded? | `docs/phase-4ag-anz-permissions-package.md` (request unsent); vault project status (`current-projects.md`, 14 November: "ANZ pilot BLOCKED on owner permission"); no decision record | **No** |
| Does the request prompt itself authorise? | The prompt says "do not infer authorisation from this prompt" | **No** |

Decision: **keep every ANZ permission unchanged; do not import or process an ANZ document; the pilot stays BLOCKED.**
The pending owner decisions are unchanged: decisions 1 to 6 of the [permissions package](phase-4ag-anz-permissions-package.md)
(ideally ANZ's written reply to the drafted request), then one reviewed registry change for `anz` only
(`manual_import = approved` with approver, date and note; `content_policy = full_text`), with the
`PRE_APPROVAL_SHA256` and `test_phase_4ag_safety.py` pins updated in the same change with a key-by-key diff. Crawling,
model processing (hosted or local), scheduling and public display stay out of scope whatever the answer.

## C. Pilot report

**BLOCKED.** Step 0 preconditions 0.1 to 0.4 are not true (no terms re-read recorded, no reply or decision, no registry
change, no pin update), and no owner-saved ANZ PDF was supplied. Steps 1 to 12 were not run. No result in this record
comes from a real ANZ document; the freshness fix is proven on synthetic PDFs only. When the pilot runs, a refused cell
in the real report now shows as `newer_report_incomplete` only once a second report exists; for the first report there is
no older vintage to hide.

## Independent review

Pending.

## Verification

Pending.

## Recommended Phase 4AI

1. **Owner action, no code:** decide on, and if wanted send, the ANZ request; record the decision.
2. **Phase 4AI, only after step 1:** run the single-document ANZ pilot from step 1 of the procedure; let the real PDF's
   refusals drive any extractor work (synthetic fixture and failing test first).
3. At ANZ's second quarterly report, confirm on real data that `vintages` and the freshness exclusions behave as tested.
