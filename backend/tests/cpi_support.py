"""Captured official CPI releases (Dec 2025, Mar 2026, Jun 2026) for offline tests."""

from __future__ import annotations

from datetime import UTC, datetime

from nzstats.domain import ReleaseRef, ReleaseStatus
from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.release_page import ReleasePage, classify_download, parse_release_page
from nzstats.store import repo
from tests.conftest import FIXTURES, fixture_bytes, fixture_text
from tests.support import BASE

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
KINDS = ("index_numbers", "seasonally_adjusted", "tradables")


def page(month: str = "2026-06") -> ReleasePage:
    return parse_release_page(fixture_text(f"cpi_{month}_page.html"), BASE)


def files(month: str = "2026-06") -> dict[str, bytes]:
    names = {"index_numbers": "cpi_index_numbers", "seasonally_adjusted": "cpi_seasonally_adjusted"}
    return {names.get(k, "cpi_tradables"): fixture_bytes(f"cpi_{month}_{k}.csv") for k in KINDS}


def edited(source: dict[str, bytes], kind: str, old: str, new: str) -> dict[str, bytes]:
    """A copy of `source` with `old` replaced by `new` in one file; fails if `old` is absent."""
    text = source[kind].decode("utf-8")
    assert old in text, f"{old!r} not found in {kind}"
    return {**source, kind: text.replace(old, new, 1).encode("utf-8")}


NOW = datetime(2026, 10, 18, tzinfo=UTC)
KIND_FILE = {
    "cpi_index_numbers": "index_numbers",
    "cpi_seasonally_adjusted": "seasonally_adjusted",
    "cpi_tradables": "tradables",
}


def serve_cpi(site, month="2026-06"):
    """Serve a CPI release's real page and files from the fake site, without touching the database."""
    pg = page(month)
    parts = parse_title(pg.title)
    url = f"{BASE}/information-releases/{parts.series_slug}-{parts.period_label.lower().replace(' ', '-')}/"
    ref = ReleaseRef(
        make_release_key(pg.title),
        parts.series_slug,
        pg.title,
        parts.period_label,
        parts.reference_period,
        pg.published_at,
        ReleaseStatus.PUBLISHED,
        page_url=url,
    )
    site.routes[url] = (200, fixture_bytes(f"cpi_{month}_page.html"), "text/html")
    downloads = {}
    for u in pg.download_urls:
        kind = classify_download(u)
        if kind in KIND_FILE:
            downloads[kind] = u
            site.routes[u] = (200, fixture_bytes(f"cpi_{month}_{KIND_FILE[kind]}.csv"), "text/csv")
        elif kind == "cpi_workbook":
            downloads[kind] = u
            if (FIXTURES / f"cpi_{month}_workbook.xlsx").exists():
                site.routes[u] = (200, fixture_bytes(f"cpi_{month}_workbook.xlsx"), XLSX)
    return ref, url, downloads


def seed_cpi(rt, site, month="2026-06"):
    """Register a published CPI release and serve its real page and files from the fake site."""
    ref, url, downloads = serve_cpi(site, month)
    return repo.upsert_release(rt.conn, ref, NOW), ref.release_key, url, downloads


def ingest_cpi(rt, site, *months):
    """Seed and ingest real fixture releases, oldest first; returns {month: release id}."""
    from nzstats.pipeline.ingest import ingest_release

    ids = {}
    for month in months:
        rid, key, _, _ = seed_cpi(rt, site, month)
        outcome = ingest_release(rt, key, now_fn=lambda: NOW)
        assert outcome.outcome == "ingested", outcome.detail
        ids[month] = rid
    return ids


def mutated(source: dict[str, bytes], kind: str, reference: str, **fields: str) -> dict[str, bytes]:
    """A copy of `source` where the first row of `reference` in one file has `fields` replaced."""
    import csv
    import io

    rows = list(csv.reader(io.StringIO(source[kind].decode("utf-8"))))
    header = rows[0]
    row = next(r for r in rows[1:] if r[header.index("Series_reference")] == reference)
    for name, value in fields.items():
        row[header.index(name)] = value
    out = io.StringIO()
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    return {**source, kind: out.getvalue().encode("utf-8")}


def workbook_with_cell(text: str, ref: str = "SE9NS4110", period: str = "2026-06") -> bytes:
    """The real June 2026 workbook with one quarterly cell rewritten as raw cell text (e.g. NaN)."""
    import io
    import xml.etree.ElementTree as ET
    import zipfile

    from nzstats.adapters.cpi.workbook import CELL, MONTH, M

    ET.register_namespace("", M[1:-1])
    shared = [
        "".join(t.text or "" for t in si.iter(M + "t"))
        for si in ET.fromstring(
            zipfile.ZipFile(io.BytesIO(fixture_bytes("cpi_2026-06_workbook.xlsx"))).read(
                "xl/sharedStrings.xml"
            )
        ).iter(M + "si")
    ]
    out, hits = io.BytesIO(), 0
    with (
        zipfile.ZipFile(io.BytesIO(fixture_bytes("cpi_2026-06_workbook.xlsx"))) as src,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename in ("xl/worksheets/sheet16.xml", "xl/worksheets/sheet17.xml"):
                root = ET.fromstring(data)
                refs: dict[str, str] = {}
                quarterly, year = False, None
                for row in root.iter(M + "row"):
                    cells = {}
                    for c in row:
                        v = c.find(M + "v")
                        m = CELL.fullmatch(c.get("r", ""))
                        if v is not None and v.text is not None and m:
                            text_ = shared[int(v.text)] if c.get("t") == "s" else v.text
                            cells[m[1]] = (text_, v)
                    head = cells.get("A", ("",))[0]
                    if head.startswith("Series ref"):
                        refs, quarterly = {k: t for k, (t, _) in cells.items() if k != "A"}, False
                    elif head == "Percentage change from previous quarter":
                        quarterly = True
                    elif head.startswith("Percentage change from same quarter"):
                        quarterly = False
                    elif quarterly:
                        year = int(head) if head.isdigit() else year
                        month = MONTH.get(cells.get("B", ("",))[0])
                        for col, ref_ in refs.items():
                            if ref == ref_ and f"{year}-{month}" == period and col in cells:
                                cells[col][1].text = text
                                hits += 1
                data = ET.tostring(root, xml_declaration=True, encoding="UTF-8")
            dst.writestr(item, data)
    assert hits == 1
    return out.getvalue()
