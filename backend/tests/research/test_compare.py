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
            "share_of_gdp:net-core-crown-debt",
        ),
        (
            "house_prices",
            "House prices, annual % change",
            "December 2026 quarter",
            "percent",
            "annual_change:house-prices",
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
            "real_annual_change:wage",
        ),
        (
            "wages",
            "Nominal wage growth, annual % change",
            "year to March 2027",
            "percent",
            "nominal_annual_change:wage",
        ),
        (
            "wages",
            "Wage growth, annual % change",
            "year to March 2027",
            "percent",
            "annual_change:wage",
        ),
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


# --- PR #13 review round 2: the measure itself is part of the basis for indicators without one defined series ---


def debt(institution="alpha", label="Net core Crown debt", **kw):
    data = {
        "indicator": "government_debt",
        "unit": "percent_of_gdp",
        "horizon": "year to June 2027",
    }
    return claim(institution=institution, indicator_label=label, **{**data, **kw})


def test_net_and_gross_debt_as_a_share_of_gdp_are_separate_groups():
    out = compare_forecasts(
        [debt("alpha", "Net core Crown debt"), debt("beta", "Gross Crown debt")]
    )
    assert out.excluded == [] and len(out.groups) == 2
    assert all(not g.comparable and len(g.rows) == 1 for g in out.groups)
    assert len({g.key for g in out.groups}) == 2


def test_same_institution_net_and_gross_debt_are_not_vintages_of_each_other():
    out = compare_forecasts([
        debt("alpha", "Net core Crown debt", value=43.5, published_on="2026-08-01", summary_id=1),
        debt("alpha", "Gross Crown debt", value=55.0, published_on="2026-08-02", summary_id=2),
    ])  # fmt: skip
    assert len(out.groups) == 2 and all(g.rows[0].earlier_vintages == [] for g in out.groups)


def test_the_same_debt_measure_is_compared_whatever_the_unit_wording():
    out = compare_forecasts([
        debt("alpha", "Net core Crown debt"),
        debt("beta", "Net core Crown debt (% of GDP)"),
        debt("gamma", "net core Crown debt, per cent of GDP"),
    ])  # fmt: skip
    (g,) = out.groups
    assert g.comparable and len(g.rows) == 3
    assert g.basis.startswith("share_of_gdp") and "Net core Crown debt" in g.basis_label


def test_debt_vintages_of_one_measure_still_deduplicate():
    out = compare_forecasts([
        debt("alpha", value=43.0, published_on="2026-05-01", summary_id=1),
        debt("alpha", value=43.5, published_on="2026-08-01", summary_id=2),
    ])  # fmt: skip
    (g,) = out.groups
    assert g.rows[0].forecast.value == 43.5 and [e.value for e in g.rows[0].earlier_vintages] == [
        43.0
    ]


def test_a_share_of_gdp_label_that_names_no_measure_is_excluded():
    out = compare_forecasts([debt("alpha", "% of GDP")])
    assert out.groups == [] and len(out.excluded) == 1


@pytest.mark.parametrize(
    ("indicator", "a", "b"),
    [
        ("house_prices", "House prices, annual % change", "Auckland house prices, annual % change"),
        ("wages", "Average hourly earnings, annual % change", "Labour cost index, annual % change"),
        ("fiscal_balance", "OBEGALx", "Core Crown operating balance"),
    ],
)
def test_different_measures_under_one_indicator_are_never_grouped(indicator, a, b):
    unit = "percent_of_gdp" if indicator == "fiscal_balance" else "percent"
    horizon = "year to June 2027"
    out = compare_forecasts([
        claim(institution="alpha", indicator=indicator, indicator_label=a, horizon=horizon, unit=unit),
        claim(institution="beta", indicator=indicator, indicator_label=b, horizon=horizon, unit=unit),
    ])  # fmt: skip
    assert len(out.groups) == 2 and all(not g.comparable for g in out.groups)


