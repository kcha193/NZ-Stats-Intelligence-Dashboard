# Phase 4AR: ANZ canonical mapping and acceptance

22 November 2026, Pacific/Auckland. Branch `feat/phase-4ar-anz-canonical-mapping` from main `880742b` (Phase 4AQ,
PR #70 merged). This is a personal research project, run on the owner's own computer, with no connection to the owner's
employer.

**Status: MECHANISM BUILT; PILOT PENDING OWNER MAPPING ANSWERS. NO-GO for figures until then.** The owner approved the
Phase 4AQ §3 design on 22 November 2026 and asked for the build to go ahead. The six answers A to F (Phase 4AQ §2.1) have
not been supplied, so no mapping file exists. No agent chose a GDP or CPI block. No figure is stored. Nothing was
fetched, re-imported or sent to a model.

## 1. Baseline (verified, read-only)

| Check | Result |
|---|---|
| Repository | main `880742b`, clean |
| Version 5 | `xlsx`, SHA-256 begins `4c2d4b47cdf2`, 0 stored extractions |
| Database | schema 16, `integrity_check` ok |
| Dry run | 0 figures, 97 rejections (`ambiguous_indicator` ×52, `unmapped_row` ×42, `unsupported_period` ×2, `unit_unstated` ×1), code `e3f56a46`, interpreter `xlsx-anz-3` |
| Owner answers | none recorded; `data/research/` does not exist |

After the build, the same dry run without a mapping still gives the same counts, the same codes and code `e3f56a46`.

## 2. What was built

The Phase 4AQ §3 design, with no redesign of the workbook adapter.

| Part | Where | What it does |
|---|---|---|
| Manifest parser | `research/xlsx_mapping.py` | Strict schema `anz-workbook-mapping-1`: exact key sets, strict types (a bool is not a position), no duplicate JSON keys, 256 KiB cap. Indicators are `gdp`, `cpi_inflation` and `unemployment` only. OCR is invalid. Unit evidence is allowed only for unemployment, and only on its own sheet. One column per (indicator, basis), one entry per column, one headline block per indicator. Whole-file codes: `mapping_invalid`, `mapping_duplicate`. The mapping's identity is the SHA-256 of its exact bytes |
| Interpreter `xlsx-anz-4` | `research/xlsx_anz.py` | Used only with a mapping. `mapping_refusal` refuses the whole mapping for a workbook-hash mismatch (`mapping_hash_mismatch`) or a publication cell that does not hold the recorded text (`mapping_structure_mismatch`). The interpreter raises on either, so the check cannot be skipped. See §2.1 |
| Stored revalidation | `research/table_context.py` (`_reviewed_caption`) | A reviewed sheet name is exempt from the unknown-word rule only, and only on mapped evidence (`mapping_entry`) whose `caption_review` is `editorial`, names the same caption, and carries the same 64-hex mapping hash as the evidence. The period, unit, scenario, scope and adjustment checks still read the sheet name |
| Storage gate | `research/table_ingest.py` | `extract_version_tables(mapping=bytes)`. The confirmation code covers `xlsx-anz-4` and the mapping hash. Without a mapping it is unchanged. The stored extraction is `xlsx-anz-4` under a digest of the cells and the mapping, so a changed mapping is a new extraction with a new code |
| Superseded extractions | `research/table_store.py` | Re-applying an earlier mapping, or going back to no mapping, matches a stored extraction that is no longer the latest. The unique key forbids a second copy, so the run is refused (`an older identical extraction exists; restore a backup to return to it`) instead of reporting `unchanged` while a newer mapping stays current |
| Owner command | `research/cli.py` | `tables map V --series IND:SHEET:BLOCK:COL:BASIS … [--unit-evidence SHEET:CELL] [--sheet-context SHEET:CLASS …] [--published-on DATE@SHEET:CELL] --decided-on DATE --out FILE`. It copies the exact texts from the stored workbook, writes a new file with mode 0600, only under the data directory, and never overwrites one. It prints only the file's SHA-256 and counts. `tables extract V --mapping FILE` applies the file |
| Consumers | `table_view.py`, `bank_analytics.py` | `xlsx-anz-4` is a current interpreter for the internal view. Its figures are `history_unverified` in revisions and evaluation, like `xlsx-anz-3` |

### 2.1 Mapped interpretation rules

1. Per entry, the sheet position and name, block number and title, column letter and unit header must match exactly,
   after whitespace normalisation only. Otherwise the column gets `mapping_structure_mismatch` and gives no
   candidate. An entry whose sheet is unreadable, or whose column is gone, is reported the same way.
2. Only listed columns may stand for their indicator. Every other column naming a mapped indicator, including the
   headline block's other bases, is `not_canonical_series`. Indicators the mapping does not name keep `xlsx-anz-3`
   behaviour, including `ambiguous_indicator`.
3. A listed column whose label names another indicator is `mapping_indicator_mismatch`.
4. The basis must equal the basis the column's own title and header state (`quarterly`, `annual` or
   `annual_average`). A rate with no stated basis is read by its quarter, as `_horizon` does. Otherwise the column is
   `mapping_basis_mismatch`.
