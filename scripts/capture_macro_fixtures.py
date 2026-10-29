"""Capture real GDP and labour market fixtures for tests. Manual; every request goes through the paced Fetcher.

Usage (from backend/ with the venv active):
    python ../scripts/capture_macro_fixtures.py RAW_DIR

For each release below, downloads the release page and the files the adapter reads into RAW_DIR (skipping files
already there), then writes excerpts to backend/tests/fixtures/. Excerpts keep every real row of the series the
adapter stores, with the original header; nothing is invented or edited. Labour market zips keep their original
member names; the HLFS and LCI members keep the stored series' rows, the other members only their header row.
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

from nzstats.adapters.gdp.series import BY_REFERENCE as GDP_REFERENCES
from nzstats.adapters.labour.series import BY_REFERENCE as LABOUR_REFERENCES
from nzstats.config import load_settings
from nzstats.sources.fetcher import Fetcher, FilePacer, build_client
from nzstats.sources.release_page import classify_download, parse_release_page

OUT = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
GDP_RELEASES = {
    "2026-06": "gross-domestic-product-june-2026-quarter",
    "2026-03": "gross-domestic-product-march-2026-quarter",
}

LABOUR_RELEASES = {
    "2026-06": "labour-market-statistics-june-2026-quarter",
    "2026-03": "labour-market-statistics-march-2026-quarter",
}
LABOUR_MEMBERS = ("hlfs-", "lci-")  # the members the adapter reads; others keep only their header


def excerpt(raw: bytes, keep: set[str]) -> str:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    header, body = rows[0], rows[1:]
    ref = header.index("Series_reference")
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(r for r in body if r[ref] in keep)
    return out.getvalue()


def excerpt_zip(raw: bytes, keep: set[str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            kept = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            kept.compress_type = zipfile.ZIP_DEFLATED
            if info.is_dir():
                target.writestr(kept, b"")
                continue
            base = info.filename.rsplit("/", 1)[-1]
            with source.open(info) as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
                rows = csv.reader(text)
                header = next(rows)
                ref = header.index("Series_reference")
                body = io.StringIO()
                writer = csv.writer(body, lineterminator="\n")
                writer.writerow(header)
                if base.startswith(LABOUR_MEMBERS):
                    writer.writerows(r for r in rows if r[ref] in keep)
            target.writestr(kept, body.getvalue().encode("utf-8"))
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

    for month, slug in LABOUR_RELEASES.items():
        page_bytes = cached(f"{slug}.html", s.base_url + s.release_page_path.format(slug=slug))
        (OUT / f"labour_{month}_page.html").write_bytes(page_bytes)
        page = parse_release_page(page_bytes.decode("utf-8"), s.base_url)
        url = next(u for u in page.download_urls if classify_download(u) == "labour_zip")
        raw = cached(url.rsplit("/", 1)[-1], url)
        (OUT / f"labour_{month}.zip").write_bytes(excerpt_zip(raw, set(LABOUR_REFERENCES)))
        print("wrote", f"labour_{month}.zip")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
