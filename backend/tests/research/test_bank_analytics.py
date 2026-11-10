"""Phase 4AE: deterministic bank analytics over clean forecasts, partitioned by adjustment and report kind
(SYNTHETIC FIXTURE)."""

import httpx
import pytest

from nzstats.research import fetch, providers
from nzstats.research.bank_analytics import (
    bank_comparison,
    bank_consensus,
    bank_divergence,
    bank_evaluation,
    bank_revisions,
)
from tests.cpi_support import ingest_cpi

from .bank_support import nf, view_of


def groups_by_adjustment(out):
    return {g.adjustment: g for g in out.groups}


def three_banks(values=(2.0, 2.5, 3.0), **kw):
    return [
        nf(key, summary_id=i + 1, value=v, **kw)
        for i, (key, v) in enumerate(zip(("bank_a", "bank_b", "bank_c"), values, strict=True))
    ]


def test_adjusted_and_unadjusted_never_aggregate():
    out = bank_consensus(
        view_of(
            nf("bank_a", summary_id=1, value=2.5, adjustment="seasonally_adjusted"),
            nf("bank_b", summary_id=2, value=2.7, adjustment="seasonally_adjusted"),
            nf("bank_c", summary_id=3, value=3.0, adjustment="unadjusted"),
        )
    )
    by = groups_by_adjustment(out)
    assert by["seasonally_adjusted"].n == 2 and by["seasonally_adjusted"].median == 2.6
    assert by["unadjusted"].n == 1 and by["unadjusted"].median is None
    assert "not_stated" not in by


@pytest.mark.parametrize(
    ("n", "title", "has_std"),
    [
        (1, "Insufficient banks", False),
        (2, "Two-bank comparison", False),
        (3, "Consensus of banks", True),
    ],
)
def test_title_thresholds(n, title, has_std):
    out = bank_consensus(view_of(*three_banks()[:n]))
    (g,) = out.groups
    assert g.title == title and g.n == n
    assert (g.std_dev is not None) is has_std
    assert g.disclaimer == "Not a market consensus."


def test_weekly_forecasts_are_listed_not_aggregated():
    view = view_of(
        nf("bank_a", summary_id=1, value=2.0),
        nf("bank_b", summary_id=2, value=9.0, report_kind="weekly", claim_path="forecasts[3]"),
        nf("bank_c", summary_id=3, value=3.0),
    )
    out = bank_consensus(view)
    (g,) = out.groups
    assert [c.key for c in g.contributors] == ["bank_a", "bank_c"]
    assert [(e.institution_key, e.code) for e in out.excluded] == [("bank_b", "not_outlook_report")]
    assert out.excluded[0].claim_path == "forecasts[3]"
    (_, comparison) = bank_comparison(view)[0]  # the forecast table still shows the weekly note
    assert {r.forecast.institution.key for r in comparison.groups[0].rows} == {
        "bank_a", "bank_b", "bank_c",
    }  # fmt: skip


def test_an_undated_forecast_never_enters_consensus_or_revisions():
    view = view_of(
        nf("bank_a", summary_id=1, value=2.0),
        nf("bank_b", summary_id=2, value=2.2, published_on=None),
        nf("bank_c", summary_id=3, value=2.4),
    )
    out = bank_consensus(view)
    assert [c.key for c in out.groups[0].contributors] == ["bank_a", "bank_c"]
    assert [(e.institution_key, e.code) for e in out.excluded] == [
        ("bank_b", "no_publication_date")
    ]
    revisions = bank_revisions(view)
    assert {s.institution.key for _, h in revisions for s in h.series} == {"bank_a", "bank_c"}


def test_two_documents_one_date_with_different_values_are_not_averaged():
    view = view_of(
        nf("bank_a", summary_id=1, value=2.0),
        nf("bank_a", summary_id=2, value=3.0, claim_path="forecasts[1]"),
        nf("bank_b", summary_id=3, value=2.5),
        nf("bank_c", summary_id=4, value=2.7),
    )
    out = bank_consensus(view)
    assert [c.key for c in out.groups[0].contributors] == ["bank_b", "bank_c"]
    assert sorted((e.institution_key, e.summary_id, e.code) for e in out.excluded) == [
        ("bank_a", 1, "conflicting_forecasts"),
        ("bank_a", 2, "conflicting_forecasts"),
    ]


def test_two_documents_one_date_with_the_same_value_are_one_vintage():
    view = view_of(
        nf("bank_a", summary_id=1, value=2.0),
        nf("bank_a", summary_id=2, value=2.0),
        nf("bank_b", summary_id=3, value=2.5),
    )
    out = bank_consensus(view)
    assert [c.key for c in out.groups[0].contributors] == ["bank_a", "bank_b"]
    assert out.excluded == []


