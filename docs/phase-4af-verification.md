# Phase 4AF: verification record

11 November 2026, Pacific/Auckland. Branch `feat/phase-4af-bank-pdf-extraction` from main `a3a5449` (PR #58 merged).

**No live ingestion exists for any bank and no permission field was changed.** No bank was contacted, no hosted or local model
was called, nothing was paid for, nothing was deployed, scheduled or written to production data. The registry pin
(`PRE_APPROVAL_SHA256`) is unchanged, and `tests/research/test_table_isolation.py` asserts that all five real banks stay
`needs_review` with manual import and model processing denied.

## Results on the final tree

| Check | Result |
|---|---|
| Backend (`pytest`, whole suite) | 6,341 passed (baseline `main`: research subset 4,310 passed, 5 skipped before this work) |
| Ruff `check` and `format --check` | clean |
| Frontend unit tests, `tsc -b`, oxlint (no bank or table warnings), build | 630 passed; types clean; build ok |
| `npm audit` | 0 vulnerabilities |
| `npm run gen:api` | `schema.d.ts` unchanged (the internal bank routes are hand-written types, not in the published API) |
| Playwright, live (desktop, tablet, mobile) | 204 passed |
| Playwright, synthetic research | 18 passed, 3 expected skips |
| Static site and parity (`scripts/e2e_static.sh`) | 315 passed, 54 expected skips |
| Offline replay (`test_table_e2e.py`) | passes; run twice from empty directories, byte-identical answers on all six routes; zero network and zero model calls (guards raise) |
| Isolation (`test_table_isolation.py`, `tests/publish/test_research_isolation.py`) | table modules imported only inside `research/`; never by a public or private gate; not scheduled; a snapshot is byte-identical with table rows present |

The browser suites are unchanged by this phase's UI edits except the bank section; they were run on the final build of the
branch. The backend suite was run on the same tree after the review fixes.

## What the replay proves

Synthetic PDFs (three fictitious banks, two quarterly reports each) go through the real manual-import path, the real table
extractor in its isolated child process, the real summarise and verify pipeline (a scripted local stand-in, two reports only),
the bank view and analytics, and the internal routes. Asserted: actuals stored apart from forecasts; a dash kept as missing;
a second table with a row between two columns refused whole (`ambiguous_columns`) and none of its values anywhere; a report whose
prose disagrees with its own table (bank C: 4.4 against 4.3) excluded on both readings with the bank's older figure **not**
shown in its place; the OCR comparison a three-bank consensus and the CPI comparison a two-bank comparison, each labelled "Not a
market consensus"; a revision between two table-read reports; forecast versus the first-published actual; real bank keys still
`permission_denied`.

## Independent review and what was done with it

A separate reviewer read the whole diff without this session's context. Every finding below was checked against the code.

| Finding | Disposition |
|---|---|
| Critical: a scenario or downside table read as the central forecast | **Fixed**, failing test first: scenario in a caption, row label or column header refuses it (`scenario_table`, `scenario_row`, `scenario_column`); scenario *claims* are not reconciled with central table figures |
| Critical: a captioned second table (same header, or none) joined as a continuation of the first | **Fixed**: a block with its own caption starts a new table unless the caption says "continued" |
| Important: footnote or source line away from the table; caption naming another forecaster | **Fixed**: any footnote marker refuses the figure; a caption naming another forecaster (and not the bank) makes it third party; names match as whole words (`anz` is not found in `Manzano`) |
| Important: `(%)` caption applied to a count; absurd magnitude overflowing `float` | **Fixed**: `unsupported_unit` for `000s`, `million`, `$`, `index`, `persons`, `hours`; `value_out_of_range` from one million |
| Important: an exact claim and table figure double counted downstream (two vintages, double matched) | **Fixed**: an exact match is not added as a second forecast; the checked claim stands and the match is reported in `table_reconciliation` |
| Important: a header drawn in two pieces (`Dec`, `2026`) became a calendar year | **Fixed**: month or quarter plus year merge into one header |
| Important: pypdf coalesces text drawn in one `BT..ET` block | **Documented limit** with a fail-safe test (no table, never a wrong number); a content-stream reader is the first Phase 4AG item |
| Important: no per-document owner withdrawal of table figures | **Documented** (purge, revoke the route, or turn `auto_display` off) |
| Minor: purge landing during a parse raised an unhandled database error | **Fixed**: fixed refusal `purged`, nothing stored |
| Minor: `undated` not counted as an expected-but-missing series | **Fixed** |
| Minor: non-finite word positions; `sys.path` insert of a site-packages root; evidence drawer overclaim | **Fixed** |
| Minor: purge dry-run omits table rows; stale extraction after a hash revert; analytics now key "same document" by version | **Documented** |

## Deferred 4AE findings: decisions

| Finding | Decision |
|---|---|
| `derive_adjustment` read `U.S.A.` and a bare `SA` as seasonally adjusted | **Fixed**, failing test first (`(SA)` and `S.A.` still count) |
| An all-undated series reported `ok` | **Fixed**: new `undated` state, attention (exit 1), shown as "Date unknown", counted as expected-but-missing |
| `bank-status` printed UTC | **Fixed**: Pacific/Auckland in text, UTC kept in `--json` |
| `/freshness` returned exit code 0 on an unreadable registry | **Fixed**: 3, "could not run", as the command reports |
| A failed AI stance was shown in full on the card | **Fixed**: collapsed behind its failure label, closed by default |
| Divergence did not rank banks within a group | **Fixed**: highest forecast first, ties by key; the page says so |
| Gate re-evaluated for every route | **Measured, deferred**: about 50 ms per route at 40 synthetic summaries, about 320 ms for a page's six requests. Not a demonstrated defect at this size; real documents are larger, so re-measure at the pilot |
| Empty-state wording, revisions "Unchanged" copy and unrendered measure changes, `UNIT_LABELS` import location, three loose review-focus tests | **Deferred**: wording and structure only, no wrong number, state or leak |

## Limits stated plainly

- **Real bank layouts are untested.** No real report was read. The extractor reads synthetic fixtures built from the brief,
  and the text-block limit above may mean real PDFs yield nothing at first. A first pilot must begin with a dry run and a
  person checking every cell ([pilot](phase-4af-first-bank-pilot.md)).
- **Agreement is not accuracy.** Two readings of one page can share a misreading; the reconciliation carries no "verified" flag
  and an exact match is reported as agreement only. Economic correctness of any figure is not assessed.
- Rounding differences keep the model claim and drop the table figure, losing the more precise printed value.
- Only the "table attributes it to someone else" direction of attribution is detected.
- Details of every rule and limit: [phase-4af-pdf-tables.md](phase-4af-pdf-tables.md).
