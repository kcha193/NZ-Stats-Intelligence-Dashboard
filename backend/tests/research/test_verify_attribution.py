"""Who made a forecast (Phase 4I): a third party's forecast must never pass as the author's, or the reverse."""

import pytest

from nzstats.research.contract import SectionText
from nzstats.research.issuers import credited, named, organisation_of

from .test_verify_layout import TABLE
from .verify_support import check, codes, forecast, ref, warning_codes

PROSE = SectionText(
    "SYNTHETIC FIXTURE. The IMF expects New Zealand GDP to grow 2.9% in 2027. We expect growth of"
    " 2.8% in 2027. According to the OECD, growth will be 2.6% in 2027.",
    1, 1,
)  # fmt: skip
NEAR = SectionText(
    "SYNTHETIC FIXTURE. The October World Economic Outlook was published this month. Growth is"
    " projected at 3.0% in 2027.",
    3, 3,
)  # fmt: skip
BANK = SectionText(
    "SYNTHETIC FIXTURE. The RBNZ is expected to cut the OCR to 2.25% by February 2027. Markets are"
    " pricing the OCR to fall to 2.0% by August 2027.",
    4, 4,
)  # fmt: skip
SECTIONS = {1: PROSE, 2: TABLE, 3: NEAR, 4: BANK}
OUTLOOK = ref(1, "We expect growth of 2.8% in 2027")


def run(*claims, institution="treasury", **kw):
    return check(SECTIONS, outlook_ref=OUTLOOK, institution=institution, forecasts=claims, **kw)


def prose(value: float, quote: str, issuer: str, role: str, **kw):
    return forecast(1, quote, 1, value=value, unit="percent", issuer=issuer, issuer_role=role, **kw)


IMF_SENTENCE = "The IMF expects New Zealand GDP to grow 2.9% in 2027"
OWN_SENTENCE = "We expect growth of 2.8% in 2027"


def test_the_authors_own_forecast_passes():
    assert codes(run(prose(2.8, OWN_SENTENCE, "The Treasury", "author"))) == set()


def test_an_imf_forecast_attributed_to_the_author_is_an_error():
    report = run(prose(2.9, IMF_SENTENCE, "The Treasury", "author"))
    assert "issuer_mismatch" in codes(report)
    assert any("imf" in p.message.lower() for p in report.errors if p.code == "issuer_mismatch")


def test_an_imf_forecast_attributed_to_the_imf_passes():
    assert (
        codes(run(prose(2.9, IMF_SENTENCE, "International Monetary Fund", "third_party"))) == set()
    )


@pytest.mark.parametrize(
    ("value", "quote", "issuer"),
    [
        (2.8, OWN_SENTENCE, "IMF"),  # the author's forecast credited to the IMF
        (2.9, IMF_SENTENCE, "OECD"),  # one third party credited to another
        (2.6, "According to the OECD, growth will be 2.6% in 2027", "IMF"),
    ],
)
def test_a_forecast_credited_to_the_wrong_third_party_is_an_error(value, quote, issuer):
    assert "issuer_mismatch" in codes(run(prose(value, quote, issuer, "third_party")))


def test_an_author_role_naming_another_organisation_is_an_error():
    claim = prose(2.8, OWN_SENTENCE, "IMF", "author")  # the document is the Treasury's
    assert "issuer_mismatch" in codes(run(claim))


def test_a_v2_forecast_without_an_issuer_is_an_error_but_a_v1_one_is_not():
    bare = prose(2.8, OWN_SENTENCE, "x", "author").model_copy(
        update={"issuer": None, "issuer_role": None}
    )
    assert "missing_issuer" in codes(run(bare))
    assert "missing_issuer" not in codes(run(bare, contract_version=1))


def test_a_v1_forecast_is_still_checked_as_the_authors_own():
    bare = prose(2.9, IMF_SENTENCE, "x", "author").model_copy(
        update={"issuer": None, "issuer_role": None}
    )
    assert "issuer_mismatch" in codes(run(bare, contract_version=1))


# --- tables: the row label, then the table's titled caption ---------------------------------------
ISSUER_CODES = {"issuer_mismatch", "issuer_not_in_evidence", "issuer_unclear"}


def table_row(quote: str, value: float, issuer: str, role: str):
    return forecast(2, quote, 2, value=value, unit="percent", horizon="2026", issuer=issuer,
                    issuer_role=role, indicator_label="Real GDP")  # fmt: skip