def test_one_measure_under_another_indicator_still_compares_across_institutions():
    kw = {"indicator": "house_prices", "horizon": "December 2026 quarter", "unit": "percent"}
    out = compare_forecasts([
        claim(institution="alpha", indicator_label="House prices, annual % change", **kw),
        claim(institution="beta", indicator_label="House prices (annual % change)", **kw),
    ])  # fmt: skip
    (g,) = out.groups
    assert g.comparable and g.basis == "annual_change:house-prices"


def test_measure_wording_in_the_basis_label_is_plain_words_only():
    out = compare_forecasts([debt("alpha", "Net <b>core</b> Crown debt & more")])
    (g,) = out.groups
    assert "<" not in g.basis_label and "&" not in g.basis_label and "<" not in g.key


# --- PR #13 review round 2b: a debt or balance label must say which statistic it is ---


@pytest.mark.parametrize(
    "label",
    [
        "Government debt",
        "Crown debt",
        "Core Crown debt",
        "Total Crown debt",
        "Public debt",
        "Net and gross Crown debt",
        "Gross, net core Crown debt",
    ],
)
def test_debt_that_does_not_say_net_or_gross_exactly_once_is_excluded(label):
    out = compare_forecasts([debt("alpha", label)])
    assert out.groups == [] and len(out.excluded) == 1
    assert "not stated clearly enough" in out.excluded[0].reason


def test_core_crown_and_total_crown_net_debt_are_never_conflated():
    out = compare_forecasts(
        [debt("alpha", "Net core Crown debt"), debt("beta", "Net total Crown debt")]
    )
    assert len(out.groups) == 2 and all(not g.comparable for g in out.groups)


def test_net_debt_without_a_stated_scope_is_not_grouped_with_a_stated_scope():
    out = compare_forecasts([debt("alpha", "Net debt"), debt("beta", "Net core Crown debt")])
    assert len(out.groups) == 2 and all(not g.comparable for g in out.groups)


def test_identical_net_debt_measures_from_two_institutions_compare():
    out = compare_forecasts(
        [debt("alpha", "Net core Crown debt"), debt("beta", "Net core Crown debt, % of GDP")]
    )
    (g,) = out.groups
    assert g.comparable and len(g.rows) == 2 and "Net core Crown debt" in g.basis_label


@pytest.mark.parametrize(
    "label", ["Fiscal balance", "Budget balance", "Balance", "Deficit", "Surplus (% of GDP)"]
)
def test_a_bare_fiscal_balance_is_excluded(label):
    out = compare_forecasts([debt("alpha", label, indicator="fiscal_balance")])
    assert out.groups == [] and len(out.excluded) == 1


def test_operating_balance_obegal_and_cash_balance_are_separate_groups():
    labels = ("Operating balance", "OBEGAL", "Cash balance")
    out = compare_forecasts(
        [debt(f"i{n}", label, indicator="fiscal_balance") for n, label in enumerate(labels)]
    )
    assert len(out.groups) == 3 and all(not g.comparable for g in out.groups)


@pytest.mark.parametrize(
    "label", ["Interest rates", "Mortgage rate", "2-year swap rate", "Floating mortgage rate"]
)
def test_interest_rate_levels_without_a_stated_change_basis_are_excluded(label):
    out = compare_forecasts(
        [claim(indicator="interest_rates", indicator_label=label, unit="percent")]
    )
    assert out.groups == [] and len(out.excluded) == 1


def test_a_tenor_is_part_of_the_measure():
    kw = {"indicator": "interest_rates", "unit": "percent"}
    out = compare_forecasts([
        claim(institution="alpha", indicator_label="2 year swap rate, annual % change", **kw),
        claim(institution="beta", indicator_label="2 month swap rate, annual % change", **kw),
        claim(institution="gamma", indicator_label="12 month swap rate, annual % change", **kw),
        claim(institution="delta", indicator_label="1 year swap rate, annual % change", **kw),
    ])  # fmt: skip
    assert len(out.groups) == 4 and all(not g.comparable for g in out.groups)