def test_zero_and_negative_values_are_contributors():
    out = bank_consensus(view_of(*three_banks((0.0, -0.25, 0.5))))
    (g,) = out.groups
    assert g.n == 3 and g.median == 0.0 and g.minimum == -0.25 and g.maximum == 0.5
    assert {c.value for c in g.contributors} == {0.0, -0.25, 0.5}


def test_divergence_requires_three_banks_and_ranks_by_spread():
    wide = three_banks((1.0, 2.0, 3.0))
    narrow = [
        nf(f.institution_key, summary_id=10 + i, value=v, horizon="year to June 2028")
        for i, (f, v) in enumerate(zip(wide, (1.0, 1.5, 2.5), strict=True))
    ]
    pair = [
        nf("bank_a", summary_id=20, value=1.0, horizon="year to June 2029"),
        nf("bank_b", summary_id=21, value=4.0, horizon="year to June 2029"),
    ]
    div = bank_divergence(bank_consensus(view_of(*wide, *narrow, *pair)))
    assert [d.horizon_label for d in div] == ["Year to June 2027", "Year to June 2028"]
    assert [d.spread for d in div] == [2.0, 1.5]
    assert div[0].median == 2.0
    assert {b.key: b.distance_from_median for b in div[0].banks} == {
        "bank_a": -1.0, "bank_b": 0.0, "bank_c": 1.0,
    }  # fmt: skip


def test_reference_institutions_are_markers_not_contributors():
    marker = nf("ref_central", summary_id=9, value=2.3, kind="central_bank", report_kind="other")
    out = bank_consensus(view_of(*three_banks(), markers=[marker]))
    (g,) = out.groups
    assert g.n == 3 and "ref_central" not in [c.key for c in g.contributors]
    assert [(m.key, m.value) for m in g.markers] == [("ref_central", 2.3)]


def test_a_marker_with_another_basis_is_not_shown_against_the_group():
    marker = nf(
        "ref_gov", summary_id=9, value=2.3, kind="government", report_kind="other",
        indicator_label="Annual average CPI inflation",
    )  # fmt: skip
    (g,) = bank_consensus(view_of(*three_banks(), markers=[marker])).groups
    assert g.markers == []


def test_revisions_across_outlook_vintages():
    view = view_of(
        nf("bank_a", summary_id=1, value=2.0, published_on="2026-05-13"),
        nf("bank_a", summary_id=2, value=2.4, published_on="2026-08-13"),
    )
    ((adjustment, history),) = bank_revisions(view)
    assert adjustment == "not_stated"
    (series,) = history.series
    assert [v.value for v in series.vintages] == [2.0, 2.4]
    assert series.vintages[-1].revision == pytest.approx(0.4)
    assert series.n_revisions == 1


@pytest.fixture()
def cpi_conn(rt, site):
    ingest_cpi(rt, site, "2025-12", "2026-03", "2026-06", "2026-09")
    rt.conn.execute(
        "UPDATE vintage SET captured_at = (SELECT published_at FROM release WHERE id = release_id)"
    )
    return rt.conn


def test_evaluation_uses_first_published_actuals_skips_lookahead_and_non_outlook(cpi_conn):
    view = view_of(
        nf("bank_a", summary_id=1, published_on="2025-12-10", horizon="year to June 2026", value=3.5),
        nf("bank_b", summary_id=2, published_on="2026-07-21", horizon="year to June 2026", value=4.1),
        nf("bank_c", summary_id=3, published_on="2025-12-10", horizon="year to June 2026", value=9.9,
           report_kind="weekly"),
    )  # fmt: skip
    out = bank_evaluation(view, cpi_conn, "cpi_inflation")
    (matched,) = [e for e in out.evaluated if e.status == "matched"]
    assert matched.first.value == 4.1 and matched.error_first == pytest.approx(-0.6)
    assert any("on or after" in x.reason for x in out.excluded)
    assert all(e.forecast.institution.key != "bank_c" for e in out.evaluated)


def test_analytics_are_pure_no_provider_or_network(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("analytics must not call a provider or fetch")

    monkeypatch.setattr(providers, "build_provider", boom)
    monkeypatch.setattr(fetch.ResearchFetcher, "__init__", boom)
    monkeypatch.setattr(httpx.Client, "send", boom)
    view = view_of(*three_banks())
    bank_comparison(view)
    bank_divergence(bank_consensus(view))
    bank_revisions(view)
