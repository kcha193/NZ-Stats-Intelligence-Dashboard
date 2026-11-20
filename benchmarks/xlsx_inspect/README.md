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

Privacy: output goes only through `xlsxinspect.guard.emit`, which accepts a fixed key set, numbers, booleans, fixed codes,
lists of ints and the file's SHA-256. It never prints sheet names, cell text, figures, paths or error messages, and no model
or service reads the workbook.