5. The unemployment unit becomes `percent` only when the cited cell is a text note below the table on that sheet (so
   the context rule reads it too), holds exactly the recorded text, and that text alone names percent. Otherwise the column stays `unit_unstated`. A note that
   disagrees with a stated header unit is `contradictory_unit`.
6. Every existing rule still applies: the bold tail and boundary, number formats, `unit_of_text`, `_horizon`, the
   context rule, the third-party and explicit-source checks, and the GDP price-basis rule. A title, header or note is
   never exempted. Only an `editorial` sheet name, at that exact position and name, is exempt, and only from the
   unknown-word rule.
7. Each candidate's evidence adds `mapping_sha256`, `mapping_reviewer`, `mapping_decided_on`, `mapping_entry`, and
   `caption_review` or `unit_evidence` where used.

## 3. Tests (synthetic workbooks only, a fictional bank)

`tests/research/test_xlsx_mapping.py` (interpreter and parser) and `tests/research/test_xlsx_mapping_pipeline.py`
(storage gate, internal view, CLI). Every Phase 4AQ §3.3 scenario has its own test. Coverage includes:

- the approved block; component and variant blocks; two plausible headlines with the manifest naming one;
- duplicate mappings; hash mismatch; a revised workbook version; a moved sheet or column; a modified title or header;
- unsupported and conflicting units; unit evidence that is absent, in the wrong cell, wrong text or names no percent;
- a sheet that is unreviewed, `substantive`, misnamed or mispositioned; wrong forecast boundaries; basis mismatches;
- third-party attribution, OCR, duplicate contributions and revoked source authorization;
- the confirmation code changing with the manifest; malformed and invalid manifests; position errors in `tables map`;
- `tables map` never overwriting a file and printing no workbook text.

Results: the new tests (`test_xlsx_mapping.py` and `test_xlsx_mapping_pipeline.py`) pass. The full backend suite gives
**7,408 passed**, exit 0, in 9 min 15 s. Ruff check and format are clean.

Two goldens recorded from main `880742b` before any change pin the unmapped path: `fdc24865` and `439ccf98`. All new
tests were watched failing first. The three regression pins passed from the start, as intended. Mutation checks on
eight key rules each turned at least one test red.

## 4. Independent review

Two independent reviews ran: a Superpowers code reviewer and a Caveman reviewer. Neither found a Critical issue.
Each accepted finding was fixed test-first, with each new test watched failing:

- re-applying an earlier mapping reported `unchanged` while a newer one stayed current (Important). It is now refused;
- the sheet review is narrowed to the unknown-word rule, and needs mapped evidence;
- the unit evidence must be a note below the table;
- `tables map --out` must be under the data directory;
- added tests: `tables map` against a revoked source, and a mapping passed for a PDF version.

Points not changed, with reasons:

- one indicator from two blocks stays refused. Phase 4AQ §2.1 B allows a second basis only from the same headline
  block;
- a publication cell that does not match refuses the whole mapping. This is stricter than the spec and fails closed;
- `_stated_basis` keeps its own function, built from the same imported patterns as `_horizon`. The basis tests pin
  the horizon each basis gives.

## 5. Pilot (Stage 6): not run

The pilot needs the owner's answers. Exact steps, all from the repository root with `NZSTATS_DATA_DIR=./data`:

1. `nzstats backup --bundle data/backups/pre-4ar-<UTC>` and `verify-backup`, then `shasum -a 256` of the saved file
   (must begin `4c2d4b47cdf2`).
2. Owner: `nzstats research tables review 5` in a real terminal, then the answers A to F. The CPI answer also needs its
   basis (`annual` etc.), because the manifest records a basis per series.
3. Owner or agent, positions only: `nzstats research tables map 5 --series gdp:S:B:X:BASIS --series
   cpi_inflation:S:B:X:BASIS [--series unemployment:S:B:X:quarterly --unit-evidence S:A1] --sheet-context S:editorial
   --published-on YYYY-MM-DD@S:A1 --decided-on 2026-11-DD --out data/research/anz-workbook-mapping-v5.json`. It prints
   only the hash and counts.
4. If F states a date: re-import the same file with `--published-on YYYY-MM-DD` (no new version), and check that
   `research bank-status` no longer shows `undated`.
5. `tables extract 5 --dry-run --mapping FILE`: counts by code, compared with the 97-rejection baseline.
6. Owner, own terminal: `--dry-run --list --mapping FILE`, then full cell-by-cell reconciliation against the workbook.
7. Owner only: `tables extract 5 --mapping FILE --confirm CODE`.
8. Check the internal Bank Outlooks view, snapshot byte-identity (`export-snapshot` against the pre-pilot copy) and the
   public API, then rehearse rollback (restore the bundle) and revocation (source refusal).

## 6. Verdict

**NO-GO for figures** at this point. The success criterion needs a series that passes owner reconciliation, and that
needs the owner's answers A to F (plus the CPI basis). The mechanism is ready and tested. Evidence still required:

- A: the headline real-GDP column, and B: its stated basis;
- C: the headline CPI column and its basis;
- D: the unemployment unit cell, or `not_stated`;
- E: `editorial` or `substantive` for each sheet in A or C;
- F: the stated publication date and cell, or `not_stated`.
