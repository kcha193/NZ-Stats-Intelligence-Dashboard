"""Capture real CPI fixtures for tests. Manual; every request goes through the paced Fetcher.

Usage (from backend/ with the venv active):
    python ../scripts/capture_cpi_fixtures.py RAW_DIR

Downloads, for each release below, the release page and the three required CSVs into RAW_DIR
(skipping files already there), then writes excerpts to backend/tests/fixtures/. Excerpts keep
every real row of the series the adapter reads; nothing is invented or edited.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

from nzstats.config import load_settings
from nzstats.sources.fetcher import Fetcher, FilePacer, build_client
from nzstats.sources.release_page import parse_release_page

OUT = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
RELEASES = {
    "2026-09": "consumers-price-index-september-2026-quarter",
    "2026-06": "consumers-price-index-june-2026-quarter",
    "2026-03": "consumers-price-index-march-2026-quarter",
    "2025-12": "consumers-price-index-december-2025-quarter",
}
# file-name fragment on the Stats NZ download -> fixture kind
KINDS = {
    "index-numbers": "index_numbers",
    "seasonally-adjusted": "seasonally_adjusted",
    "tradeables-and-non-tradeables": "tradables",
}
LEVEL1 = [f"CPIQ.SE9{n:02d}" for n in range(1, 12)]
KEEP = {
    "index_numbers": {
        "CPIQ.SE9A",
        *LEVEL1,
        # optional allow-list (Level 2/3)
        "CPIQ.SE9011",
        "CPIQ.SE9012",
        "CPIQ.SE9013",
        "CPIQ.SE9015",
        "CPIQ.SE9041",
        "CPIQ.SE904201",
        "CPIQ.SE904401",
        "CPIQ.SE904403",
        "CPIQ.SE9045",
        "CPIQ.SE904501",
        "CPIQ.SE904502",
        "CPIQ.SE9072",
        "CPIQ.SE907202",
    },
    "tradables": {"CPIQ.SE9A", "CPIQ.SE9NS6000", "CPIQ.SE9NS6500"},
    "seasonally_adjusted": {
        "CPIQ.SE9SA",
        "CPIQ.SE9SNS6000",
        "CPIQ.SE9SNS6500",
        *(f"CPIQ.SE9S{n:02d}" for n in range(1, 12)),
    },
}


def excerpt(raw: bytes, keep: set[str]) -> str:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    header, body = rows[0], rows[1:]
    ref = header.index("Series_reference")
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n")
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
    for month, slug in RELEASES.items():
        page_file = raw_dir / f"cpi_{month}_page.html"
        if not page_file.exists():
            url = s.base_url + s.release_page_path.format(slug=slug)
            page_file.write_bytes(fetcher.get(url).body)
        page = parse_release_page(page_file.read_text(encoding="utf-8"), s.base_url)
        (OUT / page_file.name).write_bytes(page_file.read_bytes())
        for url in page.download_urls:
            name = url.rsplit("/", 1)[-1]
            kind = next((k for frag, k in KINDS.items() if name.endswith(f"{frag}.csv")), None)
            if kind is None:
                continue
            target = raw_dir / f"cpi_{month}_{kind}.csv"
            if not target.exists():
                target.write_bytes(fetcher.get(url).body)
            (OUT / target.name).write_text(excerpt(target.read_bytes(), KEEP[kind]), encoding="utf-8")
            print("wrote", target.name)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
