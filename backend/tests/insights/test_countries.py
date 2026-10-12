import pandas as pd
import pytest

from nzstats.adapters.migration.parse import REGIONS, UNALLOCATED
from nzstats.insights.countries import rank_countries
from tests.conftest import FIXTURES
from tests.support import ingest_months


def _expected():
    df = pd.read_csv(FIXTURES / "im_2026-07_citizenship_country.csv")
    sel = df[
        (df.visa == "TOTAL")
        & (df.citizenship == "TOTAL")
        & (df.direction == "Arrivals")
        & (df.year_month >= "2025-08")
    ]
    countries = sel[~sel.country_of_residence.isin(REGIONS | UNALLOCATED | {"TOTAL"})]
    return countries.groupby("country_of_residence").estimate.sum().sort_values(ascending=False)


def test_ranking_matches_independent_sums_and_excludes_regions(rt) -> None:
    ingest_months(rt, "2026-07")
    out = rank_countries(rt.conn, months=12, top=5)
    expected = _expected()
    assert out.available and out.derived
    assert (out.period_start, out.period_end) == ("2025-08", "2026-07")
    assert [c.name for c in out.countries] == list(expected.index[:5])
    assert [c.value for c in out.countries] == [float(v) for v in expected.values[:5]]
    assert {r.name for r in out.regions} == set(REGIONS)
    assert out.unallocated is not None and out.unallocated.name == "Not Stated"
    assert all(c.name not in REGIONS for c in out.countries)
    assert out.countries[0].share_percent == pytest.approx(out.countries[0].value / out.total * 100)
    assert all(
        c.prior_value is None and c.change is None for c in out.countries
    )  # 14 months stored
    assert any(c.provisional for c in out.countries)


def test_not_available_before_any_ingestion(rt) -> None:
    out = rank_countries(rt.conn)
    assert out.available is False and out.countries == [] and "No country data" in out.note


def test_prior_change_is_withheld_when_the_latest_vintage_does_not_cover_the_prior_window(
    rt,
) -> None:
    """An older vintage may hold more history than the latest one; the prior sum reads the latest."""
    adapter = rt.adapters["international-migration"]
    ingest_months(rt, "2026-06")  # 36-month window: holds everything the file contains
    adapter._window = 13  # the latest vintage then holds only 13 months
    ingest_months(rt, "2026-07")
    out = rank_countries(rt.conn, months=7, top=5)
    assert out.available
    # prior window = 2025-06..2025-12, but the latest vintage starts at 2025-07: not fully covered
    assert all(
        c.prior_value is None and c.change is None and c.change_percent is None
        for c in out.countries
    )
