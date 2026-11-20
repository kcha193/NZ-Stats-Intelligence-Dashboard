"""Phase 4AM masked what-if probe. Owner's machine; prints ints, bools and fixed codes only.

Read-only: DB opened mode=ro, same registry gate and SHA check as `tables extract`, nothing written.
Every string leaving this script must be a production rejection/indicator code or a key from KEYS below.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path.cwd()
SRC = ROOT / "backend/src/nzstats/research"
CODES = set()
for f in SRC.glob("table_*.py"):
    CODES |= set(re.findall(r'"([a-z]+(?:_[a-z]+)+)"', f.read_text()))
CODES |= {
    "ocr",
    "cpi_inflation",
    "gdp",
    "unemployment",
    "none",
    "author",
    "third_party",
    "forecast",
    "actual",
    "unknown",
    "calendar",
    "quarter",
    "month_end",
    "year_to",
    "percent",
    "ok",
    "error",
    "percentage_points",
    "basis_points",
    "percent_of_gdp",
    "multi",
}


def check(v, path="$"):
    if isinstance(v, (bool, int)):
        return
    if isinstance(v, str):
        if v not in CODES:
            raise SystemExit(json.dumps({"guard": "refused_string", "at_depth": path.count("/")}))
        return
    if isinstance(v, dict):
        for k, x in v.items():
            if not (re.fullmatch(r"[a-z][a-z0-9_]*", k) or re.fullmatch(r"\d{1,2}", k)):
                raise SystemExit(json.dumps({"guard": "refused_key"}))
            check(x, f"{path}/{k}")
        return
    if isinstance(v, list):
        for x in v:
            check(x, path + "/i")
        return
    raise SystemExit(json.dumps({"guard": "refused_type"}))


@contextlib.contextmanager
def silenced():
    logging.disable(logging.CRITICAL)
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (*saved, null):
            os.close(fd)


YEAR = re.compile(r"\b(19\d\d|20\d\d)\b")
LABEL = re.compile(r"\b(?:table|figure|chart|exhibit)\s+\d+\b", re.IGNORECASE)


def run() -> dict:
    from nzstats.research.extract import ExtractionLimits
    from nzstats.research.registry import load_registry
    from nzstats.research.table_context import (
        _NEUTRAL,
        _PUBLICATION,
        FOOTNOTE,
        SCENARIO,
        _unknown_context,
        unmarked_notes,
    )
    from nzstats.research.table_forecast import (
        _OTHER_FORECASTERS,
        _SOURCE,
        _indicator,
        _names,
        _third_party,
        interpret,
    )
    from nzstats.research.table_grid import find_tables
    from nzstats.research.table_ingest import _VERSION, version_refusal
    from nzstats.research.table_parse import column_kind, period_of, unit_of_text
    from nzstats.research.table_words import extract_words

    data = Path(os.environ.get("NZSTATS_DATA_DIR", "./data"))
    conn = sqlite3.connect(f"file:{(data / 'nzstats.db').resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute(_VERSION, (4,)).fetchone()
    reason, inst = version_refusal(row, load_registry())
    if reason or inst is None:
        return {"error": "error"}
    body = (data / "raw" / row["path"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != row["raw_sha256"]:
        return {"error": "error"}
    words = extract_words(body, ExtractionLimits())
    tables, _ = find_tables(words)
    names = (inst.name, inst.key, inst.name.removesuffix(" New Zealand"))
    fallback = urlsplit(row["canonical_url"]).path.rstrip("/").rsplit("/", 1)[-1]
    title = row["title"] if row["title"] != fallback else ""
    conn.close()

    others = [n for n in _OTHER_FORECASTERS if not _names(n, names)]
    stats = ("stats nz", "statistics new zealand")

    def who(text: str) -> dict:
        return {
            "names_publisher": _names(text, names),
            "names_stats_agency": _names(text, stats),
            "other_forecasters": sum(_names(text, (n,)) for n in others if n not in stats),
            "third_party_rule": _third_party(text, names),
        }

    def unknown(text: str) -> int:
        t = text
        for n in names:
            t = re.sub(rf"(?<!\w){re.escape(n)}(?!\w)", " ", t, flags=re.IGNORECASE)
        return sum(w.lower() not in _NEUTRAL for w in re.findall(r"[^\W\d_]+", t))

    out: dict = {}
    # ---- document title
    t_pub = _PUBLICATION.sub(" ", title)
    head, _, tail = t_pub.partition(":")
    out["title"] = {
        "present": bool(title),
        "has_colon": ":" in title,
        "unknown_words_before_colon": unknown(head),
        "unknown_words_after_colon": unknown(tail),
        "years": len(YEAR.findall(title)),
        "scenario_words": len(SCENARIO.findall(title)),
        **who(title),
    }

    p5 = [t for t in tables if t.page_start == 5]
    p8 = [t for t in tables if t.page_start == 8]
    out["tables_p5"] = len(p5)
    out["tables_p8"] = len(p8)

    def describe(t) -> dict:
        cap = t.caption or ""
        m = list(LABEL.finditer(cap))
        prose, label = (cap[: m[-1].start()], cap[m[-1].start() :]) if m else ("", cap)
        col_years = set()
        cols = []
        for c in t.columns:
            if c.role != "value":
                continue
            col_years |= {int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", c.headers[-1])}
            p_own, code_own = period_of((c.headers[-1],))
            p_ctx, code_ctx = period_of((cap, *unmarked_notes(t.notes), *c.headers))
            cols.append(
                {
                    "kind": column_kind(c.headers),
                    "groups": len(c.headers) - 1,
                    "own_period": p_own.kind if p_own else (code_own or "none"),
                    "with_context": p_ctx.kind if p_ctx else (code_ctx or "none"),
                    "redefined": bool(p_own and p_ctx and p_own != p_ctx),
                    "pct_in_header": "%" in " ".join(c.headers),
                }
            )
        notes = []
        for n in t.notes:
            s = n.strip()
            ys = {int(y) for y in YEAR.findall(s)}
            notes.append(
                {
                    "marked": bool(FOOTNOTE.match(s)),
                    "source_line": bool(_SOURCE.match(s)),
                    "words": len(s.split()),
                    "years": len(ys),
                    "years_matching_columns": len(ys & col_years),
                    "months": len(
                        re.findall(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", s, re.IGNORECASE)
                    ),
                    "pct": "%" in s,
                    "unknown_words": unknown(s),
                    "unknown_context_rule": _unknown_context(s, names),
                    **who(s),
                }
            )
        rows = []
        for r in t.body_rows:
            lab = r[0].text
            found = _indicator(lab)
            u, ucode = unit_of_text(lab)
            rows.append(
                {
                    "indicator": next(iter(found)) if len(found) == 1 else ("multi" if found else "none"),
                    "label_words": len(lab.split()),
                    "label_footnote": bool(re.search(r"[*†‡¹²³⁴⁵⁶⁷⁸⁹]", lab)),
                    "label_unit": u or ucode or "none",
                    "values": len(r) - 1,
                }
            )
        return {
            "caption": {
                "label_found": bool(m),
                "label_count": len(m),
                "prose_words": len(prose.split()),
                "label_words": len(label.split()),
                "prose_scenario": len(SCENARIO.findall(prose)),
                "label_scenario": len(SCENARIO.findall(label)),
                "prose_years": len(YEAR.findall(prose)),
                "label_years": len(YEAR.findall(label)),
                "prose_unknown": unknown(prose),
                "label_unknown": unknown(label),
                "prose_who": who(prose),
                "label_who": who(label),
                "forecast_word": bool(re.search(r"\bforecasts?\b", cap, re.IGNORECASE)),
                "pct": "%" in cap,
            },
            "columns": cols,
            "notes": notes,
            "rows": rows,
        }

    out["p5"] = [describe(t) for t in p5]
    out["p8"] = [describe(t) for t in p8]

    # ---- what-if variants (interpret on modified table objects; nothing written)
    def label_only(t):
        cap = t.caption or ""
        m = list(LABEL.finditer(cap))
        return dataclasses.replace(t, caption=cap[m[-1].start() :] if m else cap)

    def no_source(t):
        return dataclasses.replace(t, notes=tuple(n for n in t.notes if not _SOURCE.match(n.strip())))

    def no_years(t):
        return dataclasses.replace(t, notes=tuple(YEAR.sub(" ", n) for n in t.notes))

    def no_notes(t):
        return dataclasses.replace(t, notes=())

    variants = {
        "baseline": (lambda t: t, title),
        "caption_label_only": (label_only, title),
        "title_blank": (lambda t: t, ""),
        "label_only_title_blank": (label_only, ""),
        "label_only_title_blank_no_source": (lambda t: no_source(label_only(t)), ""),
        "label_only_title_blank_note_years_removed": (lambda t: no_years(label_only(t)), ""),
        "label_only_title_blank_no_notes": (lambda t: no_notes(label_only(t)), ""),
    }
    wi = {}
    for key, (fn, ttl) in variants.items():
        fc, rj = interpret([fn(t) for t in tables], publisher_names=names, document_title=ttl)
        wi[key] = {
            "accepted": len(fc),
            "accepted_p5": sum(f.page == 5 for f in fc),
            "accepted_p8": sum(f.page == 8 for f in fc),
            "by": dict(Counter(f"{f.indicator}__{f.author_role}__{f.kind}" for f in fc)),
            "p5_codes": dict(Counter(r.code for r in rj if r.page == 5)),
            "p8_codes": dict(Counter(r.code for r in rj if r.page == 8)),
        }
    out["what_if"] = wi
    return out


if __name__ == "__main__":
    with silenced():
        try:
            result = run()
        except BaseException:  # noqa: BLE001
            result = {"error": "error"}
    # keys like cpi_inflation__third_party__forecast must also pass the guard
    for v in result.get("what_if", {}).values():
        for k in list(v.get("by", {})):
            for part in k.split("__"):
                if part not in CODES:
                    raise SystemExit(json.dumps({"guard": "refused_by_key"}))
    check(result)
    print(json.dumps(result, indent=1, sort_keys=True))
