"""Accuracy against ground truth on the synthetic cases: one row per (case, parser). Synthetic text only."""

from __future__ import annotations

import dataclasses
import statistics
import sys

from pdfbench.adapters import PARSERS, run
from pdfbench.metrics import Score, score
from pdfbench.model import Case
from pdfbench.synth import cases as all_cases

_COLUMNS = ["case", "parser", "error", *(f.name for f in dataclasses.fields(Score)), "seconds"]


def rows(cases: list[Case], parsers: list[str], repeat: int = 1) -> list[dict]:
    out = []
    for case in sorted(cases, key=lambda c: c.name):
        pages = sorted({t.page for t in case.truth})
        for name in parsers:
            times, result = [], None
            for _ in range(repeat):
                result = run(name, case.pdf, pages)
                times.append(result[2])
            tables, error, _ = result
            s = score(case.truth, tables or [])
            out.append(
                {
                    "case": case.name,
                    "parser": name,
                    "error": error,
                    **dataclasses.asdict(s),
                    "seconds": statistics.median(times),
                }
            )
    return out


def markdown(table: list[dict]) -> str:
    def fmt(v: object) -> str:
        return f"{v:.3f}" if isinstance(v, float) else ("" if v is None else str(v))

    lines = ["| " + " | ".join(_COLUMNS) + " |", "|" + "---|" * len(_COLUMNS)]
    lines += ["| " + " | ".join(fmt(r[c]) for c in _COLUMNS) + " |" for r in table]
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.write(markdown(rows(all_cases(), sorted(PARSERS), repeat=3)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
