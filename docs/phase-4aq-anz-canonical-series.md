# Phase 4AQ: ANZ canonical forecast series resolution

21 November 2026, Pacific/Auckland. Branch `feat/phase-4aq-anz-canonical-series` from main `f0e6fad` (Phase 4AP, PR #69
merged). This is a personal research project, run on the owner's own computer, with no connection to the owner's employer.

**Status: PENDING OWNER MAPPING REVIEW.** Stages 1 and 2 are done. Stage 3 is designed below but not built: Stage 5 builds
it only after the owner approves an exact mapping. No figure is stored. No validation rule changed. Nothing was fetched,
re-imported or sent to a model.

## 1. Stage 1: baseline (verified, read-only)

Every command ran from the repository root with `NZSTATS_DATA_DIR=./data`. Only counts, codes and hashes entered the
session.

| Check | Result |
|---|---|
| Version 5 | Exactly one row, `format` `xlsx`, not purged. It is the only `xlsx` row |
| Workbook SHA-256 | Stored `content_sha256` begins `4c2d4b47cdf2`, matching Phase 4AO and 4AP |
| Schema | `schema_version` 16, `integrity_check` ok |
| Stored figures | 0 table extractions and 0 table forecasts for version 5 |
| Source | `research bank-status`: ANZ `forecasts_workbook` is `undated`. The registry is unchanged from main |
| Dry run | `tables extract 5 --dry-run`: **0 figures, 97 rejections**: `ambiguous_indicator` ×52, `unmapped_row` ×42, `unsupported_period` ×2, `unit_unstated` ×1. Reader `xlsx-cells-2`, interpreter `xlsx-anz-3`. The code is `e3f56a46`, not 4AP's `4f53cda1`, because the code includes the interpreter version (`xlsx-anz-1` then, `xlsx-anz-3` now). It still covers 0 candidates |

Cause of the 52 `ambiguous_indicator` refusals (Phase 4AP §1.4, unchanged): 10 distinct block titles name real GDP and 3
name CPI inflation. The mapping cannot tell which one is the headline series, so it refuses all of them. This is the
intended fail-closed result, not a defect.

## 2. Stage 2: owner-only series review

New command, read-only and local:

```sh
nzstats research tables review 5        # from the repository root, in your own terminal
```

- It refuses unless both stdin and stdout are a terminal (exit 2), so a tool session, a pipe or a redirect gets only the
  refusal line. The same gate guards `tables extract --list`.
- For each sheet, it prints the position and actual name, the quarterly date range, the bold-forecast legend, the "as at"
  note and every other note under the table.
- For each block, it prints the position, original title and column range.
- For each column, it prints the letter, unit header, indicator interpretation, unit result, bold forecast boundary
  (first to last bold date), first horizon (period basis) and current result (candidate count or fixed rejection code).
- It **never prints a cell value**. All workbook text is JSON-quoted, so a control character shows escaped.
- It uses the same version, source-permission and raw-hash checks as `tables extract` (`_checked_version`), and the
  same interpreter, so its results match the dry run.

Code: `research/xlsx_review.py`, `table_ingest.review_version_workbook`, `cli.py`. Tests:
`tests/research/test_xlsx_review.py` (9). Each was watched failing first, except the escape test: its first version
used ESC, which XML cannot hold, so the reader refused it first. It now uses C1 CSI `\u009b`.

### 2.1 Questions for the owner

Run `tables review 5` and open the original workbook beside it. Answer **in positions and fixed words only**: sheet
number, block number, column letter, cell address, a date, and the choices below. Do not paste titles, notes or values
back into a Claude Code session.

| | Question | Answer form |
|---|---|---|
| A | Which column is the headline real-GDP series? A block is not the headline just because it comes first or has a matching name | `gdp: sheet S block B column X`, or `none` |
| B | Which growth basis does that column state, and is it stated in its own title or unit header? | `quarterly` / `annual` / `annual_average`, plus `stated` or `not_stated`. A second GDP column with the other basis is allowed only if it is the same headline block |
| C | Which column is the headline CPI-inflation series (not a component, not an alternative measure)? | `cpi: sheet S block B column X`, or `none` |
| D | Is the unemployment column's percent unit stated anywhere in the workbook, explicitly for that series? | `stated at sheet S cell A1`, or `not_stated` (keeps `unit_unstated`) |
| E | For each sheet holding A or C, do the sheet name's non-neutral words change the meaning of the series (scenario, region, component, basis)? | `sheet S editorial` or `sheet S substantive` |
| F | What publication date does the workbook state, and where? | `YYYY-MM-DD at sheet S cell A1`, or `not_stated` |

`none`, `not_stated` and `substantive` are valid answers. Each one keeps the matching series refused.

## 3. Stage 3: mapping manifest design (not built)

### 3.1 The file

`data/research/anz-workbook-mapping-v5.json`, written only by the owner. It holds ANZ titles, so it lives under `data/`,
which Git ignores. Draft shape:

