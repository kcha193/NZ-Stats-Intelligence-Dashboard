"""Offline Phase 4Y evidence helpers. Synthetic October bytes are NEVER official data.

The reconciliation reads the ZIP directly with stdlib CSV/Decimal, independently of
the adapter, its identity mapping and the dashboard's change functions. It can also
check a locally saved genuine ZIP against a same-vintage /api/ect response.
"""

import csv
import html
import io
import json
import zipfile
from datetime import datetime
from decimal import Decimal

from nzstats.clock import AKL
from nzstats.domain import ReleaseRef, ReleaseStatus
from nzstats.store import repo
from tests.adapters.test_ect import archive, csv_rows
from tests.support import BASE

OCTOBER_KEY = "electronic-card-transactions:october 2026"
OCTOBER_TIME = datetime(2026, 11, 12, 10, 45, tzinfo=AKL)
# MockTransport-only URLs: not assertions that an October publication exists.
SYNTHETIC_PAGE = f"{BASE}/information-releases/SYNTHETIC-ect-october/"
SYNTHETIC_ZIP = f"{BASE}/assets/Uploads/SYNTHETIC/electronic-card-transactions-october-2026.zip"


def seed_synthetic_october(rt, site):
    """Extend September monthly rows unchanged; retain September quarterly rows.

    One quarterly transaction count is revised by one to exercise history retention.
    P on the new month deliberately tests provisional versus published status.
    """
    rows = csv_rows()
    monthly = [
        r | {"Period": "2026.10", "STATUS": "P"}
        for r in rows
        if r["Series_reference"].startswith("ECTM.") and r["Period"] == "2026.09"
    ]
    for row in monthly:
        if row["Series_reference"].endswith("PC"):
            row["Data_value"] = "0.0"
    rows.extend(monthly)
    revised = next(
        r for r in rows if r["Series_reference"] == "ECTQ.S29A9" and r["Period"] == "2026.09"
    )
    revised["Data_value"] = str(int(revised["Data_value"]) + 1)
    raw = archive(rows)
    obj = {
        "Title": "Electronic card transactions: October 2026",
        "PageDate": "2026-11-12 10:45:00",
        "PageBlocks": [],
        "MetaDescription": "SYNTHETIC OCTOBER REHEARSAL — NOT OFFICIAL DATA",
        "Download": SYNTHETIC_ZIP.removeprefix(BASE),
    }
    body = f'<div data-value="{html.escape(json.dumps(obj), quote=True)}"></div>'.encode()
    ref = ReleaseRef(
        OCTOBER_KEY,
        "electronic-card-transactions",
        obj["Title"],
        "October 2026",
        "2026-10",
        OCTOBER_TIME,
        ReleaseStatus.SCHEDULED,
        page_url=SYNTHETIC_PAGE,
    )
    rid = repo.upsert_release(rt.conn, ref, OCTOBER_TIME)
    site.routes[SYNTHETIC_PAGE] = (200, body, "text/html")
    site.routes[SYNTHETIC_ZIP] = (200, raw, "application/zip")
    return rid, raw


