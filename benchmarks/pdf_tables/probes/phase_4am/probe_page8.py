"""Masked what-if for page 8: supply an f marker on every month-end column and a % on the OCR label. Codes and ints only."""

import dataclasses
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path[:0] = ["benchmarks/pdf_tables", "backend/src"]
from pdfbench.masked import silenced


def run():
    from urllib.parse import urlsplit

    from nzstats.research.extract import ExtractionLimits
    from nzstats.research.registry import load_registry
    from nzstats.research.table_forecast import interpret
    from nzstats.research.table_grid import find_tables
    from nzstats.research.table_ingest import _VERSION
    from nzstats.research.table_parse import period_of
    from nzstats.research.table_words import extract_words

    from pdfbench.run_masked import load_version

    data = Path("./data")
    conn = sqlite3.connect(f"file:{(data / 'nzstats.db').resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    reg = load_registry()
    pdf = load_version(conn, 4, data / "raw", reg)
    row = conn.execute(_VERSION, (4,)).fetchone()
    inst = reg[row["key"]]
    conn.close()
    names = (inst.name, inst.key, inst.name.removesuffix(" New Zealand"))
    fb = urlsplit(row["canonical_url"]).path.rstrip("/").rsplit("/", 1)[-1]
    title = row["title"] if row["title"] != fb else ""
    tables, _ = find_tables(extract_words(pdf, ExtractionLimits()))
    p8 = [t for t in tables if t.page_start == 8]

    def supplied(t):
        cols = tuple(
            dataclasses.replace(c, headers=(*c.headers[:-1], c.headers[-1] + "f"))
            if c.role == "value" and period_of((c.headers[-1],))[0]
            else c
            for c in t.columns
        )
        rows = tuple(
            (dataclasses.replace(r[0], text=r[0].text + " (%)"), *r[1:])
            if re.search(r"\bocr\b|official cash rate", r[0].text, re.IGNORECASE)
            else r
            for r in t.body_rows
        )
        return dataclasses.replace(t, columns=cols, body_rows=rows)

    out = {}
    for key, fn, ttl in [
        ("markers_units", supplied, title),
        ("markers_units_title_blank", supplied, ""),
        ("markers_units_title_blank_no_caption", lambda t: dataclasses.replace(supplied(t), caption=None), ""),
        ("markers_units_no_caption", lambda t: dataclasses.replace(supplied(t), caption=None), title),
    ]:
        fc, rj = interpret([fn(t) for t in p8], publisher_names=names, document_title=ttl)
        out[key] = {
            "accepted": len(fc),
            "roles": dict(Counter(f.author_role for f in fc)),
            "ocr_row_codes": dict(Counter(r.code for r in rj if r.code not in ("unmapped_row", "unsupported_unit"))),
        }
    return out


with silenced():
    try:
        r = run()
    except BaseException:  # noqa: BLE001 - only a fixed code may leave, never a message
        r = {"error": 1}


def chk(v):
    if isinstance(v, dict):
        for k, x in v.items():
            assert re.fullmatch(r"[a-z_]+", k)
            chk(x)
    else:
        assert isinstance(v, int)


chk(r)
print(json.dumps(r, sort_keys=True))