def test_the_distinction_survives_serialisation_and_is_deterministic():
    claims = [
        debt("alpha", "Net core Crown debt"),
        debt("beta", "Gross Crown debt"),
        debt("gamma", "Gross Crown debt"),
    ]
    body = compare_forecasts(claims).model_dump(mode="json")
    assert compare_forecasts(list(reversed(claims))).model_dump(mode="json") == body
    by_basis = {g["basis"]: g for g in body["groups"]}
    assert set(by_basis) == {"share_of_gdp:net-core-crown-debt", "share_of_gdp:gross-crown-debt"}
    assert by_basis["share_of_gdp:gross-crown-debt"]["key"] == (
        "government_debt|percent_of_gdp|share_of_gdp:gross-crown-debt|year_to:2027-06|central"
    )
    assert (
        by_basis["share_of_gdp:gross-crown-debt"]["basis_label"]
        == "Share of GDP (Gross Crown debt)"
    )
    assert by_basis["share_of_gdp:gross-crown-debt"]["comparable"] is True
    assert by_basis["share_of_gdp:net-core-crown-debt"]["comparable"] is False


# --- PR #13 review round 3: the population an unemployment rate covers, and peaks versus ordinary forecasts ---


def cpi(institution="alpha", label="Annual CPI inflation", horizon="year to June 2027", **kw):
    return claim(institution=institution, indicator_label=label, horizon=horizon, **kw)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        # Headline wording, however it is dressed, is one population.
        ("Annual average unemployment rate", "rate_average"),
        ("Annual average unemployment rate, seasonally adjusted", "rate_average"),
        ("Headline unemployment rate, annual average", "rate_average"),
        ("Annual average unemployment rate for New Zealand", "rate_average"),
        # A stated subgroup is part of the basis, in any word order.
        ("Annual average youth unemployment rate", "rate_average:youth"),
        ("Annual average unemployment rate for youth", "rate_average:youth"),
        ("Annual average Māori unemployment rate", "rate_average:maori"),
        ("Annual average female unemployment rate", "rate_average:female"),
        ("Annual average Auckland unemployment rate", "rate_average:auckland"),
        ("Annual average Māori women unemployment rate", "rate_average:maori-women"),
        ("Annual average women Māori unemployment rate", "rate_average:maori-women"),
        ("End of year youth unemployment rate", "rate_end:youth"),
        # The population wording is never assumed away, and never guessed at.
        ("Annual average unemployment rate excluding youth", None),
        ("Annual average non-youth unemployment rate", None),
        ("Annual average youth and female unemployment rate", None),
        ("Annual average youth/female unemployment rate", None),
        ("Annual average other unemployment rate", None),
    ],
)
def test_unemployment_population_is_part_of_the_basis(label, expected):
    assert basis_of("unemployment", label, "2027", "percent") == expected


def test_headline_and_youth_unemployment_are_separate_groups_across_institutions():
    out = compare_forecasts([
        unemployment("alpha", "Annual average unemployment rate", "2027", value=5.2),
        unemployment("beta", "Annual average youth unemployment rate", "2027", value=11.0),
    ])  # fmt: skip
    assert out.excluded == [] and len(out.groups) == 2
    assert all(not g.comparable and len(g.rows) == 1 for g in out.groups)
    assert {g.basis for g in out.groups} == {"rate_average", "rate_average:youth"}
    assert len({g.key for g in out.groups}) == 2


def test_one_institution_headline_and_youth_unemployment_are_not_vintages_of_each_other():
    out = compare_forecasts([
        unemployment("alpha", "Annual average unemployment rate", "2027", value=5.2, published_on="2026-08-01", summary_id=1),
        unemployment("alpha", "Annual average youth unemployment rate", "2027", value=11.0, published_on="2026-08-02", summary_id=2),
    ])  # fmt: skip
    assert len(out.groups) == 2 and all(g.rows[0].earlier_vintages == [] for g in out.groups)


