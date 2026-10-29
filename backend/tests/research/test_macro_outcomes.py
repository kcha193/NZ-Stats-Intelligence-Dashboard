"""Phase 4C: GDP and unemployment forecasts matched to official outcomes, on the real March and June 2026 quarter
releases. Forecast claims are SYNTHETIC FIXTURE; every expected actual is Stats NZ's own published figure.
"""

from __future__ import annotations

import pytest

from nzstats.research.accuracy import evaluate_forecasts
from nzstats.research.macro_outcomes import (
    gdp_actuals,
    gdp_target,
    unemployment_actuals,
    unemployment_target,
)
from nzstats.research.outcomes import CpiActuals, cpi_target
from tests.macro_support import ingest_gdp, ingest_labour

from .test_compare import claim


def gdp(label, horizon, **kw):
    return claim(indicator="gdp", indicator_label=label, horizon=horizon, **kw)


def unemployment(label="Unemployment rate", horizon="June 2026 quarter", **kw):
    return claim(indicator="unemployment", indicator_label=label, horizon=horizon, **kw)


@pytest.mark.parametrize(("label", "horizon", "measure", "quarter"), [
    ("Real GDP growth, quarterly", "June 2026 quarter", "gdp_quarterly_production", "2026-06"),
    ("Real GDP growth, production measure, quarterly", "June 2026 quarter", "gdp_quarterly_production", "2026-06"),
    ("Real GDP growth, measure production, quarterly", "Q1 2026", "gdp_quarterly_production", "2026-03"),
    ("Real production GDP quarterly growth, seasonally adjusted", "Q1 2026", "gdp_quarterly_production", "2026-03"),
    ("Real GDP growth, expenditure measure, quarterly", "June 2026 quarter", "gdp_quarterly_expenditure", "2026-06"),
    ("Real GDP growth, measure expenditure, quarterly", "Q1 2026", "gdp_quarterly_expenditure", "2026-03"),
    ("Real GDP, annual average growth", "year to June 2026", "gdp_annual_average", "2026-06"),
    ("Real GDP, production measure, annual average growth", "year to June 2026", "gdp_annual_average", "2026-06"),
    ("Real GDP, measure production, annual average growth", "year to March 2026", "gdp_annual_average", "2026-03"),
    ("Real GDP growth (annual average)", "March 2026 quarter", "gdp_annual_average", "2026-03"),
    ("Real GDP, year-on-year growth, seasonally adjusted", "June 2026 quarter", "gdp_annual_change_sa", "2026-06"),
    ("Real GDP, production measure, year-on-year growth, seasonally adjusted", "June 2026 quarter", "gdp_annual_change_sa", "2026-06"),
    ("Real GDP, measure production, year-on-year growth, seasonally adjusted", "Q1 2026", "gdp_annual_change_sa", "2026-03"),
])  # fmt: skip
def test_gdp_targets_on_a_stated_basis(label, horizon, measure, quarter):
    target = gdp_target(gdp(label, horizon))
    assert (target.measure, target.quarter) == (measure, quarter)


