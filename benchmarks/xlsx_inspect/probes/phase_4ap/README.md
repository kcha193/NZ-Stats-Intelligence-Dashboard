# Phase 4AP masked probes

These run on the owner's machine only. Each probe opens `data/nzstats.db` read-only and checks the stored raw copy
against its SHA-256. It reads the workbook with the production reader (`xlsx-cells-1`) and re-runs the production rules
(`xlsx-anz-1`) part by part. Output is limited to ints, booleans and production codes, and nothing is written.

Record: [`docs/phase-4ap-anz-xlsx-ingestion.md`](../../../../docs/phase-4ap-anz-xlsx-ingestion.md).
Outputs: `../../results/phase-4ap-*.json`.

```sh
# from the repository root
export PYTHONPATH=backend/src
P=backend/.venv/bin/python
$P benchmarks/xlsx_inspect/probes/phase_4ap/probe_rejections.py 5   # per sheet and column: why it is refused
$P benchmarks/xlsx_inspect/probes/phase_4ap/probe_identity.py 5     # sheet-name words, block-title identity counts
```

These are diagnostics for version 5, not tests. Neither the inspector nor `backend/` imports them.
