"""Phase 4V: the vote pair in colon notation ("4:3"), verifier `verify-5`. Synthetic text only.

The Treasury FEU writes a vote with a colon. `verify-4` read a dash or "to" between the counts and never a colon, so a
correctly copied vote was rejected as `vote_not_in_evidence` (confirmed in Phase 4U). `verify-5` reads a colon only inside a
sentence about a vote, only between two single-digit counts, and never as a time or ratio. Nothing else about votes changed.
"""

from datetime import date

import pytest

from nzstats.research.contract import PolicyAction, PolicyDecision, SectionText
from nzstats.research.verify import _votes

from .verify_support import check, codes, ref

OCR = "the Official Cash Rate at 2.75 percent"


def section(sentence: str) -> dict[int, SectionText]:
    return {0: SectionText(f"SYNTHETIC FIXTURE. {sentence}", None, None, "News release")}


def decision(quote: str, vote: tuple[int, int] | None) -> PolicyDecision:
    return PolicyDecision(
        action="hold", rate=2.75, decided_on="2026-10-28", decision_maker="Monetary Policy Committee",
        vote_for=vote[0] if vote else None, vote_against=vote[1] if vote else None,
        evidence=[ref(0, quote)],
    )  # fmt: skip


def run(sentence: str, quote: str, vote: tuple[int, int] | None, **kw):
    return check(
        section(sentence), outlook_ref=ref(0, "SYNTHETIC FIXTURE"), published_on=date(2026, 10, 28),
        institution="rbnz", decisions=[decision(quote, vote)], **kw,
    )  # fmt: skip


def voted(pair: str) -> tuple[str, str]:
    quote = f"today voted {pair} to hold {OCR}"
    return f"The Monetary Policy Committee {quote}.", quote


# --- the confirmed defect: a correctly copied colon vote ---------------------------------------------
@pytest.mark.parametrize("pair", ["4:3", "4 : 3", "4: 3", "4 :3"])
def test_a_correctly_claimed_colon_vote_is_accepted(pair):
    sentence, quote = voted(pair)
    assert codes(run(sentence, quote, (4, 3))) == set()


@pytest.mark.parametrize("claimed", [(3, 4), (5, 2), (4, 4), (7, 0)])
def test_a_wrongly_claimed_colon_vote_is_still_rejected(claimed):
    sentence, quote = voted("4:3")
    assert "vote_not_in_evidence" in codes(run(sentence, quote, claimed))


def test_a_colon_vote_the_decision_does_not_record_is_flagged_like_any_other_vote():
    sentence, quote = voted("4:3")
    assert "vote_not_captured" in codes(run(sentence, quote, None))


# --- the notations that already worked still work -----------------------------------------------------
@pytest.mark.parametrize("pair", ["4–3", "4-3", "4—3", "4 to 3", "four to three"])
def test_the_dash_and_word_notations_are_unchanged(pair):
    sentence, quote = voted(pair)
    assert codes(run(sentence, quote, (4, 3))) == set()


@pytest.mark.parametrize("pair", ["4–3", "4-3", "4 to 3"])
def test_a_wrong_dash_vote_is_still_rejected(pair):
    sentence, quote = voted(pair)
    assert "vote_not_in_evidence" in codes(run(sentence, quote, (3, 4)))


# --- a colon that is not a vote must never become one -------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "The Committee voted at 9:30 to hold the OCR",  # a time
        "The Committee voted at 4:30 to hold the OCR",  # a time with a plausible first count
        "The Committee voted at 10:30 to hold the OCR",
        "The Committee voted to hold the OCR, in a funding ratio of 3:1",  # a ratio, preceded by its word
        "The Committee voted to hold the OCR, a 3:1 ratio of members to staff",  # a ratio, followed by its word
        "Seven members voted; the log shows 4:3:2",  # three terms
        "The Committee voted to hold the OCR; the index moved 1.5:3",  # a decimal term
        "The Committee voted to hold the OCR; the score was 4:30",  # a two-digit second term
    ],
)
def test_a_time_or_ratio_is_not_a_vote(text):
    assert _votes(text, PolicyAction.HOLD, colon=True) == set()


@pytest.mark.parametrize("pair", ["4:3", "4 : 3"])
def test_a_colon_pair_outside_a_vote_sentence_is_not_a_vote(pair):
    assert _votes(f"The score was {pair} at half time.", PolicyAction.HOLD, colon=True) == set()


def test_a_colon_vote_is_read_only_when_enabled():
    # `verify-4` semantics: the same sentence yields nothing, which is the false rejection this phase fixes.
    sentence, _ = voted("4:3")
    assert _votes(sentence, PolicyAction.HOLD, colon=False) == set()
    assert _votes(sentence, PolicyAction.HOLD, colon=True) == {(4, 3)}


# --- found by the independent review: the pair must sit right after the vote word, not anywhere in a vote sentence ------
STRAY = [
    "The Committee voted to hold the Official Cash Rate at 2.75 percent, with growth of 2:3",
    "Table 2: 5 of the 7 members preferred hold",
    "Resolution 1: 4 members preferred a hold",
    "The Committee voted to hold the OCR after a 3:2 split of opinion in the staff paper",
    "The Committee voted to hold, citing aspect 1:2 of the mandate",
    "The Committee voted to hold the OCR; inflation is 6:3 per cent of target",
    "The Committee voted to hold the OCR, 6:3 times the usual rate",
]


@pytest.mark.parametrize("text", STRAY)
def test_a_colon_pair_that_is_not_the_votes_own_is_never_read_as_one(text):
    assert _votes(text, PolicyAction.HOLD, colon=True) == set()


@pytest.mark.parametrize(
    "text",
    [
        "The Committee voted 4:3 to hold the OCR",
        "The Committee voted by 4:3 to hold the OCR",
        "The vote was 4:3 to hold the OCR",
        "The Committee decided by a vote of 4:3",
        "The Committee voted in favour 4 : 3",
    ],
)
def test_a_colon_pair_straight_after_the_vote_word_is_read(text):
    assert _votes(text, PolicyAction.HOLD, colon=True) == {(4, 3)}


def test_a_fabricated_vote_from_a_stray_colon_pair_is_still_rejected():
    sentence = "The Monetary Policy Committee today voted to hold the Official Cash Rate at 2.75 percent, with growth of 2:3."
    quote = sentence.rstrip(".")
    assert "vote_not_in_evidence" in codes(run(sentence, quote, (2, 3)))


def test_a_decision_with_no_vote_is_not_newly_rejected_by_a_stray_colon_pair():
    sentence = "The Monetary Policy Committee today voted to hold the Official Cash Rate at 2.75 percent, with growth of 2:3."
    quote = sentence.rstrip(".")
    assert codes(run(sentence, quote, None)) == set()
