"""Phase 3E: an independent oracle for CPI outcome matching, on the real Stats NZ release files.

The expected values here never go through the adapter, the database or `outcomes.compute`: they are calculated from
the official CSVs' index strings with the csv module and Decimal, rounded half away from zero to one decimal place
(Stats NZ's convention). The first-published value of a quarter must come from that quarter's own release file and the
latest from the newest release file; with only the newest release stored, every earlier quarter must be labelled as the
earliest stored, never as a first release.
"""

from __future__ import annotations

import csv
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from nzstats.research.outcomes import CpiActuals, Target
from tests.cpi_support import ingest_cpi

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RELEASES = ("2025-12", "2026-03", "2026-06", "2026-09")
SERIES = {"nsa": ("index_numbers", "CPIQ.SE9A"), "sa": ("seasonally_adjusted", "CPIQ.SE9SA")}


def official_index(release: str, kind: str) -> dict[str, Decimal]:
    """Quarter (YYYY-MM) -> index number as printed in that release's own CSV."""
    name, ref = SERIES[kind]
    out = {}
    with (FIXTURES / f"cpi_{release}_{name}.csv").open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if row["Series_reference"] == ref and row["Data_value"] not in ("", "NA"):
                year, month = row["Period"].split(".")
                out[f"{year}-{month}"] = Decimal(row["Data_value"])
    return out


def back(quarter: str, n: int) -> str:
    y, m = int(quarter[:4]), int(quarter[5:])
    i = y * 4 + m // 3 - 1 - n
    return f"{i // 4:04d}-{(i % 4 + 1) * 3:02d}"


def one_dp(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def expected(measure: str, release: str, quarter: str) -> float:
    if measure == "quarterly_change_sa":
        idx = official_index(release, "sa")
        return one_dp((idx[quarter] / idx[back(quarter, 1)] - 1) * 100)
    idx = official_index(release, "nsa")
    if measure == "annual_change":
        return one_dp((idx[quarter] / idx[back(quarter, 4)] - 1) * 100)
    if measure == "quarterly_change_nsa":
        return one_dp((idx[quarter] / idx[back(quarter, 1)] - 1) * 100)
    recent = sum(idx[back(quarter, k)] for k in range(4))
    earlier = sum(idx[back(quarter, k)] for k in range(4, 8))
    return one_dp((recent / earlier - 1) * 100)


MEASURES = ("annual_change", "annual_average_change", "quarterly_change_nsa", "quarterly_change_sa")


@pytest.mark.parametrize("measure", MEASURES)
def test_first_published_and_latest_match_the_official_files(rt, site, measure):
    ingest_cpi(rt, site, *RELEASES)
    actuals = CpiActuals(rt.conn)
    for quarter in RELEASES:
        out = actuals.outcome(Target(measure, quarter))
        assert out is not None, quarter
        assert not out.first.first_release, quarter  # all captures are historical
        assert out.first.value == expected(measure, quarter, quarter), (measure, quarter)
        assert out.latest.value == expected(measure, "2026-09", quarter), (measure, quarter)
        assert out.revision == pytest.approx(out.latest.value - out.first.value)


@pytest.mark.parametrize("measure", MEASURES)
def test_with_only_the_newest_release_stored_earlier_quarters_are_earliest_stored_not_first(
    rt, site, measure
):
    ingest_cpi(rt, site, "2026-09")
    actuals = CpiActuals(rt.conn)
    for quarter in RELEASES:
        out = actuals.outcome(Target(measure, quarter))
        assert out.first.first_release is False, quarter
        assert out.first.value == expected(measure, "2026-09", quarter)
        assert out.revision == 0


def test_the_unadjusted_index_was_not_revised_across_these_releases_but_the_adjusted_one_was():
    """Context for reading the results: earliest-stored and first-published agree for the unadjusted measures here
    only because Stats NZ does not revise the unadjusted CPI; the seasonally adjusted series is re-estimated."""
    nsa = [official_index(r, "nsa") for r in RELEASES]
    for older, newer in zip(nsa, nsa[1:], strict=False):
        assert all(newer[q] == v for q, v in older.items())
    sa = [official_index(r, "sa") for r in RELEASES]
    assert any(sa[-1][q] != v for q, v in sa[0].items())


def test_stored_release_coverage_names_the_oldest_genuine_first_release(rt, site):
    from nzstats.research.outcomes import stored_cpi_releases

    assert stored_cpi_releases(rt.conn) == []
    ingest_cpi(rt, site, "2026-06", "2026-09")
    rows = stored_cpi_releases(rt.conn)
    assert [r.reference_period for r in rows] == ["2026-06", "2026-09"]
    assert all(r.bundles == 1 and r.earliest_captured_at for r in rows)


def test_cli_cpi_vintages_reports_the_earliest_stored_boundary(rt, site, capsys, monkeypatch):
    from nzstats.cli import main

    ingest_cpi(rt, site, "2026-09")
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(rt.settings.data_dir))
    assert main(["research", "cpi-vintages"]) == 0
    out = capsys.readouterr().out
    assert "2026-09" in out and "before 2026-09" in out and "earliest stored" in out
    assert "their first-published values are genuine" not in out


@pytest.mark.parametrize("measure", MEASURES)
def test_backfilling_older_releases_after_the_newest_gives_the_in_order_result(rt, site, measure):
    """The Phase 3E backfill plan: the production database holds only the September 2026 release, and the older ones
    would be ingested after it. Release order, not ingestion order, decides first-published and latest."""
    from nzstats.store.repo import latest_points

    ingest_cpi(rt, site, "2026-09", "2025-12", "2026-03", "2026-06")
    actuals = CpiActuals(rt.conn)
    for quarter in RELEASES:
        out = actuals.outcome(Target(measure, quarter))
        assert not out.first.first_release and out.first.value == expected(
            measure, quarter, quarter
        )
        assert out.latest.value == expected(measure, "2026-09", quarter)
    assert max(latest_points(rt.conn, "cpi.index.nsa.all_groups")) == "2026-09"