```json
{
  "schema": "anz-workbook-mapping-1",
  "workbook_sha256": "<the full 64 hex of version 5>",
  "reviewer": "owner",
  "decided_on": "YYYY-MM-DD",
  "published_on": {"date": "YYYY-MM-DD", "sheet": 1, "cell": "A1", "text": "<exact cell text>"},
  "series": [
    {"indicator": "gdp", "basis": "quarterly", "sheet": 2, "sheet_name": "<exact>", "block": 1,
     "block_title": "<exact>", "column": "C", "unit_header": "<exact>"},
    {"indicator": "cpi_inflation", "basis": "annual", "sheet": 3, "sheet_name": "<exact>", "block": 1,
     "block_title": "<exact>", "column": "B", "unit_header": "<exact>"},
    {"indicator": "unemployment", "basis": "quarterly", "sheet": 3, "sheet_name": "<exact>", "block": 4,
     "block_title": "<exact>", "column": "J", "unit_header": "<exact>",
     "unit_evidence": {"sheet": 3, "cell": "A44", "text": "<exact>"}}
  ],
  "sheet_context": [{"sheet": 2, "sheet_name": "<exact>", "classification": "editorial"}]
}
```

To keep ANZ text out of every session, a small owner command would fill in the exact texts from positions:
`tables map 5 --gdp 2:1:C:quarterly … --out FILE`. It would write the file and print only the file's SHA-256 and the
count of entries.

### 3.2 Interpreter `xlsx-anz-4` (semantic change, so a new version)

Without a manifest, or with one that does not validate, the result is **exactly** `xlsx-anz-3` (pinned by a test).
`tables extract V --mapping FILE` applies a manifest as follows:

1. **Whole-file checks.** The schema must match, and `workbook_sha256` must equal the version's raw SHA-256. Each
   (indicator, basis) may appear at most once, and no column may appear twice. Indicators are limited to `gdp`,
   `cpi_inflation` and `unemployment`; `ocr` is refused in the manifest. Any failure refuses the whole manifest with a
   fixed code (`mapping_hash_mismatch`, `mapping_invalid`, `mapping_duplicate`) and stores nothing.
2. **Structure checks per entry.** Sheet position and name, block number and title, column letter and unit header
   must all match the workbook exactly, after whitespace normalisation only. A moved, renamed or retitled entry gives
   `mapping_structure_mismatch` for that entry and produces no candidates.
3. **Selection.** Only listed columns are exempt from `ambiguous_indicator`. Every other column that names the same
   indicator is refused with the new code `not_canonical_series`, including components, variants and other bases. Ten
   GDP variants never become ten copies of headline GDP.
4. **Every existing rule still applies to listed columns.** These include the bold tail and the boundary,
   `unit_of_text`, `_horizon`, `context_rejection`, the third-party and explicit-source checks, and the number format.
   - The manifest's `basis` must equal the basis the interpreter derives from the column's own title and header, or
     the column gets `mapping_basis_mismatch`.
   - GDP still needs "real" (or "nominal") in its own label. The manifest never supplies a word the source does not
     print.
5. **Unemployment unit.** It becomes `percent` only when `unit_evidence` points at an existing text cell on that
   sheet, its text matches exactly, and `unit_of_text` on that text alone gives percent. Otherwise the column stays
   `unit_unstated`.
6. **Sheet context.** An `editorial` entry, for that exact sheet name in that exact workbook hash, drops the sheet name
   from the context rule for that sheet only. The evidence keeps the original name (`caption`) and adds
   `caption_review: {classification, mapping_sha256, decided_on}`. Stored-evidence revalidation honours the review
   only when the mapping hash in the evidence is present. A `substantive` sheet keeps `unsupported_context`. Title and
   header qualifiers are never dropped.
7. **Provenance.** Each candidate's evidence adds `mapping_sha256`, `reviewer`, `decided_on` and the manifest entry.
   The confirmation code (`candidate_hash8`) also covers `mapping_sha256`.
8. **Publication date.** The date is applied by re-importing with `--published-on`, as in Phase 4AP §2.2 item 4. The
   manifest only records where the workbook states it.

### 3.3 Stage 5 tests (synthetic workbooks, written first)

Each scenario below gets its own test:

- the approved canonical block
- a component or variant block that names the same indicator
- two plausible headline candidates, with the manifest naming one
- a manifest naming two columns for one (indicator, basis)
- a workbook hash mismatch
- a revised workbook version
- a moved worksheet
- a moved column
- a modified block title
- a modified unit header
- unsupported or conflicting units
- unemployment `unit_evidence` absent, wrong cell or wrong text
- a sheet context that is not reviewed, or reviewed as `substantive`
- a wrong forecast boundary
- a basis mismatch
- third-party attribution
- an OCR entry
- duplicate forecast contributions
- revoked source authorization (`version_refusal`)
- the confirmation code changing with the manifest
- unchanged `xlsx-anz-3` results without a manifest

## 4. Next steps

1. The owner runs `tables review 5` and answers A to F (§2.1).
2. The owner approves or amends §3. Stage 5 then builds it with TDD. Stage 6 is the real pilot: backup, dry run with
   counts by indicator, owner `--list` and full cell-by-cell reconciliation, then `--confirm`, then internal view,
   snapshot isolation, and rollback and revocation checks.
3. If the answers leave no supportable series (A and C `none`, or `substantive` sheets), the result is NO-GO with
   validation unchanged.