def test_the_same_unemployment_subgroup_is_compared_across_institutions_whatever_the_wording():
    out = compare_forecasts([
        unemployment("alpha", "Annual average youth unemployment rate", "2027", value=11.0),
        unemployment("beta", "Youth unemployment rate, annual average", "2027", value=11.4),
        unemployment("gamma", "Annual average unemployment rate for youth", "2027", value=10.8),
    ])  # fmt: skip
    (g,) = out.groups
    assert g.comparable and len(g.rows) == 3 and g.basis == "rate_average:youth"
    assert "youth" in g.basis_label.lower() and "Average rate" in g.basis_label


def test_unemployment_subgroup_vintages_still_deduplicate():
    out = compare_forecasts([
        unemployment("alpha", "Youth unemployment rate, annual average", "2027", value=10.5, published_on="2026-05-01", summary_id=1),
        unemployment("alpha", "Annual average youth unemployment rate", "2027", value=11.0, published_on="2026-08-01", summary_id=2),
    ])  # fmt: skip
    (g,) = out.groups
    assert g.rows[0].forecast.value == 11.0 and [e.value for e in g.rows[0].earlier_vintages] == [
        10.5
    ]


@pytest.mark.parametrize(
    "a, b",
    [
        ("Annual average youth unemployment rate", "Annual average female unemployment rate"),
        (
            "Annual average Auckland unemployment rate",
            "Annual average Canterbury unemployment rate",
        ),
        ("Annual average male unemployment rate", "Annual average female unemployment rate"),
        ("Annual average Māori unemployment rate", "Annual average Pacific unemployment rate"),
    ],
)
def test_different_unemployment_subgroups_are_never_grouped(a, b):
    out = compare_forecasts([unemployment("alpha", a, "2027"), unemployment("beta", b, "2027")])
    assert len(out.groups) == 2 and all(not g.comparable for g in out.groups)


def test_ambiguous_unemployment_population_is_excluded_with_a_reason():
    out = compare_forecasts(
        [unemployment("alpha", "Annual average unemployment rate excluding youth", "2027")]
    )
    assert out.groups == [] and len(out.excluded) == 1
    assert "population" in out.excluded[0].reason.lower()


def test_unemployment_subgroup_survives_serialisation_and_ordering():
    claims = [
        unemployment("alpha", "Annual average unemployment rate", "2027"),
        unemployment("beta", "Annual average youth unemployment rate", "2027"),
        unemployment("gamma", "Youth unemployment rate, annual average", "2027"),
    ]
    body = compare_forecasts(claims).model_dump(mode="json")
    assert compare_forecasts(list(reversed(claims))).model_dump(mode="json") == body
    by_basis = {g["basis"]: g for g in body["groups"]}
    assert set(by_basis) == {"rate_average", "rate_average:youth"}
    assert (
        by_basis["rate_average:youth"]["key"]
        == "unemployment|percent|rate_average:youth|calendar:2027|central"
    )
    assert by_basis["rate_average:youth"]["basis_label"] == "Average rate over the period (youth)"
    assert by_basis["rate_average"]["basis_label"] == "Average rate over the period"
    assert [g["basis"] for g in body["groups"]] == ["rate_average", "rate_average:youth"]


# --- peaks, troughs and other extremes are not the ordinary forecast for the period ---


@pytest.mark.parametrize(
    "label",
    [
        "Peak annual CPI inflation",
        "Annual CPI inflation peak",
        "Annual CPI inflation, trough",
        "Maximum annual CPI inflation",
        "Minimum annual CPI inflation",
        "Highest annual CPI inflation",
        "Lowest annual CPI inflation",
        "Annual CPI inflation at its peak",
    ],
)
def test_extreme_cpi_forecasts_have_no_ordinary_basis(label):
    assert basis_of("cpi_inflation", label, "year to June 2027", "percent") is None


def test_a_peak_cpi_forecast_is_excluded_with_a_public_reason_not_grouped():
    out = compare_forecasts([cpi("alpha", "Peak annual CPI inflation")])
    assert out.groups == [] and len(out.excluded) == 1
    reason = out.excluded[0].reason.lower()
    assert "peak" in reason and "trough" in reason and "not compared" in reason


