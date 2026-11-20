# Phase 4AO: ANZ forecasts workbook, suitability and integration

21 November 2026, Pacific/Auckland. Branch `feat/phase-4ao-anz-workbook` from main `c6893ab` (Phase 4AN, PR #67 merged).
**Not legal advice, and not a licence from ANZ.**

No model, Claude session or service read any workbook text, value or sheet name. The session read only masked output
(counts, flags, row and column indices, fixed codes and the file's SHA-256) from the Phase 4AN inspector and the Phase 4AO
layout probe. The owner answered yes/no questions by eye.

## Verdict (Stages 1 to 3)

| Question | Status | Evidence |
|---|---|---|
| Workbook held | **Yes.** One browser-saved file, outside the repository | §1 |
| Archive safety (G2) | **Pass.** No VBA, macro type, active content, external-link part or external formula | §1 |
| Source authorization (C2W, G1) | **Met, 21 November 2026** (owner). Registry note changed on this branch; in effect when merged | §2 |
| Boundary, periods, units (G3) | **Pass for GDP, CPI inflation and unemployment. OCR fails on units:** no unit is printed anywhere a deterministic reader can see | §3 |
| Indicators and cached values (G4) | **Pass.** All four labelled; no formulas at all (values only) | §1 |
| Attribution (G5) | **Pass** (owner, corroborated by 32 ANZ mentions in the cover text). Stability across two releases is checked on the next release before any trend is shown | §2, §3 |
| Adapter | **GO for a narrow ANZ-specific adapter.** OCR cells are rejected `unit_unstated` | §4 |

## 1. Real workbook inspection (Stage 1)

File: `ANZ-Forecasts.xlsx`, 178,346 bytes, SHA-256 `4c2d4b47cdf2afa24b72636cafaf6d5d29e4d3fcfa8eb81bedf46db9a6da7358`,
internal modified date 2026-11-05. Masked outputs: `benchmarks/xlsx_inspect/results/phase-4ao.json` (inspector) and
`phase-4ao-layout.json` (layout probe). Both hold numbers and fixed codes only.

| Check | Result |
|---|---|
| Archive and XML | status `ok`; 31 members; ratio 10.7; not encrypted; no DTD, entity, unsafe path or over-limit part |
| VBA, macros, active content | none; `macro_content_type` false; `active_content_parts` 0 |
| External links | `external_link_parts` 0; `formulas_external` 0 on every sheet. `external_targets` 2: relationships with `TargetMode="External"` from the one drawing part (the cover); no media part exists, so these are links, not loaded content |
| Formulas | 0 on every sheet. Every figure is a stored constant; nothing can be evaluated |
| Sheets | 6, all visible, none hidden. Sheet 1 has no cells (a cover drawing only). Sheets 2 to 6 hold data |
| Layout | Vertical time series: dates in column A, one row per period. Row 1 holds series titles merged over 4-column blocks; row 2 holds unit headers. Two text notes sit below each table |
| Periods | Sheets 2 to 4: 116 quarterly dates, step 3 months, all on the 1st of March, June, September or December (each date lies inside one calendar quarter). Sheets 5 and 6: monthly (288 and 192 dates); sheet 5 has 2 dates not on the 1st, sheet 6 mixes month-start and month-end days |
| Indicators | GDP on sheet 2 (11 labelled blocks); CPI inflation (3) and unemployment (1) on sheet 3; OCR (1) on sheet 5. Sheets 4 and 6 carry none of the four |
| Forecast versus actual | Each data sheet has an undated note naming forecasts and "bold" (style code 1), and every column turns **bold at exactly one date row** and stays bold. Sheet 2 turns at date index 106; sheet 3 at 107; sheet 5 at 262; sheet 6 at 166; sheet 4 splits by block (106, 107). No shading is involved |
| Vintage | A second, dated note on each data sheet uses "as at / updated" wording (code 3). It is a vintage date, not the boundary |
| Units | Sheets 2 to 4: row-2 headers state percent with annual or quarterly basis on 3 of every 4 columns. Sheet 5 (OCR) and sheet 6: no unit text in any cell, the sheet title, the header/footer or the cover text |
| Attribution and notice | No cell names ANZ or any other forecaster, and no cell holds a notice. The cover drawing (107 text runs) names ANZ 32 times, carries 3 notice runs and 1 date |
| Publication date | Only the "as at" notes and file metadata; the owner confirms the workbook states a date (§2) |

The GDP boundary is one quarter earlier than the CPI and labour boundary. That fits the release calendar on 5 November
2026: the September quarter CPI and labour figures were out; September quarter GDP was not.

### 1.1 Layout probe (built in this phase)

The Phase 4AN counts could not say where the boundary was, so `benchmarks/xlsx_inspect/xlsxinspect/layout.py`
(`--layout`) adds indices and fixed codes only, through the same `emit` guard: date columns and spans, month steps and
month-of-year set, marker and note rows, a parsed period in a forecast note reported as a **date-row index** (never the
period), fixed-pattern codes for note wording (from / to / as at) and style words (bold / italic / colour / shading),
per-column font and fill change rows with an attribute bitmask, sheet-title and cover-text unit and indicator counts.
It runs only on a workbook `inspect` accepted. 17 synthetic tests; the inspector suite is 125 passed.

## 2. Owner approval (Stage 2)

Recorded 21 November 2026, from the owner's answers in this session (yes/no; no text or figure quoted):

| C2W condition | Owner's answer |
|---|---|
| Workbook-specific terms permit this use | **Yes.** A notice exists and is no stricter than the ANZ website terms |
| The workbook contains ANZ's own forecasts | **Yes**, and it states a publication or finalisation date |
| Forecast dates and units are identifiable | **Yes.** Forecasts are shown in bold, as the note states |
| Historical data sources are identifiable | **Yes.** The historical rows are labelled with their source |

C1 (website terms re-read 2026-11-15) is within 90 days. C3W and C4 are unchanged. This is the owner's decision on the
owner's own reading. ANZ has not issued a separate licence.

Two answers were checked mechanically:

- **Attribution:** the cover text names ANZ 32 times. Consistent.
- **OCR unit:** the owner said the cover text box states it. No cover text run, cell, sheet title or header/footer
  contains `%`, `per cent`, `percent`, `p.a.` or `per annum`. The adapter therefore rejects OCR cells
  (`unit_unstated`), as the project never infers a unit. The owner may re-check; a printed form the patterns miss would
  need a reviewed change, not a default.

### 2.1 Registry change (applied, Phase 4AN §2.5)

`[institutions.anz]` only. `manual_import_note` now covers "one browser-saved forecasts workbook (XLSX), Phase 4AN
(docs/phase-4an-anz-workbook.md), conditions C2W met on 2026-11-21". Automated fetching, any model, public or shared
display, snapshots and scheduling stay under "Not covered". `review_status` stays `needs_review` (no crawler),
`llm_processing` stays denied, and both display gates stay `none`. Checked key by key against main: only that note
changed. `PRE_APPROVAL_SHA256` moves to `4d876b6f…` and `assert_anz_holds_only_the_personal_scope` now pins the workbook
route; both were changed test-first (the scope test failed before the note changed).

## 3. Suitability decision (Stage 3)

| Gate | Result |
|---|---|
| G1 | C2W recorded; registry change on this branch, effective on merge |
| G2 | Pass |
| G3 | Boundary: explicit legend plus one bold switch per column, verified per column. Periods: dates inside calendar quarters (quarterly sheets) or months. Units: stated for GDP, CPI and unemployment; **not for OCR** |
| G4 | Pass: the four indicators are labelled and every value is a stored constant |
| G5 | Pass (owner plus cover text). Two-release stability is pending the next release |

GO for a narrow adapter. OCR stays unreadable until a unit is printed.
