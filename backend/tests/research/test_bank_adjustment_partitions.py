"""Phase 4AE review round 2: `compare.resolve` ignores adjustment wording, so every place the bank layer resolves
must do it per adjustment (SYNTHETIC FIXTURE)."""

import pytest

from nzstats.research.bank_analytics import bank_consensus, bank_evaluation
from tests.cpi_support import ingest_cpi

from .bank_support import nf, view_of

QUARTERLY = {"indicator_label": "Quarterly CPI inflation", "horizon": "June 2026 quarter"}


@pytest.fixture()
def cpi_conn(rt, site):
    ingest_cpi(rt, site, "2025-12", "2026-03", "2026-06", "2026-09")
    rt.conn.execute(
        "UPDATE vintage SET captured_at = (SELECT published_at FROM release WHERE id = release_id)"
    )
    return rt.conn


def _one_document(sa, nsa):
    return view_of(
        nf("bank_a", adjustment="seasonally_adjusted", published_on="2026-03-01", value=sa, **QUARTERLY),
        nf("bank_a", adjustment="unadjusted", published_on="2026-03-01", value=nsa,
           claim_path="forecasts[1]", **QUARTERLY),
    )  # fmt: skip


@pytest.mark.parametrize(("sa", "nsa"), [(0.5, 0.7), (0.5, 0.5)])
def test_sa_and_unadjusted_forecasts_in_one_document_are_both_evaluated(cpi_conn, sa, nsa):
    """Different values are not a conflict, and equal values do not collapse into one forecast."""
    out = bank_evaluation(_one_document(sa, nsa), cpi_conn, "cpi_inflation")
    assert out.excluded == []
    assert sorted((e.measure, e.forecast.value) for e in out.evaluated) == [
        ("quarterly_change_nsa", nsa),
        ("quarterly_change_sa", sa),
    ]


def test_a_real_conflict_inside_one_adjustment_still_does_not_reach_evaluation(cpi_conn):
    view = view_of(
        nf("bank_a", adjustment="unadjusted", published_on="2026-03-01", value=0.5, **QUARTERLY),
        nf("bank_a", adjustment="unadjusted", published_on="2026-03-01", value=0.9,
           claim_path="forecasts[1]", **QUARTERLY),
    )  # fmt: skip
    assert bank_evaluation(view, cpi_conn, "cpi_inflation").evaluated == []


def _banks_in_both_adjustments():
    return [
        nf(key, summary_id=10 * (i + 1) + k, value=v, adjustment=adj, claim_path="forecasts[0]")
        for i, (key, v) in enumerate(
            zip(("bank_a", "bank_b", "bank_c"), (2.0, 2.5, 3.0), strict=True)
        )
        for k, adj in enumerate(("seasonally_adjusted", "unadjusted"))
    ]


def _reference(sa, nsa):
    """One reference-institution document stating both an SA and an unadjusted value for the same measure."""
    return [
        nf("ref_central", summary_id=9, value=value, kind="central_bank", report_kind="other",
           adjustment=adj, claim_path=f"forecasts[{k}]")
        for k, (adj, value) in enumerate((("seasonally_adjusted", sa), ("unadjusted", nsa)))
    ]  # fmt: skip


def _group_markers(out):
    return {g.adjustment: [(m.key, m.value) for m in g.markers] for g in out.groups}


@pytest.mark.parametrize(("sa", "nsa"), [(2.3, 2.9), (2.3, 2.3)])
def test_a_reference_institution_with_sa_and_unadjusted_values_keeps_both_markers(sa, nsa):
    """Different values are not a conflict, and equal values do not collapse into one adjustment."""
    out = bank_consensus(view_of(*_banks_in_both_adjustments(), markers=_reference(sa, nsa)))
    assert _group_markers(out) == {
        "seasonally_adjusted": [("ref_central", sa)],
        "unadjusted": [("ref_central", nsa)],
    }
