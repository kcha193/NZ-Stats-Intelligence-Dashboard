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


@pytest.mark.parametrize("claimed", ["2026-10-21", "2026-10-28"])
@pytest.mark.parametrize(
    "prefix",
    [
        "On 21 October 2026, the Committee met; it",
        "At its meeting on 21 October 2026, some members preferred a cut, but the Committee",
    ],
)
def test_meeting_date_in_the_selected_event_prefix_is_preserved(claimed, prefix):
    primary = f"{prefix} agreed to hold the OCR at 2.75 percent."
    errors = codes(
        contextual_decision(primary, "The outlook remains uncertain.", decided_on=claimed)
    )
    assert ("decision_date_not_supported" in errors) == (claimed != "2026-10-21")
    if claimed == "2026-10-21":
        assert not errors


@pytest.mark.parametrize("votes", [None, (4, 3)])
def test_vote_in_the_selected_event_prefix_is_preserved(votes):
    primary = "The vote was 4–3; the Committee agreed to hold the OCR at 2.75 percent today."
    errors = codes(contextual_decision(primary, "The outlook remains uncertain.", votes=votes))
    assert ("vote_not_captured" in errors) == (votes is None)
    if votes:
        assert not errors


def contextual_decision(primary, neighbor, *, decided_on="2026-10-28", votes=None, reverse=False):
    text = f"{primary} {neighbor}" if reverse else f"{neighbor} {primary}"
    item = PolicyDecision(
        action="hold",
        rate=2.75,
        decided_on=decided_on,
        decision_maker="RBNZ",
        vote_for=votes[0] if votes else None,
        vote_against=votes[1] if votes else None,
        evidence=[ref(0, primary)],
    )
    return check(
        {0: SectionText(text)},
        outlook_ref=ref(0, primary),
        decisions=[item],
        institution="rbnz",
        published_on=date(2026, 10, 28),
    )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("date_text", ["28 October 2026", "2026-10-28"])
@pytest.mark.parametrize(("claimed", "rejected"), [("2026-10-28", False), ("2026-10-21", True)])
def test_explicit_decision_date_takes_precedence_over_neighboring_decisions(
    reverse, date_text, claimed, rejected
):
    primary = f"On {date_text} the RBNZ Committee agreed to hold the OCR at 2.75 percent."
    neighbor = "On 21 October 2026 the RBNZ Committee agreed to hold the OCR at 3.0 percent."
    errors = codes(contextual_decision(primary, neighbor, decided_on=claimed, reverse=reverse))
    assert ("decision_date_not_supported" in errors) == rejected
    if not rejected:
        assert not errors


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(("votes", "rejected"), [((4, 3), False), ((5, 2), True)])
def test_adopted_vote_takes_precedence_over_neighboring_decisions(reverse, votes, rejected):
    primary = "On 28 October 2026 the RBNZ Committee voted 4–3 to hold the OCR at 2.75 percent."
    neighbor = "On 21 October 2026 the RBNZ Committee voted 5–2 to hold the OCR at 3.0 percent."
    errors = codes(contextual_decision(primary, neighbor, votes=votes, reverse=reverse))
    assert ("vote_not_in_evidence" in errors) == rejected
    if not rejected:
        assert not errors


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("votes", [None, (5, 2)])
def test_undated_unvoted_decision_does_not_borrow_another_decisions_fields(reverse, votes):
    primary = "The RBNZ Committee agreed to hold the OCR at 2.75 percent."
    neighbor = "On 21 October 2026 the RBNZ Committee voted 5–2 to hold the OCR at 3.0 percent."
    errors = codes(contextual_decision(primary, neighbor, votes=votes, reverse=reverse))
    assert ("vote_not_in_evidence" in errors) == (votes is not None)
    assert "vote_not_captured" not in errors
    if votes is None:
        assert not errors


@pytest.mark.parametrize("reverse", [False, True])
def test_separate_vote_supplement_for_the_cited_decision_is_still_usable(reverse):
    primary = "The RBNZ Committee agreed to hold the OCR at 2.75 percent today."
    assert (
        codes(contextual_decision(primary, "The vote was 4–3.", votes=(4, 3), reverse=reverse))
        == set()
    )


@pytest.mark.parametrize("date_wording", ["today", "on 28 October 2026"])
@pytest.mark.parametrize(("claimed", "rejected"), [("2026-10-28", False), ("2026-11-04", True)])
def test_forward_meeting_date_cannot_replace_the_adopted_decision_date(
    date_wording, claimed, rejected
):
    primary = (
        f"The RBNZ Committee agreed to hold the OCR at 2.75 percent {date_wording} and expects"
        " to decide again on 4 November 2026."
    )
    errors = codes(
        contextual_decision(primary, "The outlook remains uncertain.", decided_on=claimed)
    )
    assert ("decision_date_not_supported" in errors) == rejected
    if not rejected:
        assert not errors


@pytest.mark.parametrize("votes", [None, (4, 3)])
def test_member_preferences_in_the_cited_decision_still_supply_its_vote(votes):
    primary = (
        "The RBNZ Committee agreed to hold the OCR at 2.75 percent today, while four members"
        " preferred to hold and three members preferred a cut."
    )
    errors = codes(contextual_decision(primary, "The outlook remains uncertain.", votes=votes))
    assert ("vote_not_captured" in errors) == (votes is None)
    if votes is not None:
        assert not errors
