"""Phase 4AP masked probe: sheet-name words and block identity on a stored ANZ workbook version.

Same gate as `probe_rejections.py`. Prints only ints and booleans: never a word, title, name or value.

    PYTHONPATH=backend/src backend/.venv/bin/python benchmarks/xlsx_inspect/probes/phase_4ap/probe_identity.py 5
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import sqlite3
import sys

from nzstats.config import load_settings
from nzstats.research import xlsx_anz as m
from nzstats.research.compare import _GDP_VARIANT, _NOMINAL, _REAL
from nzstats.research.table_context import _NEUTRAL
from nzstats.research.table_forecast import _indicator
from nzstats.research.table_ingest import _VERSION
from nzstats.research.xlsx_cells import read_cells

NAMES = ("ANZ New Zealand", "anz", "ANZ")


def words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[^\W\d_]+", text)]


def main(version: int) -> dict:
    settings = load_settings({"NZSTATS_DATA_DIR": "data"})
    conn = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute(_VERSION, (version,)).fetchone()
    assert row is not None and row["format"] == "xlsx"
    body = (settings.raw_dir / row["path"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == row["raw_sha256"]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        wb = read_cells(body)
    out = []
    for sheet in wb.sheets:
        if m._date_rows(sheet, wb.date1904) is None:
            continue
        name_words = [w for w in words(sheet.name) if w not in {n.lower() for n in NAMES}]
        unknown = [w for w in name_words if w not in _NEUTRAL]
        blocks, _ = m._blocks(sheet)
        titles = {}
        for block, title in blocks.values():
            titles[block] = title
        mapped = {b: t for b, t in titles.items() if len(_indicator(t)) == 1}
        title_words = [set(words(t)) for t in titles.values()]
        out.append(
            {
                "position": sheet.position,
                "sheet_name_words": len(name_words),
                "sheet_name_unknown_words": len(unknown),
                "sheet_name_unknown_words_in_every_title": sum(all(w in tw for tw in title_words) for w in unknown),
                "sheet_name_unknown_words_in_some_title": sum(any(w in tw for tw in title_words) for w in unknown),
                "sheet_name_names_an_indicator": bool(_indicator(sheet.name)),
                "blocks": len(titles),
                "distinct_titles": len(set(titles.values())),
                "blocks_whose_title_alone_maps": len(mapped),
                "titles_stating_real": sum(bool(_REAL.search(t)) for t in titles.values()),
                "titles_stating_nominal": sum(bool(_NOMINAL.search(t)) for t in titles.values()),
                "titles_gdp_variant": sum(bool(_GDP_VARIANT.search(t)) for t in titles.values()),
                "title_word_counts": sorted(len(words(t)) for t in titles.values()),
            }
        )
    return {"sheets": out}


if __name__ == "__main__":
    print(json.dumps(main(int(sys.argv[1])), indent=1, sort_keys=True))
