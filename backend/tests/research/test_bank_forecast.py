"""Phase 4AE: the normalized bank forecast keeps raw values and derives adjustment and geography deterministically
(SYNTHETIC FIXTURE)."""

import pytest
from pydantic import ValidationError

from nzstats.research.api_models import EvidenceOut, ForecastOut, InstitutionOut
from nzstats.research.bank_forecast import (
    NormalizedForecast,
    derive_adjustment,
    derive_geography,
)


def forecast(value: float | None = 2.0, **overrides) -> ForecastOut:
    raw = {
        "summary_id": 1,
        "institution": InstitutionOut(key="bank_a", name="Example Bank A", kind="bank"),
        "document_title": "SYNTHETIC outlook",
        "published_on": "2026-11-01",
        "indicator": "cpi_inflation",
        "indicator_label": "CPI inflation",
        "horizon": "year to March 2027",
        "value": value,
        "unit": "percent",
        "direction": "down",
        "scenario": None,
        "qualification": None,
        "evidence": [
            EvidenceOut(section_ordinal=0, page=1, quote="SYNTHETIC quote about inflation")
        ],
    }
    raw.update(overrides)
    return ForecastOut(**raw)


def normalized(f: ForecastOut, **overrides) -> NormalizedForecast:
    raw = {
        "forecast": f,
        "institution_key": "bank_a",
        "document_version_id": 7,
        "claim_path": "forecasts[0]",
        "report_kind": "outlook",
        "forecast_author": "Example Bank A",
        "geography": "New Zealand",
        "measure": f.indicator_label,
        "adjustment": "not_stated",
        "verifier_version": "verify-5",
        "raw_value": f.value,
    }
    raw.update(overrides)
    return NormalizedForecast(**raw)


@pytest.mark.parametrize(
    ("label", "quote", "expected"),
    [
        ("GDP growth, seasonally adjusted", "growth of 0.4%", "seasonally_adjusted"),
        ("GDP growth", "a seasonally adjusted 0.4% rise", "seasonally_adjusted"),
        ("Unemployment rate (s.a.)", "unemployment to 5.0%", "seasonally_adjusted"),
        ("CPI inflation, unadjusted", "inflation of 2.0%", "unadjusted"),
        ("CPI inflation", "non-seasonally adjusted 2.0%", "unadjusted"),
        ("GDP growth, seasonally adjusted", "an unadjusted 0.4% rise", "not_stated"),
        ("GDP growth", "seasonally adjusted and unadjusted both", "not_stated"),
        ("GDP growth", "growth of 0.4%", "not_stated"),
        ("Real GDP growth", "", "not_stated"),
    ],
)
def test_adjustment_is_derived_only_from_stated_phrases(label, quote, expected):
    assert derive_adjustment(label, quote) == expected


def test_zero_and_negative_values_survive():
    zero = normalized(forecast(0.0))
    cut = normalized(forecast(-0.25, indicator="ocr", indicator_label="OCR"))
    assert zero.raw_value == 0.0 and zero.raw_value is not None
    assert cut.raw_value == -0.25 and cut.forecast.value == -0.25


def test_geography_defaults_to_new_zealand():
    assert derive_geography("cpi_inflation", "CPI inflation", "year to March 2027", "percent") == (
        "New Zealand"
    )
    assert derive_geography("ocr", "OCR", "March 2027 quarter", "percent") == "New Zealand"


def test_geography_shows_a_part_of_series_title_cased():
    assert (
        derive_geography(
            "unemployment", "Auckland unemployment rate", "March 2027 quarter", "percent"
        )
        == "Auckland"
    )
    assert (
        derive_geography(
            "cpi_inflation", "CPI inflation, Wellington", "year to March 2027", "percent"
        )
        == "Wellington"
    )


def test_extra_fields_are_rejected_and_model_is_frozen():
    f = forecast()
    with pytest.raises(ValidationError):
        normalized(f, secret="x")
    n = normalized(f)
    with pytest.raises(ValidationError):
        n.raw_value = 1.0  # type: ignore[misc]


def test_no_conversion_is_recorded_and_extraction_method_is_fixed():
    n = normalized(forecast())
    assert n.conversions == ()
    assert n.extraction_method == "llm_verified"
    with pytest.raises(ValidationError):
        normalized(forecast(), extraction_method="table")