def reconcile_archive(raw: bytes, payload: dict, reference: str) -> int:
    """Assert source levels, statuses and headline changes; return observations checked.

    Use only locally held, trusted source bytes after archive safety validation.
    Publication identity, narrative rounding and acquisition provenance are separate
    runbook gates: this function does not establish them or perform network access.
    """
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        assert len(names) == 1
        rows = list(csv.DictReader(io.StringIO(z.read(names[0]).decode("utf-8-sig"))))
    # Deliberately independent literal mappings for the acceptance indicators.
    codes = {
        "retail": "19S1",
        "core": "19S2",
        "total": "19S9",
        "consumables": "1GS1",
        "durables": "1GS2",
        "hospitality": "1GS3",
        "services": "1GS4",
        "apparel": "1GS5",
        "motor_vehicles": "1GS6",
        "fuel": "1GS7",
        "non_retail": "1GS8",
    }
    dashboard = {s["series"]["key"]: s for s in payload["series"]}
    metrics = {m["series_key"]: m for m in payload["analysis"]["headline_metrics"]}
    assert metrics["ect.m.sa.retail.value"]["period"] == reference
    checked = 0
    for frequency, prefix in (("m", "ECTM.S"), ("q", "ECTQ.S")):
        identities = [
            (f"ect.{frequency}.sa.{name}.value", prefix + code, "NZD million")
            for name, code in codes.items()
        ]
        identities += [
            (f"ect.{frequency}.actual.total.{measure}", prefix + code, unit)
            for measure, code, unit in (
                ("value", "19A9", "NZD million"),
                ("count", "29A9", "transactions"),
                ("average", "4A1V", "NZD"),
            )
        ]
        for key, code, unit in identities:
            selected = [r for r in rows if r["Series_reference"] == code]
            valid = {
                r["Period"].replace(".", "-"): r
                for r in selected
                if r["Data_value"] and not r["Suppressed"]
            }
            source = {p: Decimal(r["Data_value"]) for p, r in valid.items()}
            if frequency == "m":
                assert max(source) == reference, key
            else:
                year, month = map(int, reference.split("-"))
                index = year * 12 + month - 1 - month % 3
                assert max(source) == f"{index // 12:04d}-{index % 12 + 1:02d}", key
            data = dashboard[key]
            assert data["series"]["unit"] == unit, key
            assert data["series"]["frequency"] == ("monthly" if frequency == "m" else "quarterly")
            assert data["series"]["adjustment"] == (
                "seasonally_adjusted" if ".sa." in key else "none"
            )
            points = {p["period"]: p for p in data["points"]}
            assert points.keys() == source.keys(), key
            for period, value in source.items():
                assert Decimal(str(points[period]["value"])) == value, (key, period)
                expected = {"P": "provisional", "F": "final", "R": "unknown"}[
                    valid[period]["STATUS"]
                ]
                assert points[period]["status"] == expected, (key, period)
                checked += 1
            if key in metrics:
                metric = metrics[key]
                periods = sorted(source)
                current, prior = periods[-1], periods[-2]
                year, month = map(int, current.split("-"))
                index = year * 12 + month - 1 - (1 if frequency == "m" else 3)
                assert prior == f"{index // 12:04d}-{index % 12 + 1:02d}"
                assert metric["period"] == current
                assert Decimal(str(metric["value"])) == source[current]
                if source[prior]:
                    change = metric["change_prior"]
                    assert change["comparison_period"] == prior
                    assert abs(
                        Decimal(str(change["absolute"])) - (source[current] - source[prior])
                    ) < Decimal("0.00000001")
                    percent = (source[current] / source[prior] - 1) * 100
                    assert abs(Decimal(str(change["percent"])) - percent) < Decimal("0.00000001")
                    published = next(
                        (
                            r["Data_value"]
                            for r in rows
                            if r["Series_reference"] == code + "PC"
                            and r["Period"].replace(".", "-") == current
                        ),
                        None,
                    )
                    if published:
                        # Same existing allowance for rates based on unrounded levels.
                        assert abs(Decimal(published) - percent) <= Decimal("0.065")
    actual = {
        r["Series_reference"]: Decimal(r["Data_value"])
        for r in rows
        if r["Period"].replace(".", "-") == reference and r["Data_value"] and not r["Suppressed"]
    }
    total, count, mean = (actual[k] for k in ("ECTM.S19A9", "ECTM.S29A9", "ECTM.S4A1V"))
    assert count > 0 and count == count.to_integral_value()
    tolerance = Decimal("1.1") * (Decimal("0.05") / mean + Decimal("0.05") / total)
    assert abs(count * mean / 1_000_000 - total) / total <= tolerance
    return checked