def test_peak_and_ordinary_cpi_with_the_same_horizon_never_share_a_group():
    out = compare_forecasts(
        [cpi("alpha", "Peak annual CPI inflation", value=3.1), cpi("beta", value=2.1)]
    )
    assert len(out.groups) == 1 and len(out.excluded) == 1
    assert [r.forecast.institution.key for r in out.groups[0].rows] == ["beta"]
    assert out.groups[0].comparable is False


def test_same_institution_peak_and_ordinary_cpi_are_not_vintages_of_each_other():
    out = compare_forecasts([
        cpi("alpha", value=2.1, published_on="2026-08-01", summary_id=1),
        cpi("alpha", "Peak annual CPI inflation", value=3.1, published_on="2026-08-02", summary_id=2),
    ])  # fmt: skip
    (g,) = out.groups
    assert g.rows[0].earlier_vintages == [] and g.rows[0].forecast.value == 2.1
    assert [e.forecast.value for e in out.excluded] == [3.1]


def test_ordinary_cpi_still_compares_across_institutions_and_keeps_core_separate():
    out = compare_forecasts([
        cpi("alpha", value=2.1), cpi("beta", "CPI inflation, annual", value=2.3),
        cpi("gamma", "Core annual CPI inflation", value=2.6),
    ])  # fmt: skip
    (g,) = out.groups
    assert g.comparable and len(g.rows) == 2 and len(out.excluded) == 1


@pytest.mark.parametrize(
    ("indicator", "label", "unit"),
    [
        ("gdp", "Peak real GDP growth, annual average", "percent"),
        ("ocr", "Peak OCR", "percent"),
        ("unemployment", "Peak annual average unemployment rate", "percent"),
        ("government_debt", "Peak net core Crown debt", "percent_of_gdp"),
        ("fiscal_balance", "Lowest OBEGAL", "percent_of_gdp"),
    ],
)
def test_extremes_are_excluded_for_every_indicator(indicator, label, unit):
    assert basis_of(indicator, label, "year to June 2027", unit) is None
    out = compare_forecasts([claim(indicator=indicator, indicator_label=label, unit=unit)])
    assert out.groups == [] and "peak, trough" in out.excluded[0].reason.lower()


# --- root cause: a qualifier the rules do not know must never be silently ignored by a single-series indicator ---


@pytest.mark.parametrize(
    ("indicator", "ordinary", "qualified", "unit"),
    [
        ("cpi_inflation", "Annual CPI inflation", "Annual CPI inflation, Auckland", "percent"),
        (
            "cpi_inflation",
            "Annual CPI inflation",
            "Annual CPI inflation (downside scenario)",
            "percent",
        ),
        ("gdp", "Real GDP growth (y/y)", "Real GDP growth (y/y), Canterbury", "percent"),
        ("ocr", "OCR", "Wholesale OCR", "percent"),
    ],
)
def test_unrecognised_qualifiers_on_a_single_series_indicator_do_not_merge_with_the_plain_measure(
    indicator, ordinary, qualified, unit
):
    horizon = "year to March 2027" if indicator != "ocr" else "December 2026"
    a, b = (claim(institution=n, indicator=indicator, indicator_label=lbl, horizon=horizon, unit=unit)
            for n, lbl in (("alpha", ordinary), ("beta", qualified)))  # fmt: skip
    out = compare_forecasts([a, b])
    assert len(out.groups) == 2 and all(not g.comparable for g in out.groups)