NZ_ROW = "New Zealand 0.3 2.0 2.6 2.8 4.1 2.8"
OWN_ROW = "Treasury (PEU) -- 1.9 2.8 -- 3.6 2.1"


def test_an_imf_table_row_attributed_to_the_author_is_an_error():
    assert "issuer_mismatch" in codes(run(table_row(NZ_ROW, 2.0, "The Treasury", "author")))
    report = run(table_row(NZ_ROW, 2.0, "IMF", "third_party"))
    assert not (codes(report) | warning_codes(report)) & ISSUER_CODES


def test_the_authors_own_row_in_a_third_party_table_is_the_authors():
    report = run(table_row(OWN_ROW, 1.9, "The Treasury", "author"))
    assert not (codes(report) | warning_codes(report)) & ISSUER_CODES
    assert "issuer_mismatch" in codes(run(table_row(OWN_ROW, 1.9, "IMF", "third_party")))


# --- unclear attribution and other forecasters -----------------------------------------------------
def test_a_figure_after_a_sentence_naming_a_third_party_publication_is_not_the_authors():
    claim = forecast(3, "Growth is projected at 3.0% in 2027", 3, value=3.0, unit="percent")
    assert "issuer_mismatch" in codes(run(claim))
    imf = forecast(3, "Growth is projected at 3.0% in 2027", 3, value=3.0, unit="percent",
                   issuer="IMF", issuer_role="third_party")  # fmt: skip
    assert codes(run(imf)) == set()


def test_a_third_party_issuer_must_be_named_in_the_evidence():
    claim = forecast(3, "Growth is projected at 3.0% in 2027", 3, value=3.0, unit="percent",
                     issuer="OECD", issuer_role="third_party")  # fmt: skip
    assert "issuer_mismatch" in codes(run(claim))  # the sentence before credits the IMF's WEO
    unnamed = {9: SectionText("SYNTHETIC FIXTURE. Growth is projected at 3.0% in 2027.", 9, 9)}
    claim = claim.model_copy(
        update={"evidence": (ref(9, "Growth is projected at 3.0% in 2027", 9),)}
    )
    assert "issuer_not_in_evidence" in codes(
        check(unnamed, outlook_ref=ref(9, "Growth is projected"), forecasts=[claim])
    )


def test_a_bank_forecast_about_the_rbnz_is_the_banks_own():
    claim = forecast(4, "The RBNZ is expected to cut the OCR to 2.25% by February 2027", 4,
                     indicator="ocr", indicator_label="OCR", horizon="February 2027", value=2.25,
                     unit="percent", direction="down", issuer="ANZ", issuer_role="author")  # fmt: skip
    assert codes(run(claim, institution="anz")) == set()


def test_market_pricing_is_a_third_party_not_the_author():
    quote = "Markets are pricing the OCR to fall to 2.0% by August 2027"
    own = forecast(4, quote, 4, indicator="ocr", indicator_label="OCR", horizon="August 2027",
                   value=2.0, unit="percent", direction="down", issuer="ANZ",
                   issuer_role="author")  # fmt: skip
    assert "issuer_mismatch" in codes(run(own, institution="anz"))
    market = own.model_copy(update={"issuer": "market pricing", "issuer_role": "third_party"})
    assert codes(run(market, institution="anz")) == set()


@pytest.mark.parametrize(
    ("name", "key"),
    [("International Monetary Fund", "imf"), ("IMF", "imf"), ("The Treasury", "treasury"),
     ("Monetary Policy Committee", "rbnz"), ("Reserve Bank of New Zealand", "rbnz"),
     ("Reserve Bank of Australia", "rba"), ("market pricing", "market"), ("Example Bank", None)],
)  # fmt: skip
def test_issuer_names_resolve_to_known_organisations(name, key):
    assert organisation_of(name) == key


# --- regressions from the real Phase 4H documents (synthetic text in the same shapes) -----------------
CONTEXT = SectionText(
    "SYNTHETIC FIXTURE. The IMF revised its forecasts this month in its World Economic Outlook (WEO). The"
    " outlook for global growth in 2026 has been revised to 3.1%, and growth of 3.2% in 2027 is unchanged."
    " Oil prices are assumed by the IMF to average US$96/b in 2026 and US$90/b in 2027, according to the WEO.",
    5, 5,
)  # fmt: skip


