"""A figure cannot take a comparison's period (Phase 4Q). SYNTHETIC FIXTURE: invented sentences and figures.

`verify-4` only tightens. The `verify-3` period check is unchanged and a further check can add a rejection, so nothing it
rejected can pass. Two reviews broke an earlier design that also accepted more. The cost, kept visible in the tests below:
a true figure beside a comparison in the same clause stays rejected until a separately reviewed change.
"""

import pytest

from nzstats.research.contract import ReportedFact, SectionText

from .verify_support import check, codes, forecast, ref


def errors(
    sentence: str,
    value: float,
    period: str | None,
    *,
    unit: str = "percent",
    quote: str | None = None,
):
    quoted = quote or sentence.rstrip(".")
    claim = ReportedFact(text="Synthetic figure.", source="Synthetic Statistics", value=value, unit=unit, period=period,
                         evidence=[ref(0, quoted)])  # fmt: skip
    return codes(check({0: SectionText(sentence)}, outlook_ref=ref(0, quoted), facts=[claim]))


UP_FROM = "Output rose 6.3% in the September quarter, up from 5.9% in the June quarter."
BARE_FROM = "Prices rose 6.3% in the September quarter from 5.9% in June."
ROLLING = (
    "Arrivals were 41,200 in the 12 months to August, up from 38,400 in the year to March 2029."
)
COMPARED = "Freight volumes fell 0.8% on a seasonally adjusted basis compared with August."


@pytest.mark.parametrize(
    ("sentence", "value", "period"),
    [
        (COMPARED, 0.8, "August"),
        ("Freight fell 0.8% versus July.", 0.8, "July"),
        ("Freight fell 0.8% relative to 2029.", 0.8, "2029"),
        ("Freight fell 0.8% compared to the March quarter.", 0.8, "March quarter"),
        ("Freight rose 3% versus 2% in 2029.", 3, "2029"),
    ],
)
def test_the_base_of_a_comparison_is_not_the_figures_period(sentence, value, period):
    # verify-3 accepted these: the one thing the new check adds.
    assert "period_not_supported" in errors(sentence, value, period)


@pytest.mark.parametrize(
    ("sentence", "value", "period"),
    [
        (UP_FROM, 6.3, "June quarter"),
        (UP_FROM, 5.9, "September quarter"),
        (BARE_FROM, 6.3, "June"),
        (BARE_FROM, 5.9, "September quarter"),
        ("Wages in June 2029 compared with June 2028 rose 3%.", 3, "June 2028"),
        ("Growth in 2029 versus 2028 was 3%.", 3, "2028"),
        ("Growth in 2029 relative to 2028 was 3%.", 3, "2028"),
        ("Prices in September rose from 5% in June to 3%.", 3, "June"),
        ("Output rose 6.3% in 2029 versus 5.9%.", 5.9, "2031"),
        (
            "Imports rose 4% in June with exports at 6.3% compared with 5.9% in September.",
            6.3,
            "June",
        ),
        (ROLLING, 41200, "12 months to August 2029"),
    ],
)
def test_a_figure_cannot_take_another_period(sentence, value, period):
    unit = "persons" if value == 41200 else "percent"
    assert "period_not_supported" in errors(sentence, value, period, unit=unit)


@pytest.mark.parametrize(
    ("sentence", "value", "period"),
    [
        (UP_FROM, 6.3, "September quarter"),
        (UP_FROM, 5.9, "June quarter"),
        (BARE_FROM, 6.3, "September quarter"),
        (ROLLING, 41200, "12 months to August"),
    ],
)
def test_known_limit_a_true_period_beside_a_comparison_stays_rejected(sentence, value, period):
    # Fails closed, as verify-3 did. Accepting these needs its own reviewed design: see docs/phase-4q-evidence-grounding.md.
    unit = "persons" if value == 41200 else "percent"
    assert "period_not_supported" in errors(sentence, value, period, unit=unit)


def test_a_comparison_cannot_supply_a_horizon_or_lend_it_to_a_heading():
    sentence = "Growth in 2030 versus 2029 will be 2%."
    claim = forecast(0, sentence.rstrip("."), None, value=2, unit="percent", horizon="2029",
                     issuer="The Treasury", issuer_role="author")  # fmt: skip
    report = check(
        {0: SectionText(sentence)}, outlook_ref=ref(0, sentence.rstrip(".")), forecasts=[claim]
    )
    assert "horizon_not_supported" in codes(report)
    sentence = "Growth was 2.5% compared with 1.5% in 2029."
    fact = ReportedFact(text="Growth.", source="Synthetic Statistics", value=2.5, unit="percent", period="2030",
                        evidence=[ref(0, sentence.rstrip("."))])  # fmt: skip
    section = {0: SectionText(sentence, heading="Results for 2030")}
    assert "period_not_supported" in codes(
        check(section, outlook_ref=ref(0, sentence.rstrip(".")), facts=[fact])
    )


def test_a_year_the_sentence_omits_stays_rejected():
    assert "period_not_supported" in errors(
        "Output rose 6.3% in the September quarter.", 6.3, "September quarter 2029"
    )


@pytest.mark.parametrize(
    ("sentence", "value", "period"),
    [
        ("Output rose 6.3% in the September quarter.", 6.3, "September quarter"),
        ("In the September quarter, the net share fell from 71% to 66%.", 66, "September quarter"),
        ("The net share fell from 71% to 66% in the September quarter.", 66, "September quarter"),
        ("Output rose 6.3% in September compared with a weak base.", 6.3, "September"),
    ],
)
def test_a_figure_with_its_own_period_passes(sentence, value, period):
    assert "period_not_supported" not in errors(sentence, value, period)


def test_a_period_is_not_invented_from_the_neighbouring_sentence():
    sentence = (
        "Freight fell for a sixth month in September. The index fell 0.8% compared with August."
    )
    assert "period_not_supported" in errors(
        sentence, 0.8, "September", quote="The index fell 0.8% compared with August"
    )


def test_one_unsupported_period_still_rejects_the_whole_summary():
    good = "Output rose 6.3% in the September quarter"
    bad = "Prices rose 8.2% in the June quarter"
    section = {0: SectionText(f"{good}. {bad}.")}
    claims = [
        ReportedFact(text="Output rose.", source="Synthetic Statistics", value=6.3, unit="percent",
                     period="September quarter", evidence=[ref(0, good)]),
        ReportedFact(text="Prices rose.", source="Synthetic Statistics", value=8.2, unit="percent",
                     period="June quarter 2029", evidence=[ref(0, bad)]),
    ]  # fmt: skip
    assert check(section, outlook_ref=ref(0, good), facts=claims).passed is False


def test_a_true_figure_beside_a_comparison_passes_with_no_period_claimed():
    # What outlook-v5 asks for in this case: state nothing rather than choose. The quote still shows the document's words.
    assert "period_not_supported" not in errors(UP_FROM, 6.3, None)
    assert "period_not_supported" not in errors(BARE_FROM, 6.3, None)