@pytest.mark.parametrize(
    ("indicator", "plain", "label", "horizon", "unit"),
    [
        ("cpi_inflation", "Annual CPI inflation", "Headline CPI inflation, annual", "year to June 2027", "percent"),
        ("cpi_inflation", "Annual CPI inflation", "CPI inflation (annual % change, y/y)", "year to June 2027", "percent"),
        ("cpi_inflation", "Annual CPI inflation", "Annual CPI inflation, per cent", "year to June 2027", "percent"),
        ("gdp", "Real GDP growth (y/y)", "Real GDP growth, y/y (%)", "year to March 2027", "percent"),
        ("gdp", "Real GDP, annual average growth", "Real GDP, annual average growth, %", "year to March 2027", "percent"),
        ("gdp", "Real GDP, annual average growth", "Real GDP growth, annual average (March year)", "year to March 2027", "percent"),
        ("ocr", "OCR at the end of the year", "OCR (end of period)", "2026", "percent"),
        ("ocr", "OCR", "Official Cash Rate", "December 2026", "percent"),
    ],
)  # fmt: skip
def test_ordinary_wording_is_not_split_from_the_plain_measure(
    indicator, plain, label, horizon, unit
):
    basis = basis_of(indicator, label, horizon, unit)
    assert basis is not None and ":" not in basis, basis
    assert basis == basis_of(indicator, plain, horizon, unit)


# --- Adversarial matrix: every pair is either one measurement (must group) or two (must never group) ---

Y2027, FY, QTR, DEC = "2027", "year to March 2027", "December 2026 quarter", "December 2026"
PAIRS = [
    # (indicator, unit, horizon, label a, label b, same measurement?)
    # GDP
    ("gdp", "percent", FY, "Real GDP, annual average growth", "Real GDP growth, annual average", True),
    ("gdp", "percent", FY, "Real GDP growth (y/y)", "Real GDP growth, year-on-year", True),
    ("gdp", "percent", FY, "Real GDP, annual average growth", "Nominal GDP, annual average growth", False),
    ("gdp", "percent", FY, "Real GDP, annual average growth", "Real GDP growth (y/y)", False),
    ("gdp", "percent", FY, "Real GDP growth (y/y)", "Real GDP growth (y/y), Canterbury", False),
    ("gdp", "percent", QTR, "Real quarterly GDP growth", "Real GDP growth (y/y)", False),
    # CPI
    ("cpi_inflation", "percent", "year to June 2027", "Annual CPI inflation", "CPI inflation, annual", True),
    ("cpi_inflation", "percent", "year to June 2027", "Annual CPI inflation", "Headline CPI inflation (y/y)", True),
    ("cpi_inflation", "percent", "year to June 2027", "Annual CPI inflation", "CPI, annual average", False),
    ("cpi_inflation", "percent", "year to June 2027", "Annual CPI inflation", "Annual CPI inflation, Auckland", False),
    ("cpi_inflation", "percent", "June 2027 quarter", "Quarterly CPI inflation", "Annual CPI inflation", False),
    ("cpi_inflation", "percent", "year to June 2027", "Annual CPI inflation", "Annual CPI inflation, all groups", True),
    ("cpi_inflation", "percent", "year to June 2027", "Annual CPI inflation", "Annual percentage change in CPI", True),
    ("unemployment", "percent", QTR, "Unemployment rate", "Unemployment rate (HLFS)", True),
    # Unemployment
    ("unemployment", "percent", Y2027, "Annual average unemployment rate", "Unemployment rate, annual average", True),
    ("unemployment", "percent", Y2027, "Annual average unemployment rate", "Annual average unemployment rate, seasonally adjusted", True),
    ("unemployment", "percent", Y2027, "Annual average youth unemployment rate", "Youth unemployment rate, annual average", True),
    ("unemployment", "percent", Y2027, "Annual average unemployment rate", "Annual average youth unemployment rate", False),
    ("unemployment", "percent", Y2027, "Annual average unemployment rate", "End of year unemployment rate", False),
    ("unemployment", "percent", Y2027, "Annual average Auckland unemployment rate", "Annual average Wellington unemployment rate", False),
    ("unemployment", "percent", QTR, "Unemployment rate", "Female unemployment rate", False),
    # OCR
    ("ocr", "percent", DEC, "OCR", "Official Cash Rate", True),
    ("ocr", "percent", DEC, "OCR", "OCR at the end of the year", False),
    ("ocr", "percent", DEC, "OCR, quarterly average", "OCR at the end of the year", False),
    # Government debt and fiscal balance
    ("government_debt", "percent_of_gdp", "year to June 2027", "Net core Crown debt", "Net core Crown debt (% of GDP)", True),
    ("government_debt", "percent_of_gdp", "year to June 2027", "Net core Crown debt", "Gross Crown debt", False),
    ("government_debt", "percent_of_gdp", "year to June 2027", "Net core Crown debt", "Net total Crown debt", False),
    ("fiscal_balance", "percent_of_gdp", "year to June 2027", "OBEGAL", "OBEGAL (% of GDP)", True),
    ("fiscal_balance", "percent_of_gdp", "year to June 2027", "OBEGAL", "Core Crown operating balance", False),
]  # fmt: skip