@pytest.mark.parametrize(("label", "horizon", "why"), [
    ("GDP growth quarterly", "June 2026 quarter", "not stated clearly"),  # real or nominal unstated
    ("Nominal GDP annual average growth", "year to June 2026", "Nominal"),
    ("Real GDP growth, quarterly", "year to June 2026", "single quarter"),
    ("Real GDP growth, quarterly", "2026", "single quarter"),
    ("Real GDP, year-on-year growth", "June 2026 quarter", "seasonally adjusted"),
    ("Real GDP, annual average growth, seasonally adjusted", "year to June 2026", "actual"),
    ("Real GDP, annual average growth, expenditure", "year to June 2026", "expenditure"),
    ("Real GDP, production measure, year-on-year growth", "June 2026 quarter", "does not say seasonally adjusted"),
    ("Real GDP, production measure, annual average growth, seasonally adjusted", "year to June 2026", "actual (unadjusted) values"),
    ("Real GDP, expenditure measure, annual average growth", "year to June 2026", "annual average series is ingested for the expenditure measure"),
    ("Real GDP, measure expenditure, year-on-year growth, seasonally adjusted", "June 2026 quarter", "annual change series is ingested for the expenditure measure"),
    ("Real GDP, production measure, quarterly growth", "2026", "single quarter"),
    ("Real GDP, production and expenditure measure, quarterly growth", "June 2026 quarter", "not stated clearly"),
    ("Real GDP, production measure excluding agriculture, quarterly growth", "June 2026 quarter", "not stated clearly"),
    ("Real GDP, Auckland production measure, quarterly growth", "June 2026 quarter", "part of GDP"),
    ("Real Auckland GDP growth, quarterly", "June 2026 quarter", "part of GDP"),
    ("Real GDP per capita growth, quarterly", "June 2026 quarter", "not stated clearly"),
])  # fmt: skip
def test_unmatchable_gdp_claims_say_why(label, horizon, why):
    reason = gdp_target(gdp(label, horizon))
    assert isinstance(reason, str) and why in reason


@pytest.mark.parametrize(("label", "horizon", "why"), [
    ("Youth unemployment rate", "June 2026 quarter", "part of the labour force"),
    ("Unemployment rate (average)", "year to June 2026", "average"),
    ("Unemployment rate, end of period", "June 2026 quarter", "end-of-period"),
    ("Unemployment rate", "2026", "single quarter"),
    ("Unemployment rate", "June 2026", "month"),
])  # fmt: skip
def test_unmatchable_unemployment_claims_say_why(label, horizon, why):
    reason = unemployment_target(unemployment(label, horizon))
    assert isinstance(reason, str) and why in reason


def test_unemployment_rate_for_a_quarter_is_matched():
    target = unemployment_target(unemployment("Unemployment rate, seasonally adjusted", "Q2 2026"))
    assert (target.measure, target.quarter) == ("unemployment_rate", "2026-06")


def test_other_indicators_are_not_matched_by_these_rules():
    assert isinstance(gdp_target(unemployment()), str)
    assert isinstance(
        unemployment_target(gdp("Real GDP growth, quarterly", "June 2026 quarter")), str
    )


@pytest.mark.parametrize(("label", "measure", "actual"), [
    ("Real GDP growth, production measure, quarterly", "gdp_quarterly_production", 0.2),
    ("Real GDP, production measure, annual average growth", "gdp_annual_average", 1.7),
    ("Real GDP, production measure, year-on-year growth, seasonally adjusted", "gdp_annual_change_sa", 2.6),
    ("Real GDP growth, expenditure measure, quarterly", "gdp_quarterly_expenditure", 0.4),
])  # fmt: skip
def test_explicit_gdp_measures_evaluate_against_their_official_series(
    rt, site, label, measure, actual
):
    ingest_gdp(rt, site, "2026-06")
    forecast = gdp(label, "June 2026 quarter", value=0.5, published_on="2026-05-01")
    out = evaluate_forecasts([forecast], gdp_actuals(rt.conn), indicator="gdp")
    assert out.excluded == [] and len(out.evaluated) == 1
    evaluated = out.evaluated[0]
    assert (evaluated.measure, evaluated.target_quarter, evaluated.status) == (
        measure,
        "2026-06",
        "matched",
    )
    assert (evaluated.first.value, evaluated.latest.value) == (actual, actual)


def test_gdp_first_published_and_latest_are_the_official_figures(rt, site):
    ingest_gdp(rt, site, "2026-03", "2026-06")
    actuals = gdp_actuals(rt.conn)
    march = actuals.outcome(gdp_target(gdp("Real GDP growth, quarterly", "March 2026 quarter")))
    # Release pages: 0.8 in the March 2026 release, revised to 0.9 in June 2026.
    assert (march.first.value, march.latest.value, march.revision) == (0.8, 0.9, 0.1)
    assert (
        march.first.first_release
        and march.first.release == "Gross domestic product: March 2026 quarter"
    )
    assert march.latest.release == "Gross domestic product: June 2026 quarter"
    june = actuals.outcome(gdp_target(gdp("Real GDP, annual average growth", "year to June 2026")))
    assert (june.first.value, june.latest.value) == (1.7, 1.7)


