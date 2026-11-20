"""Masked probe of the page-5 row-label dispute (tables-14 body row 0 vs Camelot network). Ints and bools only."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path[:0] = ["benchmarks/pdf_tables", "backend/src"]
from pdfbench.masked import silenced
from pdfbench.run_masked import load_version

SUP = "¹²³⁴⁵⁶⁷⁸⁹⁰*†‡"


def run() -> dict:
    from nzstats.research.registry import load_registry

    from pdfbench.adapters import run as run_parser

    data = Path(os.environ.get("NZSTATS_DATA_DIR", "./data"))
    conn = sqlite3.connect(f"file:{(data / 'nzstats.db').resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    pdf = load_version(conn, 4, data / "raw", load_registry())
    conn.close()
    existing, err_e, _ = run_parser("existing", pdf, [5], 120)
    camelot, err_c, _ = run_parser("camelot_network", pdf, [5], 120)
    if err_e or err_c:
        return {"error_existing": bool(err_e), "error_camelot": bool(err_c)}
    (t14,) = [t for t in existing if t.page == 5]
    row = t14.grid[1]
    words = row[0].split()
    values = [c for c in row[1:] if c]
    marked = [i for i, w in enumerate(words) if any(ch in SUP for ch in w)]
    out = {
        "t14_label_words": len(words),
        "t14_marker_word_index": marked,
        "t14_marker_fused_to_word": [any(ch not in SUP for ch in words[i]) for i in marked],
        "t14_marker_is_last_word": [i == len(words) - 1 for i in marked],
        "t14_values": len(values),
    }
    best = None
    for t in camelot:
        for r in t.grid:
            hits = sum(v in [c.strip() for c in r] for v in values)
            if best is None or hits > best[0]:
                best = (hits, r)
    hits, crow = best
    clabel = " ".join(c for c in crow if c and not re.fullmatch(r"[-−–+(]?[\d.,]+\)?%?", c.strip()))
    cwords = clabel.split()
    strip = lambda w: w.rstrip(SUP)
    sup2digit = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰", "1234567890")
    out.update(
        {
            "camelot_row_value_hits": hits,
            "camelot_label_words": len(cwords),
            "word_found_exact": [w in cwords for w in words],
            "word_found_marker_stripped": [strip(w) in [strip(c) for c in cwords] for w in words],
            "word_found_marker_as_digit": [w.translate(sup2digit) in cwords for w in words],
            "camelot_extra_words": sum(c not in words and c not in [strip(w) for w in words] for c in cwords),
            "labels_equal_after_marker_strip": " ".join(strip(w) for w in words if strip(w))
            == " ".join(strip(c) for c in cwords if strip(c)),
        }
    )
    return out


if __name__ == "__main__":
    with silenced():
        try:
            result = run()
        except BaseException:  # noqa: BLE001
            result = {"error": True}
    for k, v in result.items():
        assert re.fullmatch(r"[a-z0-9_]+", k)
        vals = v if isinstance(v, list) else [v]
        assert all(isinstance(x, (bool, int)) for x in vals)
    print(json.dumps(result))