def _pair(
    indicator,
    unit,
    horizon,
    a,
    b,
    *,
    inst=("alpha", "beta"),
    ids=(1, 2),
    dates=("2026-08-01", "2026-08-02"),
):
    return [
        claim(institution=inst[i], indicator=indicator, unit=unit, horizon=horizon, indicator_label=lbl,
              value=1.0 + i, summary_id=ids[i], published_on=dates[i])
        for i, lbl in enumerate((a, b))
    ]  # fmt: skip


@pytest.mark.parametrize(("indicator", "unit", "horizon", "a", "b", "same"), PAIRS)
def test_matrix_false_matches_and_false_splits_across_institutions(
    indicator, unit, horizon, a, b, same
):
    claims = _pair(indicator, unit, horizon, a, b)
    out = compare_forecasts(claims)
    assert out.excluded == [], (a, b)
    if same:
        (g,) = out.groups
        assert g.comparable and len(g.rows) == 2, (a, b, g.basis)
    else:
        assert len(out.groups) == 2 and all(not g.comparable for g in out.groups), (a, b)
        assert len({g.key for g in out.groups}) == 2 and len({g.basis for g in out.groups}) == 2
    # Stable group keys, ordering and serialisation whatever the input order.
    body = out.model_dump(mode="json")
    assert compare_forecasts(list(reversed(claims))).model_dump(mode="json") == body


@pytest.mark.parametrize(("indicator", "unit", "horizon", "a", "b", "same"), PAIRS)
def test_matrix_one_institution_only_hides_a_genuine_earlier_vintage(
    indicator, unit, horizon, a, b, same
):
    out = compare_forecasts(_pair(indicator, unit, horizon, a, b, inst=("alpha", "alpha")))
    if same:
        (g,) = out.groups
        assert len(g.rows) == 1 and len(g.rows[0].earlier_vintages) == 1, (a, b)
    else:
        assert len(out.groups) == 2, (a, b)
        assert all(r.earlier_vintages == [] for g in out.groups for r in g.rows)


@pytest.mark.parametrize(
    ("indicator", "unit", "label"),
    [
        ("cpi_inflation", "percent", "Peak annual CPI inflation"),
        ("gdp", "percent", "Minimum real GDP growth, annual average"),
        ("unemployment", "percent", "Peak annual average unemployment rate"),
        ("ocr", "percent", "Peak OCR"),
        ("government_debt", "percent_of_gdp", "Peak net core Crown debt"),
        ("fiscal_balance", "percent_of_gdp", "Lowest OBEGAL"),
    ],
)
def test_matrix_an_extreme_never_joins_or_hides_an_ordinary_forecast(indicator, unit, label):
    plain = {"cpi_inflation": "Annual CPI inflation", "gdp": "Real GDP, annual average growth",
             "unemployment": "Annual average unemployment rate", "ocr": "OCR",
             "government_debt": "Net core Crown debt", "fiscal_balance": "OBEGAL"}[indicator]  # fmt: skip
    horizon = "year to March 2027" if indicator in ("gdp", "unemployment") else "year to June 2027"
    if indicator == "ocr":
        horizon = "December 2026"
    out = compare_forecasts(_pair(indicator, unit, horizon, plain, label, inst=("alpha", "alpha")))
    (g,) = out.groups
    assert g.rows[0].earlier_vintages == [] and len(out.excluded) == 1
    assert "peak, trough" in out.excluded[0].reason.lower()
