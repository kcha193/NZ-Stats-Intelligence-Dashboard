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
            "Real GDP, annual average growth",
            "year to March 2027",
            "percent",
            "real_annual_average_change",
        ),
        ("gdp", "Real GDP growth (y/y)", "year to March 2027", "percent", "real_annual_change"),
        (
            "gdp",
            "Nominal GDP growth (y/y)",
            "year to March 2027",
            "percent",
            "nominal_annual_change",
        ),
        (
            "gdp",
            "Real quarterly GDP growth",
            "March 2027 quarter",
            "percent",
            "real_quarterly_change",
        ),
        # Real or nominal is not stated, so it is not assumed.
        ("gdp", "GDP, annual average growth", "year to March 2027", "percent", None),
        ("gdp", "Quarterly GDP growth", "March 2027 quarter", "percent", None),
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
        claim(institution="beta", indicator="gdp", indicator_label="Real GDP, annual average growth",
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


# --- Statistical-basis regressions (PR #13 review): price basis, unemployment timing, conflicting wording ---


def gdp(
    institution="alpha", label="Real GDP, annual average growth", horizon="year to March 2027", **kw
):
    return claim(
        institution=institution, indicator="gdp", indicator_label=label, horizon=horizon, **kw
    )


def unemployment(
    institution="alpha", label="Unemployment rate", horizon="December 2026 quarter", **kw
):
    return claim(
        institution=institution,
        indicator="unemployment",
        indicator_label=label,
        horizon=horizon,
        **kw,
    )


@pytest.mark.parametrize(
    ("label", "horizon", "expected"),
    [
        ("Real GDP, annual average growth", "year to March 2027", "real_annual_average_change"),
        (
            "Nominal GDP, annual average growth",
            "year to March 2027",
            "nominal_annual_average_change",
        ),
        ("Real GDP growth (y/y)", "year to March 2027", "real_annual_change"),
        ("Nominal GDP growth, annual % change", "year to March 2027", "nominal_annual_change"),
        (
            "GDP growth at constant prices, annual average",
            "year to March 2027",
            "real_annual_average_change",
        ),
        ("GDP growth in current prices (y/y)", "year to March 2027", "nominal_annual_change"),
        ("Real quarterly GDP growth", "March 2027 quarter", "real_quarterly_change"),
        # The measurement basis is not stated: never assume real.
        ("GDP, annual average growth", "year to March 2027", None),
        ("GDP growth, annual % change", "year to March 2027", None),
        # Contradictory or different series.
        ("Real and nominal GDP growth (y/y)", "year to March 2027", None),
        ("Real GDP per capita growth (y/y)", "year to March 2027", None),
        ("Potential real GDP growth, annual average", "year to March 2027", None),
        # Real/nominal must not leak in from the horizon text, nor change the cadence rules.
        ("Real GDP growth, annual average and y/y", "year to March 2027", None),
    ],
)
def test_gdp_price_basis_is_stated_never_assumed(label, horizon, expected):
    assert basis_of("gdp", label, horizon, "percent") == expected


def test_real_and_nominal_gdp_with_the_same_horizon_and_unit_are_separate_groups():
    out = compare_forecasts([
        gdp("alpha", "Real GDP, annual average growth", value=1.8),
        gdp("beta", "Nominal GDP, annual average growth", value=4.9),
    ])  # fmt: skip
    assert out.excluded == [] and len(out.groups) == 2
    assert all(not g.comparable for g in out.groups)
    assert len({g.key for g in out.groups}) == 2
    assert {g.basis for g in out.groups} == {
        "real_annual_average_change",
        "nominal_annual_average_change",
    }
    labels = {g.basis_label for g in out.groups}
    assert any(lbl.startswith("Real") for lbl in labels) and any(
        lbl.startswith("Nominal") for lbl in labels
    )


def test_same_institution_real_and_nominal_gdp_are_not_vintages_of_each_other():
    out = compare_forecasts([
        gdp("alpha", "Real GDP, annual average growth", value=1.8, published_on="2026-08-13", summary_id=1),
        gdp("alpha", "Nominal GDP, annual average growth", value=4.9, published_on="2026-08-20", summary_id=2),
    ])  # fmt: skip
    assert len(out.groups) == 2
    for g in out.groups:
        assert len(g.rows) == 1 and g.rows[0].earlier_vintages == []


def test_cross_institution_real_gdp_and_nominal_gdp_compare_within_their_own_measure():
    out = compare_forecasts([
        gdp("alpha", "Real GDP, annual average growth", value=1.8),
        gdp("beta", "Real GDP growth, annual average", value=2.0),
        gdp("alpha", "Nominal GDP, annual average growth", value=4.9),
        gdp("beta", "Nominal GDP growth, annual average", value=5.1),
    ])  # fmt: skip
    assert len(out.groups) == 2 and all(g.comparable and len(g.rows) == 2 for g in out.groups)
    by_basis = {g.basis: sorted(r.forecast.value for r in g.rows) for g in out.groups}
    assert by_basis == {
        "real_annual_average_change": [1.8, 2.0],
        "nominal_annual_average_change": [4.9, 5.1],
    }


def test_real_gdp_vintages_still_deduplicate_within_one_institution():
    out = compare_forecasts([
        gdp("alpha", value=1.5, published_on="2026-05-01", summary_id=1),
        gdp("alpha", value=1.8, published_on="2026-08-13", summary_id=2),
    ])  # fmt: skip
    (g,) = out.groups
    assert g.rows[0].forecast.value == 1.8 and [e.value for e in g.rows[0].earlier_vintages] == [
        1.5
    ]


def test_gdp_without_a_stated_price_basis_is_excluded_with_a_reason():
    out = compare_forecasts(
        [gdp("alpha", "GDP, annual average growth"), gdp("beta", "GDP, annual average growth")]
    )
    assert out.groups == [] and len(out.excluded) == 2
    assert all("real or nominal" in e.reason.lower() for e in out.excluded)


def test_gdp_annual_average_and_through_the_year_stay_separate_for_the_same_price_basis():
    out = compare_forecasts([
        gdp("alpha", "Real GDP, annual average growth"), gdp("beta", "Real GDP growth (y/y)"),
    ])  # fmt: skip
    assert {g.basis for g in out.groups} == {"real_annual_average_change", "real_annual_change"}


@pytest.mark.parametrize(
    ("label", "horizon", "expected"),
    [
        # Timing stated in the label.
        ("Annual average unemployment rate", "2027", "rate_average"),
        ("Unemployment rate, annual average", "year to March 2027", "rate_average"),
        ("End of year unemployment rate", "2027", "rate_end"),
        ("Year-end unemployment rate", "2027", "rate_end"),
        ("Unemployment rate at the end of the period", "year to March 2027", "rate_end"),
        # Timing not stated: a quarter or month is itself the point in time; a span is not.
        ("Unemployment rate", "December 2026 quarter", "rate"),
        ("Unemployment rate", "December 2026", "rate"),
        ("Unemployment rate", "2027", "rate_timing_unstated"),
        ("Unemployment rate", "year to March 2027", "rate_timing_unstated"),
        ("Unemployment rate", "2026/27", "rate_timing_unstated"),
        # Contradictory or non-comparable wording.
        ("Average end-of-year unemployment rate", "2027", None),
        ("Peak unemployment rate", "2027", None),
        ("Unemployment", "December 2026 quarter", None),
    ],
)
def test_unemployment_timing_is_part_of_the_basis(label, horizon, expected):
    unit = "persons" if label == "Unemployment" else "percent"
    assert basis_of("unemployment", label, horizon, unit) == expected


@pytest.mark.parametrize(
    ("indicator", "label", "horizon", "unit", "expected"),
    [
        # CPI: contradictory cadence wording is not guessed at.
        (
            "cpi_inflation",
            "Annual average CPI inflation, y/y",
            "year to June 2027",
            "percent",
            None,
        ),
        (
            "cpi_inflation",
            "Quarterly CPI inflation, annual average",
            "June 2027 quarter",
            "percent",
            None,
        ),
        # CPI: core, underlying and component measures are different series from headline CPI.
        ("cpi_inflation", "Core CPI inflation, annual", "year to June 2027", "percent", None),
        (
            "cpi_inflation",
            "Annual CPI inflation excluding food and energy",
            "year to June 2027",
            "percent",
            None,
        ),
        ("cpi_inflation", "Annual tradables inflation", "year to June 2027", "percent", None),
        (
            "cpi_inflation",
            "Non-tradable CPI inflation, annual",
            "year to June 2027",
            "percent",
            None,
        ),
        ("cpi_inflation", "Annual trimmed mean inflation", "year to June 2027", "percent", None),
        # OCR: average and end-of-period in one label is ambiguous.
        ("ocr", "Average OCR at the end of the year", "2026", "percent", None),
        # Other indicators carry the price basis when it is stated, and never when contradictory.
        (
            "wages",
            "Real wage growth, annual % change",
            "year to March 2027",
            "percent",
            "real_annual_change",
        ),
        (
            "wages",
            "Nominal wage growth, annual % change",
            "year to March 2027",
            "percent",
            "nominal_annual_change",
        ),
        ("wages", "Wage growth, annual % change", "year to March 2027", "percent", "annual_change"),
        (
            "wages",
            "Real nominal wage growth, annual % change",
            "year to March 2027",
            "percent",
            None,
        ),
    ],
)
def test_adjacent_indicators_do_not_conflate_different_statistics(
    indicator, label, horizon, unit, expected
):
    assert basis_of(indicator, label, horizon, unit) == expected


def test_unemployment_average_end_and_unstated_timing_never_share_a_group():
    out = compare_forecasts([
        unemployment("alpha", "Annual average unemployment rate", "2027"),
        unemployment("beta", "End of year unemployment rate", "2027"),
        unemployment("gamma", "Unemployment rate", "2027"),
    ])  # fmt: skip
    assert out.excluded == [] and len(out.groups) == 3
    assert {g.basis for g in out.groups} == {"rate_average", "rate_end", "rate_timing_unstated"}
    assert all(not g.comparable and len(g.rows) == 1 for g in out.groups)
    assert len({g.key for g in out.groups}) == 3


def test_same_institution_average_and_end_unemployment_are_not_vintages_of_each_other():
    out = compare_forecasts([
        unemployment("alpha", "Annual average unemployment rate", "2027", value=5.2, published_on="2026-08-01", summary_id=1),
        unemployment("alpha", "End of year unemployment rate", "2027", value=5.6, published_on="2026-08-02", summary_id=2),
    ])  # fmt: skip
    assert len(out.groups) == 2
    assert all(g.rows[0].earlier_vintages == [] for g in out.groups)


def test_institutions_reporting_the_same_unemployment_measure_are_compared():
    out = compare_forecasts([
        unemployment("alpha", "Annual average unemployment rate", "2027", value=5.2),
        unemployment("beta", "Unemployment rate, annual average", "2027", value=5.4),
        unemployment("gamma", "Unemployment rate", "December 2026 quarter", value=5.5),
        unemployment("delta", "Unemployment rate", "December 2026 quarter", value=5.3),
    ])  # fmt: skip
    assert len(out.groups) == 2 and all(g.comparable for g in out.groups)
    assert {g.basis for g in out.groups} == {"rate_average", "rate"}


def test_unemployment_with_unstated_timing_over_a_span_carries_a_caution_and_is_labelled_so():
    out = compare_forecasts(
        [unemployment("alpha", horizon="2027"), unemployment("beta", horizon="2027")]
    )
    (g,) = out.groups
    assert g.basis == "rate_timing_unstated" and "not stated" in g.basis_label.lower()
    assert "not stated" in g.note.lower()
    quarter = compare_forecasts([unemployment("alpha"), unemployment("beta")]).groups[0]
    assert (
        quarter.basis == "rate"
        and "not stated" not in quarter.note.lower() + quarter.basis_label.lower()
    )


def test_grouping_is_deterministic_regardless_of_input_order():
    claims = [
        gdp("alpha", "Real GDP, annual average growth"), gdp("beta", "Nominal GDP, annual average growth"),
        unemployment("alpha", "Annual average unemployment rate", "2027"),
        unemployment("beta", "End of year unemployment rate", "2027"),
    ]  # fmt: skip
    assert compare_forecasts(list(reversed(claims))) == compare_forecasts(claims)
