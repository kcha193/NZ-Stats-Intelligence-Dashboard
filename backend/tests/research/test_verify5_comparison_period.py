"""Phase 4V: a figure and the base it is compared with each keep their own period, verifier `verify-5`. Synthetic text only.

`verify-4` read the whole clause as one period context, so "3.7% in the September 2026 quarter, up from 3.3% in the June 2026
quarter" made the claimed September period "ambiguous or contradictory" and rejected a correct claim. In summary 4 all three
`period_not_supported` errors have this shape (one month, then "from" and a second figure with another month).

`verify-5` adds one accepting path and nothing else. When the first attempt fails and the figure is followed by a comparison
word (not "above" or "below"), the figure's own side is checked alone. That side must hold only this one figure and must support
the whole claimed period by itself. The comparison-period rule still applies afterwards, so a period that only the base states
is refused.
"""

from datetime import date

import pytest

from nzstats.research.contract import OutlookSummary, ReportedFact, SectionText
from nzstats.research.verify import VerificationContext, verify

from .verify_support import PROV, V, ref

SEP = "September 2026 quarter"
JUN = "June 2026 quarter"
M = "March 2026 quarter"


def codes_for(
    sentence: str, value: float, period: str | None, *, version: str, unit: str = "percent"
):
    sections = {0: SectionText(f"SYNTHETIC FIXTURE. {sentence}")}
    fact = ReportedFact(
        text="A figure.", source="Stats NZ", value=value, unit=unit, period=period,
        evidence=[ref(0, sentence.rstrip("."))],
    )  # fmt: skip
    summary = OutlookSummary(
        version_id=V, provenance=PROV, outlook={"text": "The outlook", "evidence": [ref(0, "SYNTHETIC FIXTURE")]},
        indicators=("cpi_inflation",), facts=[fact],
    )  # fmt: skip
    ctx = VerificationContext(published_on=date(2026, 10, 29), institution="treasury")
    return {p.code for p in verify(summary, sections, ctx, version=version).errors}


HEAD_THEN_BASE = [
    f"Annual CPI inflation was 3.7% in the {SEP}, up from 3.3% in the {JUN}.",
    f"Annual CPI inflation rose to 3.7% in the {SEP} from 3.3% in the {JUN}.",
    f"Annual CPI inflation was 3.7% in the {SEP}, compared with 3.3% in the {JUN}.",
    f"Annual CPI inflation was 3.7% in the {SEP}, versus 3.3% in the {JUN}.",
]


# --- the false rejection this fixes -----------------------------------------------------------------------
@pytest.mark.parametrize("sentence", HEAD_THEN_BASE)
def test_the_figure_with_its_own_period_is_accepted_by_verify_5(sentence):
    assert codes_for(sentence, 3.7, SEP, version="verify-5") == set()


@pytest.mark.parametrize("sentence", [HEAD_THEN_BASE[0], HEAD_THEN_BASE[1], HEAD_THEN_BASE[3]])
def test_these_shapes_were_the_false_rejection_under_verify_4(sentence):
    assert codes_for(sentence, 3.7, SEP, version="verify-4") == {"period_not_supported"}


def test_the_compared_with_shape_was_already_accepted_and_is_unchanged():
    sentence = "Net migration was 3,190 in July 2026, compared with 1,530 in June 2026."
    for version in ("verify-4", "verify-5"):
        assert codes_for(sentence, 3190, "July 2026", version=version, unit="persons") == set()


# --- what must stay rejected (a false acceptance would be here) -------------------------------------------
@pytest.mark.parametrize("sentence", HEAD_THEN_BASE)
@pytest.mark.parametrize("wrong", [JUN, "December 2026 quarter", "March 2026 quarter", "2026"])
def test_the_figure_is_never_given_the_bases_period_or_an_unstated_one(sentence, wrong):
    got = codes_for(sentence, 3.7, wrong, version="verify-5")
    if wrong == "2026":
        # the year is stated on the figure's side only as part of its quarter, so it is not a different period
        assert got == codes_for(sentence, 3.7, wrong, version="verify-4")
    else:
        assert "period_not_supported" in got


@pytest.mark.parametrize("sentence", HEAD_THEN_BASE)
def test_the_base_figure_keeps_its_old_treatment(sentence):
    # Claiming the second figure is not made easier: the same result as verify-4 for either period.
    for period in (JUN, SEP):
        assert codes_for(sentence, 3.3, period, version="verify-5") == codes_for(
            sentence, 3.3, period, version="verify-4"
        )


def test_a_figure_with_no_period_of_its_own_cannot_borrow_the_comparisons():
    sentence = f"Annual CPI inflation was 3.7%, up from 3.3% in the {JUN}."
    for version in ("verify-4", "verify-5"):
        assert "period_not_supported" in codes_for(sentence, 3.7, JUN, version=version)


def test_a_comparison_with_no_second_figure_is_not_split():
    sentence = f"Annual CPI inflation was 3.7% in the {SEP}, above its level in the {JUN}."
    assert codes_for(sentence, 3.7, SEP, version="verify-5") == codes_for(
        sentence, 3.7, SEP, version="verify-4"
    )


def test_a_period_only_the_other_side_completes_is_not_borrowed():
    # the year appears only after "up from"; the figure's own side says "September" alone
    sentence = "Annual CPI inflation was 3.7% in September, up from 3.3% in June 2026."
    assert "period_not_supported" in codes_for(sentence, 3.7, SEP, version="verify-5")


