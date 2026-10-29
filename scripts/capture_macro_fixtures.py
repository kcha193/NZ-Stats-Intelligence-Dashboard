"""Capture real GDP fixtures for tests. Manual; every request goes through the paced Fetcher.

Usage (from backend/ with the venv active):
    python ../scripts/capture_macro_fixtures.py RAW_DIR

For each release below, downloads the release page and the files the adapter reads into RAW_DIR (skipping files
already there), then writes excerpts to backend/tests/fixtures/. Excerpts keep every real row of the series the
adapter stores, with the original header; nothing is invented or edited.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

from nzstats.adapters.gdp.series import BY_REFERENCE as GDP_REFERENCES
from nzstats.config import load_settings
from nzstats.sources.fetcher import Fetcher, FilePacer, build_client
from nzstats.sources.release_page import classify_download, parse_release_page

OUT = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
GDP_RELEASES = {
    "2026-06": "gross-domestic-product-june-2026-quarter",
    "2026-03": "gross-domestic-product-march-2026-quarter",
}


def excerpt(raw: bytes, keep: set[str]) -> str:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    header, body = rows[0], rows[1:]
    ref = header.index("Series_reference")
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(r for r in body if r[ref] in keep)
    return out.getvalue()


def main(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    s = load_settings()
    fetcher = Fetcher(
        build_client(s.user_agent),
        min_interval=s.min_interval_seconds,
        pacer=FilePacer(s.data_dir / ".request-pace", s.min_interval_seconds),
    )

    def cached(name: str, url: str) -> bytes:
        target = raw_dir / name
        if not target.exists():
            target.write_bytes(fetcher.get(url).body)
        return target.read_bytes()

    for month, slug in GDP_RELEASES.items():
        page_bytes = cached(f"{slug}.html", s.base_url + s.release_page_path.format(slug=slug))
        (OUT / f"gdp_{month}_page.html").write_bytes(page_bytes)
        page = parse_release_page(page_bytes.decode("utf-8"), s.base_url)
        url = next(u for u in page.download_urls if classify_download(u) == "gdp_csv")
        raw = cached(url.rsplit("/", 1)[-1], url)
        (OUT / f"gdp_{month}.csv").write_text(excerpt(raw, set(GDP_REFERENCES)), encoding="utf-8")
        print("wrote", f"gdp_{month}.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
