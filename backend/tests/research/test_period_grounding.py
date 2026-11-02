"""Each figure is bound to its own reference period (Phase 4Q). SYNTHETIC FIXTURE: invented sentences and figures.

Phase 4O's rejected facts showed two things, by code alone: a year the document does not state beside the figure, and a
comparison's period being read as the figure's own. The first must stay rejected. The second must be bound correctly, in
both directions, and that makes the check stricter as well as fairer: the base of a comparison can no longer serve as the
figure's period.
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
        (UP_FROM, 6.3, "September quarter"),
        (UP_FROM, 5.9, "June quarter"),
        (BARE_FROM, 6.3, "September quarter"),
        (BARE_FROM, 5.9, "June"),
    ],
)
def test_a_figure_keeps_its_own_period_beside_a_comparison(sentence, value, period):
    assert "period_not_supported" not in errors(sentence, value, period)


@pytest.mark.parametrize(
    ("sentence", "value", "period"),
    [
        (UP_FROM, 6.3, "June quarter"),
        (UP_FROM, 5.9, "September quarter"),
        (BARE_FROM, 6.3, "June"),
        (BARE_FROM, 5.9, "September quarter"),
    ],
)
def test_a_figure_cannot_take_the_other_figures_period(sentence, value, period):
    assert "period_not_supported" in errors(sentence, value, period)


def test_the_base_of_a_comparison_is_not_the_figures_period():
    assert "period_not_supported" in errors(COMPARED, 0.8, "August")


def test_a_comparison_base_cannot_lend_its_year_to_the_figure():
    assert "period_not_supported" in errors(
        ROLLING, 41200, "12 months to August 2029", unit="persons"
    )


def test_a_rolling_period_copied_as_written_passes():
    assert "period_not_supported" not in errors(
        ROLLING, 41200, "12 months to August", unit="persons"
    )


def test_a_year_the_sentence_omits_stays_rejected():
    assert "period_not_supported" in errors(
        "Output rose 6.3% in the September quarter.", 6.3, "September quarter 2029"
    )


def test_the_same_period_copied_as_written_passes():
    assert "period_not_supported" not in errors(
        "Output rose 6.3% in the September quarter.", 6.3, "September quarter"
    )


def test_a_period_from_a_later_clause_still_supports_a_range_in_one_period():
    sentence = "In the September quarter, the net share fell from 71% to 66%."
    assert "period_not_supported" not in errors(sentence, 66, "September quarter")


def test_a_from_to_range_is_not_split_into_two_periods():
    sentence = "The net share fell from 71% to 66% in the September quarter."
    assert "period_not_supported" not in errors(sentence, 66, "September quarter")


@pytest.mark.parametrize("word", ["up", "down", "higher", "lower"])
def test_each_comparison_wording_binds_the_same_way(word):
    sentence = f"Output was 6.3% in the September quarter, {word} from 5.9% in the June quarter."
    assert "period_not_supported" not in errors(sentence, 6.3, "September quarter")
    assert "period_not_supported" in errors(sentence, 6.3, "June quarter")


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


# Found by independent review of the first verify-4: each pair below passed the wrong period. The fix must hold in both
# directions, for facts and forecasts alike.
@pytest.mark.parametrize(
    ("sentence", "value", "period"),
    [
        ("Wages in June 2029 compared with June 2028 rose 3%.", 3, "June 2028"),
        ("Growth in 2029 versus 2028 was 3%.", 3, "2028"),
        ("Growth in 2029 relative to 2028 was 3%.", 3, "2028"),
        ("Prices in September rose from 5% in June to 3%.", 3, "June"),
    ],
)
def test_a_comparison_before_the_figure_cannot_supply_its_period(sentence, value, period):
    assert "period_not_supported" in errors(sentence, value, period)


def test_a_comparison_before_a_forecast_cannot_supply_its_horizon():
    sentence = "Growth in 2030 versus 2029 will be 2%."
    claim = forecast(
        0,
        sentence.rstrip("."),
        None,
        value=2,
        unit="percent",
        horizon="2029",
        issuer="The Treasury",
        issuer_role="author",
    )
    assert "horizon_not_supported" in codes(
        check(
            {0: SectionText(sentence)}, outlook_ref=ref(0, sentence.rstrip(".")), forecasts=[claim]
        )
    )


def test_a_heading_cannot_stand_in_once_a_comparison_with_its_own_period_is_cut():
    sentence = "Growth was 2.5% compared with 1.5% in 2029."
    section = {0: SectionText(sentence, heading="Results for 2030")}
    claim = ReportedFact(text="Growth.", source="Synthetic Statistics", value=2.5, unit="percent", period="2030",
                         evidence=[ref(0, sentence.rstrip("."))])  # fmt: skip
    assert "period_not_supported" in codes(
        check(section, outlook_ref=ref(0, sentence.rstrip(".")), facts=[claim])
    )


@pytest.mark.parametrize("word", ["versus", "relative to", "compared to", "compared with"])
def test_each_comparison_word_binds_the_figure_before_it(word):
    sentence = f"Output was 6.3% in the September quarter {word} 5.9% in the June quarter."
    assert "period_not_supported" not in errors(sentence, 6.3, "September quarter")
    assert "period_not_supported" in errors(sentence, 6.3, "June quarter")
    assert "period_not_supported" not in errors(sentence, 5.9, "June quarter")
    assert "period_not_supported" in errors(sentence, 5.9, "September quarter")
