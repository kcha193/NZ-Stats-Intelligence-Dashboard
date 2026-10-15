import pandas as pd
import pytest

from nzstats.adapters.migration.parse import REGIONS, UNALLOCATED
from nzstats.insights.countries import rank_countries
from nzstats.store import repo
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


# --- places are read from the same release vintage as the total (review #4246272317) ------------


def _all_places(out):
    return {c.series_key: c for c in out.countries} | {r.series_key: r for r in out.regions}


def test_a_place_the_latest_release_omits_counts_as_zero_not_its_older_value(rt) -> None:
    """Togo has 2025-10 = 1 in the June file; the July file has no Togo rows at all."""
    ingest_months(rt, "2026-06", "2026-07")
    out = rank_countries(rt.conn, months=12, top=1000)
    togo = _all_places(out)["mig.m.arrivals.country.togo"]
    assert togo.value == 0.0 and togo.provisional is False
    expected = _expected()
    assert sum(c.value for c in out.countries) == pytest.approx(float(expected.sum()))
    assert {c.name for c in out.countries if c.value > 0} == set(expected[expected > 0].index)


def test_a_corrected_bundle_that_drops_a_place_does_not_keep_its_earlier_value(rt, site) -> None:
    """Same release, two bundles: the place only exists in the superseded one."""
    import io

    from nzstats.pipeline.ingest import ingest_release
    from tests.conftest import fixture_bytes
    from tests.support import NOW, release_ref_for

    ref = release_ref_for("2026-06")
    repo.upsert_release(rt.conn, ref, NOW)
    assert ingest_release(rt, ref.release_key, now_fn=lambda: NOW).outcome == "ingested"
    before = _all_places(rank_countries(rt.conn, months=12, top=1000))
    assert before["mig.m.arrivals.country.togo"].value == 1.0

    df = pd.read_csv(io.BytesIO(fixture_bytes("im_2026-06_citizenship_country.csv")))
    corrected = df[df.country_of_residence != "Togo"].to_csv(index=False, quoting=1).encode()
    site.override(site.file_url("2026-06", "citizenship_visa_country"), 200, corrected)
    assert ingest_release(rt, ref.release_key, now_fn=lambda: NOW).outcome == "ingested"
    after = _all_places(rank_countries(rt.conn, months=12, top=1000))
    assert after["mig.m.arrivals.country.togo"].value == 0.0
    assert after["mig.m.arrivals.country.togo"].series_key in after


# --- the prior window carries its own provisional flag (audit: unflagged provisional prior) -----


def _country_file_with_final_through(site, period: str) -> None:
    import io

    from tests.conftest import fixture_bytes

    df = pd.read_csv(io.BytesIO(fixture_bytes("im_2026-07_citizenship_country.csv")))
    df.loc[df.year_month <= period, "status"] = "Final"
    site.override(
        site.file_url("2026-07", "citizenship_visa_country"),
        200,
        df.to_csv(index=False, quoting=1).encode(),
    )


def test_prior_window_built_from_provisional_months_is_flagged(rt) -> None:
    ingest_months(rt, "2026-07")  # every stored month from 2025-06 is provisional in the real file
    out = rank_countries(rt.conn, months=6, top=5)
    assert all(c.prior_value is not None for c in out.countries)
    assert all(c.provisional and c.prior_provisional is True for c in out.countries)


def test_prior_window_of_final_months_is_not_flagged_while_the_current_one_is(rt, site) -> None:
    from nzstats.pipeline.ingest import ingest_release
    from tests.support import NOW, release_ref_for

    _country_file_with_final_through(site, "2026-01")  # prior = 2025-08..2026-01 for months=6
    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)
    assert ingest_release(rt, ref.release_key, now_fn=lambda: NOW).outcome == "ingested"
    out = rank_countries(rt.conn, months=6, top=5)
    assert all(c.prior_value is not None for c in out.countries)
    assert all(c.provisional and c.prior_provisional is False for c in out.countries)


def test_no_prior_flag_when_the_prior_window_is_withheld(rt) -> None:
    ingest_months(rt, "2026-07")
    out = rank_countries(rt.conn, months=12, top=5)  # 14 stored months: no full prior window
    assert all(c.prior_value is None and c.prior_provisional is None for c in out.countries)


def test_a_window_starting_before_stored_country_coverage_is_unavailable(rt) -> None:
    """Review #4268335623: months before coverage must not be summed as zero under a full total."""
    ingest_months(rt, "2026-07")  # country observations run 2025-06..2026-07 (14 months)
    out = rank_countries(rt.conn, months=36, top=5)
    assert out.available is False and out.countries == [] and out.regions == []
    assert out.total is None and out.period_start is None and out.period_end is None
    assert out.months == 36 and out.provenance is not None
    assert "2025-06" in out.note and "36" in out.note


def test_a_window_starting_exactly_at_stored_coverage_is_still_ranked(rt) -> None:
    ingest_months(rt, "2026-07")
    full = rank_countries(rt.conn, months=14, top=5)
    assert full.available and full.period_start == "2025-06" and full.total is not None
    assert rank_countries(rt.conn, months=15, top=5).available is False


def test_windows_and_prior_window_match_independent_sums_after_a_valid_ingest(rt) -> None:
    """Every stored month reconciles on ingest, so both windows sum from verified observations."""
    ingest_months(rt, "2026-07")
    df = pd.read_csv(FIXTURES / "im_2026-07_citizenship_country.csv")
    sel = df[
        (df.visa == "TOTAL")
        & (df.citizenship == "TOTAL")
        & (df.direction == "Arrivals")
        & (df.passenger_type == "Long-term migrant")
        & ~df.country_of_residence.isin(REGIONS | UNALLOCATED | {"TOTAL"})
    ]
    window = sel[(sel.year_month >= "2026-02") & (sel.year_month <= "2026-07")]
    prior = sel[(sel.year_month >= "2025-08") & (sel.year_month <= "2026-01")]
    now_sum = window.groupby("country_of_residence").estimate.sum()
    prior_sum = prior.groupby("country_of_residence").estimate.sum()
    out = rank_countries(rt.conn, months=6, top=1000)
    assert out.available and (out.period_start, out.period_end) == ("2026-02", "2026-07")
    for c in out.countries:
        assert c.value == float(now_sum.get(c.name, 0.0)), c.name
        assert c.prior_value == float(prior_sum.get(c.name, 0.0)), c.name
        assert c.change == c.value - c.prior_value
