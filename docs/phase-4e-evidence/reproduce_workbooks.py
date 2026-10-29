"""Independent CPI worksheet-to-SQL Decimal check. Does not use the workbook reader."""

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal
from pathlib import Path

root = Path("data/phase-4e")
ledger = json.loads((root / "activation-results.json").read_text())
conn = sqlite3.connect("file:data/nzstats.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
mapping = {
    "SE9NS4000": "tm05",
    "SE9NS4005": "tm10",
    "SE9NS4010": "tm15",
    "SE9NS4015": "tm20",
    "SE9NS4020": "tm25",
    "SE9NS4025": "tm30",
    "SE9NS4100": "pct10",
    "SE9NS4105": "pct25",
    "SE9NS4110": "median",
    "SE9NS4115": "pct75",
    "SE9NS4120": "pct90",
}
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
months = {"Mar": "03", "Jun": "06", "Sep": "09", "Sept": "09", "Dec": "12"}
checks = []
for release in ledger.get("release_results", []):
    if not release["release_key"].startswith("consumers-price-index") or release[
        "outcome"
    ]["outcome"] not in ("ingested", "unchanged"):
        continue
    target = next(
        r
        for r in json.loads((root / "backfill-offline.json").read_text())["releases"]
        if r["release_key"] == release["release_key"]
    )
    url = target["selected_downloads"]["cpi_workbook"]
    capture = next(r for r in ledger["requests"] if r["url"] == url)
    expected = {}
    with zipfile.ZipFile(root / "live-captures" / capture["sha256"]) as archive:
        strings = [
            "".join(item.itertext())
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))
        ]
        rels = {
            r.attrib["Id"]: r.attrib["Target"].lstrip("/")
            for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        }
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).find(M + "sheets"):
            if sheet.attrib["name"] not in ("10", "11"):
                continue
            rel = sheet.attrib[
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ]
            path = rels[rel]
            path = path if path.startswith("xl/") else "xl/" + path
            refs = {}
            quarterly = False
            year = None
            for row in ET.fromstring(archive.read(path)).iter(M + "row"):
                cells = {}
                for cell in row:
                    value = cell.find(M + "v")
                    if value is not None:
                        column = re.match("[A-Z]+", cell.attrib["r"])[0]
                        cells[column] = (
                            strings[int(value.text)]
                            if cell.attrib.get("t") == "s"
                            else value.text
                        )
                head = cells.get("A", "")
                if head.startswith("Series ref"):
                    refs = {col: ref for col, ref in cells.items() if ref in mapping}
                    quarterly = False
                if head == "Percentage change from previous quarter":
                    quarterly = True
                if head.startswith("Percentage change from same quarter"):
                    quarterly = False
                if head.isdigit():
                    year = head
                if quarterly and year and cells.get("B") in months:
                    for col, ref in refs.items():
                        if col in cells:
                            expected[
                                (
                                    f"cpi.underlying.{mapping[ref]}",
                                    year + "-" + months[cells["B"]],
                                )
                            ] = Decimal(cells[col])
    actual = {
        (r["key"], r["period"]): Decimal(str(r["value"]))
        for r in conn.execute(
            "SELECT s.key,o.period,o.value FROM observation o JOIN vintage v ON v.id=o.vintage_id JOIN series s ON s.id=v.series_id JOIN release r ON r.id=v.release_id WHERE r.release_key=? AND s.category='cpi:underlying'",
            (release["release_key"],),
        )
    }
    differences = [
        (
            key,
            str(value),
            str(actual.get(key)),
            str(abs(value - actual[key])) if key in actual else None,
        )
        for key, value in expected.items()
        if actual.get(key) != value
    ]
    assert expected and set(expected) == set(actual)
    assert all(float(value) == float(actual[key]) for key, value in expected.items()), (
        "SQLite REAL conversion mismatch"
    )
    assert all(
        value.quantize(Decimal("0.1")) == actual[key].quantize(Decimal("0.1"))
        for key, value in expected.items()
    ), "Published one-decimal value mismatch"
    checks.append(
        {
            "release_key": release["release_key"],
            "source_url": url,
            "sha256": capture["sha256"],
            "series": len({key for key, period in actual}),
            "observations": len(actual),
            "representation_differences": len(differences),
            "maximum_decimal_to_sqlite_real_difference": str(
                max(
                    (abs(expected[key] - actual[key]) for key in expected),
                    default=Decimal(0),
                )
            ),
            "exact_float_conversion_match": True,
            "exact_published_one_decimal_match": True,
            "discrepancies": [],
        }
    )
conn.close()
(root / "workbook-reconciliation.json").write_text(
    json.dumps(
        {
            "method": "stdlib_XLSX_XML_and_Decimal_independent_of_application_workbook_reader",
            "checks": checks,
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps(checks, indent=2))
