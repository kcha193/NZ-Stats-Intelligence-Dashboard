# PDF table parser benchmark (Phase 4AL)

Benchmark only. Production code (`backend/`) never imports this package, and none of these dependencies is a production
dependency. Record and results: `docs/phase-4al-pdf-parser-benchmark.md`.

```sh
cd benchmarks/pdf_tables
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest                      # synthetic fixtures only
.venv/bin/python -m pdfbench.run_synthetic      # accuracy against ground truth (synthetic replicas)
# From the repository root, owner's machine only: masked, counts-only diagnostics of a stored version
PYTHONPATH=benchmarks/pdf_tables:backend/src benchmarks/pdf_tables/.venv/bin/python -m pdfbench.run_masked 4 --pages 5 8
```

Privacy: `run_masked` prints only integers, floats, booleans and fixed codes through a schema that refuses anything else.
It never prints text, figures, coordinates, paths or images from the document, and no model or service reads it.
