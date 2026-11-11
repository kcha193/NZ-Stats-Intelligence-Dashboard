"""Phase 4AE review round 4: where adjustment wording sits (label or evidence) must not change which measure a claim is,
and a same-day conflict must include every claim on that day (SYNTHETIC FIXTURE)."""

import pytest

from nzstats.research.bank_analytics import bank_consensus
from nzstats.research.bank_forecast import canonical_label

from .bank_support import nf, view_of
from .llm_support import SECTIONS, draft
from .test_bank_view import seed_bank, view
from .test_drafts_auto import store_hosted


@pytest.mark.parametrize(
    ("label", "adjustment", "expected"),
    [
        ("Annual CPI inflation (unadjusted)", "unadjusted", "Annual CPI inflation"),
        ("Annual CPI inflation (non-seasonally adjusted)", "unadjusted", "Annual CPI inflation"),
        (
            "Quarterly CPI inflation, seasonally adjusted",
            "seasonally_adjusted",
            "Quarterly CPI inflation",
        ),
        (
            "Seasonally adjusted quarterly CPI inflation",
            "seasonally_adjusted",
            "quarterly CPI inflation",
        ),
        (
            "Real GDP, seasonally adjusted, production measure",
            "seasonally_adjusted",
            "Real GDP, production measure",
        ),
        ("Unemployment rate (s.a.)", "seasonally_adjusted", "Unemployment rate"),
        ("Annual CPI inflation", "unadjusted", "Annual CPI inflation"),
        # A label that disagrees with its evidence is left as stated (its basis stays unclear).
        ("GDP growth, seasonally adjusted", "not_stated", "GDP growth, seasonally adjusted"),
        ("Annual CPI inflation", "not_stated", "Annual CPI inflation"),
        # Nothing but the adjustment wording: keep it rather than leave an empty label.
        ("Seasonally adjusted", "seasonally_adjusted", "Seasonally adjusted"),
    ],
)
def test_canonical_label_drops_only_the_adjustment_wording(label, adjustment, expected):
    assert canonical_label(label, adjustment) == expected


def _stored(conn, key, label, *, quote_tail="", doc="research/outlook/q4"):
    sections = (SECTIONS[0], SECTIONS[1].rstrip(".") + quote_tail + ".")
    v = seed_bank(conn, key=key, doc=doc, sections=sections)
    out = draft(v)
    out["forecasts"][1]["indicator_label"] = label
    out["forecasts"][1]["evidence"][0]["quote"] = (
        "forecast to fall to 2.1% in the year to June 2027" + quote_tail
    )
    store_hosted(conn, v, output=out)


def test_the_same_adjustment_in_the_label_or_the_evidence_is_the_same_measure(conn):
    _stored(conn, "bank_a", "Annual CPI inflation (unadjusted)")
    _stored(conn, "bank_b", "Annual CPI inflation", quote_tail=", unadjusted")
    _stored(conn, "bank_c", "Annual CPI inflation (non-seasonally adjusted)")
    got = view(conn)
    cpi = [f for f in got.forecasts if f.forecast.indicator == "cpi_inflation"]
    assert {f.adjustment for f in cpi} == {"unadjusted"}
    assert {f.forecast.indicator_label for f in cpi} == {"Annual CPI inflation"}
    assert {f.measure for f in cpi} >= {"Annual CPI inflation (unadjusted)", "Annual CPI inflation"}
    (group,) = [g for g in bank_consensus(got).groups if g.indicator == "cpi_inflation"]
    assert group.adjustment == "unadjusted" and group.n == 3
    assert group.title == "Consensus of banks"


def test_a_report_that_conflicts_with_itself_conflicts_with_another_report_that_day():
    view = view_of(
        nf("bank_a", summary_id=2, value=2.0, published_on="2026-05-12", claim_path="forecasts[0]"),
        nf("bank_a", summary_id=2, value=3.0, published_on="2026-05-12", claim_path="forecasts[1]"),
        nf("bank_a", summary_id=5, value=2.0, published_on="2026-05-12", claim_path="forecasts[0]"),
        nf("bank_b", summary_id=7, value=3.9, published_on="2026-05-13"),
    )
    out = bank_consensus(view)
    assert [c.key for c in out.groups[0].contributors] == ["bank_b"]
    assert sorted((e.summary_id, e.claim_path, e.code) for e in out.excluded) == [
        (2, "forecasts[0]", "conflicting_forecasts"),
        (2, "forecasts[1]", "conflicting_forecasts"),
        (5, "forecasts[0]", "conflicting_forecasts"),
    ]


def test_a_conflicting_day_does_not_touch_the_same_measure_on_another_day():
    view = view_of(
        nf("bank_a", summary_id=2, value=2.0, published_on="2026-05-12", claim_path="forecasts[0]"),
        nf("bank_a", summary_id=2, value=3.0, published_on="2026-05-12", claim_path="forecasts[1]"),
        nf("bank_a", summary_id=5, value=2.0, published_on="2026-08-12", claim_path="forecasts[0]"),
        nf("bank_b", summary_id=7, value=3.9, published_on="2026-08-13"),
    )
    out = bank_consensus(view)
    assert [c.key for c in out.groups[0].contributors] == ["bank_a", "bank_b"]
    assert [(e.summary_id, e.code) for e in out.excluded] == [
        (2, "conflicting_forecasts"),
        (2, "conflicting_forecasts"),
    ]
