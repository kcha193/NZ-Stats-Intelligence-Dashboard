"""Claim-local grounding matrix (Phase 4Q review round). SYNTHETIC FIXTURE: invented sentences and figures.

One table for the review findings that kept coming back one example at a time. Each valid claim is paired with a near-twin
that must still be rejected, so a fix cannot pass by loosening the check. A claim is judged on the words around its own
figure: the horizon it states, and the forecaster its own clause credits.
"""

import pytest

from nzstats.research.contract import ReportedFact, SectionText

from .verify_support import check, codes, forecast, ref

HORIZON_CODES = {"horizon_not_supported", "period_not_supported"}
ISSUER_CODES = {"issuer_mismatch", "issuer_not_in_evidence"}


def forecast_codes(
    sentence, value, *, horizon="2029", issuer="The Treasury", role="author", indicator="gdp"
):
    quote = sentence.rstrip(".")
    claim = forecast(
        0, quote, 1, value=value, unit="percent", horizon=horizon, issuer=issuer, issuer_role=role,
        indicator=indicator,
    )  # fmt: skip
    report = check(
        {0: SectionText(sentence, 1, 1)},
        outlook_ref=ref(0, quote),
        institution="treasury",
        forecasts=[claim],
    )
    return codes(report)


def fact_codes(sentence, value, period):
    quote = sentence.rstrip(".")
    fact = ReportedFact(text="Synthetic figure.", source="Synthetic Statistics", value=value, unit="percent",
                        period=period, evidence=[ref(0, quote)])  # fmt: skip
    return codes(check({0: SectionText(sentence)}, outlook_ref=ref(0, quote), facts=[fact]))


# --- the horizon a figure states ------------------------------------------------------------------------------
HORIZON_VALID = [
    ("We expect inflation to remain at 2% from 2027 in our central forecast.", 2, "2027"),
    ("We expect output to be 3% above trend in 2029.", 3, "2029"),
    ("We expect output to be 3% below trend by 2029.", 3, "2029"),
    ("We expect inflation of 3% or below by 2029.", 3, "2029"),
    ("We expect inflation of 3% or above in 2029.", 3, "2029"),
    (
        "We expect output to be 3% above trend over the 12 months to June 2029.",
        3,
        "12 months to June 2029",
    ),
    ("We expect output to be 3% above trend over the 12 months to June 2029.", 3, "June 2029"),
    ("We expect output to be 3% above trend in the 4 quarters to June 2029.", 3, "June 2029"),
]


@pytest.mark.parametrize(("sentence", "value", "horizon"), HORIZON_VALID)
def test_a_stated_horizon_survives_starts_bounds_and_durations(sentence, value, horizon):
    assert not forecast_codes(sentence, value, horizon=horizon) & HORIZON_CODES


HORIZON_INVALID = [
    ("We expect inflation to remain at 2% from 2027 in our central forecast.", 2, "2028"),
    ("We expect output to be 3% above trend in 2029.", 3, "2030"),
    ("We expect inflation of 3% or below by 2029.", 3, "2030"),
    (
        "We expect output to be 3% above trend over the 12 months to June 2029.",
        3,
        "12 months to June 2030",
    ),
    ("We expect output to be 3% above trend over the 12 months to June 2029.", 3, "June 2030"),
    ("We expect output to be 3% above trend over the 12 months to June 2029.", 3, "March 2029"),
]


@pytest.mark.parametrize(("sentence", "value", "horizon"), HORIZON_INVALID)
def test_an_unstated_horizon_is_still_rejected(sentence, value, horizon):
    assert forecast_codes(sentence, value, horizon=horizon) & HORIZON_CODES


def test_a_duration_is_not_a_second_figure_but_a_second_figure_still_is():
    sentence = "Output was 3% above trend over the 12 months to June 2029."
    assert "period_not_supported" not in fact_codes(sentence, 3, "June 2029")
    assert "period_not_supported" in fact_codes(sentence, 3, "June 2028")
    # A real second figure keeps the gap exemption off: "3% above 2%" compares, and 2029 is not the 3%'s period.
    assert "period_not_supported" in fact_codes("Freight rose 3% above 2% in 2029.", 3, "2029")


def test_a_sentence_opening_year_still_reaches_a_coordinated_fact():
    sentence = "In 2030, output rose 2% and inflation rose 3%, up from 1% in June."
    assert "period_not_supported" not in fact_codes(sentence, 3, "2030")
    assert "period_not_supported" in fact_codes(sentence, 3, "June")


