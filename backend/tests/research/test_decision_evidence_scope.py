"""The adopted decision supplies its own action, resulting rate, and maker."""

from datetime import date

import pytest

from nzstats.research.contract import PolicyDecision, SectionText

from .verify_support import check, codes, ref


def report(text, *, rate=2.75, action="hold", maker="RBNZ", institution="rbnz"):
    item = PolicyDecision(
        action=action,
        rate=rate,
        decided_on="2026-10-28",
        decision_maker=maker,
        evidence=[ref(0, text)],
    )
    return check(
        {0: SectionText(text)},
        outlook_ref=ref(0, text),
        decisions=[item],
        published_on=date(2026, 10, 28),
        institution=institution,
    )


def test_dissent_before_adopted_decision_does_not_supply_its_action():
    text = (
        "Three members preferred to cut the OCR to 2.5 percent, but the Committee agreed to hold"
        " the OCR at 2.75 percent today."
    )
    # Counts without a complete division must not manufacture a vote.
    assert codes(report(text)) == set()


def test_expectation_before_the_adopted_clause_does_not_make_the_decision_a_forecast():
    text = "Markets expected a cut, but the Committee agreed to hold the OCR at 2.75 percent today."
    assert codes(report(text)) == set()


def test_today_cannot_borrow_the_date_of_a_previous_decision():
    text = (
        "On 21 October 2026 the Committee held the OCR at 3.0 percent. "
        "The Committee agreed to hold the OCR at 2.75 percent today."
    )
    quote = "The Committee agreed to hold the OCR at 2.75 percent today"
    item = PolicyDecision(
        action="hold",
        rate=2.75,
        decided_on="2026-10-21",
        decision_maker="RBNZ",
        evidence=[ref(0, quote)],
    )
    result = check(
        {0: SectionText(text)},
        outlook_ref=ref(0, quote),
        decisions=[item],
        institution="rbnz",
        published_on=date(2026, 10, 28),
    )
    assert "decision_date_not_supported" in codes(result)


@pytest.mark.parametrize(("rate", "rejected"), [(2.75, False), (2.5, True)])
def test_forward_guidance_rate_cannot_replace_the_adopted_rate(rate, rejected):
    text = (
        "The Committee agreed to hold the OCR at 2.75 percent today and expects it to fall to"
        " 2.5 percent in 2027."
    )
    errors = codes(report(text, rate=rate))
    assert ("decision_rate_contradiction" in errors) == rejected
    if not rejected:
        assert not errors


@pytest.mark.parametrize(("rate", "rejected"), [(2.75, False), (3.0, True)])
def test_dissent_rate_cannot_replace_the_adopted_rate(rate, rejected):
    text = (
        "The Committee agreed to cut the OCR by 25 basis points to 2.75 percent today, while"
        " some members preferred to hold it at 3.0 percent."
    )
    errors = codes(report(text, rate=rate, action="decrease"))
    assert ("decision_rate_contradiction" in errors) == rejected
    if not rejected:
        assert not errors


@pytest.mark.parametrize("verb", ["reported that", "reported", "said"])
@pytest.mark.parametrize(("maker", "rejected"), [("RBNZ", False), ("The Treasury", True)])
def test_reporting_institution_is_not_the_policy_decision_maker(maker, rejected, verb):
    text = f"The Treasury {verb} the RBNZ Committee agreed to hold the OCR at 2.75 percent today."
    errors = codes(report(text, maker=maker, institution="treasury"))
    assert ("issuer_mismatch" in errors) == rejected
    if not rejected:
        assert not errors
