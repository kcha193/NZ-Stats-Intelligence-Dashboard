"""Phase 4AE review round 1: a newer report that conflicts with itself must not resurrect an older figure
(SYNTHETIC FIXTURE)."""

from nzstats.research.bank_analytics import bank_comparison, bank_consensus, bank_revisions

from .bank_support import nf, unusable, view_of


def _by_adjustment(out):
    return {g.adjustment: g for g in out.groups}


def _contributors(out):
    return [c.key for c in out.groups[0].contributors]


def _excluded(out, bank="bank_a"):
    return sorted((e.summary_id, e.code) for e in out.excluded if e.institution_key == bank)


def _older_a_with_peers(*extra, **kw):
    return view_of(
        nf("bank_a", summary_id=1, value=3.8, published_on="2026-02-10"),
        nf("bank_b", summary_id=3, value=3.9, published_on="2026-05-13"),
        nf("bank_c", summary_id=4, value=3.7, published_on="2026-05-14"),
        *extra,
        **kw,
    )


def _newer_conflicting_pair(**kw):
    """Bank A's newer document (one summary) states two different values for one measure and horizon."""
    return [
        nf("bank_a", summary_id=2, value=4.0, published_on="2026-05-12", claim_path="forecasts[0]", **kw),
        nf("bank_a", summary_id=2, value=4.4, published_on="2026-05-12", claim_path="forecasts[1]", **kw),
    ]  # fmt: skip


def test_two_conflicting_claims_in_one_newer_document_hide_the_older_figure():
    view = _older_a_with_peers(*_newer_conflicting_pair())
    out = bank_consensus(view)
    assert _contributors(out) == ["bank_b", "bank_c"]
    assert _excluded(out) == [
        (1, "newer_claim_unusable"),
        (2, "conflicting_forecasts"),
        (2, "conflicting_forecasts"),
    ]
    ((_, comparison),) = bank_comparison(view)
    assert {r.forecast.institution.key for r in comparison.groups[0].rows} == {"bank_b", "bank_c"}
    series = {s.institution.key for _, h in bank_revisions(view) for s in h.series}
    assert series == {"bank_b", "bank_c"}


def test_conflicting_failed_claims_in_one_newer_document_hide_the_older_figure():
    view = _older_a_with_peers(
        excluded=[
            unusable("bank_a", summary_id=2, value=9.0, published_on="2026-05-12"),
            unusable("bank_a", summary_id=2, value=9.5, published_on="2026-05-12",
                     claim_path="forecasts[1]"),
        ]
    )  # fmt: skip
    out = bank_consensus(view)
    assert _contributors(out) == ["bank_b", "bank_c"]
    assert _excluded(out) == [(1, "newer_claim_unusable")]


def test_conflicting_warned_claims_in_one_newer_document_hide_the_older_figure():
    view = _older_a_with_peers(
        excluded=[
            unusable("bank_a", "claim_has_warning", summary_id=2, value=9.0, published_on="2026-05-12"),
            unusable("bank_a", "claim_has_warning", summary_id=2, value=9.5, published_on="2026-05-12",
                     claim_path="forecasts[1]"),
        ]
    )  # fmt: skip
    assert _contributors(bank_consensus(view)) == ["bank_b", "bank_c"]


def test_an_identical_repeat_of_a_newer_claim_is_one_claim_not_a_conflict():
    view = view_of(
        nf("bank_a", summary_id=1, value=3.8, published_on="2026-02-10"),
        nf("bank_a", summary_id=2, value=4.0, published_on="2026-05-12"),
        nf("bank_a", summary_id=2, value=4.0, published_on="2026-05-12", claim_path="forecasts[1]"),
        nf("bank_b", summary_id=3, value=3.9, published_on="2026-05-13"),
    )
    out = bank_consensus(view)
    (g,) = out.groups
    assert {c.key: c.value for c in g.contributors} == {"bank_a": 4.0, "bank_b": 3.9}
    assert out.excluded == []


