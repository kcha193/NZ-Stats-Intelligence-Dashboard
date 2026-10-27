"""Forecast comparability: only like with like, and a plain reason for everything else (SYNTHETIC FIXTURE claims)."""

import pytest

from nzstats.research.api_models import ForecastOut, InstitutionOut
from nzstats.research.compare import basis_of, compare_forecasts, horizon_of, unit_of


def claim(**kw) -> ForecastOut:
    inst = kw.pop("institution", "alpha")
    data = {
        "summary_id": 1, "institution": InstitutionOut(key=inst, name=inst.title(), kind="bank"),
        "document_title": "Synthetic outlook", "published_on": "2026-08-13", "indicator": "cpi_inflation",
        "indicator_label": "Annual CPI inflation", "horizon": "year to June 2027", "value": 2.1,
        "unit": "percent", "direction": "down", "scenario": None, "qualification": None, "evidence": [],
    }  # fmt: skip
    data.update(kw)
    return ForecastOut(**data)


@pytest.mark.parametrize(
    ("text", "key", "label"),
    [
        ("year to March 2027", "year_to:2027-03", "Year to March 2027"),
        ("the year ended June 2027", "year_to:2027-06", "Year to June 2027"),
        ("Year ending Dec 2026", "year_to:2026-12", "Year to December 2026"),
        ("March 2027 quarter", "quarter:2027-03", "March 2027 quarter"),
        ("the September quarter of 2026", "quarter:2026-09", "September 2026 quarter"),
        ("Q4 2026", "quarter:2026-12", "December 2026 quarter"),
        ("2027Q1", "quarter:2027-03", "March 2027 quarter"),
        ("2027", "calendar:2027", "Calendar year 2027"),
        ("calendar year 2027", "calendar:2027", "Calendar year 2027"),
        ("December 2026", "month:2026-12", "December 2026"),
        ("end of 2026", "month:2026-12", "December 2026"),
        ("by end-2026", "month:2026-12", "December 2026"),
        ("2026/27", "split:2026/27", "2026/27 (as stated)"),
        ("2026/2027", "split:2026/27", "2026/27 (as stated)"),
    ],
)
def test_recognised_horizons(text, key, label):
    assert horizon_of(text) == (key, label)


@pytest.mark.parametrize(
    "text",
    [
        "next year",
        "over the coming year",
        "medium term",
        "May 2027 quarter",
        "2026/28",
        "Q5 2026",
        "",
    ],
)
def test_relative_or_odd_horizons_are_not_recognised(text):
    assert horizon_of(text) is None


@pytest.mark.parametrize(
    ("indicator", "label", "horizon", "unit", "expected"),
    [
        ("cpi_inflation", "Annual CPI inflation", "year to June 2027", "percent", "annual_change"),
        ("cpi_inflation", "CPI inflation", "year to June 2027", "percent", "annual_change"),
        (
            "cpi_inflation",
            "Quarterly CPI inflation",
            "June 2027 quarter",
            "percent",
            "quarterly_change",
        ),
        (
            "cpi_inflation",
            "CPI, annual average",
            "year to June 2027",
            "percent",
            "annual_average_change",
        ),
        ("cpi_inflation", "CPI inflation", "2027", "percent", None),
        (
            "gdp",
            "GDP, annual average growth",
            "year to March 2027",
            "percent",
            "annual_average_change",
        ),
        ("gdp", "GDP growth, annual % change", "year to March 2027", "percent", "annual_change"),
        ("gdp", "Real GDP growth (y/y)", "year to March 2027", "percent", "annual_change"),
        ("gdp", "Quarterly GDP growth", "March 2027 quarter", "percent", "quarterly_change"),
        (
            "gdp",
            "Economic growth",
            "year to March 2027",
            "percent",
            None,
        ),  # average or through the year?
        ("unemployment", "Unemployment rate", "December 2026 quarter", "percent", "rate"),
        ("unemployment", "Unemployment", "December 2026 quarter", "persons", None),
        ("ocr", "OCR", "December 2026", "percent", "level"),
        ("ocr", "OCR, quarterly average", "December 2026 quarter", "percent", "level_average"),
        ("ocr", "OCR at the end of the year", "2026", "percent", "level_end"),
        ("ocr", "Peak OCR", "2027", "percent", None),
        (
            "government_debt",
            "Net core Crown debt",
            "year to June 2027",
            "percent_of_gdp",
            "share_of_gdp",
        ),
        (
            "house_prices",
            "House prices, annual % change",
            "December 2026 quarter",
            "percent",
            "annual_change",
        ),
        ("house_prices", "House prices", "2027", "percent", None),
    ],
)
def test_statistical_basis(indicator, label, horizon, unit, expected):
    assert basis_of(indicator, label, horizon, unit) == expected


