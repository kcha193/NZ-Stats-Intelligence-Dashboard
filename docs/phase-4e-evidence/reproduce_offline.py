"""Offline release evidence. Run from repository root; makes no network requests."""

import csv
import hashlib
import io
import json
import re
import socket
import zipfile
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from nzstats.clock import to_utc_iso
from nzstats.config import load_settings
from nzstats.runtime import build_adapters
from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.release_page import parse_release_page, pick_downloads


def no_network(*args, **kwargs):
    raise RuntimeError("Network is forbidden in this offline audit")


socket.socket = no_network
fixtures = Path("backend/tests/fixtures")
captures = Path("data/capture-4c")
out = Path("data/phase-4e")
out.mkdir(parents=True, exist_ok=True)
adapters = build_adapters(load_settings({}))
base = "https://www.stats.govt.nz"
# Chronological seven-release plan, exact publication instants from retained evidence.
targets = [
    ("cpi", "2025-12", "2026-01-22T21:45:00Z"),
    ("cpi", "2026-03", "2026-04-20T22:45:00Z"),
    ("labour", "2026-03", "2026-05-05T22:45:00Z"),
    ("gdp", "2026-03", "2026-06-17T22:45:00Z"),
    ("cpi", "2026-06", "2026-07-20T22:45:00Z"),
    ("labour", "2026-06", "2026-08-04T22:45:00Z"),
    ("gdp", "2026-06", "2026-09-16T22:45:00Z"),
]
releases = []
for kind, month, expected in targets:
    path = fixtures / f"{kind}_{month}_page.html"
    page = parse_release_page(path.read_text(), base)
    parts = parse_title(page.title)
    assert parts.reference_period == month
    assert to_utc_iso(page.published_at) == expected
    adapter = adapters[parts.series_slug]
    wanted = pick_downloads(page.download_urls, adapter.required_downloads)
    optional = pick_downloads(
        page.download_urls, getattr(adapter, "optional_downloads", ())
    )
    assert set(wanted) == set(adapter.required_downloads)
    if kind == "cpi":
        files = {
            key: (fixtures / f"cpi_{month}_{suffix}.csv").read_bytes()
            for key, suffix in [
                ("cpi_index_numbers", "index_numbers"),
                ("cpi_seasonally_adjusted", "seasonally_adjusted"),
                ("cpi_tradables", "tradables"),
            ]
        }
        workbook = fixtures / f"cpi_{month}_workbook.xlsx"
        if workbook.exists():
            files["cpi_workbook"] = workbook.read_bytes()
    else:
        key, ext = ("gdp_csv", "csv") if kind == "gdp" else ("labour_zip", "zip")
        files = {key: (fixtures / f"{kind}_{month}.{ext}").read_bytes()}
    bundle = adapter.parse(page, files)
    findings = adapter.validate(bundle, reference_period=month, previous={})
    assert not [f for f in findings if f.severity == "error"], findings
    key = make_release_key(page.title)
    slug, period = key.split(":", 1)
    releases.append(
        {
            "release_key": key,
            "reference_period": month,
            "published_at": expected,
            "page_url": f"{base}/information-releases/{slug}-{period.replace(' ', '-')}/",
            "page_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "selected_downloads": {**wanted, **optional},
            "minimum_logical_gets": 2 + len(wanted) + len(optional),
            "offline_series_vintages": len(bundle.series),
            "offline_observations": sum(len(s.observations) for s in bundle.series),
            "warnings": list(bundle.warnings),
            "validation_findings": [asdict(f) for f in findings],
            "uncaptured_optional_downloads": sorted(set(optional) - set(files)),
            "first_publication_verified": False,
        }
    )
assert sum(r["minimum_logical_gets"] for r in releases) == 30
assert sum(r["offline_series_vintages"] for r in releases) == 246
assert sum(r["offline_observations"] for r in releases) == 23730
plan = Path("docs/phase-4d-backfill-plan.md").read_text()
code = re.search(r"```python\n(.*?)```", plan, re.DOTALL)[1]
compile(code, "phase-4d-bounded-registration", "exec")
(out / "backfill-offline.json").write_text(
    json.dumps(
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "status": "OFFLINE_VALID_LIVE_AVAILABILITY_UNVERIFIED",
            "network_requests": 0,
            "logical_get_budget": 30,
            "releases": releases,
        },
        indent=2,
    )
    + "\n"
)


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def numbers(raw):
    result = defaultdict(dict)
    for row in rows(raw):
        if row["Data_value"]:
            ref, period = row["Series_reference"], row["Period"]
            assert period not in result[ref]
            result[ref][period] = Decimal(row["Data_value"])
    return result


def earlier(period, months):
    year, month = map(int, period.split("."))
    index = year * 12 + month - 1 - months
    return f"{index // 12:04d}.{index % 12 + 1:02d}"


def compare(full, excerpt):
    selected = {row["Series_reference"] for row in excerpt}
    retained = [row for row in full if row["Series_reference"] in selected]
    normalise = lambda data: sorted(tuple(sorted(row.items())) for row in data)
    assert normalise(retained) == normalise(excerpt)
    return {"selected_series": len(selected), "rows": len(excerpt), "exact_match": True}


