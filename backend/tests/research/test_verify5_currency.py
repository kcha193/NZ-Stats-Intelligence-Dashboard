"""Phase 4V: a foreign-currency amount is never accepted as New Zealand dollars, verifier `verify-5`. Synthetic text only.

Found while investigating the Brent crude `missing_unit` error. The contract has no US-dollar unit, so a model cannot state
"US$82 a barrel" correctly: `null` gives `missing_unit` and an invented unit gives `unknown_unit`. But `verify-4` ALSO accepted the
figure when the model called it `nzd`, because it looked only for a dollar sign. That is a false acceptance. Telling a model to copy
the units shown beside figures (outlook-v6) would make that mislabel more likely, so `verify-5` rejects it.
"""

from datetime import date

import pytest

from nzstats.research.contract import OutlookSummary, ReportedFact, SectionText
from nzstats.research.verify import VerificationContext, verify

from .verify_support import PROV, V, ref


def codes_for(sentence: str, value: float, unit: str | None, *, version: str) -> set[str]:
    sections = {0: SectionText(f"SYNTHETIC FIXTURE. {sentence}")}
    fact = ReportedFact(
        text="A figure.", source="Stats NZ", value=value, unit=unit, period="October 2026",
        evidence=[ref(0, sentence.rstrip("."))],
    )  # fmt: skip
    summary = OutlookSummary(
        version_id=V, provenance=PROV, outlook={"text": "The outlook", "evidence": [ref(0, "SYNTHETIC FIXTURE")]},
        indicators=("gdp",), facts=[fact],
    )  # fmt: skip
    ctx = VerificationContext(published_on=date(2026, 10, 29), institution="treasury")
    return {p.code for p in verify(summary, sections, ctx, version=version).errors}


@pytest.mark.parametrize(
    ("sentence", "value", "unit"),
    [
        ("Brent crude averaged US$82 a barrel in October 2026.", 82, "nzd"),
        ("The Australian deficit was A$4.2 billion in October 2026.", 4.2, "nzd_billion"),
        ("The deficit was US$4.2 billion in October 2026.", 4.2, "nzd_billion"),
        ("Exports were worth C$4.2 million in October 2026.", 4.2, "nzd_million"),
        ("Exports were worth HK$4.2 million in October 2026.", 4.2, "nzd_million"),
        ("Exports were worth US $4.2 million in October 2026.", 4.2, "nzd_million"),
    ],
)
def test_a_dollar_sign_amount_in_another_currency_claimed_as_nzd_was_a_false_acceptance(
    sentence, value, unit
):
    assert "unit_mismatch" not in codes_for(sentence, value, unit, version="verify-4")
    assert "unit_mismatch" in codes_for(sentence, value, unit, version="verify-5")


@pytest.mark.parametrize(
    ("sentence", "value", "unit"),
    [
        ("Brent crude averaged USD 82 a barrel in October 2026.", 82, "nzd"),
        ("Brent crude averaged 82 US dollars a barrel in October 2026.", 82, "nzd"),
        ("Exports to Europe were worth €4.2 million in October 2026.", 4.2, "nzd_million"),
        ("Exports to the UK were worth £4.2 million in October 2026.", 4.2, "nzd_million"),
        ("Exports were worth CAD 4.2 million in October 2026.", 4.2, "nzd_million"),
        ("Exports were worth 4.2 million US dollars in October 2026.", 4.2, "nzd_million"),
    ],
)
def test_other_currency_markers_were_already_rejected_and_stay_rejected(sentence, value, unit):
    for version in ("verify-4", "verify-5"):
        assert "unit_mismatch" in codes_for(sentence, value, unit, version=version)


@pytest.mark.parametrize(
    ("sentence", "value", "unit"),
    [
        ("The deficit was $4.2 billion in October 2026.", 4.2, "nzd_billion"),
        ("The deficit was NZ$4.2 billion in October 2026.", 4.2, "nzd_billion"),
        ("The deficit was NZD 4.2 billion in October 2026.", 4.2, "nzd_billion"),
        ("Exports were worth $4.2 million in October 2026.", 4.2, "nzd_million"),
        ("The median wage was $1,250 in October 2026.", 1250, "nzd"),
        ("The median wage was NZ$1,250 in October 2026.", 1250, "nzd"),
        (
            "Exports of US$3 million fell, while the deficit was $4.2 billion in October 2026.",
            4.2,
            "nzd_billion",
        ),
        ("A $4.2 billion deficit was recorded in October 2026.", 4.2, "nzd_billion"),
        ("The deficit measured in $4.2 billion terms in October 2026.", 4.2, "nzd_billion"),
    ],
)
def test_new_zealand_dollar_amounts_are_still_accepted(sentence, value, unit):
    assert codes_for(sentence, value, unit, version="verify-5") == codes_for(
        sentence, value, unit, version="verify-4"
    )
    assert "unit_mismatch" not in codes_for(sentence, value, unit, version="verify-5")


@pytest.mark.parametrize("unit", [None, "usd", "usd_per_barrel"])
def test_a_us_dollar_figure_still_has_no_valid_unit_so_it_is_still_rejected(unit):
    # The conservative failure is kept and documented: the contract needs a reviewed US-dollar unit before this can pass.
    sentence = "Brent crude averaged US$82 a barrel in October 2026."
    expected = {"missing_unit"} if unit is None else {"unknown_unit"}
    for version in ("verify-4", "verify-5"):
        assert codes_for(sentence, 82, unit, version=version) == expected


