"""Capture real Stats NZ fixtures for tests. Manual; throttled to 10 s per request.

Usage: python scripts/capture_fixtures.py
Writes excerpts to backend/tests/fixtures/. Excerpts keep real rows; nothing is invented.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import httpx
import pandas as pd

BASE = "https://www.stats.govt.nz"
UA = "NZStatsDashboard-research/0.1 (fixture capture)"
OUT = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
RELEASES = {
    "2026-07": "international-migration-july-2026",
    "2026-06": "international-migration-june-2026",
}


def get(client: httpx.Client, url: str) -> httpx.Response:
    time.sleep(10)
    resp = client.get(url)
    resp.raise_for_status()
    print(f"GET {url} -> {resp.status_code} {len(resp.content)}B", file=sys.stderr)
    return resp


def downloads(page_html: str) -> list[str]:
    text = page_html.replace("\\/", "/")
    found = re.findall(r"/assets/Uploads/[^\"\\\s&]+?\.(?:csv|xlsx)", text)
    return list(dict.fromkeys(found))


def pick(urls: list[str], pattern: str) -> str:
    matches = [u for u in urls if u.endswith(".csv") and re.search(pattern, u.lower())]
    if len(matches) != 1:
        raise SystemExit(f"expected one file matching {pattern!r}, got {matches}")
    return matches[0]


def excerpt_age_sex(raw: bytes, release_month: str) -> str:
    df = pd.read_csv(io.BytesIO(raw))
    total = (df["sex"] == "TOTAL") & (df["age"] == "TOTAL")
    detail = df[(~total) & (df["year_month"] == release_month)].head(60)
    return pd.concat([df[total], detail]).to_csv(index=False, quoting=1)


def excerpt_citizenship_country(raw: bytes) -> str:
    df = pd.read_csv(io.BytesIO(raw))
    vt = df["visa"] == "TOTAL"
    recent_countries = vt & (df["citizenship"] == "TOTAL") & (df["year_month"] >= "2025-06")
    country_total = vt & (df["country_of_residence"] == "TOTAL")
    noise = df[(~vt) & (df["year_month"] == df["year_month"].max())].head(100)
    kept = pd.concat([df[recent_countries | country_total], noise]).drop_duplicates()
    return kept.to_csv(index=False, quoting=1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=120) as client:
        ics = get(client, f"{BASE}/release-calendar/calendar-export/").text
        events = re.findall(r"BEGIN:VEVENT.*?END:VEVENT", ics, flags=re.S)
        head = ics[: ics.index("BEGIN:VEVENT")]
        # Deterministic selection: every migration event plus the earliest others, 12 in total.
        mig = [e for e in events if "SUMMARY:International migration:" in e]
        others = [e for e in events if e not in mig]
        chosen = (mig + others)[:12]
        (OUT / "calendar_export_excerpt.ics").write_text(
            head + "\n".join(chosen) + "\nEND:VCALENDAR\n", encoding="utf-8"
        )

        for month, name in (
            ("2026-09", "release_month_2026-09.json"),
            ("2026-10", "release_month_2026-10.json"),
        ):
            payload = get(client, f"{BASE}/api/v1/releaseCalendarMonth/{month}").json()
            for key in ("published", "upcoming"):
                payload["items"][key] = payload["items"].get(key, [])[:4]
            (OUT / name).write_text(json.dumps(payload, indent=1), encoding="utf-8")

        for month, slug in RELEASES.items():
            page = get(client, f"{BASE}/information-releases/{slug}/").text
            (OUT / f"im_{month}_page.html").write_text(page, encoding="utf-8")
            urls = downloads(page)
            age_sex = pick(urls, r"age.*sex")
            cit = pick(urls, r"citizenship.*visa.*country")
            (OUT / f"im_{month}_age_sex.csv").write_text(
                excerpt_age_sex(get(client, BASE + age_sex).content, month), encoding="utf-8"
            )
            (OUT / f"im_{month}_citizenship_country.csv").write_text(
                excerpt_citizenship_country(get(client, BASE + cit).content), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
