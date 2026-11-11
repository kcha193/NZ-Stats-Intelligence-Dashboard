"""Phase 4AE review round 6: geography is a place, not a measurement qualifier, and an adjustment stated both ways is not
the same as one never stated (SYNTHETIC FIXTURE)."""

import pytest

from nzstats.research.bank_analytics import bank_evaluation
from nzstats.research.bank_forecast import adjustment_conflicts, derive_geography
from tests.cpi_support import ingest_cpi
from tests.macro_support import ingest_gdp

from .bank_support import nf, view_of
from .test_bank_canonical_identity import _stored
from .test_bank_view import view


@pytest.mark.parametrize(
    ("indicator", "label", "expected"),
    [
        ("cpi_inflation", "Annual CPI inflation (unadjusted)", "New Zealand"),
        ("cpi_inflation", "Annual CPI inflation (non-seasonally adjusted)", "New Zealand"),
        ("gdp", "Real GDP growth, production measure, quarterly", "New Zealand"),
        ("gdp", "Net core Crown debt", "New Zealand"),
        ("unemployment", "Youth unemployment rate", "New Zealand"),
        ("unemployment", "Unemployment rate, women", "New Zealand"),
        ("unemployment", "Auckland unemployment rate", "Auckland"),
        ("cpi_inflation", "CPI inflation, Wellington", "Wellington"),
        ("unemployment", "Bay of Plenty unemployment rate", "Bay of Plenty"),
        ("unemployment", "Unemployment rate: Canterbury and Otago", "Canterbury, Otago"),
        ("unemployment", "Waikato unemployment rate (seasonally adjusted)", "Waikato"),
    ],
)
def test_geography_is_a_place_only(indicator, label, expected):
    assert derive_geography(indicator, label, "March 2027 quarter", "percent") == expected


@pytest.mark.parametrize(
    ("label", "quote", "expected"),
    [
        ("Annual CPI inflation", "inflation of 2.0%", False),
        ("Annual CPI inflation", "seasonally adjusted 2.0%", False),
        ("Annual CPI inflation", "seasonally adjusted 2.0%, unadjusted 2.4%", True),
        ("GDP growth, seasonally adjusted", "an unadjusted 0.4% rise", True),
        ("GDP growth, seasonally adjusted", "a seasonally adjusted 0.4% rise", False),
        ("GDP growth, seasonally adjusted and unadjusted", "0.4%", True),
    ],
)
def test_adjustment_conflicts_are_stated_both_ways(label, quote, expected):
    assert adjustment_conflicts(label, quote) is expected


def test_the_bank_view_flags_evidence_that_states_both_adjustments(conn):
    _stored(
        conn,
        "bank_a",
        "Annual CPI inflation",
        quote_tail=", seasonally adjusted and unadjusted both",
    )
    _stored(conn, "bank_b", "Annual CPI inflation", doc="research/outlook/q5")
    got = {
        f.institution_key: f
        for f in view(conn).forecasts
        if f.forecast.indicator == "cpi_inflation"
    }
    assert (got["bank_a"].adjustment, got["bank_a"].adjustment_conflict) == ("not_stated", True)
    assert (got["bank_b"].adjustment, got["bank_b"].adjustment_conflict) == ("not_stated", False)


@pytest.fixture()
def cpi_conn(rt, site):
    ingest_cpi(rt, site, "2025-12", "2026-03", "2026-06", "2026-09")
    rt.conn.execute(
        "UPDATE vintage SET captured_at = (SELECT published_at FROM release WHERE id = release_id)"
    )
    return rt.conn


def test_a_contradictory_adjustment_is_not_scored_as_if_it_were_silent(cpi_conn):
    annual = {
        "indicator_label": "Annual CPI inflation",
        "horizon": "year to June 2026",
        "value": 0.5,
    }
    silent = nf("bank_a", published_on="2026-03-01", **annual)
    both = nf("bank_b", published_on="2026-03-01", adjustment_conflict=True, **annual)
    out = bank_evaluation(view_of(silent, both), cpi_conn, "cpi_inflation")
    assert [e.forecast.institution.key for e in out.evaluated] == ["bank_a"]
    (excluded,) = out.excluded
    assert excluded.forecast.institution.key == "bank_b"
    assert "adjustment" in excluded.reason and "both ways" in excluded.reason


def test_a_contradictory_gdp_adjustment_does_not_default_to_the_seasonally_adjusted_series(
    rt, site
):
    ingest_gdp(rt, site, "2026-06")
    gdp = {"indicator": "gdp", "indicator_label": "Real GDP growth, quarterly",
           "horizon": "June 2026 quarter", "published_on": "2026-05-01", "value": 0.5}  # fmt: skip
    out = bank_evaluation(view_of(nf("bank_a", adjustment_conflict=True, **gdp)), rt.conn, "gdp")
    assert out.evaluated == [] and "both ways" in out.excluded[0].reason