def test_a_quarter_whose_own_release_is_not_stored_is_labelled_earliest_stored(rt, site):
    ingest_gdp(rt, site, "2026-06")
    out = gdp_actuals(rt.conn).outcome(
        gdp_target(gdp("Real GDP growth, quarterly", "March 2026 quarter"))
    )
    assert out.first.value == 0.9 and out.first.first_release is False


def test_a_quarter_not_yet_published_is_pending(rt, site):
    ingest_gdp(rt, site, "2026-06")
    actuals = gdp_actuals(rt.conn)
    assert (
        actuals.outcome(gdp_target(gdp("Real GDP growth, quarterly", "September 2026 quarter")))
        is None
    )
    assert actuals.newest_release()[0] == "Gross domestic product: June 2026 quarter"


def test_unemployment_first_published_5_3_latest_5_4(rt, site):
    ingest_labour(rt, site, "2026-03", "2026-06")
    out = unemployment_actuals(rt.conn).outcome(
        unemployment_target(unemployment(horizon="March 2026 quarter"))
    )
    assert (out.first.value, out.latest.value, out.revision) == (5.3, 5.4, 0.1)


def test_evaluation_scores_against_first_published_and_latest(rt, site):
    ingest_labour(rt, site, "2026-03", "2026-06")
    forecasts = [unemployment(horizon="March 2026 quarter", value=5.0, published_on="2026-02-10")]
    out = evaluate_forecasts(forecasts, unemployment_actuals(rt.conn), indicator="unemployment")
    assert out.state == "available" and out.official_series == "hlfs.rate.unemployment.sa"
    e = out.evaluated[0]
    assert e.status == "matched" and e.measure_label.startswith("Unemployment rate")
    assert (e.error_first, e.error_latest) == (-0.3, -0.4)


def test_look_ahead_forecasts_are_excluded(rt, site):
    ingest_labour(rt, site, "2026-03", "2026-06")
    late = unemployment(horizon="March 2026 quarter", value=5.3, published_on="2026-05-06")
    out = evaluate_forecasts([late], unemployment_actuals(rt.conn), indicator="unemployment")
    assert out.evaluated == [] and "on or after the official figure" in out.excluded[0].reason


def test_gdp_evaluation_never_uses_cpi_actuals(rt, site):
    ingest_gdp(rt, site, "2026-06")
    forecasts = [
        gdp("Real GDP growth, quarterly", "June 2026 quarter", value=0.5, published_on="2026-05-01")
    ]
    assert (
        evaluate_forecasts(forecasts, CpiActuals(rt.conn), indicator="gdp").state
        == "no_official_series"
    )
    out = evaluate_forecasts(forecasts, gdp_actuals(rt.conn), indicator="gdp")
    assert out.evaluated[0].error_first == 0.3


def test_ocr_has_no_official_series_and_says_why(rt):
    out = evaluate_forecasts(
        [claim(indicator="ocr", indicator_label="OCR", horizon="June 2026 quarter", value=3.0)],
        CpiActuals(rt.conn),
        indicator="ocr",
    )
    assert out.state == "no_official_series" and "RBNZ" in (out.unavailable_reason or "")


def test_cpi_matching_rules_are_unchanged():
    # A quarterly CPI change that does not say whether it is seasonally adjusted stays unmatched (Phase 3D-B rule),
    # even though GDP quarterly growth is now matched to Stats NZ's seasonally adjusted headline.
    reason = cpi_target(claim(indicator_label="CPI, quarterly change", horizon="June 2026 quarter"))
    assert isinstance(reason, str) and "seasonally adjusted" in reason