# --- who the figure's own clause credits ----------------------------------------------------------------------
# (sentence, value, issuer, role): a correctly labelled claim.
ISSUER_VALID = [
    ("The IMF expects growth of 2%, less than we forecast at 3% in 2029.", 3, "The Treasury", "author"),
    ("Markets forecast growth of 3% in 2029.", 3, "Markets", "third_party"),
    ("Markets anticipate growth of 3% in 2029.", 3, "Markets", "third_party"),
    ("The market forecasts growth of 3% in 2029.", 3, "The market", "third_party"),
    ("With the RBNZ expected by the IMF to cut the OCR to 3% in 2029, financing costs will ease.", 3, "IMF", "third_party"),
    ("The Treasury expected growth of 3% in 2029, while the RBNZ expected inflation of 2% in 2029.", 3, "The Treasury", "author"),
    ("The Treasury expected growth of 3% in 2029, while the RBNZ expected inflation of 2% in 2029.", 2, "RBNZ", "third_party"),
    ("We expect growth of 3% in 2029, which exceeds what the IMF forecasts.", 3, "The Treasury", "author"),
    ("The RBNZ expected growth of 2% but we forecast 3% in 2029.", 3, "The Treasury", "author"),
    ("We expect growth of 3% in 2029, while inflation will be 2%, which the IMF expects.", 3, "The Treasury", "author"),
    ("We expect growth of 3% in 2029, while inflation will be 2%, which the IMF expects.", 2, "IMF", "third_party"),
    ("The RBNZ expected growth of 2% but the IMF forecasts 3% in 2029.", 3, "IMF", "third_party"),
    ("Our growth forecast of 3% in 2029 compares with market forecasts of 2%.", 3, "The Treasury", "author"),
]  # fmt: skip


@pytest.mark.parametrize(("sentence", "value", "issuer", "role"), ISSUER_VALID)
def test_a_correctly_labelled_forecast_is_accepted(sentence, value, issuer, role):
    assert not forecast_codes(sentence, value, issuer=issuer, role=role) & ISSUER_CODES


ISSUER_INVALID = [
    ("Markets forecast growth of 3% in 2029.", 3, "The Treasury", "author"),
    ("Markets forecast growth of 3% in 2029.", 3, "IMF", "third_party"),
    ("With the RBNZ expected by the IMF to cut the OCR to 3% in 2029, financing costs will ease.", 3, "RBNZ", "third_party"),
    ("With the RBNZ expected by the IMF to cut the OCR to 3% in 2029, financing costs will ease.", 3, "The Treasury", "author"),
    ("The IMF forecasts growth of 3% in 2029, which exceeds what we expect.", 3, "The Treasury", "author"),
    ("The RBNZ expected growth of 2% but we forecast 3% in 2029.", 3, "RBNZ", "third_party"),
    ("The RBNZ expected growth of 2% but we forecast 3% in 2029.", 2, "The Treasury", "author"),
    ("We expect inflation of 2% in 2029, while growth will be 3%, which the IMF expects.", 3, "The Treasury", "author"),
    ("The RBNZ expected growth of 2% but the IMF forecasts 3% in 2029.", 3, "RBNZ", "third_party"),
    ("The RBNZ expected growth of 2% but the IMF forecasts 3% in 2029.", 2, "IMF", "third_party"),
    ("The RBNZ expected growth of 2% but the IMF forecasts 3% in 2029.", 3, "The Treasury", "author"),
    ("We expect growth of 3% in 2029, which the IMF expects, while inflation will be 2%.", 3, "The Treasury", "author"),
    ("The IMF forecasts growth of 2%, but the RBNZ expected 3% in 2029.", 3, "IMF", "third_party"),
    ("We expect growth of 3% in 2029 and inflation of 2%, which the IMF expects.", 3, "The Treasury", "author"),
    ("The IMF forecasts growth of 2% in 2029, but the IMF is above what the RBNZ expects: the RBNZ expected 3% in 2029.", 3, "IMF", "third_party"),
    ("The IMF expects growth of 3% in 2029, higher than we expected.", 3, "The Treasury", "author"),
    ("The IMF expects growth of 3%, less than we forecast at 2% in 2029.", 3, "The Treasury", "author"),
    ("The IMF expects growth of 2%, less than we forecast, and the IMF also forecasts 3% in 2029.", 3, "The Treasury", "author"),
    ("Markets anticipate growth of 3% in 2029.", 3, "The Treasury", "author"),
    ("Markets projected growth of 3% in 2029.", 3, "The Treasury", "author"),
]  # fmt: skip


@pytest.mark.parametrize(("sentence", "value", "issuer", "role"), ISSUER_INVALID)
def test_a_misattributed_forecast_is_still_rejected(sentence, value, issuer, role):
    assert forecast_codes(sentence, value, issuer=issuer, role=role) & ISSUER_CODES
