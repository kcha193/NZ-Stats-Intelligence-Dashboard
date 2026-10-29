"""OCR domain model and CSV contract, on SYNTHETIC decisions dated 2031 (no RBNZ data is approved for use)."""

from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from nzstats.ocr.model import (
    changes_bp,
    month_end_series,
    monthly_average_series,
    rate_on,
)
from nzstats.ocr.parse import OcrContractError, parse_decisions
from tests.conftest import FIXTURES, fixture_text

SYNTHETIC = "ocr_SYNTHETIC_decisions.csv"
HEADER = "announced_on,effective_on,ocr_percent,change_bp,decision,source_url"
URL = "https://www.rbnz.govt.nz/synthetic/x"


def decisions():
    return parse_decisions(fixture_text(SYNTHETIC), allow_synthetic=True)


def csv_text(*rows: str) -> str:
    return "\n".join((HEADER, *rows)) + "\n"


def test_synthetic_files_are_refused_unless_explicitly_allowed():
    with pytest.raises(OcrContractError, match="SYNTHETIC"):
        parse_decisions(fixture_text(SYNTHETIC))


def test_parses_the_contract():
    ds = decisions()
    assert len(ds) == 6
    assert ds[1].announced_on == date(2031, 4, 9) and ds[1].effective_on == date(2031, 4, 10)
    assert ds[1].rate == Decimal("3.25") and ds[1].change_bp == 25 and ds[1].decision == "increase"
    assert ds[0].change_bp is None


def test_changes_in_basis_points_are_rate_differences():
    assert [bp for _, bp in changes_bp(decisions())] == [None, 25, 0, -25, -50, 0]


def test_rate_in_force_follows_the_effective_date_not_the_announcement():
    ds = decisions()
    assert rate_on(ds, date(2031, 2, 19)) is None  # before the first effective date
    assert rate_on(ds, date(2031, 4, 9)) == Decimal("3.00")  # announced, not yet effective
    assert rate_on(ds, date(2031, 4, 10)) == Decimal("3.25")
    assert rate_on(ds, date(2031, 7, 23)) == Decimal("2.50")  # same-day effective


def test_month_end_observations():
    series = month_end_series(decisions(), "2031-02", "2031-08")
    assert series == {
        "2031-02": Decimal("3.00"),
        "2031-03": Decimal("3.00"),
        "2031-04": Decimal("3.25"),
        "2031-05": Decimal("3.25"),
        "2031-06": Decimal("3.25"),
        "2031-07": Decimal("2.50"),
        "2031-08": Decimal("2.50"),
    }


def test_monthly_average_weights_each_day_and_skips_partly_covered_months():
    series = monthly_average_series(decisions(), "2031-02", "2031-08")
    assert "2031-02" not in series  # the first rate takes effect on 20 February
    assert series["2031-03"] == Decimal("3.000")
    # July: 9 days at 3.25, 13 days at 3.00, 9 days at 2.50
    assert series["2031-07"] == Decimal("2.927")
    assert series["2031-04"] == Decimal("3.175")  # 9 days at 3.00, 21 days at 3.25: 95.25 / 30


def test_two_decisions_in_one_month_give_different_month_end_and_average():
    ds = decisions()
    assert (
        month_end_series(ds, "2031-07", "2031-07")["2031-07"]
        != monthly_average_series(ds, "2031-07", "2031-07")["2031-07"]
    )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (("2031-02-19,2031-02-18,3.00,,unchanged," + URL,), "effective"),
        (
            (
                "2031-02-19,2031-02-20,3.00,,unchanged," + URL,
                "2031-02-19,2031-02-20,3.25,25,increase," + URL,
            ),
            "order",
        ),
        (
            (
                "2031-02-19,2031-02-20,3.00,,unchanged," + URL,
                "2031-04-09,2031-04-10,3.25,50,increase," + URL,
            ),
            "basis points",
        ),
        (
            (
                "2031-02-19,2031-02-20,3.00,,unchanged," + URL,
                "2031-04-09,2031-04-10,3.25,25,decrease," + URL,
            ),
            "decision",
        ),
        (
            (
                "2031-02-19,2031-02-20,3.00,,unchanged," + URL,
                "2031-04-09,2031-04-10,3.25,,increase," + URL,
            ),
            "basis points",
        ),
        (("2031-02-19,2031-02-20,3.00,,unchanged,https://example.com/x",), "source"),
        (("2031-02-19,2031-02-20,3.00,,unchanged,http://www.rbnz.govt.nz/x",), "source"),
        (("2031-02-19,2031-02-20,abc,,unchanged," + URL,), "rate"),
        (("2031-02-19,2031-02-20,30.00,,unchanged," + URL,), "rate"),
        (("2031-02-19,2031-02-20,3.001,,unchanged," + URL,), "rate"),
        (("19/02/2031,2031-02-20,3.00,,unchanged," + URL,), "date"),
        (("2031-02-19,2031-02-20,3.00,,paused," + URL,), "decision"),
        (("2031-02-19,2031-02-20,3.00,,unchanged",), "columns"),
        ((), "no decisions"),
    ],
)
def test_contract_violations_are_refused(rows, message):
    with pytest.raises(OcrContractError, match=message):
        parse_decisions(csv_text(*rows))


def test_header_must_match_exactly():
    with pytest.raises(OcrContractError, match="header"):
        parse_decisions("announced,effective,rate\n")


def test_ocr_module_has_no_network_access():
    banned = {"httpx", "requests", "urllib.request", "http.client", "socket", "nzstats.sources"}
    src = Path(__file__).resolve().parents[2] / "src" / "nzstats" / "ocr"
    for path in src.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = (
                [a.name for a in getattr(node, "names", [])] if isinstance(node, ast.Import) else []
            )
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any(n.split(".")[0] in banned or n in banned for n in names), (
                path.name,
                names,
            )


def test_no_production_code_reads_the_synthetic_fixture():
    src = Path(__file__).resolve().parents[2] / "src"
    assert not [p for p in src.rglob("*.py") if "SYNTHETIC_decisions" in p.read_text()]
    assert (FIXTURES / SYNTHETIC).read_text().startswith("# SYNTHETIC")
