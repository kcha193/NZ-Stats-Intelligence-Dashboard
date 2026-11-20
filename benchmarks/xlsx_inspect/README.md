# Masked workbook inspector (Phase 4AN)

Diagnostic only. Production code (`backend/`) never imports this package, and `openpyxl` is not a production dependency.
Record and owner runbook: `docs/phase-4an-anz-workbook.md`.

```sh
cd benchmarks/xlsx_inspect
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest                      # synthetic workbooks only
# From the repository root, owner's machine only, on a workbook the owner saved:
PYTHONPATH=benchmarks/xlsx_inspect:backend/src benchmarks/xlsx_inspect/.venv/bin/python -m xlsxinspect FILE.xlsx \
  --expect-sha256 HEX
```

The archive is checked with the standard library before `openpyxl` opens anything (sizes, member names, encryption,
DOCTYPE/ENTITY, VBA, external links). `openpyxl` then reads formulas and cached values with links and macros off; nothing is
evaluated.

Before loading, streaming XML checks bound worksheet rectangles (including implicit cells), merged ranges, hyperlink
ranges and comment references. Across the archive, limits are 100,000 rectangle cells, 100,000 expanded range cells,
1,000 merges, 200,000 XML elements and nesting depth 64. Oversized sparse sheets are refused rather than truncated.
Repeated worksheet/comment targets and ambiguous worksheet structures are refused; ordinary chart anchors and shared
image dependencies remain supported. The resulting worksheet bounds are checked again before cell iteration.

Relationship and content-type metadata is parsed with the standard library's Expat parser, including UTF-8 and UTF-16
LE/BE and XML character references. DTDs and entities are refused. Missing, malformed, unsupported or ambiguous metadata
refuses inspection; incomplete metadata flags remain `null`. Macro-enabled, VBA and legacy macro-sheet content types
are flagged. Archive refusals keep the existing masked output schema.

Formula classification uses a linear lexer: only workbook-qualified reference operands count as external. Bracketed
numeric table headers and string literals do not count. Uninspectable quotes or brackets return a fixed error code.

Privacy: output goes only through `xlsxinspect.guard.emit`, which accepts a fixed key set, numbers, booleans, fixed codes,
lists of ints and the file's SHA-256. It never prints sheet names, cell text, figures, paths or error messages, and no model
or service reads the workbook.