# --- found by the independent review: more spellings of another currency ----------------------------------------------
@pytest.mark.parametrize(
    "sentence",
    [
        "The deficit was us$4.2 billion in October 2026.",
        "The deficit was Aus$4.2 billion in October 2026.",
        "The deficit was Can$4.2 billion in October 2026.",
        "The deficit was CAD$4.2 billion in October 2026.",
        "The deficit was NT$4.2 billion in October 2026.",
        "The deficit was Mex$4.2 billion in October 2026.",
        "The deficit was R$4.2 billion in October 2026.",
        "The deficit was $4.2 billion USD in October 2026.",
        "The deficit was $4.2 billion US in October 2026.",
        "The deficit was $4.2 billion AUD in October 2026.",
        "The deficit was $4.2 billion (US dollars) in October 2026.",
    ],
)
def test_more_spellings_of_another_currency_are_rejected_as_nzd(sentence):
    assert "unit_mismatch" in codes_for(sentence, 4.2, "nzd_billion", version="verify-5")


@pytest.mark.parametrize(
    "sentence",
    [
        "The deficit was $4.2 billion in October 2026.",
        "The deficit was $4.2 billion, up from last year, in October 2026.",
        "A $4.2 billion deficit was recorded in October 2026.",
        "The deficit was NZ$4.2 billion in October 2026.",
        "The deficit was $4.2 billion NZD in October 2026.",
    ],
)
def test_the_new_spellings_do_not_reject_new_zealand_amounts(sentence):
    assert "unit_mismatch" not in codes_for(sentence, 4.2, "nzd_billion", version="verify-5")


# --- review round 1, finding 3: a converted amount beside a New Zealand figure is not that figure's currency label -----
def codes_quoting(sentence: str, quote: str, value: float, unit: str, *, version: str) -> set[str]:
    sections = {0: SectionText(f"SYNTHETIC FIXTURE. {sentence}")}
    fact = ReportedFact(
        text="A figure.", source="Stats NZ", value=value, unit=unit, period="October 2026",
        evidence=[ref(0, quote)],
    )  # fmt: skip
    summary = OutlookSummary(
        version_id=V, provenance=PROV, outlook={"text": "The outlook", "evidence": [ref(0, "SYNTHETIC FIXTURE")]},
        indicators=("gdp",), facts=[fact],
    )  # fmt: skip
    ctx = VerificationContext(published_on=date(2026, 10, 29), institution="treasury")
    return {p.code for p in verify(summary, sections, ctx, version=version).errors}


@pytest.mark.parametrize(
    "sentence",
    [
        "The deficit was NZ$4.2 billion (US$2.5 billion) in October 2026.",
        "The deficit was NZ$4.2 billion (USD 2.5 billion) in October 2026.",
        "The deficit was NZ$4.2 billion (US 2.5 billion) in October 2026.",
        "The deficit was $4.2 billion (US$2.5 billion) in October 2026.",
        "The deficit was NZ$4.2 billion, or US$2.5 billion, in October 2026.",
        "The deficit was NZ$4.2 billion (about US$2.5 billion) in October 2026.",
    ],
)
def test_a_converted_amount_after_the_new_zealand_figure_is_not_its_currency(sentence):
    assert "unit_mismatch" not in codes_for(sentence, 4.2, "nzd_billion", version="verify-4")
    assert codes_for(sentence, 4.2, "nzd_billion", version="verify-5") == codes_for(
        sentence, 4.2, "nzd_billion", version="verify-4"
    )


def test_the_same_holds_when_the_quote_ends_before_the_parenthesis():
    sentence = "The deficit was NZ$4.2 billion (US$2.5 billion) in October 2026."
    quote = "The deficit was NZ$4.2 billion"
    for version in ("verify-4", "verify-5"):
        assert "unit_mismatch" not in codes_quoting(
            sentence, quote, 4.2, "nzd_billion", version=version
        )


@pytest.mark.parametrize(
    ("sentence", "quote", "value"),
    [
        (
            "The deficit was NZ$4.2 billion (US$2.5 billion) in October 2026.",
            "(US$2.5 billion)",
            2.5,
        ),
        (
            "The deficit was NZ$4.2 billion (USD 2.5 billion) in October 2026.",
            "(USD 2.5 billion)",
            2.5,
        ),
    ],
)
def test_claiming_the_converted_amount_as_new_zealand_dollars_is_still_rejected(
    sentence, quote, value
):
    assert "unit_mismatch" in codes_quoting(
        sentence, quote, value, "nzd_billion", version="verify-5"
    )


@pytest.mark.parametrize(
    "sentence",
    [
        "The deficit was $4.2 billion (US$) in October 2026.",
        "The deficit was $4.2 billion US$ in October 2026.",
        "The deficit was $4.2 billion USD, or NZ$7 billion, in October 2026.",
        "The deficit was $4.2 billion (USD) in October 2026.",
        "The deficit was $4.2 billion US, up on last year, in October 2026.",
    ],
)
def test_a_currency_label_on_the_claimed_amount_is_still_rejected(sentence):
    assert "unit_mismatch" in codes_for(sentence, 4.2, "nzd_billion", version="verify-5")
