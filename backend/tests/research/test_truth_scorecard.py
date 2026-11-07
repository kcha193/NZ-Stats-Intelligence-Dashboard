"""Phase 4V: the synthetic truth-labelled scorecard, pinned (SYNTHETIC FIXTURE).

The numbers are the measurement on constructed minimal pairs, kept exact so a change to the verifier that moves any of them is a
visible, reviewed decision and not a silent drift. They do not say the verifier is accurate on real documents.
"""

from .truth_corpus import CORPUS, score

V4, V5 = score("verify-4"), score("verify-5")


def test_the_corpus_has_every_kind_of_example_and_unique_ids():
    assert len({e.id for e in CORPUS}) == len(CORPUS)
    counts = {
        t: sum(e.truth == t for e in CORPUS)
        for t in ("supported", "unsupported", "ambiguous", "inexpressible")
    }
    assert counts == {"supported": 22, "unsupported": 19, "ambiguous": 3, "inexpressible": 2}


def test_verify_4_baseline_on_the_corpus():
    assert V4["false_rejections"] == [
        "dec-forward-first", "period-base-figure", "period-other-figure-own", "period-rose-from-ok",
        "period-up-from-ok", "vote-colon-ok", "vote-spaced-colon-ok",
    ]  # fmt: skip
    assert V4["false_acceptances"] == ["unit-aus-as-nzd-billion", "unit-us-as-nzd"]


def test_verify_5_on_the_corpus_every_remaining_false_rejection_is_a_documented_limit():
    assert V5["false_rejections"] == [
        "dec-forward-first",
        "period-base-figure",
        "period-other-figure-own",
    ]
    assert V5["false_acceptances"] == []
    notes = {e.id: e.note for e in CORPUS}
    assert all(notes[i] for i in V5["false_rejections"]), (
        "a remaining false rejection must say why it stays"
    )


def test_verify_5_is_no_worse_than_verify_4_anywhere_on_the_corpus():
    assert set(V5["false_rejections"]) <= set(V4["false_rejections"])
    assert set(V5["false_acceptances"]) <= set(V4["false_acceptances"])
    assert (
        set(V5["ambiguous_accepted"]) <= set(V4["ambiguous_accepted"]) | set()
    )  # nothing ambiguous became accepted


def test_nothing_ambiguous_or_inexpressible_is_accepted_by_either_verifier():
    for r in (V4, V5):
        assert r["ambiguous_accepted"] == [] and r["inexpressible_accepted"] == []
