"""Every attribution finding Codex raised on PR 46, with its original reproducer and its neighbours (SYNTHETIC FIXTURE: invented text).

One row per sentence: (finding, sentence, role, issuer, claimed value, whether the label is TRUE). Whether a label is true is read from
the sentence's meaning, never from what the verifier returns. `finding` names the review round and the commit that was reviewed.

For each finding the table holds
  * the reproducer as Codex wrote it (marked ORIGINAL),
  * the right label in its other role (the author's label and a third party's),
  * counterexamples that look alike but make the label wrong, so a fix cannot be bought by loosening the check,
  * the neighbouring wording of the findings before and after it, so that a later fix cannot undo an earlier one.

A true label must be accepted and a wrong one refused, except for the rows in LIMITS: wording where the older Phase 4I check decides, which
Phase 4R leaves byte-identical (docs/phase-4r-acceptance.md, "Follow-up"). A limit row documents what happens today and why.
"""

import pytest

from .test_verify_attribution import authors, codes

REFUSED = {"issuer_mismatch", "issuer_not_in_evidence"}
A, T = "author", "third_party"
TREASURY = "The Treasury"

# (finding, sentence, role, issuer, value, label_is_true)
ROWS = [
    # R1 d63805d: modified names of the author's own people were read as an outside group.
    ("R1 ORIGINAL", "Our market analysts expect growth of 3% in 2029.", A, TREASURY, 3, True),
    ("R1 ORIGINAL", "Our bank economists expect growth of 3% in 2029.", A, TREASURY, 3, True),
    (
        "R1 ORIGINAL",
        "Our independent forecasters expect growth of 3% in 2029.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R1 near",
        "Our private-sector analysts and forecasters expect growth of 3% in 2029.",
        A,
        TREASURY,
        3,
        True,
    ),
    ("R1 near", "Market analysts expect growth of 3% in 2029.", A, TREASURY, 3, False),
    ("R1 near", "Our analysts at ANZ expect growth of 3% in 2029.", A, TREASURY, 3, False),
    ("R1 near", "Market analysts expect growth of 3% in 2029.", T, "Analysts", 3, True),
    ("R1 near", "Unlike us, market analysts expect growth of 3% in 2029.", A, TREASURY, 3, False),
    ("R1 near", "According to market analysts, growth will be 3% in 2029.", A, TREASURY, 3, False),
    # R3 65f46ef: a group that is only the other side of a comparison after the figure.
    (
        "R3 ORIGINAL",
        "We expect growth of 3% in 2029, higher than forecast by analysts.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R3 near",
        "We expect growth of 3% in 2029, lower than forecast by analysts.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R3 near",
        "We expect growth of 3% in 2029, above what analysts expect.",
        A,
        TREASURY,
        3,
        True,
    ),
    ("R3 near", "We expect growth of 3% in 2029, as forecast by analysts.", A, TREASURY, 3, False),
    ("R3 near", "Growth of 3% in 2029 is forecast by analysts.", A, TREASURY, 3, False),
    ("R3 near", "We expect growth of 3% in 2029, according to analysts.", A, TREASURY, 3, False),
    (
        "R3 near",
        "Analysts expect growth of 3% in 2029, higher than we forecast.",
        T,
        "Analysts",
        3,
        True,
    ),
    # R4a 30d22a8: the claimed reporter's own "said" ends an earlier reporter's reach.
    (
        "R4a ORIGINAL",
        "The OECD said growth would be 2% in 2029, but the IMF said growth would be 3% in 2029.",
        T,
        "IMF",
        3,
        True,
    ),
    (
        "R4a near",
        "The OECD said growth would be 2% in 2029, but the IMF said growth would be 3% in 2029.",
        T,
        "OECD",
        2,
        True,
    ),
    (
        "R4a near",
        "The OECD said growth would be 2% in 2029, but the IMF said growth would be 3% in 2029.",
        T,
        "OECD",
        3,
        False,
    ),
    (
        "R4a near",
        "The OECD said growth would be 2% in 2029, but the IMF said growth would be 3% in 2029.",
        A,
        TREASURY,
        3,
        False,
    ),
    (
        "R4a near",
        "The IMF said growth would be 3% in 2029, but the OECD said growth would be 2% in 2029.",
        T,
        "IMF",
        3,
        True,
    ),
    (
        "R4a near",
        "The OECD said growth would be 3% in 2029, and the IMF noted risks.",
        T,
        "IMF",
        3,
        False,
    ),
    # R4b: a reporter's comment on the forecast year is no forecast of the figure.
    (
        "R4b ORIGINAL",
        "We expect growth of 3% in 2029, which the IMF says will be a challenging year.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R4b near",
        "We expect growth of 3% in 2029, which the IMF said would be too optimistic.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R4b near",
        "We expect growth of 3% in 2029, which the IMF says will be 3%.",
        A,
        TREASURY,
        3,
        False,
    ),
    (
        "R4b near",
        "We expect growth of 3% in 2029, which the IMF says will be higher.",
        A,
        TREASURY,
        3,
        False,
    ),
    ("R4b near", "We expect growth of 3% in 2029, which the IMF says.", A, TREASURY, 3, False),
    # R5 5ac0501: a group that is the agent of another indicator's own passive.
    (
        "R5 ORIGINAL",
        "We expect growth of 3% in 2029, and inflation of 2% is forecast by analysts.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R5 near",
        "We expect growth of 3% in 2029, but inflation of 2% is forecast by analysts.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R5 near",
        "We expect growth of 3% in 2029, and inflation of 2% is forecast by analysts.",
        A,
        TREASURY,
        2,
        False,
    ),
    (
        "R5 near",
        "We expect growth of 3% in 2029, and inflation of 2% is forecast by analysts.",
        T,
        "Analysts",
        2,
        True,
    ),
    ("R5 near", "3% and 4% are forecast by analysts.", A, TREASURY, 3, False),
    (
        "R5 near",
        "We expect growth of 3% in 2029, and inflation of 2%, as forecast by analysts.",
        A,
        TREASURY,
        2,
        False,
    ),
    (
        "R5 near",
        "We expect growth of 3% in 2029, with inflation at 2% now forecast by analysts.",
        A,
        TREASURY,
        2,
        False,
    ),
    # R7 b5f5d33: group labels with modifiers.
    ("R7 ORIGINAL", "The major banks expect growth of 3% in 2029.", T, "Major banks", 3, True),
    ("R7 near", "Most analysts expect growth of 3% in 2029.", T, "Most analysts", 3, True),
    (
        "R7 near",
        "The four major banks expect growth of 3% in 2029.",
        T,
        "The four major banks",
        3,
        True,
    ),
    ("R7 near", "The major banks expect growth of 3% in 2029.", T, "Major banks of Asia", 3, False),
    ("R7 near", "The major banks expect growth of 3% in 2029.", T, "Westpac", 3, False),
    ("R7 near", "Analysts expect growth of 3% in 2029.", T, "Major banks", 3, False),
    ("R7 near", "The major banks expect growth of 3% in 2029.", A, TREASURY, 3, False),
    # R7b: a group's comment on the year, in each speech wording.
    (
        "R7b ORIGINAL",
        "We expect growth of 3% in 2029, which analysts say will be a challenging year.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R7b near",
        "We expect growth of 3% in 2029, which analysts said would be a testing year.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R7b near",
        "We expect growth of 3% in 2029, which analysts are expecting to be a testing year.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R7b near",
        "We expect growth of 3% in 2029, which market economists currently reckon will be a tough year.",
        A,
        TREASURY,
        3,
        True,
    ),
    (
        "R7b near",
        "We expect growth of 3% in 2029, which analysts say will be 3%.",
        A,
        TREASURY,
        3,
        False,
    ),
    (
        "R7b near",
        "We expect growth of 3% in 2029, which analysts said would be higher.",
        A,
        TREASURY,
        3,
        False,
    ),
    ("R7b near", "We expect growth of 3% in 2029, which analysts say.", A, TREASURY, 3, False),
    # R8 af0c00e: a group at one named organisation, answered by that organisation's label only.
    ("R8 ORIGINAL", "Analysts at ANZ expect growth of 3% in 2029.", T, "ANZ", 3, True),
    ("R8 ORIGINAL", "Growth of 3% in 2029 is forecast by analysts at ANZ.", T, "ANZ", 3, True),
    ("R8 near", "Analysts at ANZ expect growth of 3% in 2029.", T, "ANZ Bank New Zealand", 3, True),
    ("R8 near", "Analysts at ANZ expect growth of 3% in 2029.", T, "Analysts", 3, True),
    ("R8 near", "Analysts at ANZ expect growth of 3% in 2029.", A, TREASURY, 3, False),
    ("R8 near", "Analysts at ANZ expect growth of 3% in 2029.", T, "Westpac", 3, False),
    ("R8 near", "Analysts at ANZ and Westpac expect growth of 3% in 2029.", T, "ANZ", 3, False),
    ("R8 near", "Analysts expect growth of 3% in 2029, as ANZ noted.", T, "ANZ", 3, False),
    # R9 e85973e: the author's own organisation's analysts, for the author's label only.
    (
        "R9 ORIGINAL",
        "Growth of 3% in 2029 is forecast by analysts at the Treasury.",
        A,
        TREASURY,
        3,
        True,
    ),
    ("R9 near", "Analysts at the Treasury expect growth of 3% in 2029.", A, TREASURY, 3, True),
    ("R9 near", "Growth of 3% in 2029 is forecast by analysts at ANZ.", A, TREASURY, 3, False),
    (
        "R9 near",
        "Growth of 3% in 2029 is forecast by analysts at ANZ and the Treasury.",
        A,
        TREASURY,
        3,
        False,
    ),
    ("R9 near", "Analysts at the Treasury expect growth of 3% in 2029.", T, "ANZ", 3, False),
    # R10 e85973e: a group label ends an earlier reporter's reach at the group's own forecast.
    (
        "R10 ORIGINAL",
        "The IMF said growth would be 2% in 2029, but analysts expect growth of 3% in 2029.",
        T,
        "Analysts",
        3,
        True,
    ),
    (
        "R10 near",
        "The IMF said growth would be 2% in 2029, but growth of 3% in 2029 is forecast by analysts.",
        T,
        "Analysts",
        3,
        True,
    ),
    (
        "R10 near",
        "The IMF said growth would be 2% in 2029, but analysts expect growth of 3% in 2029.",
        A,
        TREASURY,
        3,
        False,
    ),
    (
        "R10 near",
        "The IMF said growth would be 3% in 2029, and analysts expect 2%.",
        T,
        "Analysts",
        3,
        False,
    ),
    (
        "R10 near",
        "Analysts expect growth of 2% in 2028, while the IMF said growth would be 3% in 2029.",
        T,
        "Analysts",
        3,
        False,
    ),
    (
        "R10 near",
        "The IMF said growth would be 3% in 2029, higher than analysts expect.",
        T,
        "Analysts",
        3,
        False,
    ),
    # R11 this review: the earlier assertion's forecaster does not reach a later figure that names its own.
    (
        "R11 ORIGINAL",
        "Market analysts expect growth of 3% in 2029, but analysts at ANZ expect inflation of 2% in 2029.",
        T,
        "ANZ",
        2,
        True,
    ),
    (
        "R11 ORIGINAL",
        "Analysts predict growth of 3% in 2029, while inflation of 2% in 2029 is forecast by the IMF.",
        T,
        "IMF",
        2,
        True,
    ),
    (
        "R11 near",
        "Growth of 3% in 2029 is forecast by the major banks, while inflation of 2% in 2029 is expected by our analysts.",
        A,
        TREASURY,
        2,
        True,
    ),
    (
        "R11 near",
        "Market analysts expect growth of 3% in 2029, but analysts at ANZ expect inflation of 2% in 2029.",
        T,
        "Analysts",
        3,
        True,
    ),
    (
        "R11 near",
        "Market analysts expect growth of 3% in 2029, but analysts at ANZ expect inflation of 2% in 2029.",
        A,
        TREASURY,
        2,
        False,
    ),
    (
        "R11 near",
        "Market analysts expect growth of 3% in 2029, but only 2% in 2030.",
        A,
        TREASURY,
        2,
        False,
    ),
    (
        "R11 near",
        "Analysts expect growth of 3% in 2029, and we expect inflation of 2% in 2029.",
        A,
        TREASURY,
        3,
        False,
    ),
]
# Rows where the sentence's meaning and the verifier disagree because of the OLDER Phase 4I check ("the evidence credits this forecast to
# the author"), which Phase 4R leaves byte-identical. Identical message at the PR baseline 1c021c9, at 905100f and now. Each is a TRUE label
# refused (it fails closed). The test asserts the limit exactly, so a change to the older check makes it fail and the row gets reviewed.
LIMITS = {
    ("R3 near", "Analysts expect growth of 3% in 2029, higher than we forecast.", "Analysts"),
    (
        "R5 near",
        "We expect growth of 3% in 2029, and inflation of 2% is forecast by analysts.",
        "Analysts",
    ),
}