def context_claim(quote: str, value: float, **kw):
    base = dict(value=value, unit="percent", issuer="The Treasury", issuer_role="author")
    return forecast(5, quote, 5, **(base | kw))


def run_context(claim):
    return check(
        {5: CONTEXT}, outlook_ref=ref(5, "The IMF revised its forecasts"), forecasts=[claim]
    )


def test_us_dollars_are_not_the_author_speaking():
    """In "US$96/b", "US" is the United States, not "us": the IMF credit must not become unclear."""
    claim = context_claim("Oil prices are assumed by the IMF to average US$96/b in 2026", 96,
                          horizon="2026", unit="nzd", indicator="other", indicator_label="Oil prices")  # fmt: skip
    assert "issuer_mismatch" in codes(run_context(claim))


def test_a_figure_continuing_a_sentence_that_credits_a_third_party_is_the_third_partys():
    quote = "The outlook for global growth in 2026 has been revised to 3.1%"
    assert "issuer_mismatch" in codes(run_context(context_claim(quote, 3.1, horizon="2026")))
    imf = context_claim(quote, 3.1, horizon="2026", issuer="IMF", issuer_role="third_party")
    report = run_context(imf)
    assert not (codes(report) | warning_codes(report)) & ISSUER_CODES


def test_a_third_party_merely_named_nearby_is_only_a_warning():
    sections = {6: SectionText("SYNTHETIC FIXTURE. The IMF met in Washington this month. Growth is"
                               " projected at 3.0% in 2027.", 6, 6)}  # fmt: skip
    claim = forecast(6, "Growth is projected at 3.0% in 2027", 6, value=3.0, unit="percent")
    report = check(sections, outlook_ref=ref(6, "Growth is projected"), forecasts=[claim])
    assert codes(report) == set() and "issuer_unclear" in warning_codes(report)


# Phase 4Q: reporting wording that makes a third party the forecaster. A figure in the author's document is not the
# author's forecast because the author reports it.
REPORTED = {
    0: SectionText(
        "SYNTHETIC FIXTURE. The MPC said it expected inflation to reach 7.4% in the December quarter."
        " Markets expect the Fed will lift its policy rate 75 basis points by the end of 2029."
        " The RBNZ expected inflation of 7.1% in June 2029. The RBNZ, expected to cut, may reach 1.25% by June 2029.",
        1, 1,
    )
}  # fmt: skip
MPC = "The MPC said it expected inflation to reach 7.4% in the December quarter"
MARKET = "Markets expect the Fed will lift its policy rate 75 basis points by the end of 2029"
RBNZ_VIEW = "The RBNZ expected inflation of 7.1% in June 2029"


def reported(value, quote, issuer, role, unit="percent"):
    claim = forecast(0, quote, 1, value=value, unit=unit, issuer=issuer, issuer_role=role)
    return check(REPORTED, outlook_ref=ref(0, MPC), institution="treasury", forecasts=[claim])


@pytest.mark.parametrize(
    ("value", "quote", "unit"),
    [(7.4, MPC, "percent"), (75, MARKET, "basis_points"), (7.1, RBNZ_VIEW, "percent")],
)
def test_a_reported_third_party_forecast_cannot_be_labelled_the_authors(value, quote, unit):
    assert "issuer_mismatch" in codes(reported(value, quote, "The Treasury", "author", unit))


@pytest.mark.parametrize(
    ("value", "quote", "issuer", "unit"),
    [(7.4, MPC, "Monetary Policy Committee", "percent"), (75, MARKET, "Markets", "basis_points")],
)
def test_the_actual_third_party_is_accepted_as_the_issuer(value, quote, issuer, unit):
    report = reported(value, quote, issuer, "third_party", unit)
    assert not codes(report) & {"issuer_mismatch", "issuer_not_in_evidence"}


def test_being_expected_to_act_still_does_not_make_an_organisation_the_forecaster():
    quote = "The RBNZ, expected to cut, may reach 1.25% by June 2029"
    assert "issuer_mismatch" not in codes(reported(1.25, quote, "The Treasury", "author"))
    assert "rbnz" not in credited("The RBNZ expected to cut")
    assert "rbnz" not in credited("The RBNZ is expected to cut the OCR")


def test_market_is_recognised_only_as_a_whole_issuer_name():
    assert (
        organisation_of("Markets") == "market" and organisation_of("financial markets") == "market"
    )
    assert organisation_of("Monetary Policy Committee") == "rbnz"
    assert "market" not in named("Export markets remain strong.")