checks = []
source_identity = []
headlines = []
for month in ("2026-03", "2026-06"):
    gdp_text = (fixtures / f"gdp_{month}.csv").read_text(encoding="utf-8-sig")
    gdp = numbers(gdp_text)
    labour = {}
    fixture_labour = []
    full_labour = []
    for filename in (fixtures / f"labour_{month}.zip",):
        with zipfile.ZipFile(filename) as archive:
            for name in archive.namelist():
                if name.endswith(".csv"):
                    text = archive.read(name).decode("utf-8-sig")
                    labour.update(numbers(text))
                    fixture_labour.append((name, rows(text)))
    for kind in ("gdp", "labour"):
        r = next(
            r
            for r in releases
            if r["release_key"].startswith(
                "gross-domestic-product"
                if kind == "gdp"
                else "labour-market-statistics"
            )
            and r["reference_period"] == month
        )
        url = next(iter(r["selected_downloads"].values()))
        path = captures / url.rsplit("/", 1)[-1]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if kind == "gdp":
            matches = [
                compare(rows(path.read_text(encoding="utf-8-sig")), rows(gdp_text))
            ]
        else:
            matches = []
            with zipfile.ZipFile(path) as archive:
                for name, excerpt in fixture_labour:
                    selected = {row["Series_reference"] for row in excerpt}
                    with archive.open(name) as member:
                        full = [
                            row
                            for row in csv.DictReader(
                                io.TextIOWrapper(member, encoding="utf-8-sig")
                            )
                            if row["Series_reference"] in selected
                        ]
                    matches.append({"member": name, **compare(full, excerpt)})
        source_identity.append({"url": url, "sha256": digest, "selection": matches})
    for level, rate, lag, annual in [
        ("SNEQ.SG01RSC00B01", "SNEQ.SG01RSC01B01PC", 3, False),
        ("SNEQ.SG01RSC00B01", "SNEQ.SG01RSC01B01AC", 12, False),
        ("SNEQ.SG01RAC00B01", "SNEQ.SG01RAC01B01AC", 12, True),
        ("SNEQ.SG02RSC00B15", "SNEQ.SG02RSC31B15PC", 3, False),
    ]:
        residuals = []
        for period, value in gdp[rate].items():
            periods = (
                [earlier(period, 3 * k) for k in range(8)]
                if annual
                else [period, earlier(period, lag)]
            )
            if not all(p in gdp[level] for p in periods):
                continue
            numerator = (
                sum(gdp[level][p] for p in periods[:4])
                if annual
                else gdp[level][period]
            )
            denominator = (
                sum(gdp[level][p] for p in periods[4:])
                if annual
                else gdp[level][periods[1]]
            )
            calculated = (numerator / denominator - 1) * 100
            residuals.append(abs(calculated - value))
            if period == month.replace("-", "."):
                headlines.append(
                    {
                        "release": month,
                        "series": rate,
                        "numerator": str(numerator),
                        "denominator": str(denominator),
                        "calculated": str(calculated),
                        "published": str(value),
                    }
                )
        assert max(residuals) <= Decimal("0.06")
        checks.append(
            {
                "release": month,
                "series": rate,
                "checks": len(residuals),
                "max_difference_pp": str(max(residuals)),
                "tolerance_pp": "0.06",
                "ok": True,
            }
        )
    forces = []
    rates = []
    for period, force in labour["HLFQ.S1Z3S"].items():
        employed, unemployed, population = (
            labour[ref][period] for ref in ("HLFQ.S1A3S", "HLFQ.S1B3S", "HLFQ.S1D3S")
        )
        forces.append(abs(employed + unemployed - force))
        for numerator, denominator, ref in [
            (unemployed, force, "HLFQ.S1F3S"),
            (employed, population, "HLFQ.S1H3S"),
            (force, population, "HLFQ.S1E3S"),
        ]:
            calculated = numerator / denominator * 100
            rates.append(abs(calculated - labour[ref][period]))
            if period == month.replace("-", "."):
                headlines.append(
                    {
                        "release": month,
                        "series": ref,
                        "numerator": str(numerator),
                        "denominator": str(denominator),
                        "calculated": str(calculated),
                        "published": str(labour[ref][period]),
                    }
                )
    assert max(forces) <= Decimal("1.5") and max(rates) <= Decimal("0.08")
    checks.extend(
        [
            {
                "release": month,
                "check": "labour_force_identity",
                "checks": len(forces),
                "max_difference_thousands": str(max(forces)),
                "tolerance_thousands": "1.5",
                "ok": True,
            },
            {
                "release": month,
                "check": "hlfs_rates",
                "checks": len(rates),
                "max_difference_pp": str(max(rates)),
                "tolerance_pp": "0.08",
                "ok": True,
            },
        ]
    )
    index = labour["LCIQ.SG53Z9"]
    for ref, lag in [("LCIQ.SG53Z9PC", 3), ("LCIQ.SG53Z9AC", 12)]:
        residuals = []
        for period, value in labour[ref].items():
            if period not in index or earlier(period, lag) not in index:
                continue
            calculated = (index[period] / index[earlier(period, lag)] - 1) * 100
            residuals.append(abs(calculated - value))
            if period == month.replace("-", "."):
                headlines.append(
                    {
                        "release": month,
                        "series": ref,
                        "numerator": str(index[period]),
                        "denominator": str(index[earlier(period, lag)]),
                        "calculated": str(calculated),
                        "published": str(value),
                    }
                )
        assert max(residuals) <= Decimal("0.06")
        checks.append(
            {
                "release": month,
                "series": ref,
                "checks": len(residuals),
                "max_difference_pp": str(max(residuals)),
                "tolerance_pp": "0.06",
                "ok": True,
            }
        )
(out / "independent-macro.json").write_text(
    json.dumps(
        {
            "scope": "retained_official_captures_not_populated_production",
            "arithmetic": "standard_library_csv_zip_decimal_no_application_calculation_helpers",
            "source_identity": source_identity,
            "checks": checks,
            "headlines": headlines,
            "unexplained_discrepancies": [],
        },
        indent=2,
    )
    + "\n"
)
print(
    "Seven releases: 30 logical GETs; 246 offline vintages / 23,730 observations. Full macro source selections match. Independent arithmetic passed."
)