def test_units_use_the_verifier_vocabulary():
    assert unit_of("percent") == "percent" and unit_of("percent_of_gdp") == "percent_of_gdp"
    assert unit_of(None) is None and unit_of("%") is None and unit_of("furlongs") is None


def test_like_forecasts_are_grouped_and_each_institution_shows_its_latest_vintage():
    claims = [
        claim(institution="alpha", value=2.4, published_on="2026-05-01", summary_id=1),
        claim(institution="alpha", value=2.1, published_on="2026-08-13", summary_id=2),
        claim(institution="beta", value=2.3, published_on="2026-08-20", summary_id=3),
    ]
    out = compare_forecasts(claims)
    assert out.excluded == [] and len(out.groups) == 1
    g = out.groups[0]
    assert (g.indicator, g.unit, g.basis, g.horizon_key, g.kind) == (
        "cpi_inflation", "percent", "annual_change", "year_to:2027-06", "central")  # fmt: skip
    assert g.comparable and [r.forecast.institution.key for r in g.rows] == ["alpha", "beta"]
    alpha = g.rows[0]
    assert alpha.forecast.value == 2.1 and [e.value for e in alpha.earlier_vintages] == [2.4]
    assert "Annual" in g.basis_label and g.unit_label == "%"


@pytest.mark.parametrize(
    ("other", "why"),
    [
        ({"horizon": "year to March 2027"}, "horizon"),
        ({"indicator_label": "Quarterly CPI inflation", "horizon": "June 2027 quarter"}, "basis"),
        ({"unit": "percentage_points"}, "unit"),
        ({"scenario": "Downside"}, "scenario"),
    ],
)
def test_unlike_forecasts_are_never_in_one_group(other, why):
    out = compare_forecasts([claim(institution="alpha"), claim(institution="beta", **other)])
    assert len(out.groups) == 2, why
    assert all(not g.comparable for g in out.groups)
    assert all("only one institution" in g.note.lower() for g in out.groups)


def test_scenarios_are_grouped_by_name_and_labelled():
    out = compare_forecasts([
        claim(institution="alpha", scenario="Downside"), claim(institution="beta", scenario=" downside "),
        claim(institution="gamma"),
    ])  # fmt: skip
    kinds = sorted((g.kind, g.scenario, len(g.rows)) for g in out.groups)
    assert kinds == [("central", None, 1), ("scenario", "Downside", 2)]


@pytest.mark.parametrize(
    ("kw", "reason"),
    [
        ({"value": None}, "direction only"),
        ({"unit": None}, "no unit"),
        ({"horizon": "next year"}, "horizon"),
        (
            {
                "indicator": "gdp",
                "indicator_label": "Economic growth",
                "horizon": "year to March 2027",
            },
            "basis",
        ),
    ],
)
def test_claims_that_cannot_be_compared_say_why(kw, reason):
    out = compare_forecasts([claim(**kw)])
    assert out.groups == [] and len(out.excluded) == 1
    assert reason in out.excluded[0].reason.lower()


def test_facets_and_ordering_are_deterministic():
    claims = [
        claim(institution="beta", indicator="gdp", indicator_label="GDP, annual average growth",
              horizon="year to March 2027"),
        claim(institution="alpha"),
        claim(institution="alpha", horizon="year to March 2027"),
    ]  # fmt: skip
    out = compare_forecasts(claims)
    assert [g.indicator for g in out.groups] == ["gdp", "cpi_inflation", "cpi_inflation"]
    assert [g.horizon_key for g in out.groups][1:] == ["year_to:2027-03", "year_to:2027-06"]
    assert [(f.value, f.count) for f in out.indicators] == [("gdp", 1), ("cpi_inflation", 2)]
    assert [f.value for f in out.institutions] == ["alpha", "beta"]
    assert [f.value for f in out.horizons] == ["year_to:2027-03", "year_to:2027-06"]
    assert compare_forecasts(list(reversed(claims))) == out
