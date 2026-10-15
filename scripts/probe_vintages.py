"""Measure how far back official migration release files exist with the expected layout.

Usage: python scripts/probe_vintages.py 2026-07 2020-09   (newest to oldest, inclusive)
Throttled to 10 s per request; ~30 s per release.
Writes docs/data-sources/migration-vintage-depth.md.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import httpx

BASE = "https://www.stats.govt.nz"
UA = "NZStatsDashboard-research/0.1 (vintage-depth probe)"
OUT = Path(__file__).resolve().parents[1] / "docs" / "data-sources" / "migration-vintage-depth.md"
MONTHS = [
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
]
AGE_SEX_COLS = (
    "year_month", "month_of_release", "passenger_type", "direction", "sex", "age",
    "estimate", "standard_error", "status",
)
CIT_COLS = (
    "year_month", "month_of_release", "passenger_type", "direction", "citizenship",
    "visa", "country_of_residence", "estimate", "standard_error", "status",
)


def months_desc(start: str, end: str) -> list[str]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) >= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def throttled(client: httpx.Client, url: str, **kw) -> httpx.Response:
    time.sleep(10)
    return client.get(url, **kw)


def header_line(client: httpx.Client, url: str) -> str | None:
    resp = throttled(client, BASE + url, headers={"Range": "bytes=0-600"})
    if resp.status_code not in (200, 206):
        return None
    return resp.content.decode("utf-8-sig", errors="replace").splitlines()[0]


def has_columns(header: str | None, columns: tuple[str, ...]) -> bool:
    if not header:
        return False
    names = {c.strip().strip('"') for c in header.split(",")}
    return all(col in names for col in columns)


def main(start: str, end: str) -> None:
    rows = []
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=120) as c:
        for ym in months_desc(start, end):
            year, month = ym.split("-")
            slug = f"international-migration-{MONTHS[int(month) - 1]}-{year}"
            page = throttled(c, f"{BASE}/information-releases/{slug}/")
            if page.status_code != 200:
                rows.append((ym, f"page {page.status_code}", "-", "-"))
                print(rows[-1], file=sys.stderr, flush=True)
                continue
            text = page.text.replace("\\/", "/")
            urls = list(dict.fromkeys(re.findall(r"/assets/Uploads/[^\"\\\s&]+?\.csv", text)))
            a = next((u for u in urls if re.search(r"age.*sex", u.lower())), None)
            b = next((u for u in urls if re.search(r"citizenship.*visa.*country", u.lower())), None)
            ha = header_line(c, a) if a else None
            hb = header_line(c, b) if b else None
            ok_a, ok_b = has_columns(ha, AGE_SEX_COLS), has_columns(hb, CIT_COLS)
            rows.append((
                ym, "ok",
                "ok" if ok_a else f"MISSING/CHANGED ({ha})",
                "ok" if ok_b else f"MISSING/CHANGED ({hb})",
            ))
            print(rows[-1], file=sys.stderr, flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Migration release-file vintage depth", "",
        f"Probed {start} down to {end}. 'ok' = file present and header has all expected columns.",
        "", "| Release | Page | age/sex CSV | citizenship/visa/country CSV |", "|---|---|---|---|",
    ]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