def _id(row):
    finding, sentence, role, issuer, value, true = row
    return f"{finding}|{role}|{issuer}|{value}|{'true' if true else 'wrong'}|{sentence[:48]}"


@pytest.mark.parametrize("row", ROWS, ids=_id)
def test_each_review_finding_keeps_its_original_reproducer_and_neighbours(row):
    finding, sentence, role, issuer, value, true = row
    refused = bool(codes(authors(sentence, role, issuer, value)) & REFUSED)
    if (finding, sentence, issuer) in LIMITS:
        assert true and refused, "an older-wording limit changed: review it and remove the row"
        return
    assert refused is (not true), (
        f"{finding}: {'a true label was refused' if true else 'a wrong label was accepted'}"
    )


def test_the_table_covers_every_review_round_with_an_original_reproducer_and_both_roles():
    rounds = {row[0].split()[0] for row in ROWS}
    assert rounds == {"R1", "R3", "R4a", "R4b", "R5", "R7", "R7b", "R8", "R9", "R10", "R11"}
    for r in rounds:
        mine = [row for row in ROWS if row[0].split()[0] == r]
        assert any("ORIGINAL" in row[0] for row in mine)
        assert any(row[5] for row in mine) and any(not row[5] for row in mine)
    assert {row[2] for row in ROWS} == {A, T}