def test_other_checks_still_apply_to_the_accepted_shape():
    forecast = (
        f"Annual CPI inflation is forecast to be 3.7% in the {SEP}, up from 3.3% in the {JUN}."
    )
    assert "forecast_as_fact" in codes_for(forecast, 3.7, SEP, version="verify-5")
    assert "unit_mismatch" in codes_for(
        HEAD_THEN_BASE[0], 3.7, SEP, version="verify-5", unit="basis_points"
    )


# --- verify-5 never rejects what verify-4 accepted ---------------------------------------------------------
@pytest.mark.parametrize("sentence", HEAD_THEN_BASE + [
    f"Annual CPI inflation was 3.7% in the {SEP}.",
    "Net migration was 3,190 in July 2026 and 1,530 in August 2026.",
    "Unemployment was 5.1% in the June 2026 quarter, down from 5.3% in the March 2026 quarter.",
])  # fmt: skip
@pytest.mark.parametrize("period", [SEP, JUN, "July 2026", "June 2026 quarter", "2026", None])
@pytest.mark.parametrize("value", [3.7, 3.3, 5.1, 3190, 1530])
def test_verify_5_only_ever_removes_a_period_error(sentence, period, value):
    old = codes_for(sentence, value, period, version="verify-4")
    new = codes_for(sentence, value, period, version="verify-5")
    assert new <= old
    assert old - new <= {"period_not_supported"}


# --- what the new path leaves alone ----------------------------------------------------------------------
def with_heading(
    sentence: str, heading: str, value: float, period: str, *, version: str
) -> set[str]:
    sections = {0: SectionText(f"SYNTHETIC FIXTURE. {sentence}", None, None, heading)}
    fact = ReportedFact(
        text="A figure.", source="Stats NZ", value=value, unit="percent", period=period, evidence=[ref(0, sentence.rstrip("."))]
    )  # fmt: skip
    summary = OutlookSummary(
        version_id=V, provenance=PROV, outlook={"text": "The outlook", "evidence": [ref(0, "SYNTHETIC FIXTURE")]},
        indicators=("cpi_inflation",), facts=[fact],
    )  # fmt: skip
    ctx = VerificationContext(published_on=date(2026, 10, 29), institution="treasury")
    return {p.code for p in verify(summary, sections, ctx, version=version).errors}


def test_a_period_that_comes_only_from_the_heading_is_still_rejected():
    sentence = f"Annual CPI inflation was 3.7%, up from 3.3% in the {JUN}."
    assert with_heading(sentence, SEP, 3.7, SEP, version="verify-4") == {"period_not_supported"}
    assert with_heading(sentence, SEP, 3.7, SEP, version="verify-5") == {"period_not_supported"}


@pytest.mark.parametrize("word", ["above", "below"])
def test_a_gap_to_another_figure_is_not_split_like_a_comparison_of_periods(word):
    sentence = f"Annual CPI inflation was 3.7% in the {SEP}, {word} the 3.3% trend in the {JUN}."
    assert codes_for(sentence, 3.7, SEP, version="verify-5") == codes_for(
        sentence, 3.7, SEP, version="verify-4"
    )
    assert "period_not_supported" in codes_for(sentence, 3.7, SEP, version="verify-5")


def test_a_comparison_with_a_bare_period_and_no_second_figure_is_unchanged():
    sentence = f"Annual CPI inflation was 3.7% in the {SEP}, compared with 2025."
    assert codes_for(sentence, 3.7, SEP, version="verify-5") == codes_for(
        sentence, 3.7, SEP, version="verify-4"
    )


# --- found by the Phase 4Q period-grounding suite: the other figure's period must not be borrowed ---------------------
OTHER_FIGURE = "Imports rose 4% in June with exports at 6.3% compared with 5.9% in September."


@pytest.mark.parametrize(
    ("value", "period"), [(6.3, "June"), (4, "June"), (5.9, "June"), (6.3, "September")]
)
def test_a_period_belonging_to_another_figure_on_the_same_side_is_never_borrowed(value, period):
    assert codes_for(OTHER_FIGURE, value, period, version="verify-5") == codes_for(
        OTHER_FIGURE, value, period, version="verify-4"
    )
    if (value, period) == (6.3, "June"):
        assert "period_not_supported" in codes_for(OTHER_FIGURE, value, period, version="verify-5")


def test_a_list_of_figures_before_a_comparison_is_unchanged():
    sentence = f"Unemployment was 5.1% in the {M}, 5.3% in the {JUN}, up from 5.0% in the {SEP}."
    for value, period in ((5.3, JUN), (5.1, M), (5.0, SEP)):
        assert codes_for(sentence, value, period, version="verify-5") == codes_for(
            sentence, value, period, version="verify-4"
        )


# --- review round 1, finding 5: a quantity written in words is another figure on the same side -------------------------
@pytest.mark.parametrize(
    "other",
    [
        "four percent",
        "four per cent",
        "twenty percent",
        "Two",
        "a dozen",
        "one hundred and five",
        "forty-five percent",
    ],
)
def test_a_spelled_out_quantity_on_the_same_side_stops_the_period_being_borrowed(other):
    sentence = f"Imports rose {other} in June with exports at 6.3% compared with 5.9% in September."
    for period in ("June", "September"):
        v4, v5 = (codes_for(sentence, 6.3, period, version=v) for v in ("verify-4", "verify-5"))
        assert v5 == v4  # verify-5 must not accept what verify-4 refused
    assert "period_not_supported" in codes_for(sentence, 6.3, "June", version="verify-5")


def test_the_digit_form_of_the_same_sentence_was_already_refused_and_stays_so():
    assert "period_not_supported" in codes_for(OTHER_FIGURE, 6.3, "June", version="verify-5")
