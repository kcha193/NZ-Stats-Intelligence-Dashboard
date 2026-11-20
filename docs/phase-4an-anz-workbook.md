# Phase 4AN: ANZ forecasts workbook, source use and masked structure inspection

20 November 2026, Pacific/Auckland. Branch `feat/phase-4an-anz-workbook` from main `d65ed44` (Phase 4AM, PR #66 merged).
**Not legal advice, and not a licence from ANZ.**

**Nothing was fetched, imported or parsed from ANZ in this phase.** No ANZ workbook is held. No permission field, safety
pin, migration or production module changed. The only new code is a counts-only inspector under `benchmarks/`, tested on
synthetic workbooks, which the owner runs on the real file.

## Verdict

| Question | Status | Evidence |
|---|---|---|
| Source authorization | **Owner approved, conditional; not yet in effect.** Takes effect when C2W is met and recorded | §2 |
| Workbook suitability | **Unknown.** No workbook held; structure not inspected | §3 |
| Technical implementation | **Inspector built (synthetic-tested); adapter not built.** The adapter waits for gates G1 to G5 | §4, §5 |
| Accepted forecast accuracy | **None.** No figure read | — |
| Internal dashboard readiness | **Unchanged.** ANZ still shows only the PDF route (0 figures, Phase 4AM) | — |

The ANZ PDF pilot remains NO-GO: 0 accepted figures, 49 rejections (version 4).

## 1. Starting point

- The Phase 4AI scope (`config/research_sources.toml`, `manual_import_note`) lists "the forecasts workbook" under **Not
  covered**. This phase does not silently extend it.
- Phase 4AG §4 set the trigger for an XLSX adapter: (a) permission names the workbook and the use; (b) the owner has saved
  and inspected one genuine workbook; (c) it holds the four priority indicators with periods and actual/forecast status;
  (d) values are cached, not bare formulas; (e) its structure is stable across two releases.
- `008_research_manual_import.sql` limits `file_format` to `html` and `pdf`. Importing an XLSX needs a migration.
- Migration `015` (immutable forecasts and rejections, evidence JSON, purge tombstones) fits workbook figures as it is.
- `adapters/cpi/workbook.py` is an existing bounded stdlib XLSX reader: archive, member and ratio limits, no VBA parts, no
  external links, no DOCTYPE or ENTITY. Its limits are reused here.
- `openpyxl` is not a backend dependency.

## 2. Source-use assessment (deliverable A)

### 2.1 Use assessed

The Phase 4AI use, with one document swapped:

- one ANZ forecasts workbook (XLSX) from "ANZ Forecasts: Latest forecast and historical data" on
  `https://www.anz.co.nz/about-us/economic-markets-research/`, saved manually by the owner in a browser;
- stored on this computer and its local backups;
- read by deterministic local code: no model (local or hosted), no crawler, no schedule;
- shown only on the owner's loopback dashboard, attributed to ANZ with the workbook's date;
- personal research, unrelated to the owner's employer; nothing published, shared, snapshotted or served publicly.

### 2.2 Evidence

| # | Evidence | Status |
|---|---|---|
| E2 | ANZ website terms: content may be saved "for your own personal use" | owner re-read in a browser on 2026-11-15 (Phase 4AI C1) |
| E3 | Copyright Act 1994 s 43, fair dealing for research or private study | as Phase 4AI; secondary sources |
| W1 | **The workbook's own notice or disclaimer**, if any | **unread**: no workbook is held |
| W2 | Whether the historical series are ANZ's or are reproduced from a third party (Stats NZ, RBNZ) | **unknown** |
| W3 | Whether the URL is overwritten in place on each release | **unknown**; the design assumes it is (§4.4) |

### 2.3 Analysis: what differs from the PDF

1. **The same licence basis applies.** A file saved from the website is "ANZ website content". The personal-use reading
   (E2) and the s 43 fallback (E3) carry over unchanged, as do the Phase 4AI employment conditions.
2. **It is a whole compilation, not a report.** A forecasts workbook is a forecast table in its most complete form.
   Compilation copyright (Phase 4AI §3.3) weighs more heavily here than for a PDF table. Mitigation: one local copy, no
   redistribution and no display beyond loopback, so the s 43 market factor stays neutral.
3. **Third-party data inside.** Historical rows may be official statistics that ANZ reproduces. The dashboard already holds
   Stats NZ actuals from Stats NZ itself. The adapter keeps only ANZ-attributed forecasts. Workbook actuals are never shown
   as official data.
4. **Machine reading is the purpose of a spreadsheet.** Deterministic cell reading is closer to ordinary use of an XLSX than
   PDF table extraction is to ordinary use of a PDF. This modestly strengthens the personal-use reading. It is not a
   statement by ANZ.
5. **The notice may be narrower.** As with the PDF (Phase 4AI C2), the workbook's own notice governs if it is stricter.

### 2.4 Owner decision (recorded 20 November 2026)

The owner approved, in this session, a narrow extension of the Phase 4AI scope to one manually saved forecasts workbook
for the use in §2.1. **It is conditional and takes effect only when C2W is met.** It is the owner's decision on the
owner's own reading, not a representation that ANZ has granted a licence.

| # | Condition | If not met |
|---|---|---|
| C1 | ANZ website terms re-read in a browser (done 2026-11-15). Re-read if more than 90 days pass before the import | stop |
| C2W | Save the workbook in a browser. Run the inspector first (§6 step 2), then read the workbook's own notice, disclaimer or copyright text in a spreadsheet program with external content disabled. Stop if it forbids saving, storing or analysing the file, or limits use beyond the website terms | stop; ask ANZ (Phase 4AG request, item 9) |
| C3W | One workbook; local; loopback display; no model; no sharing; no snapshot; no crawler or schedule | outside scope |
| C4 | Personal device; outputs never used in employment work | outside scope |

### 2.5 Registry change: prepared, not applied

Applied only after C2W is recorded, on its own commit for review. `[institutions.anz]` only:

| Field | Change |
|---|---|
| `manual_import_note` | "Not covered: … the forecasts workbook" becomes a covered item: "one browser-saved forecasts workbook (XLSX), Phase 4AN (docs/phase-4an-anz-workbook.md), conditions C2W met on DATE". Automated fetching, models, public or shared display, snapshots and scheduling stay excluded |
| everything else | unchanged: `review_status = needs_review` (no crawler), `llm_processing` denied, both display gates `none` |

The note change moves the pinned registry hash (`PRE_APPROVAL_SHA256` in the Phase 4AG/4AI pins), and
`assert_anz_holds_only_the_personal_scope` must name the workbook route. Those pins change in the same commit, test-first.

## 3. Workbook structure assessment (deliverable B): pending

Nothing can be assessed until a workbook is held. The inspector (§5) answers these questions with counts and flags only.

| Question | Inspector field | What would block an adapter |
|---|---|---|
| Archive safety | `archive.*` | any refusal flag; `vba_part`; `macro_content_type`; `external_link_parts > 0` |
| Sheets, visibility, size | `workbook.sheets`, `sheets[].state`, `rows`, `cols` | figures only on hidden sheets |
| Formulas and cached values | `formulas`, `formulas_cached`, `formulas_uncached`, `formulas_external` | any uncached or external formula in a forecast block |
| Indicator coverage | `indicator_labels`, `label_columns` | fewer than the four priority indicators (Phase 4AG gate c) |
| Period convention | `period_headers`, `period_header_rows` / `_cols`, `period_kinds`, `dates`, `year_like_numbers` | periods only as unlabelled serial dates or ambiguous year numbers |
| Actual versus forecast | `forecast_markers`, `actual_markers` | no explicit marker (the PDF failure mode, Phase 4AM) |
| Units | `percent_format`, `unit_hints` | percent-formatted cells beside unlabelled rows (fraction versus percent) |
| Attribution and notice | `anz_mentions`, `other_forecaster_mentions`, `notice_cells` | a sheet naming another forecaster for the figures |
| Publication date | `workbook.modified_ymd`, `has_created` | no date anywhere (file metadata alone is weak evidence) |

Questions only the owner can answer by eye, recorded as yes or no (never values):

1. Does a sheet state that its forecasts are ANZ's own?
2. Does it state a forecast-finalisation or publication date?
3. Does each row state its unit and seasonal adjustment?
4. Are the historical rows labelled with their source?

## 4. Implementation design (deliverable C): conditional

Built only when gates G1 to G5 all hold:

| Gate | Test |
|---|---|
| G1 | C2W recorded and the §2.5 registry change merged |
| G2 | Inspector status `ok` with no archive refusal flag, no VBA and no external link part |
| G3 | The forecast block has explicit actual/forecast markers, parseable periods and stated units (inspector plus owner yes/no) |
| G4 | The four priority indicators are present with cached values |
| G5 | Owner confirms ANZ attribution (question 1). Stability across two releases (Phase 4AG gate e) is checked on the next release before anything is shown as a trend |

If they hold, the design is:

1. **Reader.** Decide between `openpyxl` (as an optional `research` extra) and extending the stdlib pattern of
   `adapters/cpi/workbook.py`, on the inspector's evidence about number formats and merged cells. Either way, the
   stdlib archive checks run first, in the existing hardened child process, with the CPI limits.
2. **Contract.** Migration 016 widens `file_format` to `html`, `pdf`, `xlsx` (a table rebuild in SQLite), with a rollback
   script and a migration test. Workbook figures use migration 015 as is: `page` = sheet position, `tbl`/`tbl_row`/
   `tbl_col` = block and cell, `evidence` = sheet position, A1 address, number format, cached-value flag and workbook
   SHA-256. Interpreter version `xlsx-1`.
3. **Mapping.** One ANZ-specific mapping, justified by the real structure, reusing `table_parse` (`period_of`,
   `column_kind`, `parse_value`) and the `table_forecast` vocabulary. No generic spreadsheet framework.
4. **Fail closed.** Fixed rejection codes for: uncached formula, external reference, hidden sheet, percent format without a
   stated unit, missing or contradictory period, no actual/forecast marker, third-party attribution, unsupported sheet,
   changed layout.
5. **Versions.** Each saved workbook is its own document version, keyed by SHA-256. A duplicate is refused. A revision is a
   new version. Older forecasts are never inferred from a newer workbook, and a stored copy is never overwritten.
6. **Isolation.** Same gates as the PDF figures: `table_view` under the internal loopback gate, no snapshot, no public API,
   no single-bank "consensus".
7. **Tests (synthetic).** Normal table, wrong units, missing dates, historical values, uncached formulas, external links,
   unsupported sheets, duplicate versions, revised forecasts, changed structure, wrong bank attribution.

## 5. Masked workbook inspector (built in this phase)

`benchmarks/xlsx_inspect/` (own venv; `openpyxl==3.1.5`; never imported by `backend/`):

- **Archive first, standard library only:** size, member count, uncompressed size, ratio, encryption, unsafe member names,
  a corrupt member, and DOCTYPE or ENTITY in **every** member whatever its name, in UTF-8, UTF-16 or UTF-32. Counted and
  reported: VBA parts, macro-enabled content type, external-link parts, active content (`xl/connections.xml`,
  `xl/embeddings/`, `xl/activeX/`, `customUI/`) and relationships with `TargetMode="External"`. A refused archive is
  never opened by `openpyxl`. A check that an earlier refusal stopped is reported as `null`, never `false`.
- **Then `openpyxl`, twice:** formulas (`data_only=False`) and cached values (`data_only=True`), with `keep_links=False`
  and `keep_vba=False`. Nothing is evaluated; stdout, stderr and warnings are captured and only counted.
- **Vocabulary from production:** `period_of` and `column_kind` are imported from `nzstats.research.table_parse`. The
  indicator and forecaster lists are copied from `table_forecast`, and a test fails if they drift.
- **Output guard:** `emit` accepts only a fixed key set, numbers, booleans, fixed codes, lists of ints and the file's
  SHA-256. Sheet names, cell text, figures, paths and error messages are refused. A reader failure becomes `"error"` with
  no message. The CLI hashes the bytes once and inspects those same bytes, refuses a file over 16 MB before reading it,
  and turns any unexpected failure into `{"status": "error"}` with stderr empty.
- **Counting rules:** a formula is a cell stored as a formula (text starting with `=` is text; shared formulas count per
  cell). A percent format counts as `percent_format` only when it scales by 100; `0.0"%"` and `0.0\%` print a literal `%`
  and count as `literal_percent_format`. A merged period header reports its column span.
- **Tests:** 46, all synthetic, including one that plants a secret label and figure and checks neither leaves. Mutation
  checks run in this session (not scripted in the repository): dropping the XML-declaration refusal, a UTF-8-only
  declaration scan, dropping the encryption refusal, formula-by-leading-`=`, treating every `%` as scaling and inverting
  the forecast marker each failed at least one test.

## 6. Owner runbook (deliverable G)

Run from the repository root on the personal device. Steps 1 to 4 are this phase; step 5 starts the next.

1. **Save** the workbook from the ANZ research page in a browser. Do not script the download. Keep it outside the
   repository (for example `~/Downloads`), and do not open it yet.
2. **Inspect, masked.** This also reports macro, active-content and external-reference parts before any spreadsheet
   program opens the file. It does not prove a file is safe to open:

   ```sh
   cd benchmarks/xlsx_inspect && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ../..
   shasum -a 256 ~/Downloads/<file>.xlsx
   mkdir -p benchmarks/xlsx_inspect/results
   PYTHONPATH=benchmarks/xlsx_inspect:backend/src benchmarks/xlsx_inspect/.venv/bin/python -m xlsxinspect \
     ~/Downloads/<file>.xlsx --expect-sha256 <hash> > benchmarks/xlsx_inspect/results/phase-4an.json
   ```

   Exit 0 means inspected; 2 means refused, unreadable, wrong hash or any other failure. The output holds counts, flags, cell indices and the
   hash only, so it may be committed and shared with the session.
3. **C2W.** Only if step 2 shows status `ok`, `vba_part` false, `macro_content_type` false, `active_content_parts` 0,
   `external_link_parts` 0 and `formulas_external` 0 on every sheet, open the file in a spreadsheet program with external
   content disabled and read its notice. Record the date and outcome (one sentence, no quotation of figures).
4. **Owner yes/no answers** to the four questions in §3.
5. **Next phase, only if C2W is met:** apply §2.5 test-first; assess G2 to G5 from the inspector output; then build the
   adapter (§4) test-first on synthetic replicas shaped by the masked structure. The real pilot follows the Phase 4AG
   procedure: back up, import one workbook, check hash and identity, dry run, show candidate counts and rejection codes,
   one-time owner reconciliation, store accepted figures only, check the internal view and snapshot isolation, and
   rehearse rollback and revocation.

Revocation is as in Phase 4AI §7. Before §2.5 is applied, there is nothing to revoke: delete the saved file.

## 7. Verification

- `benchmarks/xlsx_inspect`: 46 passed; ruff check and format clean.
- Backend unchanged (no file under `backend/`, `config/` or `frontend/` modified). Backend suite run anyway because
  `CLAUDE.md` and `docs/progress.md` changed: 7,148 passed, exit 0; ruff clean.
- Privacy: no ANZ material was read by the session or by any model. The inspector's output contract is enforced by `emit`
  and tested.

## 8. Independent review

A fresh-context reviewer read the code and this record, ran only the synthetic tests and probes, and was barred from
`data/` and any real file. No Critical finding. The authorization wording was confirmed as accurate. Fixed test-first:

- **High:** a corrupt member raised outside the guarded block, and the CLI could print a traceback with the path. Both
  are now fixed codes, with stderr empty.
- **High:** the DOCTYPE/ENTITY scan missed UTF-16 parts and parts without an `.xml` extension. It now scans every member
  in every encoding expat accepts.
- **Medium:** literal-percent formats were counted as scaling; text starting with `=` was counted as a formula; merged
  period headers had no span; the CLI read the file twice; the runbook's safety claim and open condition were narrower
  than §3; the exit-code claim was wrong while the traceback path existed.
- **Low:** chartsheets are counted apart from worksheets, duration values count as dates, and unchecked flags are `null`.

Not changed: sheet-scoped defined names and hidden rows or columns are not counted. Neither bears on gates G2 to G5.
