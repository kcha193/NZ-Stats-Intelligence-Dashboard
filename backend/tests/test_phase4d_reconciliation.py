"""Independent arithmetic against captured official rows, without application calculation helpers."""

from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MONTHS = ("2026-03", "2026-06")


def values(text: str) -> dict[str, dict[str, Decimal]]:
    result: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for row in csv.DictReader(io.StringIO(text)):
        if row["Data_value"]:
            series, period = row["Series_reference"], row["Period"]
            assert period not in result[series], (series, period)
            assert period[-2:] in ("03", "06", "09", "12"), period
            result[series][period] = Decimal(row["Data_value"])
    return result


def earlier(period: str, months: int) -> str:
    year, month = map(int, period.split("."))
    index = year * 12 + month - 1 - months
    return f"{index // 12:04d}.{index % 12 + 1:02d}"


def labour(month: str) -> dict[str, dict[str, Decimal]]:
    result = {}
    with zipfile.ZipFile(FIXTURES / f"labour_{month}.zip") as archive:
        for member in archive.namelist():
            if member.endswith(".csv"):
                result.update(values(archive.read(member).decode("utf-8-sig")))
    return result


def page(kind: str, month: str) -> dict:
    text = (FIXTURES / f"{kind}_{month}_page.html").read_text()
    match = re.search(r'id="pageViewData" data-value="(.*?)"', text)
    assert match is not None
    return json.loads(html.unescape(match[1]))


@pytest.mark.parametrize("month", MONTHS)
@pytest.mark.parametrize(
    ("level", "rate", "months", "annual_average", "counts"),
    [
        ("SNEQ.SG01RSC00B01", "SNEQ.SG01RSC01B01PC", 3, False, (155, 156)),
        ("SNEQ.SG01RSC00B01", "SNEQ.SG01RSC01B01AC", 12, False, (152, 153)),
        ("SNEQ.SG01RAC00B01", "SNEQ.SG01RAC01B01AC", 12, True, (149, 150)),
        ("SNEQ.SG02RSC00B15", "SNEQ.SG02RSC31B15PC", 3, False, (155, 156)),
    ],
)
def test_published_gdp_growth_reconciles_to_raw_levels(
    month, level, rate, months, annual_average, counts
):
    data = values((FIXTURES / f"gdp_{month}.csv").read_text())
    checked = 0
    for period, published in data[rate].items():
        if annual_average:
            periods = [earlier(period, 3 * k) for k in range(8)]
            if not all(p in data[level] for p in periods):
                continue
            numerator = sum(data[level][p] for p in periods[:4])
            denominator = sum(data[level][p] for p in periods[4:])
        else:
            if period not in data[level] or earlier(period, months) not in data[level]:
                continue
            numerator, denominator = data[level][period], data[level][earlier(period, months)]
        independently_calculated = (numerator / denominator - 1) * 100
        assert abs(independently_calculated - published) <= Decimal("0.06"), (rate, period)
        checked += 1
    assert checked == counts[MONTHS.index(month)]


@pytest.mark.parametrize("month", MONTHS)
def test_hlfs_identities_use_population_and_labour_force_denominators(month):
    data = labour(month)
    for period, force in data["HLFQ.S1Z3S"].items():
        employed, unemployed, population = (
            data[ref][period] for ref in ("HLFQ.S1A3S", "HLFQ.S1B3S", "HLFQ.S1D3S")
        )
        assert abs(employed + unemployed - force) <= Decimal("1.5")
        for numerator, denominator, rate in (
            (unemployed, force, "HLFQ.S1F3S"),
            (employed, population, "HLFQ.S1H3S"),
            (force, population, "HLFQ.S1E3S"),
        ):
            assert abs(numerator / denominator * 100 - data[rate][period]) <= Decimal("0.08")
    assert len(data["HLFQ.S1Z3S"]) == (161 if month == "2026-03" else 162)


@pytest.mark.parametrize("month", MONTHS)
@pytest.mark.parametrize(
    ("rate", "months", "counts"),
    [
        ("LCIQ.SG53Z9PC", 3, (133, 134)),
        ("LCIQ.SG53Z9AC", 12, (130, 131)),
    ],
)
def test_lci_published_growth_reconciles_to_same_quality_wage_index(month, rate, months, counts):
    data = labour(month)
    index = data["LCIQ.SG53Z9"]
    checked = 0
    for period, published in data[rate].items():
        if period in index and earlier(period, months) in index:
            calculated = (index[period] / index[earlier(period, months)] - 1) * 100
            assert abs(calculated - published) <= Decimal("0.06"), period
            checked += 1
    assert checked == counts[MONTHS.index(month)]


@pytest.mark.parametrize(
    ("kind", "month", "published"),
    [
        ("gdp", "2026-03", "2026-06-18 10:45:00"),
        ("gdp", "2026-06", "2026-09-17 10:45:00"),
        ("labour", "2026-03", "2026-05-06 10:45:00"),
        ("labour", "2026-06", "2026-08-05 10:45:00"),
    ],
)
def test_official_release_dates_come_from_captured_page(kind, month, published):
    assert page(kind, month)["PageDate"] == published


def test_march_labour_republication_scope_and_original_headline_are_explicit():
    captured = page("labour", "2026-03")
    note = next(b["Content"] for b in captured["PageBlocks"] if "error note" in b["Title"])
    assert "5 August 2026" in note and "HLFQ.SVE" in note and "LCIQ.SG33Z9" in note
    assert "5.3 percent in the March 2026 quarter" in captured["MetaDescription"]
    data = labour("2026-03")
    assert data["HLFQ.S1F3S"]["2026.03"] == Decimal("5.3")
    assert "LCIQ.SG33Z9" not in data
    assert not any(ref.startswith("HLFQ.SVE") for ref in data)


def test_original_release_headlines_and_later_revisions_remain_distinct():
    march = values((FIXTURES / "gdp_2026-03.csv").read_text())
    june = values((FIXTURES / "gdp_2026-06.csv").read_text())
    assert march["SNEQ.SG01RSC01B01PC"]["2026.03"] == Decimal("0.8")
    assert june["SNEQ.SG01RSC01B01PC"]["2026.03"] == Decimal("0.9")
    assert labour("2026-03")["HLFQ.S1F3S"]["2026.03"] == Decimal("5.3")
    assert labour("2026-06")["HLFQ.S1F3S"]["2026.03"] == Decimal("5.4")
