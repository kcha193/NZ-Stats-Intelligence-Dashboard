# Phase 4AM masked probes

Owner's machine only. Each probe opens `data/nzstats.db` read-only, applies the same gate and SHA-256 check as
`tables extract`, silences every stream while the document is parsed, and prints only ints, booleans and production codes.
Nothing is written. Record: `docs/phase-4am-anz-root-cause.md`. Outputs: `../../results/phase-4am/`.

```sh
# from the repository root
export PYTHONPATH=backend/src
P=benchmarks/pdf_tables/.venv/bin/python
$P benchmarks/pdf_tables/probes/phase_4am/probe_semantics.py        # structure, what-if variants (pages 5 and 8)
$P benchmarks/pdf_tables/probes/phase_4am/probe_label.py            # page-5 row-label dispute, word by word
$P benchmarks/pdf_tables/probes/phase_4am/probe_page8.py            # page 8 with markers and units supplied
$P benchmarks/pdf_tables/probes/phase_4am/probe_attribution.py --collapse   # counts only; without --collapse, classes (do not commit)
```

They are diagnostics for version 4, not tests, and are not imported by the benchmark or by `backend/`.
