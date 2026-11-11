"""Phase 4AE review round 1: bank evaluation keeps the normalized seasonal adjustment when it picks an official series
(SYNTHETIC forecasts scored against real Stats NZ test releases)."""

import pytest

from nzstats.research.bank_analytics import bank_evaluation
from tests.cpi_support import ingest_cpi
from tests.macro_support import ingest_gdp, ingest_labour

from .bank_support import nf, view_of

QUARTERLY = {"indicator_label": "Quarterly CPI inflation", "horizon": "June 2026 quarter"}
ANNUAL = {"indicator_label": "Annual CPI inflation", "horizon": "year to June 2026"}
GDP = {
    "indicator": "gdp",
    "horizon": "June 2026 quarter",
    "published_on": "2026-05-01",
    "value": 0.5,
}
UNEMPLOYMENT = {
    "indicator": "unemployment",
    "indicator_label": "Unemployment rate",
    "horizon": "March 2026 quarter",
    "published_on": "2026-02-10",
    "value": 5.0,
}


def cpi(adjustment, *, published_on="2026-03-01", **kw):
    return nf("bank_a", adjustment=adjustment, published_on=published_on, value=0.5, **kw)


@pytest.fixture()
def cpi_conn(rt, site):
    ingest_cpi(rt, site, "2025-12", "2026-03", "2026-06", "2026-09")
    rt.conn.execute(
        "UPDATE vintage SET captured_at = (SELECT published_at FROM release WHERE id = release_id)"
    )
    return rt.conn


def evaluate(conn, indicator, *forecasts):
    return bank_evaluation(view_of(*forecasts), conn, indicator)


def matched(out):
    return [(e.measure, e.target_quarter) for e in out.evaluated if e.status != "excluded"]


def reasons(out):
    return [x.reason for x in out.excluded]


# --- CPI --------------------------------------------------------------------------------------------------------
def test_a_quarterly_cpi_adjustment_stated_only_in_the_evidence_is_matched_to_the_sa_series(
    cpi_conn,
):
    out = evaluate(cpi_conn, "cpi_inflation", cpi("seasonally_adjusted", **QUARTERLY))
    assert out.excluded == [] and matched(out) == [("quarterly_change_sa", "2026-06")]


def test_an_unadjusted_quarterly_cpi_is_matched_to_the_unadjusted_series(cpi_conn):
    out = evaluate(cpi_conn, "cpi_inflation", cpi("unadjusted", **QUARTERLY))
    assert out.excluded == [] and matched(out) == [("quarterly_change_nsa", "2026-06")]


def test_a_quarterly_cpi_that_never_states_its_adjustment_is_still_not_matched(cpi_conn):
    out = evaluate(cpi_conn, "cpi_inflation", cpi("not_stated", **QUARTERLY))
    assert out.evaluated == [] and "does not say whether" in reasons(out)[0]


def test_an_annual_cpi_marked_seasonally_adjusted_in_the_evidence_is_not_scored_against_the_unadjusted_index(
    cpi_conn,
):
    out = evaluate(cpi_conn, "cpi_inflation", cpi("seasonally_adjusted", **ANNUAL))
    assert out.evaluated == []
    assert "seasonally adjusted annual change is not the official measure" in reasons(out)[0]


@pytest.mark.parametrize("adjustment", ["unadjusted", "not_stated"])
def test_an_annual_cpi_that_is_unadjusted_or_silent_is_matched_to_the_unadjusted_index(
    cpi_conn, adjustment
):
    out = evaluate(cpi_conn, "cpi_inflation", cpi(adjustment, **ANNUAL))
    assert out.excluded == [] and matched(out) == [("annual_change", "2026-06")]


def test_a_label_and_evidence_that_disagree_on_adjustment_are_excluded_with_a_reason(cpi_conn):
    """The label says seasonally adjusted but the evidence says unadjusted: `derive_adjustment` gives not_stated."""
    label = {
        "indicator_label": "Quarterly CPI inflation, seasonally adjusted",
        "horizon": "June 2026 quarter",
    }
    out = evaluate(cpi_conn, "cpi_inflation", cpi("not_stated", **label))
    assert out.evaluated == [] and "disagree" in reasons(out)[0]


def test_the_evaluated_forecast_keeps_its_own_label_and_value(cpi_conn):
    f = cpi("seasonally_adjusted", **QUARTERLY)
    out = evaluate(cpi_conn, "cpi_inflation", f)
    assert out.evaluated[0].forecast == f.forecast


def test_look_ahead_is_still_excluded_for_an_adjusted_forecast(cpi_conn):
    late = cpi("seasonally_adjusted", published_on="2026-08-01", **QUARTERLY)
    out = evaluate(cpi_conn, "cpi_inflation", late)
    assert out.evaluated == [] and "on or after" in reasons(out)[0]


def test_first_published_actual_is_used_whatever_the_adjustment(cpi_conn):
    sa = evaluate(cpi_conn, "cpi_inflation", cpi("seasonally_adjusted", **QUARTERLY)).evaluated[0]
    nsa = evaluate(cpi_conn, "cpi_inflation", cpi("unadjusted", **QUARTERLY)).evaluated[0]
    assert sa.first.release == nsa.first.release and sa.first.first_release


# --- GDP and unemployment: only the seasonally adjusted series is stored (annual average GDP is from actual values) -
def gdp(adjustment, label, **kw):
    return nf("bank_a", adjustment=adjustment, indicator_label=label, **{**GDP, **kw})


def test_gdp_quarterly_growth_adjustment_compatibility(rt, site):
    ingest_gdp(rt, site, "2026-06")
    label = "Real GDP growth, quarterly"
    for adjustment, expected in [
        ("seasonally_adjusted", True),
        ("not_stated", True),
        ("unadjusted", False),
    ]:
        out = evaluate(rt.conn, "gdp", gdp(adjustment, label))
        assert bool(out.evaluated) is expected, adjustment
        if not expected:
            assert "seasonally adjusted series" in reasons(out)[0]


def test_gdp_annual_change_of_a_quarter_needs_the_seasonally_adjusted_series(rt, site):
    ingest_gdp(rt, site, "2026-06")
    label = "Real GDP, production measure, year-on-year growth"
    sa = evaluate(rt.conn, "gdp", gdp("seasonally_adjusted", label))
    assert matched(sa) == [("gdp_annual_change_sa", "2026-06")]
    for adjustment in ("unadjusted", "not_stated"):
        assert evaluate(rt.conn, "gdp", gdp(adjustment, label)).evaluated == []


def test_gdp_annual_average_is_an_actual_values_measure(rt, site):
    ingest_gdp(rt, site, "2026-06")
    label = "Real GDP, production measure, annual average growth"
    kw = {"horizon": "year to June 2026"}
    assert matched(evaluate(rt.conn, "gdp", gdp("unadjusted", label, **kw))) == [
        ("gdp_annual_average", "2026-06")
    ]
    out = evaluate(rt.conn, "gdp", gdp("seasonally_adjusted", label, **kw))
    assert out.evaluated == [] and "not an official measure" in reasons(out)[0]


def test_unemployment_adjustment_compatibility(rt, site):
    ingest_labour(rt, site, "2026-03", "2026-06")
    for adjustment, expected in [
        ("seasonally_adjusted", True),
        ("not_stated", True),
        ("unadjusted", False),
    ]:
        out = evaluate(rt.conn, "unemployment", nf("bank_a", adjustment=adjustment, **UNEMPLOYMENT))
        assert bool(out.evaluated) is expected, adjustment
        if not expected:
            assert "seasonally adjusted series" in reasons(out)[0]
