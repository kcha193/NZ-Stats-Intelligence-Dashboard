import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path[:0] = ["benchmarks/pdf_tables", "backend/src"]
from pdfbench.masked import silenced

# Class names are written to stdout only on the owner's terminal; the committed output collapses them (see --collapse).
CLASSES = {
    "official": ("treasury", "rbnz", "reserve bank", "imf", "oecd", "world bank"),
    "data_vendor": ("bloomberg", "reuters"),
    "market_pricing": ("market pricing",),
    "consensus": ("consensus",),
    "other_bank": ("asb", "bnz", "westpac", "kiwibank"),
}
COLLAPSE = "--collapse" in sys.argv


def run():
    from nzstats.research.extract import ExtractionLimits
    from nzstats.research.registry import load_registry
    from nzstats.research.table_forecast import _SOURCE, _names
    from nzstats.research.table_grid import find_tables
    from nzstats.research.table_words import extract_words

    from pdfbench.run_masked import load_version

    data = Path("./data")
    conn = sqlite3.connect(f"file:{(data / 'nzstats.db').resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    pdf = load_version(conn, 4, data / "raw", load_registry())
    conn.close()
    tables, _ = find_tables(extract_words(pdf, ExtractionLimits()))
    LABEL = re.compile(r"\b(?:table|figure|chart|exhibit)\s+\d+\b", re.IGNORECASE)
    out = {}
    for t in tables:
        if t.page_start not in (5, 8):
            continue
        cap = t.caption or ""
        m = list(LABEL.finditer(cap))
        prose = cap[: m[-1].start()] if m else ""
        for kind, text in [("prose", prose)] + [("source", n) for n in t.notes if _SOURCE.match(n.strip())]:
            key = f"p{t.page_start}_t{t.index}_{kind}"
            counts = {c: sum(_names(text, (n,)) for n in ns) for c, ns in CLASSES.items()}
            out[key] = {"listed_other_forecasters": sum(counts.values())} if COLLAPSE else counts
            if kind == "source":
                s = text.strip()
                i = s.find(":")
                tail = s[i + 1 :] if i >= 0 else s
                # does the first sentence (the source list) hold the date, or a later sentence?
                parts = re.split(r"(?<=[.;])\s+", tail, maxsplit=1)
                out[key]["year_in_first_sentence"] = bool(re.search(r"\b20\d\d\b", parts[0]))
                out[key]["year_in_later_sentence"] = len(parts) > 1 and bool(re.search(r"\b20\d\d\b", parts[1]))
                out[key]["sentences"] = len(re.findall(r"[.;](?:\s|$)", tail)) or 1
    return out


with silenced():
    try:
        r = run()
    except BaseException:  # noqa: BLE001 - only a fixed code may leave, never a message
        r = {"error": 1}
assert all(re.fullmatch(r"[a-z0-9_]+", k) for k in r)
assert all(isinstance(x, (int, bool)) for v in r.values() if isinstance(v, dict) for x in v.values())
print(json.dumps(r, sort_keys=True))