def test_a_newer_conflict_in_one_adjustment_leaves_the_other_adjustment_alone():
    view = view_of(
        nf("bank_a", summary_id=1, value=3.8, published_on="2026-02-10", adjustment="seasonally_adjusted"),
        *_newer_conflicting_pair(adjustment="unadjusted"),
        nf("bank_b", summary_id=3, value=3.9, published_on="2026-05-13", adjustment="seasonally_adjusted"),
    )  # fmt: skip
    out = bank_consensus(view)
    adjusted = _by_adjustment(out)["seasonally_adjusted"]
    assert [c.key for c in adjusted.contributors] == ["bank_a", "bank_b"]
    assert _excluded(out) == [(2, "conflicting_forecasts"), (2, "conflicting_forecasts")]
    assert "unadjusted" not in _by_adjustment(out)


def test_different_adjustments_in_one_document_are_not_a_conflict():
    view = view_of(
        nf("bank_a", summary_id=1, value=2.0, adjustment="seasonally_adjusted"),
        nf("bank_a", summary_id=1, value=3.0, adjustment="unadjusted", claim_path="forecasts[1]"),
    )
    out = bank_consensus(view)
    assert {a: g.contributors[0].value for a, g in _by_adjustment(out).items()} == {
        "seasonally_adjusted": 2.0,
        "unadjusted": 3.0,
    }
    assert out.excluded == []
    assert [a for a, _ in bank_comparison(view)] == ["seasonally_adjusted", "unadjusted"]


def test_a_failed_claim_in_one_adjustment_does_not_hide_the_other_adjustments_older_figure():
    view = view_of(
        nf("bank_a", summary_id=1, value=3.8, published_on="2026-02-10", adjustment="seasonally_adjusted"),
        excluded=[
            unusable("bank_a", summary_id=2, value=9.0, published_on="2026-05-12", adjustment="unadjusted"),
            unusable("bank_a", summary_id=2, value=9.5, published_on="2026-05-12",
                     adjustment="unadjusted", claim_path="forecasts[1]"),
        ],
    )  # fmt: skip
    out = bank_consensus(view)
    assert _contributors(out) == ["bank_a"] and out.excluded == []


def test_a_newer_conflict_leaves_other_horizons_and_measures_alone():
    view = view_of(
        nf("bank_a", summary_id=1, value=3.8, published_on="2026-02-10"),
        nf("bank_a", summary_id=1, value=3.1, published_on="2026-02-10", horizon="year to June 2028",
           claim_path="forecasts[1]"),
        nf("bank_a", summary_id=1, value=0.6, published_on="2026-02-10", indicator="gdp",
           indicator_label="Real GDP growth, quarterly", horizon="June 2027 quarter",
           claim_path="forecasts[2]"),
        *_newer_conflicting_pair(),
    )  # fmt: skip
    out = bank_consensus(view)
    kept = sorted((g.indicator, g.horizon_label) for g in out.groups)
    assert len(kept) == 2 and {i for i, _ in kept} == {"cpi_inflation", "gdp"}
    assert (
        _excluded(out)
        == [
            (1, "newer_claim_unusable"),
            (2, "conflicting_forecasts"),
            (2, "conflicting_forecasts"),
        ]
    )  # only the older figure of the conflicted measure and horizon is hidden: two of three summary-1 claims stay


def test_exclusions_are_deterministic_whatever_the_input_order():
    base = _older_a_with_peers(
        *_newer_conflicting_pair(),
        excluded=[unusable("bank_b", summary_id=9, value=8.0, published_on="2026-05-20")],
    )
    shuffled = view_of(*reversed(base.forecasts), excluded=list(reversed(base.excluded)))

    def snapshot(view):
        out = bank_consensus(view)
        return (
            sorted((e.institution_key, e.summary_id, e.claim_path, e.code) for e in out.excluded),
            sorted((g.key, tuple(c.key for c in g.contributors)) for g in out.groups),
        )

    assert snapshot(base) == snapshot(shuffled) == snapshot(base)
